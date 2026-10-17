import uuid
import hashlib
import re
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
        """
        Generate a deterministic, collision-resistant, and unguessable room name
        for Jitsi conferences, scoped by workspace and protected with a keyed hash.
        """
        clean_code = re.sub(r'[^a-zA-Z0-9]', '', str(self.meeting_code))
        clean_slug = re.sub(r'[^a-zA-Z0-9]', '', str(self.workspace.slug))
        salt_material = f"{self.id}_{self.meeting_code}_{settings.SECRET_KEY}".encode('utf-8')
        room_hash = hashlib.sha256(salt_material).hexdigest()[:16]
        return f"AetherSpace_{clean_slug}_{clean_code}_{room_hash}"

    @property
    def started_at(self):
        return self.actual_start

    @property
    def ended_at(self):
        return self.actual_end

    @property
    def scheduled_start_time(self):
        return self.scheduled_start

    @property
    def duration_seconds(self):
        if self.actual_start and self.actual_end:
            return int((self.actual_end - self.actual_start).total_seconds())
        elif self.actual_start and self.is_live:
            return int((timezone.now() - self.actual_start).total_seconds())
        return None

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
        return 0

    @property
    def duration_display(self):
        if not self.actual_start:
            if self.scheduled_start and self.scheduled_end:
                diff = self.scheduled_end - self.scheduled_start
                mins = max(1, int(diff.total_seconds() / 60))
                return f"{mins}m (est)"
            return "—"
        mins = self.duration_minutes
        if mins < 1:
            secs = self.duration_seconds or 0
            return f"{secs}s"
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
    is_hand_raised = models.BooleanField(default=False)
    is_removed = models.BooleanField(default=False)
    removed_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def duration_seconds(self):
        """Calculates attendance duration in seconds."""
        if self.joined_at and self.left_at:
            return max(0, int((self.left_at - self.joined_at).total_seconds()))
        elif self.joined_at and self.is_online:
            return max(0, int((timezone.now() - self.joined_at).total_seconds()))
        return 0


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


class CallStatus(models.TextChoices):
    RINGING = 'RINGING', _('Ringing')
    ACCEPTED = 'ACCEPTED', _('Accepted')
    CONNECTED = 'CONNECTED', _('Connected')
    DECLINED = 'DECLINED', _('Declined')
    MISSED = 'MISSED', _('Missed')
    CANCELLED = 'CANCELLED', _('Cancelled')
    ENDED = 'ENDED', _('Ended')
    FAILED = 'FAILED', _('Failed')


class CallEndedReason(models.TextChoices):
    NORMAL = 'NORMAL', _('Call completed normally')
    DECLINED = 'DECLINED', _('Declined by recipient')
    TIMEOUT = 'TIMEOUT', _('Ringing timed out')
    CANCELLED = 'CANCELLED', _('Cancelled by caller')
    BUSY = 'BUSY', _('Recipient busy in another call')
    FAILED = 'FAILED', _('Signaling or media connection failed')


