import logging
import secrets
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

from workspaces.models import WorkspaceMembership, MembershipStatus
from .models import (
    Meeting, MeetingParticipant, MeetingInvite,
    MeetingType, MeetingStatus, ParticipantRole,
    CallSession, CallStatus, CallEndedReason
)


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
    if conversation:
        other = conversation.get_other_participant(host)
        if other:
            session = initiate_call_session(
                workspace=workspace,
                caller=host,
                recipient=other,
                call_mode="AUDIO" if is_audio_only else "VIDEO",
                conversation=conversation
            )
            return session.meeting
        other_name = "User"
        title = f"{call_kind} call with {other_name}"
    elif channel:
        title = f"{call_kind} call in {channel.display_name}"
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
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        card_content = (
            f"CALL_INVITE:{meeting.meeting_code}:{'AUDIO' if is_audio_only else 'VIDEO'}:{meeting.title}"
        )
        msg = Message.objects.create(
            workspace=workspace,
            sender=host,
            channel=channel,
            conversation=conversation,
            content=card_content
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f"chat_dm_{conversation.id}" if conversation else f"chat_channel_{channel.id}"
            sender_name = host.full_name or host.email if host else "Someone"
            sender_avatar = host.avatar_url if host and hasattr(host, 'avatar_url') else ""

            # Broadcast new message card
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "chat_broadcast",
                    "event": "new_message",
                    "message": {
                        "id": str(msg.id),
                        "sender_id": str(host.id) if host else "",
                        "sender_name": sender_name,
                        "sender_avatar": sender_avatar,
                        "content": card_content,
                        "created_at": msg.created_at.strftime("%I:%M %p"),
                        "reactions": [],
                    }
                }
            )

            # Broadcast incoming call event with ringtone trigger data
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "chat_broadcast",
                    "event": "incoming_call",
                    "call": {
                        "meeting_code": meeting.meeting_code,
                        "title": meeting.title,
                        "is_audio_only": is_audio_only,
                        "caller_name": sender_name,
                        "caller_avatar": sender_avatar,
                        "room_url": f"/meetings/w/{workspace.slug}/room/{meeting.meeting_code}/"
                    }
                }
            )
    except Exception as e:
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
            # Notify invitee
            try:
                from notifications.services import create_notification
                from notifications.models import NotificationCategory, NotificationType
                host_name = host.full_name or host.email if host else "Someone"
                start_str = scheduled_start.strftime('%b %d at %I:%M %p')
                create_notification(
                    recipient=user,
                    category=NotificationCategory.MEETING,
                    notification_type=NotificationType.MEETING_INVITE,
                    title=f"Meeting Invite: {meeting.title}",
                    body=f"{host_name} invited you to '{meeting.title}' scheduled for {start_str}",
                    workspace=workspace,
                    actor=host,
                    action_url=f"/meetings/w/{workspace.slug}/room/{meeting.meeting_code}/"
                )
            except Exception:
                pass

            # Email invitee
            try:
                from notifications.email_service import send_meeting_scheduled_email
                if not host or user.id != host.id:
                    send_meeting_scheduled_email(meeting=meeting, recipient=user, actor=host)
            except Exception:
                pass

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
def end_call_session_for_meeting(meeting, user=None, reason=CallEndedReason.NORMAL):
    """
    Finds any active CallSessions associated with this meeting and transitions them to ENDED.
    """
    now = timezone.now()
    active_sessions = CallSession.objects.filter(
        meeting=meeting,
        status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
    )
    for session in active_sessions:
        session.status = CallStatus.ENDED
        session.ended_at = now
        session.ended_reason = reason
        session.save(update_fields=['status', 'ended_at', 'ended_reason'])
        logger.info(f"[CALL-DIAG] end_call_session_for_meeting: session {session.id} marked ENDED (reason={reason})")


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

    # End any active CallSessions associated with this meeting
    end_call_session_for_meeting(meeting, user=user)

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

    try:
        from notifications.email_service import send_meeting_status_email
        for invite in meeting.invites.select_related('user'):
            if not user or invite.user_id != user.id:
                send_meeting_status_email(meeting=meeting, recipient=invite.user, status_change='cancelled', actor=user)
    except Exception:
        pass

    return meeting


