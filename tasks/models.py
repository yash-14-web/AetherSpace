import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class TaskStatus(models.TextChoices):
    TODO = 'TODO', _('To Do')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    CODE_REVIEW = 'CODE_REVIEW', _('Code Review')
    TESTING = 'TESTING', _('Testing')
    DONE = 'DONE', _('Done')


class TaskPriority(models.TextChoices):
    LOW = 'LOW', _('Low')
    MEDIUM = 'MEDIUM', _('Medium')
    HIGH = 'HIGH', _('High')
    URGENT = 'URGENT', _('Urgent')


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text=_("Human-facing 6-digit task identifier, e.g. 619347")
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.TODO,
        db_index=True
    )
    priority = models.CharField(
        max_length=20,
        choices=TaskPriority.choices,
        default=TaskPriority.MEDIUM,
        db_index=True
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_tasks'
    )
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    sprint = models.CharField(max_length=50, blank=True, default='Sprint 01')
    tags = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', 'priority']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['task_code']),
        ]

    def __str__(self):
        return f"T-{self.task_code} {self.title}"

    @property
    def display_code(self):
        return f"T-{self.task_code}"

    @property
    def is_overdue(self):
        if self.due_date and self.status != TaskStatus.DONE:
            from django.utils import timezone
            return self.due_date < timezone.now().date()
        return False


class TaskActivity(models.Model):
    class Action(models.TextChoices):
        CREATED = 'CREATED', _('Created')
        STATUS_CHANGED = 'STATUS_CHANGED', _('Status Changed')
        ASSIGNED = 'ASSIGNED', _('Assigned')
        PRIORITY_CHANGED = 'PRIORITY_CHANGED', _('Priority Changed')
        UPDATED = 'UPDATED', _('Updated')
        COMMENTED = 'COMMENTED', _('Commented')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_activities'
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
        verbose_name_plural = "Task activities"

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "System"
        return f"{actor_name} {self.get_action_display()} on #{self.task.task_code}"
