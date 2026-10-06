from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from core.utils import redirect_to_login_with_next
from .models import Workspace, WorkspaceMembership, MembershipStatus, WorkspaceRole


def get_workspace_and_membership(user, slug):
    """
    Helper to fetch a workspace and user's active membership.
    Returns (workspace, membership). If user is not an active member,
    membership will be None unless the user has global platform admin privileges.
    """
    workspace = get_object_or_404(Workspace, slug=slug)

    if not user.is_authenticated:
        return workspace, None

    # Global platform admins / superusers have full administrative access across all workspaces
    if user.is_superuser or getattr(user, 'is_admin_role', False):
        membership = workspace.memberships.filter(user=user).first()
        if not membership:
            # Synthetic membership for platform admin view
            membership = WorkspaceMembership(
                workspace=workspace,
                user=user,
                role=WorkspaceRole.ADMIN,
                status=MembershipStatus.ACTIVE
            )
        return workspace, membership

    membership = workspace.memberships.filter(
        user=user,
        status=MembershipStatus.ACTIVE
    ).first()

    return workspace, membership


def workspace_member_required(view_func):
    """
    Decorator for views that require active membership in the workspace.
    Raises PermissionDenied (403) if the user is authenticated but not a member.
    Attaches `request.workspace` and `request.membership` to the request.
    """
    @wraps(view_func)
    def _wrapped_view(request, slug, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login_with_next(request)

        workspace, membership = get_workspace_and_membership(request.user, slug)

        if not membership:
            # User is authenticated but not permitted in this workspace -> 403
            raise PermissionDenied(
                f"You do not have access to the '{workspace.name}' workspace. Please request access."
            )

        request.workspace = workspace
        request.membership = membership
        return view_func(request, slug, *args, **kwargs)

    return _wrapped_view


def workspace_admin_required(view_func):
    """
    Decorator for views that require ADMIN role in the workspace.
    Raises PermissionDenied (403) if member is only Manager or Contributor.
    """
    @wraps(view_func)
    def _wrapped_view(request, slug, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login_with_next(request)

        workspace, membership = get_workspace_and_membership(request.user, slug)

        if not membership or not membership.can_manage_workspace:
            raise PermissionDenied(
                "Workspace administrator privileges are required to perform this action."
            )

        request.workspace = workspace
        request.membership = membership
        return view_func(request, slug, *args, **kwargs)

    return _wrapped_view


def workspace_manager_required(view_func):
    """
    Decorator for views that require at least MANAGER role in the workspace.
    """
    @wraps(view_func)
    def _wrapped_view(request, slug, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login_with_next(request)

        workspace, membership = get_workspace_and_membership(request.user, slug)

        if not membership or not membership.can_manage_content:
            raise PermissionDenied(
                "Workspace Manager or Admin privileges are required to perform this action."
            )

        request.workspace = workspace
        request.membership = membership
        return view_func(request, slug, *args, **kwargs)

    return _wrapped_view


def can_user_perform_action(user, workspace, action, target_resource_id=None):
    """
    Evaluates whether a user is authorized to perform an action in a workspace.
    Authoritatively checks:
    1. Superuser / Platform Admin
    2. Active TemporaryAccessGrant for this specific action & workspace
    3. Active WorkspaceMembership role permissions
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, 'is_admin_role', False):
        return True

    # Check active temporary grant first
    from .models import TemporaryAccessGrant
    if TemporaryAccessGrant.has_active_grant(user, workspace, action, target_resource_id):
        return True

    # Check workspace membership
    membership = workspace.memberships.filter(user=user, status=MembershipStatus.ACTIVE).first() if workspace else None
    if not membership:
        return False

    if action in ['bug.create', 'file.upload', 'calendar.create', 'meeting.create']:
        return True
    elif action in ['task.create', 'task.delete', 'bug.delete', 'sprint.manage']:
        return membership.role in [WorkspaceRole.ADMIN, WorkspaceRole.MANAGER]
    elif action in ['task.edit', 'bug.edit']:
        return True
    elif action in ['workspace.manage', 'member.manage', 'workspace.delete']:
        return membership.role == WorkspaceRole.ADMIN

    return False