@transaction.atomic
def record_participant_join(meeting: Meeting, user, role=ParticipantRole.ATTENDEE) -> MeetingParticipant:
    """
    Record that a user joined the meeting room.
    Re-opens previous session if recently left or creates a fresh session.
    Guarantees no duplicate records exist for (meeting, user).
    """
    # If meeting is SCHEDULED and host joins, auto-transition to LIVE
    if meeting.status == MeetingStatus.SCHEDULED and (meeting.host == user or role == ParticipantRole.HOST):
        meeting.status = MeetingStatus.LIVE
        meeting.actual_start = timezone.now()
        meeting.save(update_fields=['status', 'actual_start', 'updated_at'])

    if meeting.host == user:
        role = ParticipantRole.HOST

    now = timezone.now()
    participant = meeting.participants.filter(user=user).order_by('-joined_at').first()
    if participant:
        participant.left_at = None
        participant.is_removed = False
        if role and role != participant.role:
            participant.role = role
        participant.save(update_fields=['left_at', 'is_removed', 'role'])
        # Cleanup any stray duplicate records for this user in this meeting
        meeting.participants.filter(user=user).exclude(id=participant.id).delete()
        return participant

    return MeetingParticipant.objects.create(
        meeting=meeting,
        user=user,
        role=role,
        joined_at=now
    )


@transaction.atomic
def record_participant_leave(meeting: Meeting, user) -> bool:
    """
    Record that a user left the meeting room.
    Records attendance departure timestamp without prematurely destroying
    the meeting for active, duplicate, or reconnecting participants.
    """
    active_sessions = meeting.participants.filter(user=user, left_at__isnull=True)
    active_sessions.update(left_at=timezone.now())
    return True


# ==============================================================================
# MEET HUB M1 — REAL-TIME CALL SESSION SERVICES
# ==============================================================================

def reconcile_and_prune_stale_calls(user):
    """
    Auto-prune orphaned or abandoned call sessions for a user.
    Handles situations where:
    1. A ringing call timed out (> 45s).
    2. An accepted or connected call is linked to an ended meeting.
    3. An accepted or connected call has zero active meeting participants.
    4. An accepted or connected call was initiated > 2 hours ago.
    """
    now = timezone.now()
    active_sessions = CallSession.objects.filter(
        Q(caller=user) | Q(recipient=user),
        status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
    ).select_related('meeting')

    for session in active_sessions:
        if session.status == CallStatus.RINGING:
            if (now - session.created_at).total_seconds() > 45:
                session.mark_missed()
                logger.info(f"[CALL-DIAG] Pruned timed-out ringing CallSession {session.id}")
        elif session.status in (CallStatus.ACCEPTED, CallStatus.CONNECTED):
            meeting = session.meeting
            is_ended = (meeting.status == MeetingStatus.ENDED)
            has_no_participants = not meeting.participants.filter(left_at__isnull=True).exists()
            duration = (now - (session.connected_at or session.created_at)).total_seconds()

            if is_ended or has_no_participants or duration > 7200:
                session.status = CallStatus.ENDED
                session.ended_at = now
                session.ended_reason = CallEndedReason.NORMAL
                session.save(update_fields=['status', 'ended_at', 'ended_reason'])
                logger.info(f"[CALL-DIAG] Auto-pruned stale CallSession {session.id} (ended={is_ended}, no_participants={has_no_participants})")


