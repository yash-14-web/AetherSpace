import json
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.views.decorators.http import require_POST
from django.conf import settings

from accounts.models import User, UserRole
from workspaces.models import (
    Workspace, WorkspaceMembership, WorkspaceRole, WorkspaceStatus,
    WorkspaceInvitation, WorkspaceAccessRequest, MembershipStatus,
    InvitationStatus, AccessRequestStatus
)
from tasks.models import Task, TaskStatus
from bugs.models import Bug, BugStatus, BugSeverity
from files.models import StoredFile

from .models import AuditLog, AuditActionStatus, AdminAlert, AlertSeverity, AlertCategory
from .permissions import platform_admin_required, get_client_ip
from .services import AuditLogService, StorageSyncService, SystemHealthService, DataExportService
from .forms import (
    AdminUserRoleForm, AdminWorkspaceQuotaForm, AdminWorkspaceStatusForm,
    AdminRequestDecisionForm
)


# -------------------------------------------------------------------------
# 1. Admin Dashboard / System Overview (Screens 04, 67)
# -------------------------------------------------------------------------

@platform_admin_required
def admin_dashboard(request):
    """Main administrative dashboard & system overview."""
    SystemHealthService.sync_dynamic_alerts()
    overview = SystemHealthService.get_system_overview()
    recent_audits = AuditLog.objects.select_related('actor', 'workspace').order_by('-created_at')[:8]
    active_alerts = AdminAlert.objects.filter(is_resolved=False).order_by('-created_at')[:5]
    storage_meta = StorageSyncService.get_storage_metrics()

    context = {
        'active_section': 'dashboard',
        'overview': overview,
        'recent_audits': recent_audits,
        'active_alerts': active_alerts,
        'storage_meta': storage_meta,
        'page_title': 'Admin Dashboard',
    }
    return render(request, 'admin_panel/dashboard.html', context)


# -------------------------------------------------------------------------
# 2. User Management & User Details (Screens 59, 60)
# -------------------------------------------------------------------------

@platform_admin_required
def user_list(request):
    """View and search platform users with search-first selector and filter controls."""
    query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    status_filter = request.GET.get('status', '').strip()

    users_qs = User.objects.annotate(
        workspaces_count=Count('workspace_memberships', filter=Q(workspace_memberships__status=MembershipStatus.ACTIVE))
    ).order_by('-created_at')

    if query:
        users_qs = users_qs.filter(
            Q(full_name__icontains=query) |
            Q(email__icontains=query) |
            Q(username__icontains=query)
        )
    if role_filter:
        users_qs = users_qs.filter(role=role_filter)
    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        users_qs = users_qs.filter(is_active=False)

    paginator = Paginator(users_qs, 15)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)

    context = {
        'active_section': 'users',
        'users_page': users_page,
        'query': query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'total_count': paginator.count,
        'roles': UserRole.choices,
        'page_title': 'User Management',
    }
    return render(request, 'admin_panel/users/user_list.html', context)


@platform_admin_required
def user_details(request, user_id):
    """Detailed administrative user inspection and role/status controls."""
    target_user = get_object_or_404(User, id=user_id)
    memberships = WorkspaceMembership.objects.filter(
        user=target_user
    ).select_related('workspace', 'reporting_to', 'reporting_to__user')

    assigned_tasks = Task.objects.filter(assignees=target_user).select_related('workspace').order_by('-updated_at')[:8]
    reported_bugs = Bug.objects.filter(reporter=target_user).select_related('workspace').order_by('-created_at')[:8]
    user_audits = AuditLog.objects.filter(
        Q(actor=target_user) | Q(target_type='User', target_id=str(target_user.id))
    ).order_by('-created_at')[:10]

    role_form = AdminUserRoleForm(user_instance=target_user)

    context = {
        'active_section': 'users',
        'target_user': target_user,
        'memberships': memberships,
        'assigned_tasks': assigned_tasks,
        'reported_bugs': reported_bugs,
        'user_audits': user_audits,
        'role_form': role_form,
        'page_title': f"User: {target_user.full_name or target_user.email}",
    }
    return render(request, 'admin_panel/users/user_detail.html', context)


