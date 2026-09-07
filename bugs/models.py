import uuid
import secrets
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class BugStatus(models.TextChoices):
    OPEN = 'OPEN', _('Open')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    RESOLVED = 'RESOLVED', _('Resolved')
    CLOSED = 'CLOSED', _('Closed')


class BugPriority(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    CRITICAL = 'CRITICAL', _('Critical')


class BugSeverity(models.TextChoices):
    SEV1 = 'SEV1', _('Sev 1 - Critical / Blocker')
    SEV2 = 'SEV2', _('Sev 2 - Major')
    SEV3 = 'SEV3', _('Sev 3 - Moderate')
    SEV4 = 'SEV4', _('Sev 4 - Minor')


class BugEnvironment(models.TextChoices):
    PRODUCTION = 'PRODUCTION', _('Production')
    STAGING = 'STAGING', _('Staging')
    DEVELOPMENT = 'DEVELOPMENT', _('Development')
    QA = 'QA', _('QA / Testing')


class BugModule(models.TextChoices):
    AUTHENTICATION = 'Authentication', _('Authentication')
    DASHBOARD = 'Dashboard', _('Dashboard')
    TASKS = 'Tasks', _('Tasks')
    BUGS = 'Bug Tracking', _('Bug Tracking')
    FILES = 'Files', _('Files & Storage')
    MEETINGS = 'Meetings', _('Meet Hub')
    CHAT = 'Chat', _('Chat & Messaging')
    REPORTS = 'Reports', _('Reports')
    UI_UX = 'UI/UX', _('UI / UX')
    SETTINGS = 'Settings', _('Settings')
    OTHER = 'Other', _('Other')


class Bug(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bug_code = models.CharField(
        max_length=12,
        unique=True,
        db_index=True,
        help_text=_("Human-facing 6-digit bug identifier with prefix, e.g. B-882316")
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='bugs'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    steps_to_reproduce = models.TextField(
        blank=True,
        default='',
        help_text=_("Numbered steps to reproduce the issue")
    )
    expected_result = models.TextField(blank=True, default='')
    actual_result = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=BugStatus.choices,
        default=BugStatus.OPEN,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=BugPriority.choices,
        default=BugPriority.MEDIUM,
        db_index=True
    )
    severity = models.CharField(
        max_length=20,
        choices=BugSeverity.choices,
        default=BugSeverity.SEV3,
        db_index=True
    )
    environment = models.CharField(
        max_length=20,
        choices=BugEnvironment.choices,
        default=BugEnvironment.STAGING
    )
    module = models.CharField(
        max_length=50,
        choices=BugModule.choices,
        default=BugModule.OTHER
    )
    browser_device = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text=_("e.g. Chrome 124 / Windows 11")
    )
    sprint = models.CharField(max_length=50, blank=True, default='Sprint 01')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_bugs'
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_bugs'
    )
    due_date = models.DateField(null=True, blank=True)
    labels = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text=_("Comma-separated labels, e.g. login, server-error")
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', 'priority']),
            models.Index(fields=['workspace', 'severity']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['bug_code']),
        ]

    def __str__(self):
        return f"{self.bug_code} {self.title}"

    @property
    def is_overdue(self):
        if self.due_date and self.status not in (BugStatus.RESOLVED, BugStatus.CLOSED):
            from django.utils import timezone
            return self.due_date < timezone.now().date()
        return False

    @property
    def label_list(self):
        if not self.labels:
            return []
        return [lbl.strip() for lbl in self.labels.split(',') if lbl.strip()]


class BugActivity(models.Model):
    class Action(models.TextChoices):
        CREATED = 'CREATED', _('Created')
        STATUS_CHANGED = 'STATUS_CHANGED', _('Status Changed')
        ASSIGNED = 'ASSIGNED', _('Assigned')
        PRIORITY_CHANGED = 'PRIORITY_CHANGED', _('Priority Changed')
        SEVERITY_CHANGED = 'SEVERITY_CHANGED', _('Severity Changed')
        COMMENTED = 'COMMENTED', _('Commented')
        ATTACHMENT_ADDED = 'ATTACHMENT_ADDED', _('Attachment Added')
        UPDATED = 'UPDATED', _('Updated')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bug = models.ForeignKey(
        Bug,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bug_activities'
    )
    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        default=Action.UPDATED
    )
    old_value = models.CharField(max_length=255, blank=True, default='')
    new_value = models.CharField(max_length=255, blank=True, default='')
    message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Bug activities"

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "System"
        return f"{actor_name} {self.get_action_display()} on {self.bug.bug_code}"


class BugComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bug = models.ForeignKey(
        Bug,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bug_comments'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        author_name = self.author.full_name if self.author else "Anonymous"
        return f"Comment by {author_name} on {self.bug.bug_code}"