@transaction.atomic
def initiate_call_session(workspace, caller, recipient, call_mode='VIDEO',
                          conversation=None, channel=None) -> CallSession:
    """
    Initiate a 1-on-1 audio or video call between caller and recipient.
    Validates workspace isolation, membership, availability, and active call collisions.
    Creates Meeting + CallSession(status=RINGING) and notifies recipient globally via Channels.
    """
    from core.models import ModuleStatus
    status_obj = ModuleStatus.get_status_obj('meetings')
    if status_obj and not status_obj.is_available:
        raise PermissionError(status_obj.effective_message)

    if str(caller.id) == str(recipient.id):
        raise ValidationError("You cannot call yourself.")

    # Validate active workspace membership for both parties
    if not WorkspaceMembership.objects.filter(workspace=workspace, user=caller, status=MembershipStatus.ACTIVE).exists():
        raise PermissionError("Caller is not an active member of this workspace.")
    if not WorkspaceMembership.objects.filter(workspace=workspace, user=recipient, status=MembershipStatus.ACTIVE).exists():
        raise PermissionError("Recipient is not an active member of this workspace.")

    # Auto-prune any stale / orphaned active calls for both parties first
    reconcile_and_prune_stale_calls(caller)
    reconcile_and_prune_stale_calls(recipient)

    # Check caller active calls
    caller_active = CallSession.objects.filter(
        Q(caller=caller) | Q(recipient=caller),
        status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
    ).first()
    if caller_active:
        if caller_active.status == CallStatus.RINGING:
            if (timezone.now() - caller_active.created_at).total_seconds() > 45 or caller_active.recipient_id == recipient.id:
                caller_active.status = CallStatus.CANCELLED
                caller_active.ended_at = timezone.now()
                caller_active.ended_reason = CallEndedReason.CANCELLED
                caller_active.save(update_fields=['status', 'ended_at', 'ended_reason'])
            else:
                raise ValidationError("You already have an active call in progress.")
        else:
            raise ValidationError("You already have an active call in progress.")

    # Check recipient active calls
    recipient_active = CallSession.objects.filter(
        Q(caller=recipient) | Q(recipient=recipient),
        status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
    ).first()
    if recipient_active:
        if recipient_active.status == CallStatus.RINGING:
            if (timezone.now() - recipient_active.created_at).total_seconds() > 45 or recipient_active.caller_id == caller.id:
                recipient_active.status = CallStatus.CANCELLED
                recipient_active.ended_at = timezone.now()
                recipient_active.ended_reason = CallEndedReason.CANCELLED
                recipient_active.save(update_fields=['status', 'ended_at', 'ended_reason'])
            else:
                recipient_name = recipient.full_name or recipient.email
                raise ValidationError(f"{recipient_name} is currently on another call.")
        else:
            recipient_name = recipient.full_name or recipient.email
            raise ValidationError(f"{recipient_name} is currently on another call.")

    # Determine availability status
    recipient_profile = getattr(recipient, 'profile', None)
    recipient_status = recipient_profile.availability_status if recipient_profile else 'available'

    mode = (call_mode or 'VIDEO').upper()
    is_audio_only = (mode == 'AUDIO')
    call_kind = "Audio" if is_audio_only else "Video"
    title = f"{call_kind} call with {recipient.full_name or recipient.email}"

    meeting = Meeting.objects.create(
        workspace=workspace,
        meeting_code=generate_unique_meeting_code(),
        title=title,
        host=caller,
        meeting_type=MeetingType.CHAT_CALL,
        status=MeetingStatus.LIVE,
        is_audio_only=is_audio_only,
        channel=channel,
        actual_start=timezone.now()
    )

    MeetingParticipant.objects.create(
        meeting=meeting,
        user=caller,
        role=ParticipantRole.HOST
    )

    session = CallSession.objects.create(
        workspace=workspace,
        meeting=meeting,
        caller=caller,
        recipient=recipient,
        conversation=conversation,
        channel=channel,
        call_mode=mode,
        status=CallStatus.RINGING
    )

    channel_layer = get_channel_layer()
    # [CALL-DIAG] Log channel layer type and session details
    logger.info("[CALL-DIAG] initiate_call_session: session=%s caller=%s recipient=%s channel_layer=%s",
                session.id, caller.id, recipient.id, type(channel_layer).__name__ if channel_layer else 'None')

    if channel_layer:
        caller_avatar = caller.avatar_url if hasattr(caller, 'avatar_url') else ''
        caller_contributor_id = getattr(caller, 'contributor_id', '') or ''
        room_url = f"/meetings/w/{workspace.slug}/room/{meeting.meeting_code}/"
        # FIX: str(session.id) — UUID is not JSON serializable, must be string
        call_id_str = str(session.id)

        recipient_group = f"user_calls_{recipient.id}"
        # [CALL-DIAG] Log before sending to recipient
        logger.info("[CALL-DIAG] SENDING call_incoming to group=%s call_id=%s", recipient_group, call_id_str)
        try:
            async_to_sync(channel_layer.group_send)(
                recipient_group,
                {
                    "type": "call_incoming",
                    "call_id": call_id_str,
                    "meeting_code": meeting.meeting_code,
                    "call_mode": session.call_mode,
                    "is_audio_only": is_audio_only,
                    "caller_id": str(caller.id),
                    "caller_name": caller.full_name or caller.email,
                    "caller_avatar": caller_avatar,
                    "caller_contributor_id": caller_contributor_id,
                    "workspace_slug": workspace.slug,
                    "workspace_name": workspace.name,
                    "room_url": room_url,
                    "ringing_at": session.ringing_at.isoformat(),
                    "recipient_status": recipient_status,
                }
            )
            # [CALL-DIAG] Log success
            logger.info("[CALL-DIAG] SUCCESS call_incoming sent to group=%s", recipient_group)
        except Exception as e:
            # [CALL-DIAG] Log failure
            logger.error("[CALL-DIAG] FAILED call_incoming to group=%s error=%s", recipient_group, e, exc_info=True)

        # Broadcast outgoing call event to caller's global group (syncs all tabs)
        recipient_avatar = recipient.avatar_url if hasattr(recipient, 'avatar_url') else ''
        recipient_contributor_id = getattr(recipient, 'contributor_id', '') or ''
        caller_group = f"user_calls_{caller.id}"
        # [CALL-DIAG] Log before sending to caller
        logger.info("[CALL-DIAG] SENDING call_outgoing to group=%s call_id=%s", caller_group, call_id_str)
        try:
            async_to_sync(channel_layer.group_send)(
                caller_group,
                {
                    "type": "call_outgoing",
                    "call_id": call_id_str,
                    "meeting_code": meeting.meeting_code,
                    "call_mode": session.call_mode,
                    "is_audio_only": is_audio_only,
                    "recipient_id": str(recipient.id),
                    "recipient_name": recipient.full_name or recipient.email,
                    "recipient_avatar": recipient_avatar,
                    "recipient_contributor_id": recipient_contributor_id,
                    "workspace_slug": workspace.slug,
                    "workspace_name": workspace.name,
                    "room_url": room_url,
                    "ringing_at": session.ringing_at.isoformat(),
                }
            )
            # [CALL-DIAG] Log success
            logger.info("[CALL-DIAG] SUCCESS call_outgoing sent to group=%s", caller_group)
        except Exception as e:
            # [CALL-DIAG] Log failure
            logger.error("[CALL-DIAG] FAILED call_outgoing to group=%s error=%s", caller_group, e, exc_info=True)

    # If conversation is provided, post invite card to DM thread
    if conversation:
        try:
            from chat.models import Message
            card_content = f"CALL_INVITE:{meeting.meeting_code}:{mode}:{meeting.title}"
            msg = Message.objects.create(
                workspace=workspace,
                sender=caller,
                conversation=conversation,
                content=card_content
            )
            if channel_layer:
                group_name = f"chat_dm_{conversation.id}"
                sender_name = caller.full_name or caller.email
                sender_avatar = caller.avatar_url if hasattr(caller, 'avatar_url') else ""
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        "type": "chat_broadcast",
                        "event": "new_message",
                        "message": {
                            "id": str(msg.id),
                            "sender_id": str(caller.id),
                            "sender_name": sender_name,
                            "sender_avatar": sender_avatar,
                            "content": card_content,
                            "created_at": msg.created_at.strftime("%I:%M %p"),
                            "reactions": [],
                        }
                    }
                )
        except Exception:
            pass

    return session


