import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeEntryType(models.TextChoices):
    TIMER = 'TIMER', _('Live Timer')
    MANUAL = 'MANUAL', _('Manual Entry')


class TimeEntry(models.Model):
    """
    Authoritative time tracking record.
    Connects elapsed sprint work to workspaces, contributors, and optional 6-digit tasks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='time_entries',
        db_index=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='time_entries',
        db_index=True
    )
    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='time_entries',
        db_index=True
    )
    description = models.CharField(max_length=255, blank=True, default='')
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0, help_text=_("Total elapsed duration in seconds."))
    is_running = models.BooleanField(default=False, db_index=True)
    entry_type = models.CharField(
        max_length=10,
        choices=TimeEntryType.choices,
        default=TimeEntryType.TIMER
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['workspace', 'user', '-started_at']),
            models.Index(fields=['workspace', 'is_running']),
            models.Index(fields=['user', 'is_running']),
        ]

    def __str__(self):
        task_str = f" (#{self.task.task_code})" if self.task else ""
        return f"{self.user.email} - {self.duration_formatted}{task_str}"

    @property
    def current_duration_seconds(self):
        """Returns elapsed seconds, dynamically computing live duration if timer is running."""
        if self.is_running:
            return max(0, int((timezone.now() - self.started_at).total_seconds()))
        return self.duration_seconds

    @property
    def duration_formatted(self):
        """Format seconds into readable string (e.g. 1h 45m or 25m)."""
        secs = self.current_duration_seconds
        hours = secs // 3600
        minutes = (secs % 3600) // 60
        remaining_secs = secs % 60

        if hours > 0:
            if minutes > 0:
                return f"{hours}h {minutes}m"
            return f"{hours}h"
        elif minutes > 0:
            return f"{minutes}m {remaining_secs}s" if remaining_secs > 0 else f"{minutes}m"
        return f"{remaining_secs}s"

    @property
    def hours_decimal(self):
        """Decimal hours representation (e.g. 1.75)."""
        return round(self.current_duration_seconds / 3600.0, 2)

    def stop(self):
        """Stop running timer and finalize duration."""
        if self.is_running:
            now = timezone.now()
            self.ended_at = now
            self.duration_seconds = max(1, int((now - self.started_at).total_seconds()))
            self.is_running = False
            self.save(update_fields=['ended_at', 'duration_seconds', 'is_running', 'updated_at'])