@require_POST
@platform_admin_required
def toggle_user_status(request, user_id):
    """Activate or deactivate user account."""
    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "Security protection: You cannot deactivate your own account.")
        return redirect('admin_panel:user_details', user_id=user_id)

    target_user.is_active = not target_user.is_active
    target_user.save(update_fields=['is_active'])

    action = 'USER_ACTIVATED' if target_user.is_active else 'USER_DEACTIVATED'
    AuditLogService.log(
        action=action,
        actor=request.user,
        target_type='User',
        target_id=str(target_user.id),
        target_repr=target_user.email,
        ip_address=get_client_ip(request),
        metadata={'new_status': target_user.is_active}
    )
    status_str = "activated" if target_user.is_active else "deactivated"
    messages.success(request, f"User '{target_user.email}' has been {status_str}.")
    return redirect('admin_panel:user_details', user_id=user_id)


@require_POST
@platform_admin_required
def update_user_role(request, user_id):
    """Update user platform-wide role."""
    target_user = get_object_or_404(User, id=user_id)
    form = AdminUserRoleForm(request.POST, user_instance=target_user)
    if form.is_valid():
        old_role = target_user.role
        new_role = form.cleaned_data['role']
        target_user.role = new_role
        target_user.save(update_fields=['role'])

        AuditLogService.log(
            action='USER_ROLE_CHANGED',
            actor=request.user,
            target_type='User',
            target_id=str(target_user.id),
            target_repr=target_user.email,
            ip_address=get_client_ip(request),
            metadata={'old_role': old_role, 'new_role': new_role}
        )
        messages.success(request, f"Role for '{target_user.email}' updated to {target_user.get_role_display()}.")
    else:
        for error in form.errors.values():
            messages.error(request, error)
    return redirect('admin_panel:user_details', user_id=user_id)


# -------------------------------------------------------------------------
# 3. Roles & Permissions (Screen 61)
# -------------------------------------------------------------------------

@platform_admin_required
def roles_permissions(request):
    """Display comprehensive system and workspace RBAC capability matrix."""
    matrix = [
        {
            'module': 'Platform Administration',
            'desc': 'Access to Admin Panel, system configuration, audit logs, and global health.',
            'admin': True,
            'manager': False,
            'contributor': False,
        },
        {
            'module': 'Workspace Creation & Deletion',
            'desc': 'Create new workspaces and delete owned workspaces.',
            'admin': True,
            'manager': True,
            'contributor': False,
        },
        {
            'module': 'Workspace Settings & Quotas',
            'desc': 'Adjust max seats, storage quotas, and workspace branding.',
            'admin': True,
            'manager': False,
            'contributor': False,
        },
        {
            'module': 'Member Management & Invites',
            'desc': 'Invite members, assign workspace roles, and configure reporting lines.',
            'admin': True,
            'manager': False,
            'contributor': False,
        },
        {
            'module': 'Task Creation & Assignment',
            'desc': 'Create 6-digit numeric tasks (#619347), assign assignees, and set priorities.',
            'admin': True,
            'manager': True,
            'contributor': True,
        },
        {
            'module': 'Bug Tracking & Severity Triage',
            'desc': 'Report bugs (B-882316), triage Sev-1/Sev-2 issues, and manage resolution.',
            'admin': True,
            'manager': True,
            'contributor': True,
        },
        {
            'module': 'Chat & Channels',
            'desc': 'Participate in team channels, direct messaging, and asset sharing.',
            'admin': True,
            'manager': True,
            'contributor': True,
        },
        {
            'module': 'Meeting Rooms & Hub',
            'desc': 'Start instant audio/video rooms, schedule calendar meetings, and join calls.',
            'admin': True,
            'manager': True,
            'contributor': True,
        },
        {
            'module': 'File Storage & Management',
            'desc': 'Upload workspace files (up to 20 MB / 50 MB free-tier quota) and cloud links.',
            'admin': True,
            'manager': True,
            'contributor': True,
        },
        {
            'module': 'Audit Logs Inspection',
            'desc': 'Review administrative history, login events, and security logs.',
            'admin': True,
            'manager': False,
            'contributor': False,
        },
    ]
    context = {
        'active_section': 'roles',
        'matrix': matrix,
        'page_title': 'Roles & Permissions Matrix',
    }
    return render(request, 'admin_panel/roles/roles_permissions.html', context)


