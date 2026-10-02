from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponseForbidden

from accounts.models import User, UserRole, ApprovalStatus
from .models import (
    Workspace, WorkspaceMembership, WorkspaceRole,
    WorkspaceInvitation, InvitationStatus, WorkspaceAccessRequest,
    AccessRequestStatus, MembershipStatus, WorkspaceStatus, WorkspaceModule,
    GlobalAccessRequest, TemporaryAccessGrant, AccessRequestAction,
    AccessRequestUrgency, AccessDurationChoice
)
from notifications.models import Notification, NotificationCategory, NotificationType
from admin_panel.services import AuditLogService, SystemHealthService
from admin_panel.permissions import get_client_ip
from django.core.files.storage import default_storage
from .permissions import (
    workspace_member_required,
    workspace_admin_required,
    workspace_manager_required,
    get_workspace_and_membership
)
from .forms import (
    WorkspaceCreateForm,
    WorkspaceUpdateForm,
    WorkspaceInviteForm,
    WorkspaceMemberRoleForm,
    WorkspaceAccessRequestForm,
    WorkspaceModuleForm,
    ROLE_TAG_CHOICES,
    COMMON_FUNCTIONAL_ROLES
)
from .services import process_and_save_workspace_logo
from tasks.models import Task, TaskStatus, Sprint, SprintStatus
from bugs.models import Bug


@login_required
def dashboard_router(request):
    """
    Intelligent router for /dashboard/.
    - 0 workspaces: prompts creation or empty state.
    - Platform admin or >1 workspaces or Manager role: directs to Master Dashboard.
    - Exactly 1 workspace: directs to that workspace's dashboard.
    """
    memberships = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status=WorkspaceStatus.ACTIVE
    ).select_related('workspace')

    count = memberships.count()

    if count == 0:
        if request.user.is_superuser or getattr(request.user, 'is_admin_role', False):
            # Check if any workspace exists in the system
            first_ws = Workspace.objects.filter(status=WorkspaceStatus.ACTIVE).first()
            if first_ws:
                return redirect('workspaces:workspace_dashboard', slug=first_ws.slug)
            return redirect('workspaces:create')

        if getattr(request.user, 'is_manager_role', False) or request.user.role in [UserRole.ADMIN, UserRole.MANAGER]:
            return redirect('workspaces:create')

        return render(request, 'workspaces/no_workspaces.html')

    # If user is manager/admin or belongs to multiple workspaces -> Master Dashboard
    is_manager_or_multi = (
        count > 1 or
        any(m.role in [WorkspaceRole.ADMIN, WorkspaceRole.MANAGER] for m in memberships) or
        request.user.is_superuser or
        getattr(request.user, 'is_manager_role', False)
    )

    if is_manager_or_multi and count > 1:
        return redirect('workspaces:master_dashboard')

    # Exactly 1 workspace
    first_membership = memberships.first()
    return redirect('workspaces:workspace_dashboard', slug=first_membership.workspace.slug)


@login_required
def master_dashboard(request):
    """
    Cross-workspace overview dashboard for Managers and multi-workspace users.
    Displays aggregate metrics across projects, workspace health cards, and active team presence.
    """
    if request.user.is_superuser or getattr(request.user, 'is_admin_role', False):
        workspaces = Workspace.objects.filter(status=WorkspaceStatus.ACTIVE).annotate(
            active_member_count=Count('memberships', filter=Q(memberships__status=MembershipStatus.ACTIVE))
        )
    else:
        workspaces = Workspace.objects.filter(
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE,
            status=WorkspaceStatus.ACTIVE
        ).annotate(
            active_member_count=Count('memberships', filter=Q(memberships__status=MembershipStatus.ACTIVE))
        )

    # Attach current user's membership to each workspace
    user_memberships = {
        m.workspace_id: m for m in WorkspaceMembership.objects.filter(
            user=request.user,
            workspace__in=workspaces
        )
    }
    for ws in workspaces:
        ws.current_user_membership = user_memberships.get(ws.id)

    total_workspaces = workspaces.count()
    total_members = sum(ws.active_member_count for ws in workspaces)

    # Real database metrics across active accessible workspaces
    from bugs.models import Bug
    from meetings.models import Meeting, MeetingStatus
    total_tasks = Task.objects.filter(workspace__in=workspaces).exclude(status=TaskStatus.DONE).count()
    total_bugs = Bug.objects.filter(workspace__in=workspaces).filter(status__in=['OPEN', 'IN_PROGRESS']).count()
    total_meetings = Meeting.objects.filter(workspace__in=workspaces, status__in=[MeetingStatus.SCHEDULED, MeetingStatus.LIVE]).count()

    context = {
        'title': 'Master Dashboard — Cross-Workspace Overview',
        'workspaces': workspaces,
        'total_workspaces': total_workspaces,
        'total_members': total_members,
        'total_tasks': total_tasks,
        'total_bugs': total_bugs,
        'total_meetings': total_meetings,
    }
    return render(request, 'workspaces/master_dashboard.html', context)


