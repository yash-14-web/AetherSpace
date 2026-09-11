import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CalendarEventType(models.TextChoices):
    MEETING = 'MEETING', _('Meeting')
    MILESTONE = 'MILESTONE', _('Milestone')
    TASK_DEADLINE = 'TASK_DEADLINE', _('Task Deadline')
    WORK_SESSION = 'WORK_SESSION', _('Work Session')
    GENERAL = 'GENERAL', _('General Event')


class CalendarCategory(models.TextChoices):
    WORKSPACE = 'WORKSPACE', _('Workspace Calendar')
    PERSONAL = 'PERSONAL', _('My Calendar')


class EventStatus(models.TextChoices):
    UPCOMING = 'UPCOMING', _('Upcoming')
    IN_PROGRESS = 'IN_PROGRESS', _('In Progress')
    COMPLETED = 'COMPLETED', _('Completed')
    CANCELLED = 'CANCELLED', _('Cancelled')


class EventRepeat(models.TextChoices):
    NONE = 'NONE', _('Does not repeat')
    DAILY = 'DAILY', _('Daily')
    WEEKLY = 'WEEKLY', _('Weekly')
    MONTHLY = 'MONTHLY', _('Monthly')


class AttendeeStatus(models.TextChoices):
    INVITED = 'INVITED', _('Invited')
    ACCEPTED = 'ACCEPTED', _('Accepted')
    DECLINED = 'DECLINED', _('Declined')
    TENTATIVE = 'TENTATIVE', _('Tentative')


class CalendarEvent(models.Model):
    """
    Workspace-scoped calendar events supporting standalone events, milestones,
    work sessions, and cross-entity linkages to Tasks, Bugs, and Meetings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='calendar_events'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    event_type = models.CharField(
        max_length=30,
        choices=CalendarEventType.choices,
        default=CalendarEventType.GENERAL,
        db_index=True
    )
    calendar_category = models.CharField(
        max_length=20,
        choices=CalendarCategory.choices,
        default=CalendarCategory.WORKSPACE
    )
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    is_all_day = models.BooleanField(default=False)
    repeat = models.CharField(
        max_length=20,
        choices=EventRepeat.choices,
        default=EventRepeat.NONE
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.UPCOMING,
        db_index=True
    )
    location = models.CharField(max_length=255, blank=True, default='')
    meeting_link = models.URLField(blank=True, default='')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_calendar_events'
    )

    # Cross-entity references per docs/03_DATABASE_SCHEMA.md
    linked_task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
        help_text=_("Optional task deadline or story this event is associated with.")
    )
    linked_bug = models.ForeignKey(
        'bugs.Bug',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
        help_text=_("Optional bug fix deadline or triage this event is associated with.")
    )
    linked_meeting = models.ForeignKey(
        'meetings.Meeting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events',
        help_text=_("Optional video/audio conference linked to this calendar event.")
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_at']
        indexes = [
            models.Index(fields=['workspace', 'start_at']),
            models.Index(fields=['workspace', 'event_type']),
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['created_by', 'start_at']),
        ]

    def __str__(self):
        return f"{self.title} ({self.workspace.name})"

    @property
    def duration_display(self):
        """Human-readable duration of the event."""
        if self.is_all_day:
            return "All Day"
        if not self.start_at or not self.end_at:
            return "—"
        total_seconds = int((self.end_at - self.start_at).total_seconds())
        if total_seconds < 0:
            return "—"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours > 0 and minutes > 0:
            return f"{hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h"
        elif minutes > 0:
            return f"{minutes}m"
        return "< 1m"

    @property
    def is_past(self):
        return self.end_at < timezone.now()

    @property
    def is_live_now(self):
        now = timezone.now()
        return self.start_at <= now <= self.end_at


class CalendarEventAttendee(models.Model):
    """
    Roster of invitees and attendees for a calendar event.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        CalendarEvent,
        on_delete=models.CASCADE,
        related_name='attendees'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='calendar_attendances'
    )
    status = models.CharField(
        max_length=20,
        choices=AttendeeStatus.choices,
        default=AttendeeStatus.INVITED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.email} - {self.event.title} ({self.status})"
