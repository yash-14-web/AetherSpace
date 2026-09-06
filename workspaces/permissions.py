from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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
            login_url = reverse('accounts:login')
            return redirect(f"{login_url}?next={request.path}")

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
            login_url = reverse('accounts:login')
            return redirect(f"{login_url}?next={request.path}")

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
            login_url = reverse('accounts:login')
            return redirect(f"{login_url}?next={request.path}")

        workspace, membership = get_workspace_and_membership(request.user, slug)

        if not membership or not membership.can_manage_content:
            raise PermissionDenied(
                "Workspace Manager or Admin privileges are required to perform this action."
            )

        request.workspace = workspace
        request.membership = membership
        return view_func(request, slug, *args, **kwargs)

    return _wrapped_view