@workspace_member_required
def workspace_dashboard(request, slug):
    """
    Project-scoped daily overview for authorized workspace members.
    Displays sprint status, task/bug metrics, member presence, and quick actions.
    """
    workspace = request.workspace
    membership = request.membership

    from django.db.models import Case, When, Value, IntegerField, Sum, Count
    from django.utils import timezone
    from tasks.models import Task, TaskStatus, TaskPriority, Sprint, SprintStatus, TaskActivity
    from bugs.models import Bug, BugSeverity, BugStatus
    from meetings.models import Meeting, MeetingStatus
    from calendars.models import CalendarEvent, EventStatus
    from notifications.models import Notification
    from files.models import StoredFile

    # 1. Members and Roster
    all_active_members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user', 'user__profile', 'reporting_to', 'reporting_to__user')

    total_members_count = all_active_members.count()
    admins_count = all_active_members.filter(role=WorkspaceRole.ADMIN).count()
    managers_count = all_active_members.filter(role=WorkspaceRole.MANAGER).count()
    contributors_count = all_active_members.filter(role=WorkspaceRole.CONTRIBUTOR).count()

    roster_role_order = Case(
        When(role=WorkspaceRole.ADMIN, then=Value(1)),
        When(role=WorkspaceRole.MANAGER, then=Value(2)),
        When(role=WorkspaceRole.CONTRIBUTOR, then=Value(3)),
        default=Value(4),
        output_field=IntegerField()
    )
    members = all_active_members.order_by(roster_role_order, 'user__full_name')[:8]

    # 2. Tasks & Active Priority Tasks
    active_tasks_qs = workspace.tasks.exclude(status=TaskStatus.DONE).select_related('assignee', 'reporter')
    active_tasks_count = active_tasks_qs.count()
    
    task_priority_order = Case(
        When(priority=TaskPriority.URGENT, then=Value(1)),
        When(priority=TaskPriority.HIGH, then=Value(2)),
        When(priority=TaskPriority.MEDIUM, then=Value(3)),
        When(priority=TaskPriority.LOW, then=Value(4)),
        default=Value(5),
        output_field=IntegerField()
    )
    priority_tasks = active_tasks_qs.annotate(p_rank=task_priority_order).order_by('p_rank', '-created_at')[:6]
    recent_tasks = workspace.tasks.select_related('assignee', 'reporter').order_by('-created_at')[:6]

    # 3. Bugs & Triage
    open_bugs_qs = workspace.bugs.filter(status__in=['OPEN', 'IN_PROGRESS', 'TRIAGED']).select_related('assignee', 'reporter')
    open_bugs_count = open_bugs_qs.count()
    high_severity_bugs_count = open_bugs_qs.filter(severity__in=['SEV1', 'SEV2']).count()
    
    bug_sev_order = Case(
        When(severity='SEV1', then=Value(1)),
        When(severity='SEV2', then=Value(2)),
        When(severity='SEV3', then=Value(3)),
        When(severity='SEV4', then=Value(4)),
        default=Value(5),
        output_field=IntegerField()
    )
    triage_bugs = open_bugs_qs.annotate(s_rank=bug_sev_order).order_by('s_rank', '-created_at')[:6]
    recent_bugs = workspace.bugs.select_related('assignee', 'reporter').order_by('-created_at')[:6]

    # 4. Meetings & Today's Schedule
    today = timezone.now().date()
    now_dt = timezone.now()
    meetings_today_qs = workspace.meetings.filter(
        scheduled_start__date=today
    ).exclude(status=MeetingStatus.CANCELLED).order_by('scheduled_start')
    meetings_today_count = meetings_today_qs.count()

    next_meeting = workspace.meetings.filter(
        scheduled_start__gte=now_dt
    ).exclude(status__in=[MeetingStatus.CANCELLED, MeetingStatus.ENDED]).order_by('scheduled_start').first()

    upcoming_meetings_count = workspace.meetings.filter(
        status__in=[MeetingStatus.SCHEDULED, MeetingStatus.LIVE]
    ).count()

    # 5. Upcoming Deadlines & Calendar Events
    upcoming_events = workspace.calendar_events.filter(
        start_at__gte=now_dt
    ).exclude(status=EventStatus.CANCELLED).order_by('start_at')[:5]

    # 6. Active Sprint & Progress
    active_sprint = Sprint.objects.filter(workspace=workspace, status=SprintStatus.ACTIVE).first()
    sprint_breakdown = active_sprint.task_status_breakdown if active_sprint else None

    # 7. Team Activity Stream
    recent_task_activities = TaskActivity.objects.filter(
        task__workspace=workspace
    ).select_related('actor', 'task').order_by('-created_at')[:6]

    recent_notifications = Notification.objects.filter(
        workspace=workspace
    ).select_related('actor', 'recipient').order_by('-created_at')[:6]

    # 8. Storage & Workspace Metadata
    file_stats = StoredFile.objects.filter(workspace=workspace, is_trashed=False).aggregate(
        total_bytes=Sum('size_bytes'),
        total_count=Count('id')
    )
    storage_used_bytes = file_stats['total_bytes'] or 0
    total_files_count = file_stats['total_count'] or 0

    def format_size(size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    storage_used_display = format_size(storage_used_bytes)
    quota_mb = workspace.storage_quota_mb or 50
    storage_percent = min(100, int((storage_used_bytes / (quota_mb * 1024 * 1024)) * 100)) if quota_mb > 0 else 0

    can_create_task = (membership.role in [WorkspaceRole.ADMIN, WorkspaceRole.MANAGER]) or getattr(membership, 'can_create_task', False)

    context = {
        'title': f"{workspace.name} — Workspace Dashboard",
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'total_members_count': total_members_count,
        'admins_count': admins_count,
        'managers_count': managers_count,
        'contributors_count': contributors_count,
        'active_tasks_count': active_tasks_count,
        'priority_tasks': priority_tasks,
        'recent_tasks': recent_tasks,
        'open_bugs_count': open_bugs_count,
        'high_severity_bugs_count': high_severity_bugs_count,
        'triage_bugs': triage_bugs,
        'recent_bugs': recent_bugs,
        'meetings_today_count': meetings_today_count,
        'upcoming_meetings_count': upcoming_meetings_count,
        'next_meeting': next_meeting,
        'upcoming_events': upcoming_events,
        'active_sprint': active_sprint,
        'sprint_breakdown': sprint_breakdown,
        'recent_task_activities': recent_task_activities,
        'recent_notifications': recent_notifications,
        'storage_used_display': storage_used_display,
        'storage_percent': storage_percent,
        'total_files_count': total_files_count,
        'can_create_task': can_create_task,
    }
    return render(request, 'workspaces/workspace_dashboard.html', context)


@login_required
def create_workspace(request):
    """
    Create a new workspace.
    Restricted to Admins and Managers. Contributors cannot create workspaces.
    The creator is automatically assigned the ADMIN role in WorkspaceMembership.
    """
    is_authorized = (
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False) or
        getattr(request.user, 'is_manager_role', False) or
        request.user.role in [UserRole.ADMIN, UserRole.MANAGER]
    )
    if not is_authorized:
        raise PermissionDenied("Only Administrators and Managers can create workspaces.")

    if request.method == 'POST':
        form = WorkspaceCreateForm(request.POST)
        if form.is_valid():
            workspace = form.save(commit=False)
            workspace.owner = request.user
            workspace.save()

            # Assign creator as ADMIN
            WorkspaceMembership.objects.create(
                workspace=workspace,
                user=request.user,
                role=WorkspaceRole.ADMIN,
                status=MembershipStatus.ACTIVE
            )

            messages.success(
                request,
                f"Workspace '{workspace.name}' created successfully! You are the workspace administrator."
            )
            return redirect('workspaces:workspace_dashboard', slug=workspace.slug)
    else:
        form = WorkspaceCreateForm()

    return render(request, 'workspaces/create.html', {
        'title': 'Create New Workspace',
        'form': form,
    })


