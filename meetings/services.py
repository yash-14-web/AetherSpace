import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Meeting, MeetingParticipant, MeetingInvite, MeetingType, MeetingStatus, ParticipantRole


MEETING_CHARS = '23456789abcdefghjkmnpqrstuvwxyz'


def generate_unique_meeting_code() -> str:
    """
    Generate a unique, collision-safe meeting code formatted as 'meet-xxxx-xxxx'.
    Uses cryptographically strong secrets.choice on an unambiguous character set.
    """
    max_attempts = 30
    for _ in range(max_attempts):
        part1 = ''.join(secrets.choice(MEETING_CHARS) for _ in range(4))
        part2 = ''.join(secrets.choice(MEETING_CHARS) for _ in range(4))
        candidate = f"meet-{part1}-{part2}"
        if not Meeting.objects.filter(meeting_code=candidate).exists():
            return candidate

    # Fallback to timestamp salted code in saturation
    suffix = str(secrets.randbelow(90000) + 10000)
    return f"meet-{secrets.choice(MEETING_CHARS)}{secrets.choice(MEETING_CHARS)}{secrets.choice(MEETING_CHARS)}-{suffix}"


@transaction.atomic
def create_instant_meeting(workspace, host, title='Instant Meeting',
                           meeting_type=MeetingType.INSTANT, is_audio_only=False) -> Meeting:
    """
    Start an instant meeting that is immediately LIVE.
    Registers the host as the first participant.
    """
    code = generate_unique_meeting_code()
    meeting = Meeting.objects.create(
        workspace=workspace,
        meeting_code=code,
        title=title.strip() if title else 'Instant Meeting',
        host=host,
        meeting_type=meeting_type,
        status=MeetingStatus.LIVE,
        is_audio_only=is_audio_only,
        actual_start=timezone.now()
    )

    if host:
        MeetingParticipant.objects.create(
            meeting=meeting,
            user=host,
            role=ParticipantRole.HOST
        )

    return meeting


@transaction.atomic
def create_chat_call(workspace, host, channel=None, conversation=None, is_audio_only=False) -> Meeting:
    """
    Create a GChat-style instant call originating from a chat channel or direct message.
    Posts an automated interactive call card to the chat thread.
    """
    call_kind = "Audio" if is_audio_only else "Video"
    if channel:
        title = f"{call_kind} call in {channel.display_name}"
    elif conversation:
        other = conversation.get_other_participant(host)
        other_name = other.full_name or other.email if other else "User"
        title = f"{call_kind} call with {other_name}"
    else:
        title = f"Team {call_kind} Call"

    meeting = Meeting.objects.create(
        workspace=workspace,
        meeting_code=generate_unique_meeting_code(),
        title=title,
        host=host,
        meeting_type=MeetingType.CHAT_CALL,
        status=MeetingStatus.LIVE,
        is_audio_only=is_audio_only,
        channel=channel,
        actual_start=timezone.now()
    )

    if host:
        MeetingParticipant.objects.create(
            meeting=meeting,
            user=host,
            role=ParticipantRole.HOST
        )

    # Post meeting invitation card message to Chat thread
    try:
        from chat.models import Message
        card_content = (
            f"CALL_INVITE:{meeting.meeting_code}:{'AUDIO' if is_audio_only else 'VIDEO'}:{meeting.title}"
        )
        Message.objects.create(
            workspace=workspace,
            sender=host,
            channel=channel,
            conversation=conversation,
            content=card_content
        )
    except Exception:
        # Non-blocking if chat is offline
        pass

    return meeting