# -------------------------------------------------------------------------
# 4. Invitations (Screen 62)
# -------------------------------------------------------------------------

@platform_admin_required
def invitations_list(request):
    """View and manage cross-workspace invitations."""
    status_filter = request.GET.get('status', 'PENDING')
    workspace_filter = request.GET.get('workspace', '').strip()

    invites_qs = WorkspaceInvitation.objects.select_related('workspace', 'invited_by').order_by('-created_at')

    if status_filter != 'ALL':
        invites_qs = invites_qs.filter(status=status_filter)
    if workspace_filter:
        invites_qs = invites_qs.filter(workspace__slug=workspace_filter)

    paginator = Paginator(invites_qs, 15)
    page_number = request.GET.get('page')
    invites_page = paginator.get_page(page_number)

    all_workspaces = Workspace.objects.all().order_by('name')

    context = {
        'active_section': 'invitations',
        'invites_page': invites_page,
        'status_filter': status_filter,
        'workspace_filter': workspace_filter,
        'all_workspaces': all_workspaces,
        'statuses': InvitationStatus.choices,
        'page_title': 'Workspace Invitations',
    }
    return render(request, 'admin_panel/invitations/invitations_list.html', context)


@require_POST
@platform_admin_required
def resend_invitation(request, invite_id):
    """Refresh token and re-issue expiration for an invitation."""
    invite = get_object_or_404(WorkspaceInvitation, id=invite_id)
    invite.expires_at = timezone.now() + timezone.timedelta(days=7)
    invite.status = InvitationStatus.PENDING
    invite.save(update_fields=['expires_at', 'status'])

    AuditLogService.log(
        action='INVITATION_RESENT',
        actor=request.user,
        target_type='WorkspaceInvitation',
        target_id=str(invite.id),
        target_repr=invite.email,
        workspace=invite.workspace,
        ip_address=get_client_ip(request),
    )
    messages.success(request, f"Invitation for '{invite.email}' has been refreshed and extended by 7 days.")
    return redirect('admin_panel:invitations_list')


@require_POST
@platform_admin_required
def revoke_invitation(request, invite_id):
    """Revoke an active invitation."""
    invite = get_object_or_404(WorkspaceInvitation, id=invite_id)
    invite.status = InvitationStatus.REVOKED
    invite.save(update_fields=['status'])

    AuditLogService.log(
        action='INVITATION_REVOKED',
        actor=request.user,
        target_type='WorkspaceInvitation',
        target_id=str(invite.id),
        target_repr=invite.email,
        workspace=invite.workspace,
        ip_address=get_client_ip(request),
    )
    messages.success(request, f"Invitation for '{invite.email}' has been revoked.")
    return redirect('admin_panel:invitations_list')


# -------------------------------------------------------------------------
# 5. Workspace Management (Screen 63)
# -------------------------------------------------------------------------

