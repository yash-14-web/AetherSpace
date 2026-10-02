from .models import WorkspaceMembership, MembershipStatus


def workspace_context(request):
    """
    Context processor providing the user's accessible workspaces,
    active workspace context, and current membership across templates.
    """
    if not request.user.is_authenticated:
        return {
            'user_workspaces': [],
            'current_workspace': None,
            'current_membership': None,
        }

    memberships = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE,
        workspace__status='ACTIVE'
    ).select_related('workspace')

    user_workspaces = [m.workspace for m in memberships]

    current_workspace = getattr(request, 'workspace', None)
    current_membership = getattr(request, 'membership', None)

    # Active fallback if request is outside a workspace-specific route
    active_workspace = current_workspace or (user_workspaces[0] if user_workspaces else None)
    active_membership = current_membership
    if not active_membership and active_workspace:
        active_membership = next((m for m in memberships if m.workspace_id == active_workspace.id), None)

    can_create_task = False
    if active_workspace:
        from .permissions import can_user_perform_action
        can_create_task = can_user_perform_action(request.user, active_workspace, 'task.create')

    return {
        'user_workspaces': user_workspaces,
        'current_workspace': current_workspace,
        'current_membership': current_membership,
        'active_workspace': active_workspace,
        'active_membership': active_membership,
        'can_create_task': can_create_task,
    }
