import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.models import UserProfile
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from admin_panel.models import AuditLog, AuditActionStatus
from .forms import (
    AccountDetailsForm,
    ProfileDetailsForm,
    SecurityPasswordChangeForm,
    AppearancePreferencesForm,
    NotificationPreferencesForm,
    WorkspaceSettingsForm,
)


@login_required
def index(request):
    """Entry point for user settings - redirects to Account Settings."""
    return redirect('user_settings:account')


@login_required
def account_settings(request):
    """Account information view (Name, Email, System Role, Timezone)."""
    if request.method == 'POST':
        form = AccountDetailsForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account details have been updated successfully.")
            return redirect('user_settings:account')
    else:
        form = AccountDetailsForm(instance=request.user)

    context = {
        'active_tab': 'account',
        'form': form,
        'user_obj': request.user,
    }
    return render(request, 'settings/account.html', context)


@login_required
def profile_settings(request):
    """User profile view (Headline, Bio, Phone, Avatar)."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProfileDetailsForm(request.POST, instance=profile)
        avatar_url = request.POST.get('avatar_url', '').strip()
        if form.is_valid():
            profile_obj = form.save()
            if avatar_url != request.user.avatar:
                request.user.avatar = avatar_url
                request.user.save(update_fields=['avatar', 'updated_at'])
            messages.success(request, "Your public profile has been updated.")
            return redirect('user_settings:profile')
    else:
        form = ProfileDetailsForm(
            instance=profile,
            initial={'avatar_url': request.user.avatar}
        )

    context = {
        'active_tab': 'profile',
        'form': form,
        'profile': profile,
    }
    return render(request, 'settings/profile.html', context)


@login_required
def appearance_settings(request):
    """Theme & UI Appearance preferences (Obsidian Dark, Slate Light, System Default)."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    prefs = profile.preferences or {}

    current_theme = prefs.get('theme', 'obsidian')
    current_density = prefs.get('ui_density', 'comfortable')
    current_collapsed = prefs.get('sidebar_collapsed', False)

    if request.method == 'POST':
        form = AppearancePreferencesForm(request.POST)
        if form.is_valid():
            prefs['theme'] = form.cleaned_data['theme']
            prefs['ui_density'] = form.cleaned_data['ui_density']
            prefs['sidebar_collapsed'] = form.cleaned_data['sidebar_collapsed']
            profile.preferences = prefs
            profile.save(update_fields=['preferences', 'updated_at'])
            messages.success(request, "Appearance preferences saved successfully.")
            return redirect('user_settings:appearance')
    else:
        form = AppearancePreferencesForm(initial={
            'theme': current_theme,
            'ui_density': current_density,
            'sidebar_collapsed': current_collapsed,
        })

    context = {
        'active_tab': 'appearance',
        'form': form,
        'current_theme': current_theme,
        'current_density': current_density,
        'current_collapsed': current_collapsed,
    }
    return render(request, 'settings/appearance.html', context)


@login_required
@require_POST
def api_update_theme(request):
    """AJAX endpoint for instant live theme synchronization."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        theme = data.get('theme', 'obsidian')
        if theme not in ['obsidian', 'slate', 'system', 'dark', 'light']:
            return JsonResponse({'status': 'error', 'message': 'Invalid theme'}, status=400)
        
        # Standardize
        mapped_theme = 'obsidian' if theme in ['obsidian', 'dark'] else 'slate' if theme in ['slate', 'light'] else 'system'
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        prefs = profile.preferences or {}
        prefs['theme'] = mapped_theme
        profile.preferences = prefs
        profile.save(update_fields=['preferences', 'updated_at'])

        return JsonResponse({'status': 'ok', 'theme': mapped_theme})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def notification_settings(request):
    """Notification & Digest Delivery Preferences."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    prefs = (profile.preferences or {}).get('notifications', {})

    if request.method == 'POST':
        form = NotificationPreferencesForm(request.POST)
        if form.is_valid():
            all_prefs = profile.preferences or {}
            all_prefs['notifications'] = {
                'email_frequency': form.cleaned_data['email_frequency'],
                'task_alerts': form.cleaned_data['task_alerts'],
                'bug_alerts': form.cleaned_data['bug_alerts'],
                'chat_mentions': form.cleaned_data['chat_mentions'],
                'meeting_reminders': form.cleaned_data['meeting_reminders'],
            }
            profile.preferences = all_prefs
            profile.save(update_fields=['preferences', 'updated_at'])
            messages.success(request, "Notification preferences updated.")
            return redirect('user_settings:notifications')
    else:
        form = NotificationPreferencesForm(initial={
            'email_frequency': prefs.get('email_frequency', 'immediate'),
            'task_alerts': prefs.get('task_alerts', True),
            'bug_alerts': prefs.get('bug_alerts', True),
            'chat_mentions': prefs.get('chat_mentions', True),
            'meeting_reminders': prefs.get('meeting_reminders', True),
        })

    context = {
        'active_tab': 'notifications',
        'form': form,
    }
    return render(request, 'settings/notifications.html', context)