@platform_admin_required
def workspace_list(request):
    """Platform-wide workspace administration with quotas and status toggles."""
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    workspaces_qs = Workspace.objects.annotate(
        active_members_count=Count('memberships', filter=Q(memberships__status=MembershipStatus.ACTIVE)),
        files_count=Count('files', filter=Q(files__is_trashed=False)),
        storage_used_bytes=Sum('files__size_bytes', filter=Q(files__is_trashed=False, files__is_external_link=False))
    ).select_related('owner').order_by('-created_at')

    if query:
        workspaces_qs = workspaces_qs.filter(Q(name__icontains=query) | Q(slug__icontains=query))
    if status_filter:
        workspaces_qs = workspaces_qs.filter(status=status_filter)

    paginator = Paginator(workspaces_qs, 12)
    page_number = request.GET.get('page')
    workspaces_page = paginator.get_page(page_number)

    context = {
        'active_section': 'workspaces',
        'workspaces_page': workspaces_page,
        'query': query,
        'status_filter': status_filter,
        'statuses': WorkspaceStatus.choices,
        'page_title': 'Workspace Administration',
    }
    return render(request, 'admin_panel/workspaces/workspace_list.html', context)


@platform_admin_required
def workspace_details(request, slug):
    """Detailed workspace inspection for platform administrators."""
    workspace = get_object_or_404(Workspace, slug=slug)
    members = workspace.memberships.select_related('user', 'reporting_to', 'reporting_to__user').order_by('-role')
    quota_form = AdminWorkspaceQuotaForm(workspace=workspace)
    status_form = AdminWorkspaceStatusForm(workspace=workspace)

    storage_bytes = StoredFile.objects.filter(
        workspace=workspace,
        is_trashed=False,
        is_external_link=False
    ).aggregate(total=Sum('size_bytes'))['total'] or 0

    quota_bytes = (workspace.storage_quota_mb or 50) * 1024 * 1024
    storage_pct = round((storage_bytes / quota_bytes) * 100, 1) if quota_bytes > 0 else 0

    recent_tasks = Task.objects.filter(workspace=workspace).order_by('-created_at')[:6]
    recent_bugs = Bug.objects.filter(workspace=workspace).order_by('-created_at')[:6]
    ws_audits = AuditLog.objects.filter(workspace=workspace).order_by('-created_at')[:8]

    context = {
        'active_section': 'workspaces',
        'workspace': workspace,
        'members': members,
        'quota_form': quota_form,
        'status_form': status_form,
        'storage_bytes': storage_bytes,
        'formatted_storage': StorageSyncService.format_bytes(storage_bytes),
        'storage_pct': min(storage_pct, 100),
        'recent_tasks': recent_tasks,
        'recent_bugs': recent_bugs,
        'ws_audits': ws_audits,
        'page_title': f"Workspace: {workspace.name}",
    }
    return render(request, 'admin_panel/workspaces/workspace_detail.html', context)


@require_POST
@platform_admin_required
def toggle_workspace_status(request, slug):
    """Suspend, activate, or archive workspace."""
    workspace = get_object_or_404(Workspace, slug=slug)
    form = AdminWorkspaceStatusForm(request.POST, workspace=workspace)
    if form.is_valid():
        old_status = workspace.status
        new_status = form.cleaned_data['status']
        workspace.status = new_status
        workspace.save(update_fields=['status'])

        AuditLogService.log(
            action='WORKSPACE_STATUS_CHANGED',
            actor=request.user,
            target_type='Workspace',
            target_id=str(workspace.id),
            target_repr=workspace.name,
            workspace=workspace,
            ip_address=get_client_ip(request),
            metadata={'old_status': old_status, 'new_status': new_status}
        )
        messages.success(request, f"Workspace '{workspace.name}' status changed to {workspace.get_status_display()}.")
    return redirect('admin_panel:workspace_details', slug=slug)


@require_POST
@platform_admin_required
def update_workspace_quota(request, slug):
    """Update seats and storage quota for a workspace."""
    workspace = get_object_or_404(Workspace, slug=slug)
    form = AdminWorkspaceQuotaForm(request.POST, workspace=workspace)
    if form.is_valid():
        workspace.max_seats = form.cleaned_data['max_seats']
        workspace.storage_quota_mb = form.cleaned_data['storage_quota_mb']
        workspace.save(update_fields=['max_seats', 'storage_quota_mb'])

        AuditLogService.log(
            action='WORKSPACE_QUOTA_UPDATED',
            actor=request.user,
            target_type='Workspace',
            target_id=str(workspace.id),
            target_repr=workspace.name,
            workspace=workspace,
            ip_address=get_client_ip(request),
            metadata={'max_seats': workspace.max_seats, 'storage_quota_mb': workspace.storage_quota_mb}
        )
        messages.success(request, f"Quotas for '{workspace.name}' updated ({workspace.max_seats} seats, {workspace.storage_quota_mb} MB).")
    else:
        for err in form.errors.values():
            messages.error(request, err)
    return redirect('admin_panel:workspace_details', slug=slug)


