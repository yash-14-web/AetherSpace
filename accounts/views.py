import uuid
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import JsonResponse

from .forms import (
    LoginForm,
    RegisterForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    ResendVerificationForm,
    ProfileUpdateForm,
    AvatarUploadForm,
    TIMEZONE_CHOICES,
)
from .models import User, UserProfile, UserRole, ApprovalStatus
from workspaces.models import WorkspaceMembership, Workspace
from .tokens import account_verification_token
from .services import (
    get_or_create_user_profile,
    get_user_profile_metrics,
    get_user_assigned_tasks,
    get_user_bugs,
    get_user_activities,
    get_user_workspace_roles,
    get_user_primary_role_summary,
    process_and_save_avatar,
    remove_user_avatar,
    PRESET_AVATAR_THEMES,
    MAX_AVATAR_SIZE_BYTES,
    process_and_save_banner,
    remove_user_banner,
    PRESET_BANNER_THEMES,
)

logger = logging.getLogger(__name__)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('workspaces:dashboard')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Auto-set status to available on successful login
            try:
                from django.core.cache import cache
                from django.utils import timezone
                cache.set(f'user_last_seen_{user.id}', timezone.now().timestamp(), timeout=300)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                pref = profile.preferences or {}
                pref['status'] = 'available'
                profile.preferences = pref
                profile.save(update_fields=['preferences', 'updated_at'])
            except Exception:
                pass

            # Session expiration handling based on remember_me
            remember_me = form.cleaned_data.get('remember_me')
            if remember_me:
                # 14 days
                request.session.set_expiry(1209600)
            else:
                # Session expires on browser close
                request.session.set_expiry(0)

            # Validate redirect URL security
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('workspaces:dashboard')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {
        'form': form,
        'next_url': next_url,
        'title': 'Sign In — AetherSpace',
    })


def logout_view(request):
    if request.user.is_authenticated:
        try:
            # Delete online heartbeat
            from django.core.cache import cache
            cache.delete(f'user_last_seen_{request.user.id}')

            # Auto-pause any active running timers on sign-out
            from timetracking.models import TimeEntry, TimerStatus
            for timer in TimeEntry.objects.filter(user=request.user, status=TimerStatus.RUNNING):
                timer.pause()
            for timer in TimeEntry.objects.filter(user=request.user, is_running=True).exclude(status=TimerStatus.PAUSED):
                timer.pause()

            # Set status to offline
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            pref = profile.preferences or {}
            pref['status'] = 'offline'
            profile.preferences = pref
            profile.save(update_fields=['preferences', 'updated_at'])
        except Exception as e:
            logger.warning(f"Error handling logout status: {e}")

    logout(request)
    messages.info(request, "You have been safely signed out.")
    response = redirect('accounts:login')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def register_view(request):
    if request.user.is_authenticated:
        return redirect('workspaces:dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            user = User.objects.create_user(
                email=email,
                password=password,
                full_name=full_name,
                is_verified=False,
                role=UserRole.CONTRIBUTOR,
                approval_status=ApprovalStatus.PENDING,
            )
            UserProfile.objects.create(user=user)

            # Store in session for the Pending Approval view
            request.session['pending_contributor_id'] = user.contributor_id
            request.session['pending_user_name'] = user.full_name
            request.session['pending_user_email'] = user.email

            # User must NOT be logged in! Pending accounts cannot bypass approval.
            messages.success(
                request,
                f"Registration successful! Your Contributor ID is {user.contributor_id}. Your account is awaiting Admin/Manager approval."
            )
            return redirect('accounts:pending_approval')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'title': 'Create Your Workspace Account — AetherSpace',
    })


def pending_approval_view(request):
    """
    Dedicated screen displayed immediately after registration.
    Shows the generated dynamic Contributor ID (#####C) and explains the approval process.
    """
    if request.user.is_authenticated:
        return redirect('workspaces:dashboard')

    contributor_id = request.session.get('pending_contributor_id') or request.GET.get('cid', '')
    user_name = request.session.get('pending_user_name', '')
    user_email = request.session.get('pending_user_email', '')

    return render(request, 'accounts/pending_approval.html', {
        'contributor_id': contributor_id,
        'user_name': user_name,
        'user_email': user_email,
        'title': 'Account Pending Approval — AetherSpace',
    })


