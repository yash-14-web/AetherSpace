import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class MeetingType(models.TextChoices):
    INSTANT = 'INSTANT', _('Instant Meeting')
    STANDUP = 'STANDUP', _('Daily Standup')
    SPRINT_PLANNING = 'SPRINT_PLANNING', _('Sprint Planning')
    RETROSPECTIVE = 'RETROSPECTIVE', _('Retrospective')
    CHAT_CALL = 'CHAT_CALL', _('Chat Call')
    GENERAL = 'GENERAL', _('General Discussion')


class MeetingStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', _('Scheduled')
    LIVE = 'LIVE', _('Live Now')
    ENDED = 'ENDED', _('Ended')
    CANCELLED = 'CANCELLED', _('Cancelled')


class ParticipantRole(models.TextChoices):
    HOST = 'HOST', _('Host')
    ATTENDEE = 'ATTENDEE', _('Attendee')


class Meeting(models.Model):
    """
    Workspace-scoped meeting record supporting instant calls, scheduled conferences,
    and in-chat video/audio calls with Jitsi/WebRTC room isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='meetings'
    )
    meeting_code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_("Human-facing identifier, e.g. meet-k7xp-2m9q")
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hosted_meetings'
    )
    meeting_type = models.CharField(
        max_length=30,
        choices=MeetingType.choices,
        default=MeetingType.GENERAL,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=MeetingStatus.choices,
        default=MeetingStatus.SCHEDULED,
        db_index=True
    )
    scheduled_start = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    external_room_url = models.URLField(blank=True, default='')
    passcode = models.CharField(max_length=20, blank=True, default='')
    is_audio_only = models.BooleanField(default=False)
    channel = models.ForeignKey(
        'chat.Channel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='meetings'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['workspace', 'scheduled_start']),
            models.Index(fields=['meeting_code']),
            models.Index(fields=['workspace', 'created_at']),
        ]

    def __str__(self):
        return f"{self.meeting_code} — {self.title} ({self.get_status_display()})"

    @property
    def is_live(self):
        return self.status == MeetingStatus.LIVE

    @property
    def is_scheduled(self):
        return self.status == MeetingStatus.SCHEDULED

    @property
    def is_ended(self):
        return self.status == MeetingStatus.ENDED

    @property
    def is_cancelled(self):
        return self.status == MeetingStatus.CANCELLED

    @property
    def jitsi_room_name(self):
        # Format safe room name for public or self-hosted Jitsi instance
        clean_code = self.meeting_code.replace('-', '_')
        return f"AetherSpace_{self.workspace.slug}_{clean_code}"

    @property
    def duration_minutes(self):
        if self.actual_start and self.actual_end:
            diff = self.actual_end - self.actual_start
            return max(1, int(diff.total_seconds() / 60))
        elif self.actual_start and self.is_live:
            diff = timezone.now() - self.actual_start
            return max(1, int(diff.total_seconds() / 60))
        elif self.scheduled_start and self.scheduled_end:
            diff = self.scheduled_end - self.scheduled_start
            return max(1, int(diff.total_seconds() / 60))
        return 30

    @property
    def duration_display(self):
        mins = self.duration_minutes
        if mins < 60:
            return f"{mins}m"
        hours = mins // 60
        rem = mins % 60
        return f"{hours}h {rem}m" if rem else f"{hours}h"

    @property
    def active_participants_count(self):
        return self.participants.filter(left_at__isnull=True).count()

    @property
    def total_participants_count(self):
        return self.participants.values('user').distinct().count()


class MeetingParticipant(models.Model):
    """
    Session audit log for each user who joins a meeting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meeting_participations'
    )
    role = models.CharField(
        max_length=20,
        choices=ParticipantRole.choices,
        default=ParticipantRole.ATTENDEE
    )
    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-joined_at']
        indexes = [
            models.Index(fields=['meeting', 'left_at']),
        ]

    def __str__(self):
        user_name = self.user.full_name or self.user.email
        return f"{user_name} in {self.meeting.meeting_code} ({self.get_role_display()})"

    @property
    def is_online(self):
        return self.left_at is None


class MeetingInvite(models.Model):
    """
    Invitee record for scheduled future meetings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='invites'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meeting_invites'
    )
    status = models.CharField(max_length=20, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('meeting', 'user')

    def __str__(self):
        user_name = self.user.full_name or self.user.email
        return f"Invite for {user_name} to {self.meeting.title}"