@workspace_member_required
def workspace_team(request, slug):
    """
    Team members directory.
    If current user is Admin, displays member management controls, invitations, and role editors.
    """
    workspace = request.workspace
    membership = request.membership

    members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user', 'user__profile', 'reporting_to', 'reporting_to__user').order_by('-role', 'joined_at')

    # Build hierarchy tree for visual organization chart
    children_map = {str(m.id): [] for m in members}
    root_members = []
    member_dict = {str(m.id): m for m in members}

    for m in members:
        mgr = m.effective_reporting_to
        if mgr and str(mgr.id) in member_dict and str(mgr.id) != str(m.id):
            children_map[str(mgr.id)].append(m)
        else:
            root_members.append(m)

    for m in members:
        m.hierarchy_reports = children_map.get(str(m.id), [])

    invitations = []
    invite_form = None
    access_requests = []

    if membership.can_manage_workspace:
        invite_form = WorkspaceInviteForm()
        invitations = WorkspaceInvitation.objects.filter(
            workspace=workspace,
            status=InvitationStatus.PENDING,
            expires_at__gt=timezone.now()
        ).select_related('invited_by')
        access_requests = WorkspaceAccessRequest.objects.filter(
            workspace=workspace,
            status=AccessRequestStatus.PENDING
        ).select_related('user')

    context = {
        'title': f"{workspace.name} — Team Members",
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'root_members': root_members,
        'invitations': invitations,
        'invite_form': invite_form,
        'access_requests': access_requests,
        'roles': WorkspaceRole.choices,
        'role_tags': ROLE_TAG_CHOICES,
        'common_functional_roles': COMMON_FUNCTIONAL_ROLES,
    }
    return render(request, 'workspaces/team.html', context)


@workspace_admin_required
def invite_member(request, slug):
    """
    Issue a secure cryptographic invitation to join the workspace.
    """
    workspace = request.workspace

    if request.method == 'POST':
        form = WorkspaceInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']

            # Check seat capacity
            if workspace.is_seats_full:
                messages.error(
                    request,
                    f"Workspace seat capacity reached ({workspace.seats_assigned}/{workspace.max_seats} seats used). "
                    "Please increase allocated seats in Workspace Settings to invite more members."
                )
                return redirect('workspaces:team', slug=slug)

            # Check if user already in workspace
            existing_member = WorkspaceMembership.objects.filter(
                workspace=workspace,
                user__email=email,
                status=MembershipStatus.ACTIVE
            ).first()

            if existing_member:
                messages.warning(request, f"User with email '{email}' is already an active member of this workspace.")
                return redirect('workspaces:team', slug=slug)

            # Create or update pending invitation
            invite, created = WorkspaceInvitation.objects.update_or_create(
                workspace=workspace,
                email=email,
                status=InvitationStatus.PENDING,
                defaults={
                    'role': role,
                    'invited_by': request.user,
                    'expires_at': timezone.now() + timezone.timedelta(days=7),
                }
            )

            invite_url = request.build_absolute_uri(
                reverse('workspaces:accept_invitation', kwargs={'token': invite.token})
            )

            try:
                from notifications.email_service import send_workspace_invitation_email
                send_workspace_invitation_email(
                    invitation=invite,
                    recipient_email=email,
                    workspace=workspace,
                    invitation_url=invite_url,
                    role_name=invite.get_role_display(),
                    actor=request.user
                )
            except Exception:
                pass

            messages.success(
                request,
                f"Invitation sent to {email}! (Dev invitation link: {invite_url})"
            )
            return redirect('workspaces:team', slug=slug)
        else:
            messages.error(request, "Please provide a valid email address.")

    return redirect('workspaces:team', slug=slug)