def forgot_password_view(request):
    submitted = False
    reset_url = None

    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.filter(email=email).first()
            if user:
                token = default_token_generator.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                reset_url = request.build_absolute_uri(
                    reverse('accounts:reset_password_confirm', kwargs={'uidb64': uidb64, 'token': token})
                )
                logger.info("Password reset link generated for %s: %s", user.email, reset_url)
                request.session['last_reset_url'] = reset_url
                try:
                    from notifications.email_service import send_password_reset_email
                    send_password_reset_email(user, reset_url)
                except Exception as e:
                    logger.error("Failed to send password reset email: %s", e)
            submitted = True
    else:
        form = ForgotPasswordForm()

    return render(request, 'accounts/forgot_password.html', {
        'form': form,
        'submitted': submitted,
        'reset_url': reset_url or request.session.get('last_reset_url'),
        'title': 'Forgot Password — AetherSpace',
    })


def reset_password_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    is_valid_token = user is not None and default_token_generator.check_token(user, token)

    if not is_valid_token:
        return render(request, 'accounts/reset_password.html', {
            'invalid_token': True,
            'title': 'Invalid or Expired Reset Link — AetherSpace',
        })

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['password']
            user.set_password(new_password)
            user.save()
            messages.success(request, "Your password has been reset successfully. Please sign in.")
            return redirect('accounts:login')
    else:
        form = ResetPasswordForm()

    return render(request, 'accounts/reset_password.html', {
        'form': form,
        'uidb64': uidb64,
        'token': token,
        'title': 'Reset Your Password — AetherSpace',
    })


def verification_view(request):
    email = request.session.get('pending_verification_email')
    if not email and request.user.is_authenticated:
        email = request.user.email

    resend_success = False

    if request.method == 'POST':
        form = ResendVerificationForm(request.POST)
        if form.is_valid():
            target_email = form.cleaned_data['email']
            user = User.objects.filter(email=target_email).first()
            if user and not user.is_verified:
                token = account_verification_token.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                verify_url = request.build_absolute_uri(
                    reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
                )
                request.session['last_verify_url'] = verify_url
                resend_success = True
                try:
                    from notifications.email_service import send_email_verification_email
                    send_email_verification_email(user, verify_url)
                except Exception as e:
                    logger.error("Failed to send verification email: %s", e)
                messages.success(request, f"A fresh verification link has been sent to {target_email}.")
    else:
        form = ResendVerificationForm(initial={'email': email or ''})

    return render(request, 'accounts/verification.html', {
        'email': email or 'your email address',
        'verify_url': request.session.get('last_verify_url'),
        'form': form,
        'resend_success': resend_success,
        'title': 'Verify Your Email — AetherSpace',
    })


def verify_email_confirm_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_verification_token.check_token(user, token):
        user.is_verified = True
        user.save()
        messages.success(request, "Your email has been verified! Welcome to AetherSpace.")
        return redirect('core:landing')
    else:
        return render(request, 'accounts/verification.html', {
            'invalid_token': True,
            'title': 'Invalid Verification Link — AetherSpace',
        })


# ==============================================================================
# PHASE 12: PROFILE VIEWS (Screens 53 - 58)
# ==============================================================================

@login_required
def profile_view(request):
    """
    Screen 53 — My Profile overview:
    Professional profile banner, contact details, system roles, metrics,
    assigned tasks, relevant bugs, and chronological activity stream.
    """
    user = request.user
    profile = get_or_create_user_profile(user)
    metrics = get_user_profile_metrics(user)

    # Overview highlights
    recent_tasks = get_user_assigned_tasks(user)[:5]
    recent_bugs = get_user_bugs(user)[:5]
    recent_activities = get_user_activities(user, limit=6)
    workspace_roles = get_user_workspace_roles(user)
    primary_role = get_user_primary_role_summary(user, workspace_slug=request.GET.get('workspace', '').strip())

    return render(request, 'profile/my_profile.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
        'primary_role': primary_role,
        'recent_tasks': recent_tasks,
        'recent_bugs': recent_bugs,
        'recent_activities': recent_activities,
        'workspace_roles': workspace_roles,
        'active_tab': 'overview',
        'is_own_profile': True,
        'title': f"{user.full_name or user.email} — My Profile",
    })