@transaction.atomic
def accept_call_session(call_id, user):
    """
    Recipient accepts the incoming call.
    Transitions CallSession from RINGING to ACCEPTED and broadcasts call_accepted.
    """
    try:
        session = CallSession.objects.select_related('workspace', 'meeting', 'caller', 'recipient').get(id=call_id)
    except CallSession.DoesNotExist:
        return False, "Call session does not exist", None

    if session.recipient_id != user.id:
        raise PermissionError("Only the designated call recipient can accept this call.")

    success, msg = session.accept(user)
    if not success:
        return False, msg, None

    room_url = f"/meetings/w/{session.workspace.slug}/room/{session.meeting.meeting_code}/"
    channel_layer = get_channel_layer()
    # [CALL-DIAG] Log accept
    logger.info("[CALL-DIAG] accept_call_session: call_id=%s accepted_by=%s room_url=%s", call_id, user.id, room_url)
    if channel_layer:
        # FIX: str(session.id) — UUID is not JSON serializable
        payload = {
            "type": "call_accepted",
            "call_id": str(session.id),
            "meeting_code": session.meeting.meeting_code,
            "room_url": room_url,
            "accepted_by_id": str(user.id),
            "accepted_by_name": user.full_name or user.email,
        }
        caller_group = f"user_calls_{session.caller_id}"
        recipient_group = f"user_calls_{session.recipient_id}"
        # [CALL-DIAG] Log before sending
        logger.info("[CALL-DIAG] SENDING call_accepted to caller_group=%s recipient_group=%s", caller_group, recipient_group)
        try:
            async_to_sync(channel_layer.group_send)(caller_group, payload)
            logger.info("[CALL-DIAG] SUCCESS call_accepted sent to caller_group=%s", caller_group)
        except Exception as e:
            logger.error("[CALL-DIAG] FAILED call_accepted to caller_group=%s error=%s", caller_group, e, exc_info=True)
        try:
            async_to_sync(channel_layer.group_send)(recipient_group, payload)
            logger.info("[CALL-DIAG] SUCCESS call_accepted sent to recipient_group=%s", recipient_group)
        except Exception as e:
            logger.error("[CALL-DIAG] FAILED call_accepted to recipient_group=%s error=%s", recipient_group, e, exc_info=True)

    return True, "Call accepted", room_url


