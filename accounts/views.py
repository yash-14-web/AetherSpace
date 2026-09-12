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
from .models import User, UserProfile
from workspaces.models import WorkspaceMembership
from .tokens import account_verification_token
from .services import (
    get_or_create_user_profile,
    get_user_profile_metrics,
    get_user_assigned_tasks,
    get_user_bugs,
    get_user_activities,
    get_user_workspace_roles,
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
    logout(request)
    messages.info(request, "You have been safely signed out.")
    return redirect('accounts:login')


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
            )
            UserProfile.objects.create(user=user)

            # Generate email verification token
            token = account_verification_token.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            verify_url = request.build_absolute_uri(
                reverse('accounts:verify_email_confirm', kwargs={'uidb64': uidb64, 'token': token})
            )
            logger.info("Verification URL generated for %s: %s", user.email, verify_url)

            # Store in session for easy testing/demo display
            request.session['pending_verification_email'] = user.email
            request.session['last_verify_url'] = verify_url

            # Sign user in
            login(request, user)
            messages.success(request, f"Welcome to AetherSpace, {full_name}! Please verify your email.")
            return redirect('accounts:verification')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {
        'form': form,
        'title': 'Create Your Workspace Account — AetherSpace',
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

    return render(request, 'profile/my_profile.html', {
        'profile_user': user,
        'profile': profile,
        'metrics': metrics,
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

    # Security check: shared workspace or platform admin
    shared_workspace = WorkspaceMembership.objects.filter(
        user=request.user,
        status='ACTIVE',
        workspace__memberships__user=target_user,
        workspace__memberships__status='ACTIVE'
    ).exists()

    if not shared_workspace and not request.user.is_admin_role and not request.user.is_superuser:
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

    return render(request, 'profile/public_profile.html', {
        'profile_user': target_user,
        'profile': target_profile,
        'metrics': target_metrics,
        'shared_roles': shared_roles,
        'recent_tasks': recent_tasks,
        'recent_activities': recent_activities,
        'is_own_profile': False,
        'active_tab': 'overview',
        'title': f"{target_user.full_name or target_user.email} — Profile",
    })