@login_required
def profile_edit_view(request):
    """
    Screen 54 — Edit Profile:
    Update personal information, headline, bio, contact details, timezone,
    and manage avatar with KB-only compression (max 500 KB) or 0 KB presets/URLs.
    """
    user = request.user
    profile = get_or_create_user_profile(user)

    if request.method == 'POST':
        action = request.POST.get('action', 'update_profile')

        if action == 'update_avatar':
            avatar_form = AvatarUploadForm(request.POST, request.FILES)
            if avatar_form.is_valid():
                file_obj = avatar_form.cleaned_data.get('avatar_file')
                avatar_url = avatar_form.cleaned_data.get('avatar_url')
                preset_color = avatar_form.cleaned_data.get('preset_color')

                success, msg = process_and_save_avatar(
                    user,
                    file_obj=file_obj,
                    avatar_url=avatar_url,
                    preset_color=preset_color
                )
                if success:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
                return redirect('accounts:profile_edit')
            else:
                for error_list in avatar_form.errors.values():
                    for err in error_list:
                        messages.error(request, err)
                return redirect('accounts:profile_edit')

        elif action == 'update_banner':
            file_obj = request.FILES.get('banner_file')
            banner_url = request.POST.get('banner_url', '').strip()
            preset_gradient = request.POST.get('preset_gradient', '').strip()

            success, msg = process_and_save_banner(
                user,
                file_obj=file_obj,
                banner_url=banner_url,
                preset_gradient=preset_gradient
            )
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect('accounts:profile_edit')

        elif action == 'remove_banner':
            remove_user_banner(user)
            messages.success(request, "Banner removed. Default theme gradient restored.")
            return redirect('accounts:profile_edit')

        elif action == 'update_profile':
            profile_form = ProfileUpdateForm(request.POST)
            if profile_form.is_valid():
                user.full_name = profile_form.cleaned_data['full_name'].strip()
                user.timezone = profile_form.cleaned_data.get('timezone') or 'UTC'
                user.save(update_fields=['full_name', 'timezone', 'updated_at'])

                profile.headline = profile_form.cleaned_data.get('headline', '').strip()
                profile.bio = profile_form.cleaned_data.get('bio', '').strip()
                profile.phone = profile_form.cleaned_data.get('phone', '').strip()
                profile.save(update_fields=['headline', 'bio', 'phone', 'updated_at'])

                messages.success(request, "Your profile details have been saved successfully.")
                return redirect('accounts:profile')
            else:
                avatar_form = AvatarUploadForm()
        else:
            return redirect('accounts:profile_edit')
    else:
        profile_form = ProfileUpdateForm(initial={
            'full_name': user.full_name,
            'headline': profile.headline,
            'bio': profile.bio,
            'phone': profile.phone,
            'timezone': user.timezone or 'UTC',
        })
        avatar_form = AvatarUploadForm()

    return render(request, 'profile/edit_profile.html', {
        'profile_user': user,
        'profile': profile,
        'primary_role': get_user_primary_role_summary(user),
        'profile_form': profile_form,
        'avatar_form': avatar_form,
        'preset_themes': PRESET_AVATAR_THEMES,
        'preset_banners': PRESET_BANNER_THEMES,
        'active_tab': 'edit',
        'is_own_profile': True,
        'title': 'Edit Profile — AetherSpace',
    })


@login_required
@require_POST
def profile_avatar_remove_view(request):
    """
    Remove user avatar and reclaim storage.
    """
    remove_user_avatar(request.user)
    messages.info(request, "Profile avatar removed. Default gradient initials restored.")
    return redirect('accounts:profile_edit')