@transaction.atomic
def decline_call_session(call_id, user, reason=CallEndedReason.DECLINED):
    """
    Recipient declines the incoming call.
    Transitions CallSession to DECLINED and broadcasts call_declined to both parties.
    """
    try:
        session = CallSession.objects.select_related('workspace', 'meeting', 'caller', 'recipient').get(id=call_id)
    except CallSession.DoesNotExist:
        return False, "Call session does not exist"

    if session.recipient_id != user.id:
        raise PermissionError("Only the designated call recipient can decline this call.")

    success, msg = session.decline(user, reason=reason)
    if not success:
        return False, msg

    channel_layer = get_channel_layer()
    if channel_layer:
        # FIX: str(session.id) — UUID is not JSON serializable
        payload = {
            "type": "call_declined",
            "call_id": str(session.id),
            "declined_by_id": str(user.id),
            "declined_by_name": user.full_name or user.email,
            "reason": str(reason),
        }
        logger.info("[CALL-DIAG] SENDING call_declined call_id=%s", session.id)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.caller_id}", payload)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.recipient_id}", payload)

    return True, "Call declined"


@transaction.atomic
def cancel_call_session(call_id, user):
    """
    Caller cancels an unanswered call.
    Transitions CallSession to CANCELLED and broadcasts call_cancelled.
    """
    try:
        session = CallSession.objects.select_related('workspace', 'meeting', 'caller', 'recipient').get(id=call_id)
    except CallSession.DoesNotExist:
        return False, "Call session does not exist"

    if session.caller_id != user.id:
        raise PermissionError("Only the initiating caller can cancel this call.")

    success, msg = session.cancel(user)
    if not success:
        return False, msg

    channel_layer = get_channel_layer()
    if channel_layer:
        # FIX: str(session.id) — UUID is not JSON serializable
        payload = {
            "type": "call_cancelled",
            "call_id": str(session.id),
            "cancelled_by_id": str(user.id),
            "cancelled_by_name": user.full_name or user.email,
        }
        logger.info("[CALL-DIAG] SENDING call_cancelled call_id=%s", session.id)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.recipient_id}", payload)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.caller_id}", payload)

    return True, "Call cancelled"