# -------------------------------------------------------------------------
# 6. Workspace Requests (Screen 64)
# -------------------------------------------------------------------------

@platform_admin_required
def workspace_requests(request):
    """Review and process workspace access requests originating from 403 pages."""
    status_filter = request.GET.get('status', 'PENDING')
    requests_qs = WorkspaceAccessRequest.objects.select_related('workspace', 'user').order_by('-created_at')

    if status_filter != 'ALL':
        requests_qs = requests_qs.filter(status=status_filter)

    paginator = Paginator(requests_qs, 15)
    page_number = request.GET.get('page')
    requests_page = paginator.get_page(page_number)

    context = {
        'active_section': 'requests',
        'requests_page': requests_page,
        'status_filter': status_filter,
        'statuses': AccessRequestStatus.choices,
        'page_title': 'Workspace Access Requests',
    }
    return render(request, 'admin_panel/requests/workspace_requests.html', context)


@require_POST
@platform_admin_required
def decide_workspace_request(request, request_id):
    """Approve or reject a workspace access request."""
    access_request = get_object_or_404(WorkspaceAccessRequest, id=request_id)
    decision = request.POST.get('decision', 'APPROVE')
    role = request.POST.get('role', WorkspaceRole.CONTRIBUTOR)

    if decision == 'APPROVE':
        access_request.status = AccessRequestStatus.APPROVED
        access_request.save(update_fields=['status'])

        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=access_request.workspace,
            user=access_request.user,
            defaults={'role': role, 'status': MembershipStatus.ACTIVE}
        )
        if not created and membership.status != MembershipStatus.ACTIVE:
            membership.status = MembershipStatus.ACTIVE
            membership.role = role
            membership.save(update_fields=['status', 'role'])

        AuditLogService.log(
            action='ACCESS_REQUEST_APPROVED',
            actor=request.user,
            target_type='WorkspaceAccessRequest',
            target_id=str(access_request.id),
            target_repr=f"{access_request.user.email} -> {access_request.workspace.name}",
            workspace=access_request.workspace,
            ip_address=get_client_ip(request),
            metadata={'assigned_role': role}
        )
        messages.success(request, f"Access approved for {access_request.user.email} into '{access_request.workspace.name}'.")
    else:
        access_request.status = AccessRequestStatus.REJECTED
        access_request.save(update_fields=['status'])

        AuditLogService.log(
            action='ACCESS_REQUEST_REJECTED',
            actor=request.user,
            target_type='WorkspaceAccessRequest',
            target_id=str(access_request.id),
            target_repr=f"{access_request.user.email} -> {access_request.workspace.name}",
            workspace=access_request.workspace,
            ip_address=get_client_ip(request),
        )
        messages.info(request, f"Access request for {access_request.user.email} was rejected.")

    return redirect('admin_panel:workspace_requests')


# -------------------------------------------------------------------------
# 7. Member Management (Screen 65)
# -------------------------------------------------------------------------

