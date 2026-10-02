import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimerStatus(models.TextChoices):
    IDLE = 'IDLE', _('Idle')
    RUNNING = 'RUNNING', _('Running')
    PAUSED = 'PAUSED', _('Paused')
    COMPLETED = 'COMPLETED', _('Completed')


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
    last_resumed_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    accumulated_seconds = models.PositiveIntegerField(
        default=0,
        help_text=_("Total accumulated active running seconds (excluding paused intervals).")
    )
    duration_seconds = models.PositiveIntegerField(default=0, help_text=_("Total elapsed duration in seconds."))
    status = models.CharField(
        max_length=15,
        choices=TimerStatus.choices,
        default=TimerStatus.COMPLETED,
        db_index=True
    )
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
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['workspace', 'is_running']),
            models.Index(fields=['user', 'is_running']),
        ]

    def save(self, *args, **kwargs):
        if self.is_running:
            if self.status in [TimerStatus.COMPLETED, TimerStatus.IDLE]:
                self.status = TimerStatus.RUNNING
            if not self.last_resumed_at:
                self.last_resumed_at = self.started_at
        super().save(*args, **kwargs)

    def __str__(self):
        task_str = f" (#{self.task.task_code})" if self.task else ""
        return f"{self.user.email} - {self.duration_formatted}{task_str}"

    @property
    def current_duration_seconds(self):
        """
        Returns elapsed seconds, dynamically computing live duration if timer is running.
        Excludes paused intervals.
        """
        if self.status == TimerStatus.RUNNING or (self.is_running and self.status != TimerStatus.PAUSED):
            now = timezone.now()
            resumed_ref = self.last_resumed_at or self.started_at
            active_interval = max(0, int((now - resumed_ref).total_seconds()))
            return self.accumulated_seconds + active_interval
        elif self.status == TimerStatus.PAUSED:
            return self.accumulated_seconds
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

    def pause(self):
        """Pause running timer without finalizing. Preserves accumulated duration."""
        if self.status == TimerStatus.RUNNING or self.is_running:
            now = timezone.now()
            resumed_ref = self.last_resumed_at or self.started_at
            active_interval = max(0, int((now - resumed_ref).total_seconds()))
            self.accumulated_seconds += active_interval
            self.duration_seconds = self.accumulated_seconds
            self.paused_at = now
            self.status = TimerStatus.PAUSED
            self.is_running = False
            self.save(update_fields=['accumulated_seconds', 'duration_seconds', 'paused_at', 'status', 'is_running', 'updated_at'])
            return True
        return False

    def resume(self):
        """Resume a paused timer. Begins a new running interval from preserved accumulated duration."""
        if self.status == TimerStatus.PAUSED:
            now = timezone.now()
            self.last_resumed_at = now
            self.paused_at = None
            self.status = TimerStatus.RUNNING
            self.is_running = True
            self.save(update_fields=['last_resumed_at', 'paused_at', 'status', 'is_running', 'updated_at'])
            return True
        return False

    def stop(self):
        """Stop running or paused timer and finalize duration."""
        if self.status in [TimerStatus.RUNNING, TimerStatus.PAUSED] or self.is_running:
            now = timezone.now()
            if self.status == TimerStatus.RUNNING or self.is_running:
                resumed_ref = self.last_resumed_at or self.started_at
                active_interval = max(0, int((now - resumed_ref).total_seconds()))
                self.accumulated_seconds += active_interval
            self.ended_at = now
            self.duration_seconds = max(1, self.accumulated_seconds)
            self.status = TimerStatus.COMPLETED
            self.is_running = False
            self.save(update_fields=['ended_at', 'accumulated_seconds', 'duration_seconds', 'status', 'is_running', 'updated_at'])
            return True
        return False