@login_required
@require_POST
def profile_banner_remove_view(request):
    """
    Remove user banner and reclaim storage.
    """
    remove_user_banner(request.user)
    messages.info(request, "Profile banner removed. Default gradient cover restored.")
    return redirect('accounts:profile_edit')


@login_required
def profile_tasks_view(request):
    """
    Screen 55 — My Tasks from Profile:
    Assigned tasks viewer with status filter pills, workspace selector, and search.
    """
    user = request.user
    profile = get_or_create_user_profile(user)
    metrics = get_user_profile_metrics(user)

    status_filter = request.GET.get('status', 'ALL')
    workspace_filter = request.GET.get('workspace', 'ALL')
    query = request.GET.get('q', '')

    all_user_tasks = get_user_assigned_tasks(user, status=status_filter, workspace_slug=workspace_filter, query=query)

    # Status counts for filter pills
    raw_tasks = get_user_assigned_tasks(user)
    status_counts = {
        'ALL': raw_tasks.count(),
        'TODO': raw_tasks.filter(status='TODO').count(),
        'IN_PROGRESS': raw_tasks.filter(status='IN_PROGRESS').count(),
        'CODE_REVIEW': raw_tasks.filter(status='CODE_REVIEW').count(),
        'TESTING': raw_tasks.filter(status='TESTING').count(),
        'DONE': raw_tasks.filter(status='DONE').count(),
    }

    # Accessible workspaces for dropdown
    workspaces = [r['workspace'] for r in get_user_workspace_roles(user)]

    paginator = Paginator(all_user_tasks, 12)
    page_number = request.GET.get('page', 1)
    try:
        tasks_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        tasks_page = paginator.page(1)

    return render(request, 'profile/my_tasks.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
        'primary_role': get_user_primary_role_summary(user, workspace_slug=workspace_filter if workspace_filter != 'ALL' else None),
        'tasks_page': tasks_page,
        'status_filter': status_filter,
        'workspace_filter': workspace_filter,
        'query': query,
        'status_counts': status_counts,
        'workspaces': workspaces,
        'active_tab': 'tasks',
        'is_own_profile': True,
        'title': 'My Tasks — AetherSpace',
    })


@login_required
def profile_bugs_view(request):
    """
    Screen 56 — My Bugs from Profile:
    Assigned & reported defects with relation filter, severity pills, and search.
    """
    user = request.user
    profile = get_or_create_user_profile(user)
    metrics = get_user_profile_metrics(user)

    relation_filter = request.GET.get('relation', 'ALL')
    severity_filter = request.GET.get('severity', 'ALL')
    status_filter = request.GET.get('status', 'ALL')
    query = request.GET.get('q', '')

    all_user_bugs = get_user_bugs(
        user,
        relation=relation_filter,
        severity=severity_filter,
        status=status_filter,
        query=query
    )

    # Relation counts for filter pills
    relation_counts = {
        'ALL': get_user_bugs(user, relation='ALL').count(),
        'ASSIGNED': get_user_bugs(user, relation='ASSIGNED').count(),
        'REPORTED': get_user_bugs(user, relation='REPORTED').count(),
        'RESOLVED': get_user_bugs(user, relation='RESOLVED').count(),
    }

    paginator = Paginator(all_user_bugs, 12)
    page_number = request.GET.get('page', 1)
    try:
        bugs_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        bugs_page = paginator.page(1)

    return render(request, 'profile/my_bugs.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
        'primary_role': get_user_primary_role_summary(user),
        'bugs_page': bugs_page,
        'relation_filter': relation_filter,
        'severity_filter': severity_filter,
        'status_filter': status_filter,
        'query': query,
        'relation_counts': relation_counts,
        'active_tab': 'bugs',
        'is_own_profile': True,
        'title': 'My Bugs — AetherSpace',
    })