@workspace_member_required
def api_workspace_people_search(request, slug):
    """
    Search-first API for direct workspace member addition by Admin/Manager.
    Mandatory Search-First rule:
    - If query is empty / missing / whitespace: strictly returns empty array.
    - Searches by Contributor ID (#####C), full_name, email, or username.
    - Filters only APPROVED and active users.
    - Excludes users who are already active members in this workspace.
    """
    workspace = request.workspace
    membership = request.membership

    can_add = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    if not can_add:
        return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'status': 'ok', 'users': []})

    # Get IDs of active members in this workspace
    existing_user_ids = set(
        WorkspaceMembership.objects.filter(
            workspace=workspace,
            status=MembershipStatus.ACTIVE
        ).values_list('user_id', flat=True)
    )

    candidates = User.objects.filter(
        approval_status=ApprovalStatus.APPROVED,
        is_active=True
    ).exclude(
        id__in=existing_user_ids
    ).filter(
        Q(contributor_id__icontains=q) |
        Q(full_name__icontains=q) |
        Q(email__icontains=q) |
        Q(username__icontains=q)
    ).order_by('full_name', 'email')[:20]

    user_data = []
    for u in candidates:
        name = u.full_name or u.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
        user_data.append({
            'id': str(u.id),
            'contributor_id': u.contributor_id or '—',
            'full_name': name,
            'email': u.email,
            'initials': initials,
            'system_role': u.get_role_display(),
            'avatar': u.avatar if getattr(u, 'avatar', None) and not u.avatar.startswith('preset:') else '',
        })

    return JsonResponse({'status': 'ok', 'users': user_data})


@workspace_member_required
def api_workspace_members_search(request, slug):
    """
    Search-first active member search for task/bug assignment and comment mentions.
    STRICT RULE: Returns empty list if query string is empty unless allow_empty=true.
    Never exposes users outside this workspace.
    """
    q = request.GET.get('q', '').strip()
    allow_empty = request.GET.get('allow_empty') == 'true'
    if not q and not allow_empty:
        return JsonResponse({'status': 'ok', 'users': [], 'members': [], 'total': 0})

    workspace = request.workspace
    memberships = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE,
        user__is_active=True
    ).select_related('user')
    
    if q:
        memberships = memberships.filter(
            Q(user__contributor_id__icontains=q) |
            Q(user__full_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__username__icontains=q)
        )
    memberships = memberships.order_by('user__full_name', 'user__email')[:25]

    users_data = []
    for m in memberships:
        u = m.user
        name = u.full_name or u.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
        avatar_raw = str(u.avatar) if getattr(u, 'avatar', None) else ''
        avatar_val = '' if avatar_raw.startswith('preset:') else avatar_raw
        avatar_preset = avatar_raw.split(':', 1)[1] if avatar_raw.startswith('preset:') else ''
        users_data.append({
            'id': str(u.id),
            'contributor_id': u.contributor_id or '—',
            'full_name': name,
            'email': u.email,
            'username': u.username,
            'initials': initials,
            'role': m.get_role_display(),
            'avatar': avatar_val,
            'avatar_preset': avatar_preset,
        })

    return JsonResponse({'status': 'ok', 'users': users_data, 'members': users_data, 'total': len(users_data)})


@workspace_member_required
def api_workspace_mentions(request, slug):
    """
    Autocomplete endpoint for @ mentions returning People and Files (matching Image 1).
    If q is empty (user just typed '@'), returns top workspace members and recent files.
    If q is provided, searches members and files.
    """
    workspace = request.workspace
    q = request.GET.get('q', '').strip()

    # 1. Search People
    memberships = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE,
        user__is_active=True
    ).select_related('user')
    if q:
        memberships = memberships.filter(
            Q(user__contributor_id__icontains=q) |
            Q(user__full_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__username__icontains=q)
        )
    memberships = memberships.order_by('user__full_name', 'user__email')[:10]

    people_data = []
    for m in memberships:
        u = m.user
        name = u.full_name or u.email.split('@')[0]
        initials = ''.join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
        avatar_val = str(u.avatar) if getattr(u, 'avatar', None) else ''
        if avatar_val.startswith('preset:'):
            avatar_val = ''
        people_data.append({
            'id': str(u.id),
            'type': 'person',
            'contributor_id': u.contributor_id or '',
            'full_name': name,
            'email': u.email,
            'username': u.username,
            'initials': initials,
            'role': m.get_role_display(),
            'avatar': avatar_val,
        })

    # 2. Search Files
    from files.models import StoredFile
    files_qs = StoredFile.objects.filter(workspace=workspace, is_trashed=False)
    if q:
        files_qs = files_qs.filter(
            Q(original_name__icontains=q) |
            Q(name__icontains=q)
        )
    files_qs = files_qs.order_by('-created_at')[:6]

    files_data = []
    for f in files_qs:
        files_data.append({
            'id': str(f.id),
            'type': 'file',
            'name': f.filename,
            'size': f.size_display,
            'url': f.file_url,
            'extension': f.extension,
        })

    return JsonResponse({
        'status': 'ok',
        'people': people_data,
        'files': files_data,
        'total': len(people_data) + len(files_data),
    })