@login_required
def security_settings(request):
    """Security credentials, password change, active sessions, and security history."""
    if request.method == 'POST':
        form = SecurityPasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            
            # Log security audit trail
            ip_addr = request.META.get('REMOTE_ADDR', '127.0.0.1')
            AuditLog.objects.create(
                actor=request.user,
                actor_email=request.user.email,
                action='USER_PASSWORD_CHANGED',
                target_type='User',
                target_id=str(request.user.id),
                target_repr=request.user.email,
                ip_address=ip_addr,
                status=AuditActionStatus.SUCCESS,
                metadata={'event': 'PASSWORD_CHANGED'}
            )
            
            messages.success(request, "Your password has been changed successfully.")
            return redirect('user_settings:security')
    else:
        form = SecurityPasswordChangeForm(user=request.user)

    # Active session and audit trail
    recent_events = AuditLog.objects.filter(
        actor=request.user,
        action__in=['USER_PASSWORD_CHANGED', 'SECURITY_EVENT', 'USER_ROLE_CHANGED']
    ).order_by('-created_at')[:5]

    session_info = {
        'session_key': request.session.session_key or 'Active Session',
        'ip_address': request.META.get('REMOTE_ADDR', '127.0.0.1'),
        'user_agent': request.META.get('HTTP_USER_AGENT', 'Modern Web Browser'),
        'last_login': request.user.last_login or timezone.now(),
    }

    context = {
        'active_tab': 'security',
        'form': form,
        'session_info': session_info,
        'recent_events': recent_events,
    }
    return render(request, 'settings/security.html', context)


@login_required
def workspaces_settings(request):
    """Workspaces overview list for current user with role badges and manage links."""
    memberships = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE
    ).select_related('workspace').order_by('workspace__name')

    context = {
        'active_tab': 'workspaces',
        'memberships': memberships,
    }
    return render(request, 'settings/workspaces.html', context)


@login_required
def workspace_detail_settings(request, slug):
    """
    Workspace configuration controls.
    Enforces strict server-side RBAC:
    Only Workspace ADMIN or Platform Root ADMIN can modify settings.
    Contributors and standard Managers receive 403 Forbidden on update.
    """
    workspace = get_object_or_404(Workspace, slug=slug)

    # Check permission
    is_platform_admin = getattr(request.user, 'is_admin_role', False) or request.user.is_superuser
    membership = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=request.user,
        status=MembershipStatus.ACTIVE
    ).first()

    is_ws_admin = membership and membership.role == WorkspaceRole.ADMIN
    can_manage = is_platform_admin or is_ws_admin

    if request.method == 'POST':
        if not can_manage:
            return HttpResponseForbidden("Permission Denied: Only Workspace Administrators can modify settings.")
        
        form = WorkspaceSettingsForm(request.POST, instance=workspace)
        if form.is_valid():
            form.save()
            messages.success(request, f"Workspace '{workspace.name}' settings updated successfully.")
            return redirect('user_settings:workspace_detail', slug=workspace.slug)
    else:
        form = WorkspaceSettingsForm(instance=workspace)

    context = {
        'active_tab': 'workspaces',
        'workspace': workspace,
        'form': form,
        'can_manage': can_manage,
        'membership': membership,
    }
    return render(request, 'settings/workspace_detail.html', context)


@login_required
def integrations_settings(request):
    """Platform & Workspace external integrations and webhooks."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    prefs = profile.preferences or {}
    webhook_secret = prefs.get('webhook_secret', 'whsec_e4b10884261895a97f')

    if request.method == 'POST' and request.POST.get('action') == 'regenerate_webhook':
        import secrets
        new_secret = f"whsec_{secrets.token_hex(16)}"
        prefs['webhook_secret'] = new_secret
        profile.preferences = prefs
        profile.save(update_fields=['preferences', 'updated_at'])
        messages.success(request, "Generated new webhook signing secret.")
        return redirect('user_settings:integrations')

    context = {
        'active_tab': 'integrations',
        'webhook_secret_masked': f"{webhook_secret[:8]}••••••••••••••••",
        'webrtc_active': True,
        'supabase_storage_active': True,
    }
    return render(request, 'settings/integrations.html', context)
