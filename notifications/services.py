import logging
from django.db.models import Count, Q
from django.utils import timezone
from .models import Notification, NotificationCategory, NotificationType

logger = logging.getLogger(__name__)


def create_notification(
    recipient,
    category,
    notification_type,
    title,
    body='',
    workspace=None,
    actor=None,
    action_url=''
):
    """
    Safely creates a notification for a recipient.
    Suppresses self-notifications when the actor is the recipient.
    """
    if not recipient:
        return None

    # Do not notify user of their own actions
    if actor and recipient and actor.id == recipient.id:
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            category=category,
            notification_type=notification_type,
            title=title,
            body=body,
            workspace=workspace,
            actor=actor,
            action_url=action_url,
            is_read=False
        )
        return notification
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        return None


def mark_as_read(notification_id, user):
    """
    Marks a single notification as read if owned by the user.
    """
    try:
        notification = Notification.objects.get(id=notification_id, recipient=user)
        notification.mark_as_read()
        return True
    except Notification.DoesNotExist:
        return False


def mark_as_unread(notification_id, user):
    """
    Marks a single notification as unread if owned by the user.
    """
    try:
        notification = Notification.objects.get(id=notification_id, recipient=user)
        notification.mark_as_unread()
        return True
    except Notification.DoesNotExist:
        return False


def mark_all_as_read(user, workspace=None, category=None):
    """
    Marks all matching unread notifications as read in a single batch update.
    """
    qs = Notification.objects.filter(recipient=user, is_read=False)
    if workspace:
        qs = qs.filter(workspace=workspace)
    if category and category != 'ALL':
        qs = qs.filter(category=category)

    updated_count = qs.update(is_read=True, read_at=timezone.now())
    return updated_count


def delete_notification(notification_id, user):
    """
    Deletes a notification if owned by the user.
    """
    try:
        notification = Notification.objects.get(id=notification_id, recipient=user)
        notification.delete()
        return True
    except Notification.DoesNotExist:
        return False


def get_user_notifications(user, workspace=None, category=None, unread_only=False, search_query=None):
    """
    Retrieves filtered notifications for a user with optimized related object selection.
    """
    qs = Notification.objects.filter(recipient=user).select_related('actor', 'workspace')

    if workspace:
        qs = qs.filter(workspace=workspace)

    if unread_only:
        qs = qs.filter(is_read=False)

    if category and category != 'ALL':
        qs = qs.filter(category=category)

    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query) |
            Q(body__icontains=search_query)
        )

    return qs.order_by('-created_at')


def get_unread_count(user, workspace=None):
    """
    Returns the count of unread notifications for badge display.
    """
    if not user or not user.is_authenticated:
        return 0
    qs = Notification.objects.filter(recipient=user, is_read=False)
    if workspace:
        qs = qs.filter(workspace=workspace)
    return qs.count()


def get_notification_metrics(user, workspace=None):
    """
    Computes summary metrics across notification categories for tab badges and dashboard cards.
    """
    if not user or not user.is_authenticated:
        return {
            'total': 0,
            'unread': 0,
            'tasks': 0,
            'bugs': 0,
            'mentions': 0,
            'meetings': 0,
            'files': 0,
        }

    base_qs = Notification.objects.filter(recipient=user)
    if workspace:
        base_qs = base_qs.filter(workspace=workspace)

    aggregates = base_qs.aggregate(
        total=Count('id'),
        unread=Count('id', filter=Q(is_read=False)),
        tasks=Count('id', filter=Q(category=NotificationCategory.TASK)),
        bugs=Count('id', filter=Q(category=NotificationCategory.BUG)),
        mentions=Count('id', filter=Q(category=NotificationCategory.MENTION)),
        meetings=Count('id', filter=Q(category=NotificationCategory.MEETING)),
        files=Count('id', filter=Q(category=NotificationCategory.FILE)),
    )

    return {
        'total': aggregates['total'] or 0,
        'unread': aggregates['unread'] or 0,
        'tasks': aggregates['tasks'] or 0,
        'bugs': aggregates['bugs'] or 0,
        'mentions': aggregates['mentions'] or 0,
        'meetings': aggregates['meetings'] or 0,
        'files': aggregates['files'] or 0,
    }