@workspace_member_required
def direct_add_member(request, slug):
    """
    Directly add an existing approved user to the workspace without requiring
    an invitation link/token, matching Admin/Manager direct addition workflow.
    """
    if request.method != 'POST':
        return redirect('workspaces:team', slug=slug)

    workspace = request.workspace
    membership = request.membership

    can_add = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )
    if not can_add:
        messages.error(request, "Permission Denied: Only Workspace Admins and Managers can add members.")
        return redirect('workspaces:team', slug=slug)

    # Check seat capacity
    if workspace.is_seats_full:
        messages.error(
            request,
            f"Workspace seat capacity reached ({workspace.seats_assigned}/{workspace.max_seats} seats used). "
            "Please increase allocated seats in Workspace Settings before adding members."
        )
        return redirect('workspaces:team', slug=slug)

    target_user_id = request.POST.get('user_id', '').strip()
    role = request.POST.get('role', WorkspaceRole.CONTRIBUTOR).strip()
    if role not in dict(WorkspaceRole.choices):
        role = WorkspaceRole.CONTRIBUTOR

    if not target_user_id:
        messages.error(request, "Please select a valid user to add to the workspace.")
        return redirect('workspaces:team', slug=slug)

    target_user = get_object_or_404(User, id=target_user_id)

    # Verify user approval
    if not target_user.is_approved or not target_user.is_active:
        messages.error(
            request,
            f"Cannot add user '{target_user.email}': The account has not been approved by an administrator."
        )
        return redirect('workspaces:team', slug=slug)

    # Check if membership exists
    existing_mem = WorkspaceMembership.objects.filter(workspace=workspace, user=target_user).first()
    if existing_mem and existing_mem.status == MembershipStatus.ACTIVE:
        messages.warning(
            request,
            f"User '{target_user.full_name or target_user.email}' is already an active member of {workspace.name}."
        )
        return redirect('workspaces:team', slug=slug)

    if existing_mem:
        existing_mem.status = MembershipStatus.ACTIVE
        existing_mem.role = role
        existing_mem.save(update_fields=['status', 'role'])
    else:
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=target_user,
            role=role,
            status=MembershipStatus.ACTIVE
        )

    user_display = target_user.full_name or target_user.email
    messages.success(
        request,
        f"Member '{user_display}' [{target_user.contributor_id}] directly added to {workspace.name} as {role.capitalize()}."
    )
    return redirect('workspaces:team', slug=slug)


def accept_invitation(request, token):
    """
    Accept an invitation token to join a workspace.
    """
    invite = get_object_or_404(WorkspaceInvitation, token=token)

    if not invite.is_valid:
        return render(request, 'workspaces/accept_invite.html', {
            'title': 'Invitation Expired or Invalid',
            'is_valid': False,
            'invite': invite,
            'error_message': 'This invitation link has expired or has already been used.',
        })

    if request.method == 'POST':
        if not request.user.is_authenticated:
            login_url = reverse('accounts:login')
            return redirect(f"{login_url}?next={request.path}")

        success, msg = invite.accept(request.user)
        if success:
            messages.success(request, f"Welcome to {invite.workspace.name}! You have joined as {invite.get_role_display()}.")
            return redirect('workspaces:workspace_dashboard', slug=invite.workspace.slug)
        else:
            messages.error(request, msg)

    return render(request, 'workspaces/accept_invite.html', {
        'title': f"Join {invite.workspace.name} on AetherSpace",
        'is_valid': True,
        'invite': invite,
    })


@workspace_admin_required
def update_member_role(request, slug, member_id):
    """
    Update a member's role (Admin, Manager, Contributor), functional designation,
    role tag, and reporting line. Guarded against demoting the sole administrator.
    Only Workspace Admins can decide reporting person and roles.
    """
    workspace = request.workspace
    member = get_object_or_404(WorkspaceMembership, id=member_id, workspace=workspace)

    if request.method == 'POST':
        form = WorkspaceMemberRoleForm(request.POST, member=member)
        if form.is_valid():
            member.role = form.cleaned_data['role']
            member.functional_role = form.cleaned_data.get('functional_role', '').strip()
            member.role_tag = form.cleaned_data.get('role_tag', '').strip()
            member.reporting_to = form.cleaned_data.get('reporting_to')
            member.save(update_fields=['role', 'functional_role', 'role_tag', 'reporting_to'])
            messages.success(
                request,
                f"Updated {member.user.full_name or member.user.email}'s role & reporting line successfully."
            )
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())

    return redirect('workspaces:team', slug=slug)


@workspace_admin_required
def remove_member(request, slug, member_id):
    """
    Remove a member from the workspace.
    Guarded against removing the sole administrator.
    """
    workspace = request.workspace
    member = get_object_or_404(WorkspaceMembership, id=member_id, workspace=workspace)

    if request.method == 'POST':
        if member.is_admin:
            admin_count = WorkspaceMembership.objects.filter(
                workspace=workspace,
                role=WorkspaceRole.ADMIN,
                status=MembershipStatus.ACTIVE
            ).count()
            if admin_count <= 1:
                messages.error(request, "Cannot remove the only administrator of this workspace.")
                return redirect('workspaces:team', slug=slug)

        member_name = member.user.full_name or member.user.email
        member.delete()
        messages.success(request, f"Removed {member_name} from the workspace.")

    return redirect('workspaces:team', slug=slug)


