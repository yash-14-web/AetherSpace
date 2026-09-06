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

    return {
        'user_workspaces': user_workspaces,
        'current_workspace': current_workspace,
        'current_membership': current_membership,
    }
