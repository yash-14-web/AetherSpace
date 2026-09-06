from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied

from .models import (
    Workspace, WorkspaceMembership, WorkspaceRole,
    WorkspaceInvitation, InvitationStatus, WorkspaceAccessRequest,
    AccessRequestStatus, MembershipStatus, WorkspaceStatus
)
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
    WorkspaceAccessRequestForm
)


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

    context = {
        'title': 'Master Dashboard — Cross-Workspace Overview',
        'workspaces': workspaces,
        'total_workspaces': total_workspaces,
        'total_members': total_members,
        # Placeholder agile metrics for Phase 3 (connected to Tasks/Bugs in Phase 4/5)
        'total_tasks': 128,
        'total_bugs': 23,
        'total_meetings': 8,
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

    members = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).select_related('user', 'user__profile')[:6]

    total_members_count = workspace.memberships.filter(status=MembershipStatus.ACTIVE).count()

    context = {
        'title': f"{workspace.name} — Workspace Dashboard",
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'total_members_count': total_members_count,
        # Standardized sprint cards matching design mockup
        'active_tasks_count': 34,
        'open_bugs_count': 6,
        'upcoming_meetings_count': 3,
    }
    return render(request, 'workspaces/workspace_dashboard.html', context)


@login_required
def create_workspace(request):
    """
    Create a new workspace.
    The creator is automatically assigned the ADMIN role in WorkspaceMembership.
    """
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
    ).select_related('user', 'user__profile').order_by('-role', 'joined_at')

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
        'invitations': invitations,
        'invite_form': invite_form,
        'access_requests': access_requests,
        'roles': WorkspaceRole.choices,
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

            messages.success(
                request,
                f"Invitation sent to {email}! (Dev invitation link: {invite_url})"
            )
            return redirect('workspaces:team', slug=slug)
        else:
            messages.error(request, "Please provide a valid email address.")

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
    Update a member's role (Admin, Manager, Contributor).
    Guarded against demoting the sole administrator.
    """
    workspace = request.workspace
    member = get_object_or_404(WorkspaceMembership, id=member_id, workspace=workspace)

    if request.method == 'POST':
        form = WorkspaceMemberRoleForm(request.POST, member=member)
        if form.is_valid():
            new_role = form.cleaned_data['role']
            member.role = new_role
            member.save(update_fields=['role'])
            messages.success(
                request,
                f"Updated {member.user.full_name or member.user.email}'s role to {member.get_role_display()}."
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
    Update workspace name, description, and status.
    """
    workspace = request.workspace

    if request.method == 'POST':
        form = WorkspaceUpdateForm(request.POST, instance=workspace)
        if form.is_valid():
            form.save()
            messages.success(request, "Workspace settings updated successfully.")
            return redirect('workspaces:settings', slug=workspace.slug)
    else:
        form = WorkspaceUpdateForm(instance=workspace)

    return render(request, 'workspaces/settings.html', {
        'title': f"{workspace.name} — Workspace Settings",
        'workspace': workspace,
        'form': form,
    })


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


@workspace_member_required
def workspace_project_details(request, slug):
    """
    Detailed project summary view matching Panel 2 of the design reference.
    """
    workspace = request.workspace
    membership = request.membership

    context = {
        'title': f"{workspace.name} — Project Details — AetherSpace",
        'workspace': workspace,
        'membership': membership,
        'tech_stack': [
            'Python 3.12',
            'Django 5.x',
            'PostgreSQL',
            'Supabase Storage',
            'Tailwind CSS',
            'Alpine.js',
            'WebRTC',
        ],
        'total_members_count': workspace.memberships.filter(status=MembershipStatus.ACTIVE).count(),
        'active_tasks_count': 34,
        'open_bugs_count': 6,
        'completed_sprints': 4,
    }
    return render(request, 'workspaces/project_details.html', context)


@workspace_member_required
def workspace_chat(request, slug):
    """
    Workspace-scoped team communication launcher / placeholder.
    """
    workspace = request.workspace
    membership = request.membership

    return render(request, 'components/placeholder.html', {
        'module_title': f"{workspace.name} — Team Chat",
        'phase_badge': 'Phase 5 — Collaboration',
        'module_icon': 'chat',
        'module_description': f"Real-time team chat and topic channels scoped to '{workspace.name}'.",
        'empty_heading': f"Chat Hub for {workspace.name}",
        'empty_text': f"Channels (#general, #{workspace.slug}-dev), real-time direct messaging, and message pinning will arrive in Phase 5.",
        'features': [
            f"Dedicated #{workspace.slug}-general channel",
            'Real-time WebSocket message delivery',
            'Code snippet syntax highlighting',
            'File and image attachments via Supabase',
        ],
    })