@workspace_admin_required
def workspace_settings(request, slug):
    """
    Workspace configuration page for Admins.
    Update workspace name, description, status, storage, and logo.
    """
    workspace = request.workspace

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        form = WorkspaceUpdateForm(request.POST, request.FILES, instance=workspace)

        # Check if this is a dedicated remove logo action
        if action == 'remove_logo' or request.POST.get('remove_logo') in ['1', 'true', 'True']:
            success, msg = process_and_save_workspace_logo(workspace, remove_logo=True)
            if success:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect('workspaces:settings', slug=workspace.slug)

        if form.is_valid():
            workspace = form.save(commit=False)

            logo_file = request.FILES.get('logo_file') or request.FILES.get('logo')
            logo_url = request.POST.get('logo_url', '').strip()

            if logo_file:
                success, msg = process_and_save_workspace_logo(workspace, file_obj=logo_file)
                if not success:
                    messages.error(request, msg)
            elif logo_url and logo_url != (workspace.logo or ''):
                success, msg = process_and_save_workspace_logo(workspace, logo_url=logo_url)
                if not success:
                    messages.error(request, msg)

            workspace.save()
            messages.success(request, "Workspace settings updated successfully.")
            return redirect('workspaces:settings', slug=workspace.slug)
    else:
        form = WorkspaceUpdateForm(instance=workspace)

    return render(request, 'workspaces/settings.html', {
        'title': f"{workspace.name} — Workspace Settings",
        'workspace': workspace,
        'form': form,
    })


@workspace_admin_required
def delete_workspace(request, slug):
    """
    Permanently delete a workspace.
    Restricted to the workspace owner or platform superuser.
    Requires confirming the workspace name to prevent accidental deletion.
    """
    workspace = request.workspace

    if workspace.owner != request.user and not request.user.is_superuser:
        messages.error(request, "Only the workspace owner can permanently delete this workspace.")
        return redirect('workspaces:settings', slug=workspace.slug)

    if request.method == 'POST':
        confirm_name = request.POST.get('confirm_workspace_name', '').strip()
        if confirm_name != workspace.name:
            messages.error(
                request,
                f"Workspace name confirmation failed. Please type '{workspace.name}' exactly to delete."
            )
            return redirect('workspaces:settings', slug=workspace.slug)

        ws_name = workspace.name
        workspace.delete()
        messages.success(request, f"Workspace '{ws_name}' and all associated assets have been permanently deleted.")
        return redirect('workspaces:dashboard_router')

    return redirect('workspaces:settings', slug=workspace.slug)


@login_required
def request_access(request, slug):
    """
    Create a WorkspaceAccessRequest for an unauthorized user.
    Triggered from 403 Forbidden page or direct request.
    """
    workspace = get_object_or_404(Workspace, slug=slug)

    # If user is already a member
    if workspace.has_user(request.user):
        messages.info(request, f"You are already a member of {workspace.name}.")
        return redirect('workspaces:workspace_dashboard', slug=workspace.slug)

    if request.method == 'POST':
        form = WorkspaceAccessRequestForm(request.POST)
        if form.is_valid():
            message = form.cleaned_data.get('message', '')

            req, created = WorkspaceAccessRequest.objects.get_or_create(
                workspace=workspace,
                user=request.user,
                status=AccessRequestStatus.PENDING,
                defaults={'message': message}
            )

            if created:
                messages.success(
                    request,
                    f"Your access request for '{workspace.name}' has been submitted to the workspace administrators."
                )
            else:
                messages.info(
                    request,
                    f"You already have a pending access request for '{workspace.name}'."
                )
            return redirect('core:landing')
    else:
        form = WorkspaceAccessRequestForm()

    return render(request, 'workspaces/request_access.html', {
        'title': f"Request Access to {workspace.name}",
        'workspace': workspace,
        'form': form,
    })