@transaction.atomic
def timeout_call_session(call_id):
    """
    Ringing timeout (unanswered after 45s).
    Transitions CallSession to MISSED and sends a persistent notification to the recipient.
    """
    try:
        session = CallSession.objects.select_related('workspace', 'meeting', 'caller', 'recipient').get(id=call_id)
    except CallSession.DoesNotExist:
        return False, "Call session does not exist"

    if session.status != CallStatus.RINGING:
        return False, f"Call is in '{session.status}' state, not ringing."

    success, msg = session.mark_missed()
    if not success:
        return False, msg

    channel_layer = get_channel_layer()
    if channel_layer:
        # FIX: str(session.id) — UUID is not JSON serializable
        payload = {
            "type": "call_missed",
            "call_id": str(session.id),
            "caller_name": session.caller.full_name or session.caller.email,
            "recipient_name": session.recipient.full_name or session.recipient.email,
        }
        logger.info("[CALL-DIAG] SENDING call_missed call_id=%s", session.id)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.recipient_id}", payload)
        async_to_sync(channel_layer.group_send)(f"user_calls_{session.caller_id}", payload)

    # Persistent notification for recipient
    try:
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        caller_name = session.caller.full_name or session.caller.email
        create_notification(
            recipient=session.recipient,
            category=NotificationCategory.MEETING,
            notification_type=NotificationType.GENERAL,
            title=f"Missed Call from {caller_name}",
            body=f"You missed a {session.get_call_mode_display().lower()} from {caller_name}.",
            workspace=session.workspace,
            actor=session.caller,
            action_url=f"/meetings/w/{session.workspace.slug}/"
        )
    except Exception:
        pass

    return True, "Call marked missed"


def mark_call_connected(meeting_code, user):
    """
    Invoked when participant enters meeting room. Transitions CallSession to CONNECTED.
    """
    try:
        session = CallSession.objects.filter(
            meeting__meeting_code=meeting_code,
            status=CallStatus.ACCEPTED
        ).first()
        if session:
            session.mark_connected(user)
            return True
    except Exception:
        pass
    return False


def get_active_call_for_user(user):
    """
    Check if the user is currently involved in an active ringing call.
    Returns dict with role ('caller' or 'recipient') and call details if found, else None.
    Handles auto-expiry of calls ringing for > 45 seconds.
    """
    if not user or not user.is_authenticated:
        return None

    now = timezone.now()

    # 1. Check incoming ringing call (recipient)
    incoming = CallSession.objects.filter(
        recipient=user,
        status=CallStatus.RINGING
    ).select_related('workspace', 'meeting', 'caller').order_by('-created_at').first()

    if incoming:
        if (now - incoming.created_at).total_seconds() > 45:
            incoming.mark_missed()
        else:
            recipient_profile = getattr(user, 'profile', None)
            recipient_status = recipient_profile.availability_status if recipient_profile else 'available'
            # [CALL-DIAG] Log re-hydration
            logger.info("[CALL-DIAG] get_active_call_for_user: found incoming ringing call=%s for user=%s", incoming.id, user.id)
            return {
                "role": "recipient",
                "type": "call_incoming",
                "call_id": str(incoming.id),
                "meeting_code": incoming.meeting.meeting_code,
                "call_mode": incoming.call_mode,
                "is_audio_only": (incoming.call_mode == 'AUDIO'),
                "caller_id": str(incoming.caller.id),
                "caller_name": incoming.caller.full_name or incoming.caller.email,
                "caller_avatar": incoming.caller.avatar_url if hasattr(incoming.caller, 'avatar_url') else '',
                "caller_contributor_id": getattr(incoming.caller, 'contributor_id', '') or '',
                "workspace_slug": incoming.workspace.slug,
                "workspace_name": incoming.workspace.name,
                "room_url": f"/meetings/w/{incoming.workspace.slug}/room/{incoming.meeting.meeting_code}/",
                "ringing_at": incoming.ringing_at.isoformat(),
                "recipient_status": recipient_status,
            }

    # 2. Check outgoing ringing call (caller)
    outgoing = CallSession.objects.filter(
        caller=user,
        status=CallStatus.RINGING
    ).select_related('workspace', 'meeting', 'recipient').order_by('-created_at').first()

    if outgoing:
        if (now - outgoing.created_at).total_seconds() > 45:
            outgoing.mark_missed()
        else:
            # [CALL-DIAG] Log re-hydration
            logger.info("[CALL-DIAG] get_active_call_for_user: found outgoing ringing call=%s for user=%s", outgoing.id, user.id)
            return {
                "role": "caller",
                "type": "call_outgoing",
                "call_id": str(outgoing.id),
                "meeting_code": outgoing.meeting.meeting_code,
                "call_mode": outgoing.call_mode,
                "is_audio_only": (outgoing.call_mode == 'AUDIO'),
                "recipient_id": str(outgoing.recipient.id),
                "recipient_name": outgoing.recipient.full_name or outgoing.recipient.email,
                "recipient_avatar": outgoing.recipient.avatar_url if hasattr(outgoing.recipient, 'avatar_url') else '',
                "recipient_contributor_id": getattr(outgoing.recipient, 'contributor_id', '') or '',
                "workspace_slug": outgoing.workspace.slug,
                "workspace_name": outgoing.workspace.name,
                "room_url": f"/meetings/w/{outgoing.workspace.slug}/room/{outgoing.meeting.meeting_code}/",
                "ringing_at": outgoing.ringing_at.isoformat(),
            }

    return None