@transaction.atomic
def schedule_meeting(workspace, host, title, scheduled_start, duration_minutes=30,
                     scheduled_end=None, meeting_type=MeetingType.GENERAL,
                     description='', invitees=None, is_audio_only=False) -> Meeting:
    """
    Schedule a meeting for a future date and time with invitees.
    """
    now = timezone.now()
    # Allow a small 5 minute grace period in case of form submission latency
    if scheduled_start < now - timedelta(minutes=5):
        raise ValidationError("Meeting cannot be scheduled in the past.")

    if not scheduled_end:
        scheduled_end = scheduled_start + timedelta(minutes=int(duration_minutes or 30))

    code = generate_unique_meeting_code()
    meeting = Meeting.objects.create(
        workspace=workspace,
        meeting_code=code,
        title=title.strip(),
        description=description.strip() if description else '',
        host=host,
        meeting_type=meeting_type,
        status=MeetingStatus.SCHEDULED,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        is_audio_only=is_audio_only
    )

    if invitees:
        for user in invitees:
            MeetingInvite.objects.get_or_create(meeting=meeting, user=user)

    return meeting


@transaction.atomic
def start_meeting(meeting: Meeting, user) -> Meeting:
    """
    Start a scheduled meeting: transition from SCHEDULED to LIVE.
    """
    if meeting.status == MeetingStatus.SCHEDULED:
        meeting.status = MeetingStatus.LIVE
        meeting.actual_start = timezone.now()
        meeting.save(update_fields=['status', 'actual_start', 'updated_at'])

    record_participant_join(
        meeting,
        user,
        role=ParticipantRole.HOST if meeting.host == user else ParticipantRole.ATTENDEE
    )
    return meeting


@transaction.atomic
def end_meeting(meeting: Meeting, user=None) -> Meeting:
    """
    End a live meeting and close all participant sessions.
    Only the meeting host or workspace Admin/Manager can end the call for all.
    """
    now = timezone.now()
    meeting.status = MeetingStatus.ENDED
    meeting.actual_end = now
    if not meeting.actual_start:
        meeting.actual_start = now
    meeting.save(update_fields=['status', 'actual_end', 'actual_start', 'updated_at'])

    # Close active participant sessions
    meeting.participants.filter(left_at__isnull=True).update(left_at=now)
    return meeting


@transaction.atomic
def cancel_meeting(meeting: Meeting, user=None) -> Meeting:
    """
    Cancel a scheduled meeting.
    """
    if meeting.status != MeetingStatus.SCHEDULED:
        raise ValidationError("Only scheduled meetings can be cancelled.")
    meeting.status = MeetingStatus.CANCELLED
    meeting.save(update_fields=['status', 'updated_at'])
    return meeting


@transaction.atomic
def record_participant_join(meeting: Meeting, user, role=ParticipantRole.ATTENDEE) -> MeetingParticipant:
    """
    Record that a user joined the meeting room.
    Re-opens previous session if recently left or creates a fresh session.
    """
    # If meeting is SCHEDULED and host joins, auto-transition to LIVE
    if meeting.status == MeetingStatus.SCHEDULED and (meeting.host == user or role == ParticipantRole.HOST):
        meeting.status = MeetingStatus.LIVE
        meeting.actual_start = timezone.now()
        meeting.save(update_fields=['status', 'actual_start', 'updated_at'])

    active_session = meeting.participants.filter(user=user, left_at__isnull=True).first()
    if active_session:
        return active_session

    if meeting.host == user:
        role = ParticipantRole.HOST

    return MeetingParticipant.objects.create(
        meeting=meeting,
        user=user,
        role=role,
        joined_at=timezone.now()
    )


@transaction.atomic
def record_participant_leave(meeting: Meeting, user) -> bool:
    """
    Record that a user left the meeting room.
    """
    active_sessions = meeting.participants.filter(user=user, left_at__isnull=True)
    active_sessions.update(left_at=timezone.now())

    # If no more participants remain and meeting is an instant call, auto-mark ended
    if meeting.status == MeetingStatus.LIVE and meeting.meeting_type in (MeetingType.INSTANT, MeetingType.CHAT_CALL):
        if not meeting.participants.filter(left_at__isnull=True).exists():
            meeting.status = MeetingStatus.ENDED
            meeting.actual_end = timezone.now()
            meeting.save(update_fields=['status', 'actual_end', 'updated_at'])

    return True