@login_required
def submit_access_request(request):
    """
    Unified Global Request Access submission endpoint.
    Handles extensible action permissions (task.create, bug.create, etc.)
    and temporary workspace access requests without permanent role elevation.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are supported.'}, status=405)

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest' or
        'application/json' in request.headers.get('accept', '') or
        request.content_type == 'application/json'
    )

    try:
        workspace_id_or_slug = (
            request.POST.get('workspace_id', '').strip() or
            request.POST.get('workspace_slug', '').strip() or
            request.POST.get('workspace', '').strip()
        )
        action = request.POST.get('action', '').strip() or request.POST.get('requested_action', '').strip() or AccessRequestAction.TASK_CREATE
        target_resource_id = request.POST.get('target_resource_id', '').strip()
        reason = request.POST.get('reason', '').strip()
        goal_description = request.POST.get('goal_description', '').strip()
        urgency = request.POST.get('urgency', AccessRequestUrgency.NORMAL).strip()
        evidence_url = request.POST.get('evidence_url', '').strip()
        requested_duration = request.POST.get('requested_duration', AccessDurationChoice.ONE_HOUR).strip()

        # Resilient workspace lookup: UUID, exact slug, slugified name, or name match
        workspace = None
        if workspace_id_or_slug:
            import uuid
            from django.utils.text import slugify
            try:
                val_uuid = uuid.UUID(workspace_id_or_slug)
                workspace = Workspace.objects.filter(id=val_uuid).first()
            except (ValueError, AttributeError):
                pass

            if not workspace:
                slugified = slugify(workspace_id_or_slug)
                workspace = Workspace.objects.filter(
                    Q(slug__iexact=workspace_id_or_slug) |
                    Q(slug__iexact=slugified) |
                    Q(name__iexact=workspace_id_or_slug) |
                    Q(name__icontains=workspace_id_or_slug.strip())
                ).first()

        # Fallback to active workspace if user is member of 1 workspace or active context
        if not workspace:
            user_memberships = request.user.workspace_memberships.filter(status=MembershipStatus.ACTIVE).select_related('workspace')
            if user_memberships.count() == 1:
                workspace = user_memberships.first().workspace
            elif getattr(request, 'workspace', None):
                workspace = request.workspace

        # 1. Validation: Reason is strictly required
        if not reason:
            err_msg = "A valid justification reason is required to submit an access request."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
            messages.error(request, err_msg)
            return redirect(request.META.get('HTTP_REFERER', 'workspaces:dashboard'))

        # 2. Validation: Goal description required for emergency or resource action requests
        if urgency == AccessRequestUrgency.EMERGENCY or action != AccessRequestAction.WORKSPACE_ACCESS:
            if not goal_description:
                err_msg = "Please specify what you are trying to accomplish (required for action and emergency requests)."
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
                messages.error(request, err_msg)
                return redirect(request.META.get('HTTP_REFERER', 'workspaces:dashboard'))

        # 3. Validation: Validate choices
        if action not in AccessRequestAction.values:
            action = AccessRequestAction.TASK_CREATE
        if urgency not in AccessRequestUrgency.values:
            urgency = AccessRequestUrgency.NORMAL
        if requested_duration not in AccessDurationChoice.values:
            requested_duration = AccessDurationChoice.ONE_HOUR

        # 4. Handle optional evidence screenshot upload
        evidence_file_path = ''
        uploaded_file = request.FILES.get('evidence_file')
        if uploaded_file and uploaded_file.size > 0:
            if uploaded_file.size > 5 * 1024 * 1024:
                err_msg = "Evidence file exceeds maximum allowed limit of 5 MB."
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': err_msg}, status=400)
                messages.error(request, err_msg)
                return redirect(request.META.get('HTTP_REFERER', 'workspaces:dashboard'))

            import uuid
            ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else 'png'
            safe_name = f"evidence/{uuid.uuid4().hex[:12]}_{request.user.id}.{ext}"
            try:
                evidence_file_path = default_storage.save(safe_name, uploaded_file)
            except Exception:
                evidence_file_path = ''

        # 5. Persist GlobalAccessRequest
        access_req = GlobalAccessRequest.objects.create(
            user=request.user,
            workspace=workspace,
            action=action,
            target_resource_id=target_resource_id[:255],
            reason=reason,
            goal_description=goal_description,
            urgency=urgency,
            evidence_url=evidence_url[:1024],
            evidence_file=evidence_file_path[:1024],
            requested_duration=requested_duration,
            status=AccessRequestStatus.PENDING
        )

        # 6. AuditLog
        try:
            AuditLogService.log(
                action='ACCESS_REQUEST_SUBMITTED',
                actor=request.user,
                target_type='GlobalAccessRequest',
                target_id=str(access_req.id),
                target_repr=f"{request.user.email} -> {access_req.get_action_display()} ({urgency})",
                workspace=workspace,
                ip_address=get_client_ip(request),
                metadata={
                    'action': action,
                    'urgency': urgency,
                    'requested_duration': requested_duration,
                    'target_resource_id': target_resource_id,
                }
            )
        except Exception:
            pass

        # 7. In-App Notifications
        try:
            ws_name = workspace.name if workspace else "Global Platform"
            Notification.objects.create(
                recipient=request.user,
                actor=request.user,
                workspace=workspace,
                category=NotificationCategory.SYSTEM,
                notification_type=NotificationType.GENERAL,
                title=f"Access Request Submitted: {access_req.get_action_display()}",
                body=f"Your {access_req.get_urgency_display()} request for '{access_req.get_action_display()}' in {ws_name} has been submitted to administrators.",
            )

            admin_users = set(User.objects.filter(Q(role=UserRole.ADMIN) | Q(is_superuser=True)))
            if workspace:
                ws_admins = User.objects.filter(
                    workspace_memberships__workspace=workspace,
                    workspace_memberships__role=WorkspaceRole.ADMIN,
                    workspace_memberships__status=MembershipStatus.ACTIVE
                )
                admin_users.update(ws_admins)
            admin_users.discard(request.user)

            for admin in admin_users:
                Notification.objects.create(
                    recipient=admin,
                    actor=request.user,
                    workspace=workspace,
                    category=NotificationCategory.SYSTEM,
                    notification_type=NotificationType.GENERAL,
                    title=f"New Access Request: {access_req.get_action_display()} [{access_req.get_urgency_display()}]",
                    body=f"{request.user.email} requested '{access_req.get_action_display()}' in {ws_name}. Reason: {reason[:100]}",
                    action_url=reverse('admin_panel:workspace_requests'),
                )
        except Exception:
            pass

        # 8. Sync dynamic alerts
        try:
            SystemHealthService.sync_dynamic_alerts()
        except Exception:
            pass

        success_msg = f"Access request for '{access_req.get_action_display()}' successfully submitted. Administrators have been notified."
        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'message': success_msg,
                'request_id': str(access_req.id)
            })

        messages.success(request, success_msg)
        return redirect(request.META.get('HTTP_REFERER', 'workspaces:dashboard'))

    except Exception as exc:
        if is_ajax:
            return JsonResponse({
                'status': 'error',
                'message': f"Failed to submit access request: {str(exc)}"
            }, status=500)
        messages.error(request, f"Failed to submit access request: {str(exc)}")
        return redirect(request.META.get('HTTP_REFERER', 'workspaces:dashboard'))


@workspace_member_required
def workspace_project_details(request, slug):
    """
    Detailed project summary view matching Panel 2 of the design reference.
    Supports editing project details for Admins and Managers.
    """
    workspace = request.workspace
    membership = request.membership

    can_edit = (
        membership.is_admin or
        membership.is_manager or
        request.user.is_superuser or
        getattr(request.user, 'is_admin_role', False)
    )

    if request.method == 'POST':
        if not can_edit:
            raise PermissionDenied("You do not have permission to edit project details.")

        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        tech_stack = request.POST.get('tech_stack', '').strip()
        project_scope = request.POST.get('project_scope', '').strip()
        architecture_notes = request.POST.get('architecture_notes', '').strip()
        security_mode = request.POST.get('security_mode', '').strip() or 'Strict RBAC'
        storage_provider = request.POST.get('storage_provider', '').strip() or 'Supabase Storage'

        if not name:
            messages.error(request, "Project name cannot be blank.")
        else:
            workspace.name = name
            workspace.description = description
            workspace.tech_stack = tech_stack
            workspace.project_scope = project_scope
            workspace.architecture_notes = architecture_notes
            workspace.security_mode = security_mode
            workspace.storage_provider = storage_provider
            workspace.save()
            messages.success(request, "Project details updated successfully!")

        return redirect('workspaces:project_details', slug=workspace.slug)

    # Real calculated metrics from database
    active_tasks = Task.objects.filter(
        workspace=workspace,
        status__in=[TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.CODE_REVIEW, TaskStatus.TESTING]
    )
    active_tasks_count = active_tasks.count()
    completed_tasks_count = Task.objects.filter(workspace=workspace, status=TaskStatus.DONE).count()
    total_tasks = active_tasks_count + completed_tasks_count
    task_schedule_pct = int(round((completed_tasks_count / total_tasks) * 100)) if total_tasks > 0 else 100

    open_bugs = Bug.objects.filter(workspace=workspace, status__in=['OPEN', 'IN_PROGRESS'])
    open_bugs_count = open_bugs.count()
    high_sev_bugs_count = open_bugs.filter(severity__in=['HIGH', 'CRITICAL']).count()

    total_members_count = workspace.memberships.filter(status=MembershipStatus.ACTIVE).count()

    # Sprints
    current_sprint = Sprint.objects.filter(
        workspace=workspace,
        status=SprintStatus.ACTIVE
    ).first()
    if not current_sprint:
        current_sprint = Sprint.objects.filter(
            workspace=workspace,
            status=SprintStatus.PLANNING
        ).order_by('created_at').first()

    completed_sprints = Sprint.objects.filter(
        workspace=workspace,
        status=SprintStatus.COMPLETED
    ).count()

    context = {
        'title': f"{workspace.name} — Project Details — AetherSpace",
        'workspace': workspace,
        'membership': membership,
        'can_edit': can_edit,
        'tech_stack': workspace.tech_stack_list,
        'total_members_count': total_members_count,
        'active_tasks_count': active_tasks_count,
        'task_schedule_pct': task_schedule_pct,
        'open_bugs_count': open_bugs_count,
        'high_sev_bugs_count': high_sev_bugs_count,
        'current_sprint': current_sprint,
        'completed_sprints': completed_sprints,
    }
    return render(request, 'workspaces/project_details.html', context)


@workspace_member_required
def workspace_chat(request, slug):
    """
    Workspace-scoped team communication launcher: redirects to chat module.
    """
    return redirect('chat:chat_home', slug=slug)


@workspace_member_required
def workspace_modules_view(request, slug):
    """
    List of workspace-scoped modules with active defect counts.
    Allows Admins and Managers to add, edit, and deactivate/delete modules.
    """
    workspace = request.workspace
    membership = request.membership

    modules = workspace.modules.all().order_by('-is_active', 'name')
    form = WorkspaceModuleForm(workspace=workspace) if membership.can_manage_content else None

    context = {
        'title': f"{workspace.name} — Modules — AetherSpace",
        'workspace': workspace,
        'membership': membership,
        'modules': modules,
        'form': form,
    }
    return render(request, 'workspaces/modules.html', context)


@workspace_manager_required
def workspace_module_create(request, slug):
    """
    Create a new module for the workspace.
    Admin / Manager only.
    """
    workspace = request.workspace
    if request.method == 'POST':
        form = WorkspaceModuleForm(request.POST, workspace=workspace)
        if form.is_valid():
            module = form.save(commit=False)
            module.workspace = workspace
            module.save()
            messages.success(request, f"Module '{module.name}' created successfully.")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
    return redirect('workspaces:modules', slug=slug)


@workspace_manager_required
def workspace_module_edit(request, slug, module_id):
    """
    Edit an existing module in the workspace.
    Admin / Manager only.
    """
    workspace = request.workspace
    module = get_object_or_404(WorkspaceModule, id=module_id, workspace=workspace)

    if request.method == 'POST':
        form = WorkspaceModuleForm(request.POST, instance=module, workspace=workspace)
        if form.is_valid():
            form.save()
            messages.success(request, f"Module '{module.name}' updated successfully.")
        else:
            for error in form.errors.values():
                messages.error(request, error.as_text())
    return redirect('workspaces:modules', slug=slug)


@workspace_manager_required
def workspace_module_delete(request, slug, module_id):
    """
    Delete a workspace module.
    Any associated bugs will safely have module set to NULL (on_delete=SET_NULL).
    Admin / Manager only.
    """
    workspace = request.workspace
    module = get_object_or_404(WorkspaceModule, id=module_id, workspace=workspace)

    if request.method == 'POST':
        mod_name = module.name
        bug_count = getattr(module, 'bugs', None).count() if hasattr(module, 'bugs') else 0
        module.delete()
        msg = f"Module '{mod_name}' was deleted."
        if bug_count > 0:
            msg += f" {bug_count} bug(s) previously assigned to it are now unassigned."
        messages.success(request, msg)

    return redirect('workspaces:modules', slug=slug)