# ==============================================================================
# 8x8 JAAS (JITSI AS A SERVICE) RS256 JWT GENERATION & CONFIGURATION
# ==============================================================================

import base64
import json
import os
import time
from typing import Tuple, Optional, Dict, Any
from django.conf import settings


# Strings that indicate the API key ID has not been replaced with real credentials.
# These are checked case-insensitively against JAAS_API_KEY_ID.
_PLACEHOLDER_SUBSTRINGS = [
    'your_api_key',
    'your-api-key',
    'replace_me',
    'replace-me',
    'placeholder',
    'example',
    'changeme',
    'todo',
    'xxx',
    'insert_key',
    'insert-key',
]


def _is_placeholder_key_id(api_key_id: str) -> bool:
    """Return True if the API key ID looks like an unmodified placeholder."""
    lower = api_key_id.lower()
    return any(substr in lower for substr in _PLACEHOLDER_SUBSTRINGS)


def _b64url_encode(data: bytes) -> str:
    """Encode bytes using URL-safe Base64 without padding."""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def get_jaas_status() -> Dict[str, Any]:
    """
    Returns non-sensitive metadata about JaaS configuration status.
    Never exposes private keys or secret values.
    """
    app_id = getattr(settings, 'JAAS_APP_ID', '').strip()
    api_key_id = getattr(settings, 'JAAS_API_KEY_ID', '').strip()
    has_env_key = bool(getattr(settings, 'JAAS_PRIVATE_KEY', '').strip())
    key_path = getattr(settings, 'JAAS_PRIVATE_KEY_PATH', '').strip()
    has_path_key = bool(key_path and os.path.exists(key_path))
    placeholder_key = _is_placeholder_key_id(api_key_id) if api_key_id else False

    return {
        'is_configured': bool(app_id),
        'app_id': app_id,
        'has_api_key_id': bool(api_key_id),
        'has_placeholder_key_id': placeholder_key,
        'has_private_key': bool(has_env_key or has_path_key),
        'key_source': 'env' if has_env_key else ('file' if has_path_key else 'none'),
    }


def validate_jaas_credentials() -> Tuple[bool, Optional[str]]:
    """
    Comprehensive validation of JaaS credentials.
    Returns (is_valid, error_message).
    - If JaaS is not enabled (no JAAS_APP_ID), returns (True, None) — no validation needed.
    - If JaaS is enabled, checks that all required credentials are present and not placeholders.
    - Does NOT verify that credentials are registered with 8x8. That requires live testing.
    """
    app_id = getattr(settings, 'JAAS_APP_ID', '').strip()
    if not app_id:
        return True, None  # JaaS not enabled; nothing to validate.

    api_key_id = getattr(settings, 'JAAS_API_KEY_ID', '').strip()
    if not api_key_id:
        return False, "JaaS is enabled (JAAS_APP_ID is set) but JAAS_API_KEY_ID is missing."

    if _is_placeholder_key_id(api_key_id):
        return False, (
            "JaaS is enabled but JAAS_API_KEY_ID contains a placeholder value. "
            "Replace it with your real 8x8 JaaS API key ID from the JaaS console."
        )

    # Check private key availability
    has_env_key = bool(getattr(settings, 'JAAS_PRIVATE_KEY', '').strip())
    key_path = getattr(settings, 'JAAS_PRIVATE_KEY_PATH', '').strip()
    has_path_key = bool(key_path and os.path.exists(key_path))
    if not has_env_key and not has_path_key:
        return False, (
            "JaaS is enabled but no RSA private key is configured. "
            "Set JAAS_PRIVATE_KEY or JAAS_PRIVATE_KEY_PATH."
        )

    # Attempt to parse the private key without signing anything
    private_key, parse_err = load_jaas_private_key()
    if parse_err or not private_key:
        return False, f"JaaS private key is present but invalid: {parse_err}"

    return True, None