@login_required
def profile_activity_view(request):
    """
    Screen 57 — Profile Activity:
    Chronological text-based activity stream across tasks, defects, files, and meetings.
    Rule 57: Text-based; no radar/graph charts.
    """
    user = request.user
    profile = get_or_create_user_profile(user)
    metrics = get_user_profile_metrics(user)

    category_filter = request.GET.get('category', 'ALL')
    activities = get_user_activities(user, category=category_filter, limit=60)

    category_counts = {
        'ALL': len(get_user_activities(user, category='ALL', limit=100)),
        'TASKS': len(get_user_activities(user, category='TASKS', limit=100)),
        'BUGS': len(get_user_activities(user, category='BUGS', limit=100)),
        'FILES': len(get_user_activities(user, category='FILES', limit=100)),
    }

    return render(request, 'profile/my_activity.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
        'primary_role': get_user_primary_role_summary(user),
        'activities': activities,
        'category_filter': category_filter,
        'category_counts': category_counts,
        'active_tab': 'activity',
        'is_own_profile': True,
        'title': 'My Activity — AetherSpace',
    })


@login_required
def profile_roles_view(request):
    """
    Screen 58 — Workspace Roles:
    Displays user's roles and permissions across all accessible workspaces.
    """
    user = request.user
    profile = get_or_create_user_profile(user)
    metrics = get_user_profile_metrics(user)
    workspace_roles = get_user_workspace_roles(user)

    return render(request, 'profile/workspace_roles.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
        'primary_role': get_user_primary_role_summary(user),
        'workspace_roles': workspace_roles,
        'active_tab': 'roles',
        'is_own_profile': True,
        'title': 'Workspace Roles — AetherSpace',
    })


@login_required
def public_profile_view(request, user_id):
    """
    Teammate profile view:
    Enforces server-side permission isolation. Users can only view colleague profiles
    if they share at least one active workspace membership or the viewer is platform admin.
    """
    target_user = get_object_or_404(User, id=user_id)

    if target_user.id == request.user.id:
        return redirect('accounts:profile')

    # Security check: shared workspace or platform admin/manager
    is_manager = getattr(request.user, 'is_manager_role', False)
    shared_workspace = WorkspaceMembership.objects.filter(
        user=request.user,
        status='ACTIVE',
        workspace__memberships__user=target_user,
        workspace__memberships__status='ACTIVE'
    ).exists()

    if not shared_workspace and not request.user.is_admin_role and not is_manager and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to view this user's profile.")

    target_profile = get_or_create_user_profile(target_user)
    target_metrics = get_user_profile_metrics(target_user)
    shared_roles = [
        r for r in get_user_workspace_roles(target_user)
        if WorkspaceMembership.objects.filter(
            workspace__slug=r['workspace_slug'],
            user=request.user,
            status='ACTIVE'
        ).exists()
    ]

    recent_tasks = get_user_assigned_tasks(target_user)[:5]
    recent_activities = get_user_activities(target_user, limit=6)
    req_ws = request.GET.get('workspace', '').strip()
    primary_role = get_user_primary_role_summary(target_user, viewer=request.user, workspace_slug=req_ws)

    return render(request, 'profile/public_profile.html', {
        'profile_user': target_user,
        'profile': target_profile,
        'metrics': target_metrics,
        'primary_role': primary_role,
        'shared_roles': shared_roles,
        'recent_tasks': recent_tasks,
        'recent_activities': recent_activities,
        'is_own_profile': False,
        'active_tab': 'overview',
        'title': f"{target_user.full_name or target_user.email} — Profile",
    })