@platform_admin_required
def member_management(request):
    """Cross-workspace member lookup and membership management."""
    workspace_slug = request.GET.get('workspace', '').strip()
    user_query = request.GET.get('q', '').strip()

    memberships_qs = WorkspaceMembership.objects.select_related(
        'workspace', 'user', 'reporting_to', 'reporting_to__user'
    ).order_by('-joined_at')

    if workspace_slug:
        memberships_qs = memberships_qs.filter(workspace__slug=workspace_slug)
    if user_query:
        memberships_qs = memberships_qs.filter(
            Q(user__full_name__icontains=user_query) |
            Q(user__email__icontains=user_query) |
            Q(functional_role__icontains=user_query) |
            Q(role_tag__icontains=user_query)
        )

    paginator = Paginator(memberships_qs, 15)
    page_number = request.GET.get('page')
    memberships_page = paginator.get_page(page_number)

    all_workspaces = Workspace.objects.all().order_by('name')

    context = {
        'active_section': 'members',
        'memberships_page': memberships_page,
        'workspace_slug': workspace_slug,
        'user_query': user_query,
        'all_workspaces': all_workspaces,
        'roles': WorkspaceRole.choices,
        'page_title': 'Cross-Workspace Member Management',
    }
    return render(request, 'admin_panel/members/member_management.html', context)


# -------------------------------------------------------------------------
# 8. Audit Logs (Screen 66)
# -------------------------------------------------------------------------

@platform_admin_required
def audit_logs(request):
    """Filterable, searchable, and paginated administrative audit logs."""
    action_filter = request.GET.get('action', '').strip()
    status_filter = request.GET.get('status', '').strip()
    workspace_slug = request.GET.get('workspace', '').strip()
    query = request.GET.get('q', '').strip()

    logs_qs = AuditLog.objects.select_related('actor', 'workspace').order_by('-created_at')

    if action_filter:
        logs_qs = logs_qs.filter(action=action_filter)
    if status_filter:
        logs_qs = logs_qs.filter(status=status_filter)
    if workspace_slug:
        logs_qs = logs_qs.filter(workspace__slug=workspace_slug)
    if query:
        logs_qs = logs_qs.filter(
            Q(actor_email__icontains=query) |
            Q(target_repr__icontains=query) |
            Q(action__icontains=query) |
            Q(ip_address__icontains=query)
        )

    paginator = Paginator(logs_qs, 20)
    page_number = request.GET.get('page')
    logs_page = paginator.get_page(page_number)

    distinct_actions = AuditLog.objects.values_list('action', flat=True).distinct()[:25]
    all_workspaces = Workspace.objects.all().order_by('name')

    context = {
        'active_section': 'audit',
        'logs_page': logs_page,
        'action_filter': action_filter,
        'status_filter': status_filter,
        'workspace_slug': workspace_slug,
        'query': query,
        'distinct_actions': distinct_actions,
        'all_workspaces': all_workspaces,
        'statuses': AuditActionStatus.choices,
        'page_title': 'Audit Logs',
    }
    return render(request, 'admin_panel/audit/audit_logs.html', context)


# -------------------------------------------------------------------------
# 9. System Overview (Screen 67)
# -------------------------------------------------------------------------

@platform_admin_required
def system_overview(request):
    """High-level platform health, infrastructure, and runtime status."""
    overview = SystemHealthService.get_system_overview()
    context = {
        'active_section': 'system',
        'overview': overview,
        'page_title': 'System Overview',
    }
    return render(request, 'admin_panel/system/system_overview.html', context)


# -------------------------------------------------------------------------
# 10. Integrations (Screen 68)
# -------------------------------------------------------------------------

@platform_admin_required
def integrations(request):
    """Status of external services with zero secret disclosure."""
    integrations_list = SystemHealthService.get_integrations_status()
    context = {
        'active_section': 'integrations',
        'integrations': integrations_list,
        'page_title': 'Platform Integrations',
    }
    return render(request, 'admin_panel/integrations/integrations.html', context)


# -------------------------------------------------------------------------
# 11. Storage & Files — Real PostgreSQL & Supabase Sync (Screen 69)
# -------------------------------------------------------------------------

@platform_admin_required
def storage_files(request):
    """Accurate monitoring of PostgreSQL file metadata and Supabase Storage."""
    metrics = StorageSyncService.get_storage_metrics()
    context = {
        'active_section': 'storage',
        'metrics': metrics,
        'page_title': 'Storage & Files Administration',
    }
    return render(request, 'admin_panel/storage/storage_files.html', context)