def load_jaas_private_key():
    """
    Safely load the RSA private key from JAAS_PRIVATE_KEY or JAAS_PRIVATE_KEY_PATH.
    Returns (private_key_object, error_message).
    """
    from cryptography.hazmat.primitives import serialization

    raw_key = getattr(settings, 'JAAS_PRIVATE_KEY', '').strip()
    key_path = getattr(settings, 'JAAS_PRIVATE_KEY_PATH', '').strip()

    key_bytes = None
    if raw_key:
        formatted_key = raw_key.replace('\\n', '\n').strip()
        key_bytes = formatted_key.encode('utf-8')
    elif key_path:
        if not os.path.exists(key_path):
            return None, f"JAAS_PRIVATE_KEY_PATH not found: {key_path}"
        try:
            with open(key_path, 'rb') as f:
                key_bytes = f.read().strip()
        except Exception as e:
            return None, f"Failed reading JAAS_PRIVATE_KEY_PATH: {e}"
    else:
        return None, "JaaS private key is not configured (neither JAAS_PRIVATE_KEY nor JAAS_PRIVATE_KEY_PATH provided)."

    try:
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
        return private_key, None
    except Exception as e:
        return None, f"Invalid or unparseable RSA private key: {e}"


def generate_jaas_jwt(
    meeting: Meeting,
    user,
    is_moderator: bool = False,
    exp_seconds: Optional[int] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Generate an official RS256-signed JWT for 8x8 JaaS.
    Returns: (jwt_token, error_message)
    - If JaaS is not configured (JAAS_APP_ID is blank), returns (None, None).
    - If JaaS is configured but has missing credentials or invalid key, returns (None, error_message).
    - If successful, returns (jwt_token, None).
    """
    app_id = getattr(settings, 'JAAS_APP_ID', '').strip()
    if not app_id:
        return None, None

    api_key_id = getattr(settings, 'JAAS_API_KEY_ID', '').strip()
    if not api_key_id:
        return None, "8x8 JaaS is enabled but JAAS_API_KEY_ID is missing."

    if _is_placeholder_key_id(api_key_id):
        return None, (
            "8x8 JaaS is enabled but JAAS_API_KEY_ID contains a placeholder value "
            "('your_api_key_id'). Replace it with a real key ID from the 8x8 JaaS console."
        )

    private_key, err = load_jaas_private_key()
    if err or not private_key:
        return None, f"8x8 JaaS authentication failure: {err}"

    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    # Header
    # 8x8 JaaS kid format: "vpaas-magic-cookie-<app_id>/<key_id>"
    if "/" in api_key_id:
        kid = api_key_id
    else:
        kid = f"{app_id}/{api_key_id}"

    header = {
        "alg": "RS256",
        "typ": "JWT",
        "kid": kid
    }

    # Time bounds
    now = int(time.time())
    ttl = int(exp_seconds or getattr(settings, 'JAAS_JWT_EXP_SECONDS', 7200))
    exp = now + ttl
    nbf = now - 10  # 10s leeway for clock drift

    # User info
    user_name = user.full_name or user.get_full_name() or user.username or (user.email.split('@')[0] if user.email else 'Participant')
    user_avatar = user.avatar if getattr(user, 'avatar', None) and not user.avatar.startswith('preset:') else ''

    # Payload matching official 8x8 JaaS claims specification
    payload = {
        "aud": "jitsi",
        "iss": "chat",
        "sub": app_id,
        "room": meeting.jitsi_room_name,
        "exp": exp,
        "nbf": nbf,
        "context": {
            "user": {
                "id": str(user.id),
                "name": user_name,
                "email": user.email or "",
                "avatar": user_avatar,
                "moderator": bool(is_moderator),
            },
            "features": {
                "livestreaming": bool(is_moderator),
                "recording": bool(is_moderator),
                "transcription": bool(is_moderator),
                "file-upload": True
            }
        }
    }

    try:
        h_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        p_b64 = _b64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        signing_input = f"{h_b64}.{p_b64}".encode('utf-8')
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = _b64url_encode(signature)
        jwt_token = f"{h_b64}.{p_b64}.{sig_b64}"
        return jwt_token, None
    except Exception as e:
        return None, f"Failed signing JaaS JWT: {e}"