@login_required
def api_user_hover_card(request, user_identifier):
    """
    Returns user hover card data (name, email, contributor ID, avatar, system & workspace roles, quick links).
    Enforces workspace permission isolation.
    Resolves by UUID, Contributor ID, Full Name, Username, or Email.
    """
    target_user = None
    clean_id = str(user_identifier).strip().lstrip('@')

    # 1. Try UUID
    try:
        val = uuid.UUID(clean_id)
        target_user = User.objects.filter(id=val).first()
    except (ValueError, AttributeError):
        pass

    # 2. Try Contributor ID (e.g. 26457C)
    if not target_user:
        target_user = User.objects.filter(contributor_id__iexact=clean_id).first()

    # 3. Try Full Name
    if not target_user:
        target_user = User.objects.filter(full_name__iexact=clean_id).first()

    # 4. Try Username
    if not target_user:
        target_user = User.objects.filter(username__iexact=clean_id).first()

    # 5. Try Email
    if not target_user:
        target_user = User.objects.filter(email__iexact=clean_id).first()

    # 6. Try Case-insensitive substring/first name match
    if not target_user:
        target_user = User.objects.filter(full_name__icontains=clean_id).first()

    if not target_user:
        return JsonResponse({'error': 'User not found'}, status=404)

    workspace_slug = request.GET.get('workspace', '').strip()

    is_self = (target_user.id == request.user.id)
    is_admin = (request.user.is_admin_role or request.user.is_superuser)

    workspace = None
    target_ws_membership = None
    if workspace_slug:
        workspace = Workspace.objects.filter(slug=workspace_slug).first()
        if workspace:
            viewer_in_ws = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user, status='ACTIVE').exists()
            if not viewer_in_ws and not is_admin:
                raise PermissionDenied("You do not have access to this workspace.")
            target_ws_membership = WorkspaceMembership.objects.filter(workspace=workspace, user=target_user, status='ACTIVE').first()

    if not is_self and not is_admin and not getattr(request.user, 'is_manager_role', False) and not workspace:
        shared_workspace = WorkspaceMembership.objects.filter(
            user=request.user,
            status='ACTIVE',
            workspace__memberships__user=target_user,
            workspace__memberships__status='ACTIVE'
        ).exists()
        if not shared_workspace:
            profile = getattr(target_user, 'profile', None)
            sys_role = target_user.get_role_display() if hasattr(target_user, 'get_role_display') else target_user.role
            headline = getattr(profile, 'headline', '') if profile else ''
            return JsonResponse({
                'id': str(target_user.id),
                'full_name': target_user.full_name or target_user.email.split('@')[0],
                'email': target_user.email,
                'contributor_id': target_user.contributor_id or '',
                'avatar': target_user.avatar or '',
                'initials': (target_user.full_name[:2] if target_user.full_name else target_user.email[:2]).upper(),
                'system_role': sys_role,
                'workspace_role': None,
                'workspace_name': workspace.name if workspace else '',
                'designation': headline or sys_role,
                'tagging_role': '',
                'functional_role': '',
                'is_owner': False,
                'reporting_to_name': '',
                'reporting_to_role': '',
                'headline': headline,
                'availability_status': getattr(target_user, 'availability_status', 'available'),
                'status_message': getattr(target_user, 'status_message', ''),
                'dm_url': None,
                'mailto_url': f"mailto:{target_user.email}",
                'profile_url': f"/auth/profile/u/{target_user.id}/",
                'is_self': False,
            })

    if not target_ws_membership:
        shared_membership = WorkspaceMembership.objects.filter(
            user=target_user,
            status='ACTIVE',
            workspace__memberships__user=request.user,
            workspace__memberships__status='ACTIVE'
        ).select_related('workspace').first()
        if shared_membership:
            target_ws_membership = shared_membership
            if not workspace:
                workspace = shared_membership.workspace

    tagging_role = ''
    functional_role = ''
    if target_ws_membership:
        tagging_role = target_ws_membership.role_tag or ''
        functional_role = target_ws_membership.functional_role or ''

    workspace_name = workspace.name if workspace else (target_ws_membership.workspace.name if target_ws_membership and target_ws_membership.workspace else '')
    workspace_role = target_ws_membership.get_role_display() if target_ws_membership else None
    is_owner = False
    if workspace and workspace.owner_id == target_user.id:
        is_owner = True
    elif target_ws_membership and target_ws_membership.workspace and target_ws_membership.workspace.owner_id == target_user.id:
        is_owner = True

    profile = getattr(target_user, 'profile', None)
    headline = getattr(profile, 'headline', '') if profile else ''

    # Prioritize functional designation (e.g. "Engineering Lead", "Backend Developer", "QA / Test Engineer")
    if functional_role:
        designation = functional_role
    elif headline:
        designation = headline
    elif tagging_role:
        designation = f"{tagging_role} Specialist"
    elif workspace_role:
        designation = workspace_role
    else:
        designation = target_user.get_role_display() if hasattr(target_user, 'get_role_display') else target_user.role

    reporting_to_name = ''
    reporting_to_role = ''
    if target_ws_membership:
        mgr = target_ws_membership.effective_reporting_to
        if mgr and mgr.user_id != target_user.id:
            reporting_to_name = mgr.user.full_name or mgr.user.email
            reporting_to_role = mgr.get_role_display()

    dm_url = f"/chat/w/{workspace.slug}/dm/{target_user.id}/" if (workspace and not is_self) else None
    mailto_url = f"mailto:{target_user.email}"
    profile_url = f"/auth/profile/u/{target_user.id}/" if not is_self else "/auth/profile/"

    return JsonResponse({
        'id': str(target_user.id),
        'full_name': target_user.full_name or target_user.email.split('@')[0],
        'email': target_user.email,
        'contributor_id': target_user.contributor_id or '',
        'avatar': target_user.avatar or '',
        'initials': (target_user.full_name[:2] if target_user.full_name else target_user.email[:2]).upper(),
        'system_role': target_user.get_role_display() if hasattr(target_user, 'get_role_display') else target_user.role,
        'workspace_role': workspace_role,
        'workspace_name': workspace_name,
        'designation': designation,
        'tagging_role': tagging_role,
        'functional_role': functional_role,
        'is_owner': is_owner,
        'reporting_to_name': reporting_to_name,
        'reporting_to_role': reporting_to_role,
        'headline': headline,
        'availability_status': getattr(target_user, 'availability_status', 'available'),
        'status_message': getattr(target_user, 'status_message', ''),
        'dm_url': dm_url,
        'mailto_url': mailto_url,
        'profile_url': profile_url,
        'is_self': is_self,
    })