class CallSession(models.Model):
    """
    Authoritative server-side call state record for 1-on-1 and in-chat calling.
    Enforces atomic lifecycle transitions: RINGING -> ACCEPTED -> CONNECTED -> ENDED,
    or terminal states: DECLINED, MISSED, CANCELLED, FAILED.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='call_sessions'
    )
    caller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='initiated_calls'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_calls'
    )
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='call_sessions'
    )
    conversation = models.ForeignKey(
        'chat.DirectMessageConversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_sessions'
    )
    channel = models.ForeignKey(
        'chat.Channel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='call_sessions'
    )
    call_mode = models.CharField(
        max_length=10,
        choices=[('AUDIO', 'Audio Call'), ('VIDEO', 'Video Call')],
        default='VIDEO'
    )
    status = models.CharField(
        max_length=20,
        choices=CallStatus.choices,
        default=CallStatus.RINGING,
        db_index=True
    )
    ended_reason = models.CharField(
        max_length=20,
        choices=CallEndedReason.choices,
        blank=True,
        default=''
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ringing_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    missed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status']),
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['caller', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        caller_name = self.caller.full_name or self.caller.email
        recipient_name = self.recipient.full_name or self.recipient.email
        return f"Call {self.id}: {caller_name} -> {recipient_name} ({self.get_status_display()})"

    @property
    def is_ringing(self):
        return self.status == CallStatus.RINGING

    @property
    def is_active(self):
        return self.status in (CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED)

    @property
    def is_terminal(self):
        return self.status in (CallStatus.DECLINED, CallStatus.MISSED, CallStatus.CANCELLED, CallStatus.ENDED, CallStatus.FAILED)

    def can_transition_to(self, target_status):
        """Validate state machine invariants."""
        valid_transitions = {
            CallStatus.RINGING: [CallStatus.ACCEPTED, CallStatus.DECLINED, CallStatus.CANCELLED, CallStatus.MISSED, CallStatus.FAILED],
            CallStatus.ACCEPTED: [CallStatus.CONNECTED, CallStatus.ENDED, CallStatus.FAILED],
            CallStatus.CONNECTED: [CallStatus.ENDED, CallStatus.FAILED],
            CallStatus.DECLINED: [],
            CallStatus.MISSED: [],
            CallStatus.CANCELLED: [],
            CallStatus.ENDED: [],
            CallStatus.FAILED: [],
        }
        return target_status in valid_transitions.get(self.status, [])

    def accept(self, user):
        """Recipient accepts the incoming call."""
        if user.id != self.recipient_id:
            raise PermissionError("Only the designated call recipient can accept this call.")
        if not self.can_transition_to(CallStatus.ACCEPTED):
            return False, f"Cannot accept call in status '{self.status}'"
        
        self.status = CallStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=['status', 'accepted_at'])
        return True, "Call accepted"

    def decline(self, user, reason=CallEndedReason.DECLINED):
        """Recipient declines the incoming call."""
        if user.id != self.recipient_id:
            raise PermissionError("Only the designated call recipient can decline this call.")
        if not self.can_transition_to(CallStatus.DECLINED):
            return False, f"Cannot decline call in status '{self.status}'"

        self.status = CallStatus.DECLINED
        self.ended_at = timezone.now()
        self.ended_reason = reason
        self.save(update_fields=['status', 'ended_at', 'ended_reason'])
        return True, "Call declined"

    def cancel(self, user):
        """Caller cancels an unanswered call."""
        if user.id != self.caller_id:
            raise PermissionError("Only the initiating caller can cancel this call.")
        if not self.can_transition_to(CallStatus.CANCELLED):
            return False, f"Cannot cancel call in status '{self.status}'"

        self.status = CallStatus.CANCELLED
        self.ended_at = timezone.now()
        self.ended_reason = CallEndedReason.CANCELLED
        self.save(update_fields=['status', 'ended_at', 'ended_reason'])
        return True, "Call cancelled"

    def mark_missed(self):
        """System/timeout marks call as missed if unanswered."""
        if not self.can_transition_to(CallStatus.MISSED):
            return False, f"Cannot mark missed in status '{self.status}'"

        self.status = CallStatus.MISSED
        self.missed_at = timezone.now()
        self.ended_at = self.missed_at
        self.ended_reason = CallEndedReason.TIMEOUT
        self.save(update_fields=['status', 'missed_at', 'ended_at', 'ended_reason'])
        return True, "Call marked missed"

    def mark_connected(self, user=None):
        """Both peers established media or joined room."""
        if self.status == CallStatus.ACCEPTED:
            self.status = CallStatus.CONNECTED
            self.connected_at = timezone.now()
            self.save(update_fields=['status', 'connected_at'])
            return True, "Call connected"
        return False, f"Cannot connect call from '{self.status}'"

    def end(self, user, reason=CallEndedReason.NORMAL):
        """Either participant ends the call."""
        if user.id not in (self.caller_id, self.recipient_id):
            raise PermissionError("Only participants can end this call.")
        if self.is_terminal:
            return False, "Call is already ended"

        self.status = CallStatus.ENDED
        self.ended_at = timezone.now()
        self.ended_reason = reason
        self.save(update_fields=['status', 'ended_at', 'ended_reason'])
        return True, "Call ended"

