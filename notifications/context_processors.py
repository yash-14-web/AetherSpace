from .services import get_unread_count, get_user_notifications


def notifications_context(request):
    """
    Context processor providing unread notifications count and recent notifications
    to templates (specifically the global header bell and dropdown panel).
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'unread_notifications_count': 0,
            'header_recent_notifications': [],
        }

    current_workspace = getattr(request, 'workspace', None)

    unread_count = get_unread_count(request.user, workspace=current_workspace)
    recent_qs = get_user_notifications(request.user, workspace=current_workspace)[:6]

    return {
        'unread_notifications_count': unread_count,
        'header_recent_notifications': list(recent_qs),
    }