@login_required
@require_POST
def update_availability_status(request):
    """
    Persists user availability status (available, busy, dnd, away, ooo),
    custom status message, and optional expiration date/time.
    """
    import json
    try:
        data = json.loads(request.body) if request.body else request.POST
    except Exception:
        data = request.POST

    status = data.get('status', 'available')
    valid_statuses = ['available', 'busy', 'dnd', 'away', 'ooo', 'offline']
    if status not in valid_statuses:
        status = 'available'

    status_message = data.get('status_message', '').strip()[:100]
    expires_minutes = data.get('expires_minutes')
    expires_at = None
    if expires_minutes:
        try:
            from datetime import timedelta
            from django.utils import timezone
            mins = int(expires_minutes)
            if mins > 0:
                expires_at = (timezone.now() + timedelta(minutes=mins)).isoformat()
        except (ValueError, TypeError):
            pass

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    pref = profile.preferences or {}
    pref['status'] = status
    pref['status_message'] = status_message
    pref['status_expires_at'] = expires_at
    profile.preferences = pref
    profile.save(update_fields=['preferences', 'updated_at'])

    # Time Tracking: Away, Out of Office, and Offline automatically transition running timers to PAUSED
    if status in ['away', 'ooo', 'offline']:
        try:
            from timetracking.models import TimeEntry, TimerStatus
            running_timers = TimeEntry.objects.filter(
                user=request.user,
                status=TimerStatus.RUNNING
            )
            for timer in running_timers:
                timer.pause()

            # Legacy is_running check
            legacy_running = TimeEntry.objects.filter(
                user=request.user,
                is_running=True
            ).exclude(status=TimerStatus.PAUSED)
            for timer in legacy_running:
                timer.pause()
        except Exception:
            pass

    return JsonResponse({
        'status': 'ok',
        'availability': status,
        'status_message': status_message,
        'expires_at': expires_at,
    })


@login_required
def api_heartbeat(request):
    """
    Heartbeat ping from active browser sessions to refresh online presence cache.
    """
    from django.core.cache import cache
    from django.utils import timezone
    cache.set(f'user_last_seen_{request.user.id}', timezone.now().timestamp(), timeout=300)
    return JsonResponse({'status': 'ok', 'user_id': str(request.user.id)})


