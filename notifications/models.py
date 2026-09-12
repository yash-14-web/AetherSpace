import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class NotificationCategory(models.TextChoices):
    TASK = 'TASK', _('Task')
    BUG = 'BUG', _('Bug')
    MENTION = 'MENTION', _('Mention')
    MEETING = 'MEETING', _('Meeting')
    FILE = 'FILE', _('File')
    WORKSPACE = 'WORKSPACE', _('Workspace')
    SYSTEM = 'SYSTEM', _('System')


class NotificationType(models.TextChoices):
    TASK_ASSIGNED = 'TASK_ASSIGNED', _('Task Assigned')
    TASK_STATUS_CHANGED = 'TASK_STATUS_CHANGED', _('Task Status Changed')
    TASK_DUE_SOON = 'TASK_DUE_SOON', _('Task Due Soon')
    BUG_REPORTED = 'BUG_REPORTED', _('Bug Reported')
    BUG_ASSIGNED = 'BUG_ASSIGNED', _('Bug Assigned')
    BUG_STATUS_CHANGED = 'BUG_STATUS_CHANGED', _('Bug Status Changed')
    CHAT_MENTION = 'CHAT_MENTION', _('Chat Mention')
    CHAT_DM = 'CHAT_DM', _('Direct Message')
    MEETING_INVITE = 'MEETING_INVITE', _('Meeting Invite')
    FILE_SHARED = 'FILE_SHARED', _('File Shared')
    ROLE_UPDATED = 'ROLE_UPDATED', _('Role Updated')
    GENERAL = 'GENERAL', _('General')


class Notification(models.Model):
    """
    Workspace-scoped and user-centric notification record.
    Supports task alerts, bug triage, chat mentions, meeting invitations, and file shares.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='notifications',
        null=True,
        blank=True,
        help_text=_("Workspace context where the event occurred, if applicable.")
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        help_text=_("The user who receives this notification.")
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        help_text=_("The user who triggered the notification, if applicable.")
    )
    category = models.CharField(
        max_length=20,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
        db_index=True
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
        db_index=True
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    action_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text=_("Internal URL to navigate to when the notification is clicked.")
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['workspace', 'recipient', 'category']),
            models.Index(fields=['recipient', 'category', 'is_read']),
        ]

    def __str__(self):
        return f"[{self.category}] {self.title} -> {self.recipient.email}"

    def mark_as_read(self):
        """Mark notification as read with timestamp."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_unread(self):
        """Toggle notification back to unread."""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at'])

    @property
    def category_color_classes(self):
        """Return theme-consistent Tailwind styling for category badge."""
        mapping = {
            NotificationCategory.TASK: {
                'bg': 'bg-blue-50 dark:bg-blue-950/50',
                'text': 'text-blue-600 dark:text-blue-400',
                'border': 'border-blue-200/60 dark:border-blue-900/40',
                'icon_bg': 'bg-blue-500',
            },
            NotificationCategory.BUG: {
                'bg': 'bg-rose-50 dark:bg-rose-950/50',
                'text': 'text-rose-600 dark:text-rose-400',
                'border': 'border-rose-200/60 dark:border-rose-900/40',
                'icon_bg': 'bg-rose-500',
            },
            NotificationCategory.MENTION: {
                'bg': 'bg-purple-50 dark:bg-purple-950/50',
                'text': 'text-purple-600 dark:text-purple-400',
                'border': 'border-purple-200/60 dark:border-purple-900/40',
                'icon_bg': 'bg-purple-500',
            },
            NotificationCategory.MEETING: {
                'bg': 'bg-indigo-50 dark:bg-indigo-950/50',
                'text': 'text-indigo-600 dark:text-indigo-400',
                'border': 'border-indigo-200/60 dark:border-indigo-900/40',
                'icon_bg': 'bg-indigo-500',
            },
            NotificationCategory.FILE: {
                'bg': 'bg-cyan-50 dark:bg-cyan-950/50',
                'text': 'text-cyan-600 dark:text-cyan-400',
                'border': 'border-cyan-200/60 dark:border-cyan-900/40',
                'icon_bg': 'bg-cyan-500',
            },
            NotificationCategory.WORKSPACE: {
                'bg': 'bg-emerald-50 dark:bg-emerald-950/50',
                'text': 'text-emerald-600 dark:text-emerald-400',
                'border': 'border-emerald-200/60 dark:border-emerald-900/40',
                'icon_bg': 'bg-emerald-500',
            },
            NotificationCategory.SYSTEM: {
                'bg': 'bg-slate-100 dark:bg-zinc-800',
                'text': 'text-slate-600 dark:text-zinc-300',
                'border': 'border-slate-200 dark:border-zinc-700',
                'icon_bg': 'bg-slate-500',
            },
        }
        return mapping.get(self.category, mapping[NotificationCategory.SYSTEM])