@platform_admin_required
def storage_sync_audit(request):
    """Run diagnostics verifying database records against Supabase Storage objects."""
    audit_results = StorageSyncService.audit_storage_sync(limit=100)
    AuditLogService.log(
        action='STORAGE_SYNC_AUDIT_RUN',
        actor=request.user,
        target_type='Storage',
        ip_address=get_client_ip(request),
        metadata={'synced': audit_results['synced_count'], 'missing': audit_results['missing_count']}
    )
    if audit_results['is_healthy']:
        messages.success(request, f"Storage Sync Healthy: All {audit_results['total_audited']} checked files match physical storage.")
    else:
        messages.warning(request, f"Storage Anomaly Detected: {audit_results['missing_count']} file(s) missing from storage object bucket.")
    return redirect('admin_panel:storage_files')


@require_POST
@platform_admin_required
def purge_file(request, file_id):
    """Atomically remove an orphaned or unwanted file from storage and database."""
    success, msg = StorageSyncService.purge_file(
        file_id=file_id,
        actor=request.user,
        ip_address=get_client_ip(request)
    )
    if success:
        messages.success(request, msg)
    else:
        messages.error(request, msg)
    return redirect('admin_panel:storage_files')


# -------------------------------------------------------------------------
# 12. Security (Screen 70)
# -------------------------------------------------------------------------

@platform_admin_required
def security_overview(request):
    """Platform security controls, session statistics, and environment posture."""
    security_info = {
        'secret_key_configured': bool(getattr(settings, 'SECRET_KEY', None)),
        'debug_mode': settings.DEBUG,
        'csrf_cookie_secure': getattr(settings, 'CSRF_COOKIE_SECURE', False),
        'session_cookie_secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
        'session_cookie_httponly': getattr(settings, 'SESSION_COOKIE_HTTPONLY', True),
        'password_hasher': settings.PASSWORD_HASHERS[0].split('.')[-1] if hasattr(settings, 'PASSWORD_HASHERS') else 'PBKDF2PasswordHasher',
        'failed_logins_recorded': AuditLog.objects.filter(action='USER_LOGIN_FAILED').count(),
        'recent_security_events': AuditLog.objects.filter(
            action__in=['USER_LOGIN_FAILED', 'USER_ROLE_CHANGED', 'USER_DEACTIVATED', 'PERMISSION_DENIED']
        ).order_by('-created_at')[:8],
        'total_active_sessions': User.objects.filter(is_active=True, last_login__gte=timezone.now() - timezone.timedelta(days=1)).count(),
    }
    context = {
        'active_section': 'security',
        'security_info': security_info,
        'page_title': 'Security Controls',
    }
    return render(request, 'admin_panel/security/security.html', context)


# -------------------------------------------------------------------------
# 13. Backup & Restore (Screen 71)
# -------------------------------------------------------------------------

@platform_admin_required
def backup_restore(request):
    """Backup overview, JSON metadata export, and owner restoration procedures."""
    context = {
        'active_section': 'backup',
        'page_title': 'Backup & Restore',
    }
    return render(request, 'admin_panel/backup/backup_restore.html', context)


@platform_admin_required
def export_data(request):
    """Download JSON snapshot of application metadata."""
    json_data = DataExportService.generate_export_json()
    filename = f"aetherspace_backup_{timezone.now():%Y%m%d_%H%M%S}.json"

    AuditLogService.log(
        action='DATA_EXPORT_DOWNLOADED',
        actor=request.user,
        target_type='System',
        target_repr=filename,
        ip_address=get_client_ip(request)
    )
    response = HttpResponse(json_data, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# -------------------------------------------------------------------------
# 14. Activity Monitor (Screen 72)
# -------------------------------------------------------------------------

@platform_admin_required
def activity_monitor(request):
    """Live chronological cross-platform activity stream."""
    activities = AuditLog.objects.select_related('actor', 'workspace').order_by('-created_at')
    paginator = Paginator(activities, 25)
    page_number = request.GET.get('page')
    activities_page = paginator.get_page(page_number)

    context = {
        'active_section': 'activity',
        'activities_page': activities_page,
        'page_title': 'System Activity Monitor',
    }
    return render(request, 'admin_panel/activity/activity_monitor.html', context)


# -------------------------------------------------------------------------
# 15. Performance (Screen 73)
# -------------------------------------------------------------------------

@platform_admin_required
def performance_overview(request):
    """Measured database and application performance indicators."""
    db_latency, db_status = SystemHealthService.get_database_latency_ms()
    context = {
        'active_section': 'performance',
        'db_latency': db_latency,
        'db_status': db_status,
        'page_title': 'Performance Indicators',
    }
    return render(request, 'admin_panel/performance/performance.html', context)


# -------------------------------------------------------------------------
# 16. Alerts (Screen 74)
# -------------------------------------------------------------------------

@platform_admin_required
def alerts_list(request):
    """Actionable system health and resource alerts."""
    SystemHealthService.sync_dynamic_alerts()
    severity_filter = request.GET.get('severity', '').strip()
    status_filter = request.GET.get('status', 'active')

    alerts_qs = AdminAlert.objects.select_related('workspace', 'resolved_by').order_by('is_resolved', '-created_at')

    if status_filter == 'active':
        alerts_qs = alerts_qs.filter(is_resolved=False)
    elif status_filter == 'resolved':
        alerts_qs = alerts_qs.filter(is_resolved=True)

    if severity_filter:
        alerts_qs = alerts_qs.filter(severity=severity_filter)

    paginator = Paginator(alerts_qs, 15)
    page_number = request.GET.get('page')
    alerts_page = paginator.get_page(page_number)

    context = {
        'active_section': 'alerts',
        'alerts_page': alerts_page,
        'severity_filter': severity_filter,
        'status_filter': status_filter,
        'severities': AlertSeverity.choices,
        'page_title': 'System Alerts',
    }
    return render(request, 'admin_panel/alerts/alerts.html', context)


@require_POST
@platform_admin_required
def resolve_alert(request, alert_id):
    """Mark an administrative alert as resolved."""
    alert = get_object_or_404(AdminAlert, id=alert_id)
    alert.is_resolved = True
    alert.resolved_by = request.user
    alert.resolved_at = timezone.now()
    alert.save(update_fields=['is_resolved', 'resolved_by', 'resolved_at'])

    AuditLogService.log(
        action='ALERT_RESOLVED',
        actor=request.user,
        target_type='AdminAlert',
        target_id=str(alert.id),
        target_repr=alert.title,
        ip_address=get_client_ip(request),
    )
    messages.success(request, f"Alert '{alert.title}' marked as resolved.")
    return redirect('admin_panel:alerts_list')


# -------------------------------------------------------------------------
# Search-First People Search API Endpoint (Mandatory Rule)
# -------------------------------------------------------------------------

@platform_admin_required
def api_people_search(request):
    """
    Search-first people selector API.
    Mandatory rule:
    - Empty query / whitespace query / missing query strictly returns EMPTY list.
    - Never dumps complete user directory on modal open.
    - Only queries once characters are typed.
    """
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'status': 'ok', 'users': []})

    users = User.objects.filter(
        Q(full_name__icontains=q) |
        Q(email__icontains=q) |
        Q(username__icontains=q)
    ).order_by('full_name', 'email')[:20]

    user_data = []
    for u in users:
        user_data.append({
            'id': str(u.id),
            'full_name': u.full_name or u.email.split('@')[0],
            'email': u.email,
            'role': u.role,
            'role_display': u.get_role_display(),
            'is_active': u.is_active,
            'is_verified': u.is_verified,
            'avatar': u.avatar,
        })

    return JsonResponse({'status': 'ok', 'users': user_data})
