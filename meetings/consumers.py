import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db.models import Q
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus
from .models import (
    Meeting, MeetingParticipant, MeetingStatus, ParticipantRole,
    CallSession, CallStatus, CallEndedReason
)

logger = logging.getLogger(__name__)


class MeetingSignalingConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time WebRTC Signaling & Conference State Consumer for AetherSpace Meet Hub.
    Handles full-mesh WebRTC signaling (SDP offer/answer, ICE candidates),
    participant presence, remote media state, in-call chat, and live reactions.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            logger.warning("Meeting WebSocket rejected: unauthenticated user")
            await self.close(code=4001)
            return

        kwargs = self.scope.get("url_route", {}).get("kwargs", {})
        self.slug = kwargs.get("slug")
        self.meeting_code = kwargs.get("meeting_code")

        if not self.slug or not self.meeting_code:
            await self.close(code=4000)
            return

        # Validate workspace membership & meeting access
        access_info = await self.validate_meeting_access(self.slug, self.meeting_code, self.user)
        if not access_info:
            logger.warning(f"Meeting WebSocket rejected: no access to {self.meeting_code} in {self.slug}")
            await self.close(code=4003)
            return

        self.meeting_id = str(access_info["meeting_id"])
        self.is_host = access_info["is_host"]
        self.room_group_name = f"meeting_{self.meeting_id}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Track active sockets for this user in this meeting
        user_socket_count = await self.record_meeting_socket_connect(self.meeting_id, self.user.id)

        # Register participant presence in DB
        participant_data = await self.record_join(self.meeting_id, self.user)
        self.user_display_name = participant_data["name"]
        self.user_avatar = participant_data["avatar"]

        # Fetch all currently active participants in room
        active_peers = await self.get_active_peers(self.meeting_id, self.user.id)

        # Send initial room state to connecting peer
        await self.send_json({
            "type": "room_state",
            "meeting_id": self.meeting_id,
            "meeting_code": self.meeting_code,
            "self": participant_data,
            "peers": active_peers,
            "is_host": self.is_host,
        })

        # Broadcast peer_joined to all other participants in the room only on the first socket connection
        if user_socket_count == 1:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_peer_joined",
                    "peer": participant_data,
                    "sender_channel": self.channel_name,
                }
            )

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            remaining_sockets = 0
            if hasattr(self, "meeting_id"):
                remaining_sockets = await self.record_meeting_socket_disconnect(self.meeting_id, self.user.id)

            # If user has other active sockets in this room (e.g. Pop-out window, duplicate tab),
            # DO NOT broadcast peer_left or disrupt the active meeting.
            if remaining_sockets > 0:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
                return

            # All sockets for this user in this room have disconnected.
            # Broadcast peer_left to notify peers, but DO NOT destroy the meeting on disconnect.
            # Reconnecting users or reloads are accommodated within reconnect grace.
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_peer_left",
                    "peer_id": str(self.user.id),
                    "peer_name": getattr(self, "user_display_name", str(self.user)),
                    "sender_channel": self.channel_name,
                }
            )

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get("type")
        sender_id = str(self.user.id)

        # 1. Peer-to-Peer WebRTC Signaling: Offer (Deprecated — Media now handled by Jitsi Meet)
        if msg_type == "signal_offer":
            logger.info("Deprecated WebRTC signaling 'signal_offer' received; media transport handled by Jitsi.")
            target_id = str(content.get("target_id", ""))
            sdp = content.get("sdp")
            if target_id and sdp:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_signaling",
                        "event": "signal_offer",
                        "sender_id": sender_id,
                        "target_id": target_id,
                        "sdp": sdp,
                    }
                )

        # 2. Peer-to-Peer WebRTC Signaling: Answer (Deprecated — Media now handled by Jitsi Meet)
        elif msg_type == "signal_answer":
            logger.info("Deprecated WebRTC signaling 'signal_answer' received; media transport handled by Jitsi.")
            target_id = str(content.get("target_id", ""))
            sdp = content.get("sdp")
            if target_id and sdp:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_signaling",
                        "event": "signal_answer",
                        "sender_id": sender_id,
                        "target_id": target_id,
                        "sdp": sdp,
                    }
                )

        # 3. Peer-to-Peer WebRTC Signaling: ICE Candidate (Deprecated — Media now handled by Jitsi Meet)
        elif msg_type == "signal_ice":
            logger.info("Deprecated WebRTC signaling 'signal_ice' received; media transport handled by Jitsi.")
            target_id = str(content.get("target_id", ""))
            candidate = content.get("candidate")
            if target_id and candidate:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_signaling",
                        "event": "signal_ice",
                        "sender_id": sender_id,
                        "target_id": target_id,
                        "candidate": candidate,
                    }
                )

        # 4. Media State Synchronization (Mute / Camera / Screen share / Hand raise)
        elif msg_type == "media_state":
            media_state = {
                "is_muted": content.get("is_muted"),
                "is_camera_on": content.get("is_camera_on"),
                "screen_sharing": content.get("screen_sharing"),
                "is_hand_raised": content.get("is_hand_raised"),
            }
            # Update hand raise state in DB if specified
            if "is_hand_raised" in content and content["is_hand_raised"] is not None:
                await self.update_hand_raise(self.meeting_id, self.user.id, content["is_hand_raised"])

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_media_state",
                    "sender_id": sender_id,
                    "media_state": media_state,
                }
            )

        # 5. In-Meeting Chat
        elif msg_type == "meeting_chat":
            text = content.get("text", "").strip()
            if text:
                time_str = timezone.now().strftime("%I:%M %p")
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_chat_message",
                        "message": {
                            "id": int(timezone.now().timestamp() * 1000),
                            "sender_id": sender_id,
                            "sender": self.user_display_name,
                            "avatar": self.user_avatar,
                            "text": text,
                            "time": time_str,
                        }
                    }
                )

        # 6. Live Floating Emoji Reactions
        elif msg_type == "meeting_reaction":
            emoji = content.get("emoji", "👍")
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_reaction",
                    "sender_id": sender_id,
                    "sender_name": self.user_display_name,
                    "emoji": emoji,
                }
            )

        # 7. Live Speech-to-Text Captions Broadcast
        elif msg_type == "caption_broadcast":
            text = content.get("text", "").strip()
            if text:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_caption",
                        "sender_id": sender_id,
                        "sender_name": self.user_display_name,
                        "text": text,
                    }
                )

        # 8. Host Action: Kick Participant
        elif msg_type == "kick_participant":
            if self.is_host:
                target_id = str(content.get("target_id", ""))
                if target_id:
                    await self.eject_participant(self.meeting_id, target_id)
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "room_participant_kicked",
                            "target_id": target_id,
                        }
                    )

        # 9. Participant Action: Leave Call / Meeting
        elif msg_type == "leave_meeting":
            await self.record_leave(self.meeting_id, self.user.id)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_peer_left",
                    "peer_id": sender_id,
                    "peer_name": getattr(self, "user_display_name", "Participant"),
                    "sender_channel": self.channel_name,
                }
            )
            # If 1-on-1 call session exists, end the call and notify room
            call_ended = await self.end_call_session_if_active(self.meeting_id, self.user)
            if call_ended:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_call_ended",
                        "message": f"{getattr(self, 'user_display_name', 'Participant')} has ended the call.",
                    }
                )

        # 10. Host Action: End Meeting for All
        elif msg_type == "end_meeting":
            if self.is_host:
                await self.close_meeting_in_db(self.meeting_id, self.user)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_meeting_ended",
                        "message": "The meeting has been ended by the host.",
                    }
                )

    # ------------------------------------------------------------------
    # Channel Layer Group Event Handlers
    # ------------------------------------------------------------------

    async def room_peer_joined(self, event):
        """Notifies this client that a new peer has joined."""
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({
                "type": "peer_joined",
                "peer": event["peer"],
            })

    async def room_peer_left(self, event):
        """Notifies this client that a peer has left."""
        if event.get("sender_channel") != self.channel_name:
            await self.send_json({
                "type": "peer_left",
                "peer_id": event["peer_id"],
                "peer_name": event.get("peer_name", "A participant"),
            })

    async def room_signaling(self, event):
        """Routes targeted WebRTC signaling messages (SDP offer/answer, ICE) to this client."""
        if event.get("target_id") == str(self.user.id):
            out_msg = {
                "type": event["event"],
                "sender_id": event["sender_id"],
            }
            if "sdp" in event:
                out_msg["sdp"] = event["sdp"]
            if "candidate" in event:
                out_msg["candidate"] = event["candidate"]
            await self.send_json(out_msg)

    async def room_media_state(self, event):
        """Updates remote peer media status on this client."""
        if event.get("sender_id") != str(self.user.id):
            await self.send_json({
                "type": "media_state",
                "sender_id": event["sender_id"],
                "media_state": event["media_state"],
            })

    async def room_chat_message(self, event):
        """Delivers in-call chat message to this client."""
        await self.send_json({
            "type": "meeting_chat",
            "message": event["message"],
        })

    async def room_reaction(self, event):
        """Displays floating emoji reaction on this client."""
        await self.send_json({
            "type": "meeting_reaction",
            "sender_id": event["sender_id"],
            "sender_name": event["sender_name"],
            "emoji": event["emoji"],
        })

    async def room_caption(self, event):
        """Displays remote speech caption on this client."""
        if event.get("sender_id") != str(self.user.id):
            await self.send_json({
                "type": "caption_broadcast",
                "sender_id": event["sender_id"],
                "sender_name": event["sender_name"],
                "text": event["text"],
            })

    async def room_participant_kicked(self, event):
        """Handles participant kick event."""
        if event.get("target_id") == str(self.user.id):
            await self.send_json({
                "type": "kicked",
                "message": "You have been removed from this meeting by the host.",
            })
            await self.close(code=4003)
        else:
            await self.send_json({
                "type": "peer_left",
                "peer_id": event["target_id"],
                "peer_name": "A removed participant",
            })

    async def room_call_ended(self, event):
        """Notifies all participants that the 1-on-1 call session has ended."""
        await self.send_json({
            "type": "call_ended",
            "message": event.get("message", "The call has ended."),
        })
        await self.close(code=1000)

    async def room_meeting_ended(self, event):
        """Notifies all participants that the host has ended the meeting."""
        await self.send_json({
            "type": "meeting_ended",
            "message": event.get("message", "This meeting has been ended by the host."),
        })
        await self.close(code=1000)

    # ------------------------------------------------------------------
    # Database Helper Methods (Synchronous ORM wrapped in async)
    # ------------------------------------------------------------------

    @database_sync_to_async
    def validate_meeting_access(self, slug, meeting_code, user):
        clean_code = meeting_code.strip().lower()
        ws = Workspace.objects.filter(slug=slug).first()
        if not ws:
            return None

        membership = WorkspaceMembership.objects.filter(
            workspace=ws,
            user=user,
            status=MembershipStatus.ACTIVE
        ).first()
        if not membership:
            return None

        meeting = Meeting.objects.filter(
            workspace=ws,
            meeting_code__iexact=clean_code
        ).first()
        if not meeting:
            return None

        if meeting.status in (MeetingStatus.CANCELLED, MeetingStatus.ENDED):
            return None

        # Auto-activate scheduled meeting when host or member arrives
        if meeting.status == MeetingStatus.SCHEDULED:
            meeting.status = MeetingStatus.LIVE
            meeting.actual_start = timezone.now()
            meeting.save(update_fields=["status", "actual_start", "updated_at"])

        is_host = (meeting.host == user or getattr(membership, "can_manage_content", False))
        return {
            "meeting_id": meeting.id,
            "is_host": is_host,
        }

    @database_sync_to_async
    def record_join(self, meeting_id, user):
        meeting = Meeting.objects.get(id=meeting_id)
        now = timezone.now()

        participant = MeetingParticipant.objects.filter(
            meeting=meeting,
            user=user
        ).order_by('-joined_at').first()

        if participant:
            participant.left_at = None
            participant.is_removed = False
            participant.save(update_fields=["left_at", "is_removed"])
            # Remove any stray duplicate records
            MeetingParticipant.objects.filter(meeting=meeting, user=user).exclude(id=participant.id).delete()
        else:
            participant = MeetingParticipant.objects.create(
                meeting=meeting,
                user=user,
                role=ParticipantRole.HOST if meeting.host == user else ParticipantRole.ATTENDEE,
                joined_at=now,
            )

        name = user.full_name or user.get_full_name() or user.username or user.email.split("@")[0]
        initials = "".join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
        avatar = user.avatar if getattr(user, "avatar", None) and not user.avatar.startswith("preset:") else ""
        is_host = (meeting.host == user or participant.role == ParticipantRole.HOST)

        return {
            "id": str(user.id),
            "name": name,
            "initials": initials,
            "email": user.email,
            "avatar": avatar,
            "role": "Meeting host" if is_host else "Contributor",
            "is_host": is_host,
            "is_hand_raised": participant.is_hand_raised,
        }

    @database_sync_to_async
    def get_active_peers(self, meeting_id, current_user_id):
        meeting = Meeting.objects.get(id=meeting_id)
        active_ps = meeting.participants.filter(
            left_at__isnull=True,
            is_removed=False
        ).exclude(user_id=current_user_id).select_related("user")

        peers = []
        seen = set()
        for p in active_ps:
            if p.user_id in seen:
                continue
            seen.add(p.user_id)
            name = p.user.full_name or p.user.get_full_name() or p.user.username or p.user.email.split("@")[0]
            initials = "".join([part[0].upper() for part in name.split()[:2]]) or name[:1].upper()
            avatar = p.user.avatar if getattr(p.user, "avatar", None) and not p.user.avatar.startswith("preset:") else ""
            is_host = (meeting.host == p.user or p.role == ParticipantRole.HOST)
            peers.append({
                "id": str(p.user.id),
                "name": name,
                "initials": initials,
                "email": p.user.email,
                "avatar": avatar,
                "role": "Meeting host" if is_host else "Contributor",
                "is_host": is_host,
                "is_hand_raised": p.is_hand_raised,
            })
        return peers

    @database_sync_to_async
    def record_meeting_socket_connect(self, meeting_id, user_id):
        from django.core.cache import cache
        key = f"meeting_{meeting_id}_user_{user_id}_sockets"
        count = cache.get(key, 0) + 1
        cache.set(key, count, timeout=86400)
        return count

    @database_sync_to_async
    def record_meeting_socket_disconnect(self, meeting_id, user_id):
        from django.core.cache import cache
        key = f"meeting_{meeting_id}_user_{user_id}_sockets"
        count = cache.get(key, 1)
        new_count = max(0, count - 1)
        cache.set(key, new_count, timeout=86400)
        return new_count

    @database_sync_to_async
    def record_leave(self, meeting_id, user_id):
        now = timezone.now()
        MeetingParticipant.objects.filter(
            meeting_id=meeting_id,
            user_id=user_id,
            left_at__isnull=True
        ).update(left_at=now, is_hand_raised=False)

        # Clear socket count in cache upon explicit leave
        from django.core.cache import cache
        cache.delete(f"meeting_{meeting_id}_user_{user_id}_sockets")

    @database_sync_to_async
    def update_hand_raise(self, meeting_id, user_id, raised):
        MeetingParticipant.objects.filter(
            meeting_id=meeting_id,
            user_id=user_id,
            left_at__isnull=True
        ).update(is_hand_raised=bool(raised))

    @database_sync_to_async
    def eject_participant(self, meeting_id, target_user_id):
        now = timezone.now()
        MeetingParticipant.objects.filter(
            meeting_id=meeting_id,
            user_id=target_user_id,
            left_at__isnull=True
        ).update(
            is_removed=True,
            removed_at=now,
            left_at=now,
            is_hand_raised=False
        )

    @database_sync_to_async
    def end_call_session_if_active(self, meeting_id, user, reason=CallEndedReason.NORMAL):
        now = timezone.now()
        active_sessions = CallSession.objects.filter(
            meeting_id=meeting_id,
            status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
        )
        ended = False
        for session in active_sessions:
            session.status = CallStatus.ENDED
            session.ended_at = now
            session.ended_reason = reason
            session.save(update_fields=['status', 'ended_at', 'ended_reason'])
            ended = True
            logger.info(f"[CALL-DIAG] Consumer marked CallSession {session.id} as ENDED")
        return ended

    @database_sync_to_async
    def close_meeting_in_db(self, meeting_id, user=None):
        now = timezone.now()
        meeting = Meeting.objects.filter(id=meeting_id).first()
        if meeting:
            meeting.status = MeetingStatus.ENDED
            meeting.actual_end = now
            meeting.save(update_fields=["status", "actual_end", "updated_at"])
            meeting.participants.filter(left_at__isnull=True).update(left_at=now)

        # Also end any CallSessions
        CallSession.objects.filter(
            meeting_id=meeting_id,
            status__in=[CallStatus.RINGING, CallStatus.ACCEPTED, CallStatus.CONNECTED]
        ).update(status=CallStatus.ENDED, ended_at=now, ended_reason=CallEndedReason.NORMAL)


# ==============================================================================
# MEET HUB M1 — GLOBAL CALLING & RINGTONE CONSUMER
# ==============================================================================

class GlobalCallConsumer(AsyncJsonWebsocketConsumer):
    """
    Global Real-Time Call Signaling & Presence Consumer for AetherSpace.
    Maintains a persistent WebSocket connection across ALL authenticated pages
    (Dashboard, Tasks, Bugs, Chat, Meet Hub, Files, Settings, Profile, Admin).

    Responsibilities:
    - Real-time incoming call ringtone trigger & modal delivery across any tab/page.
    - Outgoing call state synchronization for multi-tab environments.
    - Accept, Decline, Cancel, and Timeout state transitions.
    - Active call re-hydration on connect (recovers ring state if page refreshed).
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            logger.warning("Global Call WebSocket rejected: unauthenticated user")
            await self.close(code=4001)
            return

        self.group_name = f"user_calls_{self.user.id}"

        # Join authenticated user's private call channel group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        # Join workspace presence groups for all active workspaces
        workspace_ids = await self.get_user_workspace_ids(self.user)
        self.workspace_groups = [f"workspace_presence_{wid}" for wid in workspace_ids]
        for wgroup in self.workspace_groups:
            await self.channel_layer.group_add(
                wgroup,
                self.channel_name
            )

        # Track active socket count and update heartbeat
        active_sockets = await self.record_socket_connect(self.user.id)

        await self.accept()
        # [CALL-DIAG] Log successful connection
        logger.info("[CALL-DIAG] GlobalCallConsumer CONNECTED user=%s group=%s channel=%s sockets=%s",
                    self.user.id, self.group_name, self.channel_name, active_sockets)

        # If this is the user's first active socket, broadcast online/preference status to peers
        if active_sockets == 1:
            presence_info = await self.get_user_presence_info(self.user)
            for wgroup in self.workspace_groups:
                await self.channel_layer.group_send(
                    wgroup,
                    {
                        "type": "presence_broadcast",
                        "user_id": str(self.user.id),
                        "status": presence_info["status"],
                        "status_message": presence_info["status_message"],
                        "sender_channel": self.channel_name,
                    }
                )

        # Re-hydrate active incoming or outgoing ringing call if user refreshed or navigated
        active_call = await self.fetch_active_call(self.user)
        if active_call:
            logger.info("[CALL-DIAG] GlobalCallConsumer RE-HYDRATING active call for user=%s type=%s",
                        self.user.id, active_call.get('type', 'unknown'))
            await self.send_json(active_call)
        else:
            logger.info("[CALL-DIAG] GlobalCallConsumer no active call for user=%s", self.user.id)

    async def disconnect(self, close_code):
        # [CALL-DIAG] Log disconnection
        logger.info("[CALL-DIAG] GlobalCallConsumer DISCONNECTED user=%s code=%s",
                    getattr(self, 'user', '?'), close_code)
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

        # Discard from workspace presence groups
        workspace_groups = getattr(self, "workspace_groups", [])
        for wgroup in workspace_groups:
            await self.channel_layer.group_discard(
                wgroup,
                self.channel_name
            )

        # Update socket tracking and broadcast offline ONLY when last socket disconnects
        if hasattr(self, "user") and self.user.is_authenticated:
            active_sockets = await self.record_socket_disconnect(self.user.id)
            logger.info("[CALL-DIAG] user=%s remaining active_sockets=%s", self.user.id, active_sockets)
            if active_sockets <= 0:
                for wgroup in workspace_groups:
                    await self.channel_layer.group_send(
                        wgroup,
                        {
                            "type": "presence_broadcast",
                            "user_id": str(self.user.id),
                            "status": "offline",
                            "status_message": "",
                            "sender_channel": self.channel_name,
                        }
                    )

    async def receive_json(self, content):
        """
        Handle client actions:
        - heartbeat: refreshes presence TTL in cache
        - initiate: starts a call to recipient
        - accept: recipient accepts incoming call
        - decline: recipient declines incoming call
        - cancel: caller cancels outgoing call
        - timeout: marks call missed after ringing duration
        """
        action = content.get("action")
        # [CALL-DIAG] Log all incoming WebSocket messages
        logger.info("[CALL-DIAG] GlobalCallConsumer RECEIVED action=%s user=%s content_keys=%s",
                    action, self.user.id, list(content.keys()))

        if action == "heartbeat":
            await self.record_heartbeat(self.user.id)
            return

        if action == "initiate":
            workspace_slug = content.get("workspace_slug")
            recipient_id = content.get("recipient_id")
            call_mode = content.get("call_mode", "VIDEO")
            conversation_id = content.get("conversation_id")
            res = await self.handle_initiate(workspace_slug, recipient_id, call_mode, conversation_id)
            if not res.get("success"):
                await self.send_json({
                    "type": "call_error",
                    "message": res.get("message", "Could not start call.")
                })

        elif action == "accept":
            call_id = content.get("call_id")
            res = await self.handle_accept(call_id)
            if not res.get("success"):
                await self.send_json({
                    "type": "call_error",
                    "message": res.get("message", "Could not accept call.")
                })

        elif action == "decline":
            call_id = content.get("call_id")
            reason = content.get("reason", "declined")
            await self.handle_decline(call_id, reason)

        elif action == "cancel":
            call_id = content.get("call_id")
            await self.handle_cancel(call_id)

        elif action == "timeout":
            call_id = content.get("call_id")
            await self.handle_timeout(call_id)

    # --------------------------------------------------------------------------
    # Channel Layer Event Relays (dispatched from services / group_send)
    # --------------------------------------------------------------------------

    async def call_incoming(self, event):
        """Forward incoming call to client."""
        # [CALL-DIAG] Log event relay
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_incoming RELAYING to user=%s call_id=%s caller=%s",
                    self.user.id, event.get('call_id', '?'), event.get('caller_name', '?'))
        await self.send_json(event)
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_incoming SENT to user=%s", self.user.id)

    async def call_outgoing(self, event):
        """Forward outgoing call state to client."""
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_outgoing RELAYING to user=%s call_id=%s",
                    self.user.id, event.get('call_id', '?'))
        await self.send_json(event)
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_outgoing SENT to user=%s", self.user.id)

    async def call_accepted(self, event):
        """Forward accepted call state to client (navigates to room)."""
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_accepted RELAYING to user=%s call_id=%s",
                    self.user.id, event.get('call_id', '?'))
        await self.send_json(event)
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_accepted SENT to user=%s", self.user.id)

    async def call_declined(self, event):
        """Forward declined call state to client."""
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_declined RELAYING to user=%s", self.user.id)
        await self.send_json(event)

    async def call_cancelled(self, event):
        """Forward cancelled call state to client."""
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_cancelled RELAYING to user=%s", self.user.id)
        await self.send_json(event)

    async def call_missed(self, event):
        """Forward missed call state to client."""
        logger.info("[CALL-DIAG] GlobalCallConsumer.call_missed RELAYING to user=%s", self.user.id)
        await self.send_json(event)

    async def presence_broadcast(self, event):
        """Forward presence change to client."""
        if event.get("sender_channel") == self.channel_name:
            return
        logger.info("[CALL-DIAG] GlobalCallConsumer.presence_broadcast RELAYING user=%s status=%s",
                    event.get("user_id"), event.get("status"))
        await self.send_json({
            "type": "presence_change",
            "user_id": event["user_id"],
            "status": event["status"],
            "status_message": event.get("status_message", ""),
        })

    # --------------------------------------------------------------------------
    # Database Operations (executed asynchronously via database_sync_to_async)
    # --------------------------------------------------------------------------

    @database_sync_to_async
    def fetch_active_call(self, user):
        from .services import get_active_call_for_user
        return get_active_call_for_user(user)

    @database_sync_to_async
    def handle_initiate(self, workspace_slug, recipient_id, call_mode, conversation_id):
        from django.contrib.auth import get_user_model
        from workspaces.models import Workspace
        from chat.models import DirectMessageConversation
        from core.models import ModuleStatus
        from .services import initiate_call_session

        # 0. Check Meet Hub operational status & maintenance gating
        status_obj = ModuleStatus.get_status_obj('meetings')
        if status_obj and not status_obj.is_available:
            return {"success": False, "message": status_obj.effective_message}

        User = get_user_model()
        workspace = Workspace.objects.filter(slug=workspace_slug).first()
        if not workspace:
            return {"success": False, "message": "Workspace not found."}

        recipient = User.objects.filter(id=recipient_id).first()
        if not recipient:
            return {"success": False, "message": "Recipient not found."}

        conversation = None
        if conversation_id:
            conversation = DirectMessageConversation.objects.filter(id=conversation_id).first()

        try:
            session = initiate_call_session(
                workspace=workspace,
                caller=self.user,
                recipient=recipient,
                call_mode=call_mode,
                conversation=conversation
            )
            return {"success": True, "call_id": session.id}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @database_sync_to_async
    def handle_accept(self, call_id):
        from .services import accept_call_session
        try:
            success, msg, room_url = accept_call_session(call_id, self.user)
            return {"success": success, "message": msg, "room_url": room_url}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @database_sync_to_async
    def handle_decline(self, call_id, reason):
        from .services import decline_call_session
        from .models import CallEndedReason
        reason_val = CallEndedReason.BUSY if reason == 'busy' else CallEndedReason.DECLINED
        try:
            return decline_call_session(call_id, self.user, reason=reason_val)
        except Exception as e:
            logger.warning(f"Error declining call {call_id}: {e}")
            return False, str(e)

    @database_sync_to_async
    def handle_cancel(self, call_id):
        from .services import cancel_call_session
        try:
            return cancel_call_session(call_id, self.user)
        except Exception as e:
            logger.warning(f"Error cancelling call {call_id}: {e}")
            return False, str(e)

    @database_sync_to_async
    def handle_timeout(self, call_id):
        from .services import timeout_call_session
        try:
            return timeout_call_session(call_id)
        except Exception as e:
            logger.warning(f"Error timing out call {call_id}: {e}")
            return False, str(e)

    @database_sync_to_async
    def get_user_workspace_ids(self, user):
        from workspaces.models import WorkspaceMembership, MembershipStatus
        return list(
            WorkspaceMembership.objects.filter(
                user=user,
                status=MembershipStatus.ACTIVE
            ).values_list('workspace_id', flat=True)
        )

    @database_sync_to_async
    def get_user_presence_info(self, user):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u = User.objects.filter(id=user.id).first() or user
        return {
            "status": u.availability_status,
            "status_message": u.status_message,
        }

    @database_sync_to_async
    def record_socket_connect(self, user_id):
        from django.core.cache import cache
        from django.utils import timezone
        count = cache.get(f"user_active_sockets_{user_id}", 0) + 1
        cache.set(f"user_active_sockets_{user_id}", count, timeout=86400)
        cache.set(f"user_last_seen_{user_id}", timezone.now().timestamp(), timeout=300)
        return count

    @database_sync_to_async
    def record_socket_disconnect(self, user_id):
        from django.core.cache import cache
        count = cache.get(f"user_active_sockets_{user_id}", 1)
        new_count = max(0, count - 1)
        cache.set(f"user_active_sockets_{user_id}", new_count, timeout=86400)
        if new_count == 0:
            cache.delete(f"user_last_seen_{user_id}")
        return new_count

    @database_sync_to_async
    def record_heartbeat(self, user_id):
        from django.core.cache import cache
        from django.utils import timezone
        cache.set(f"user_last_seen_{user_id}", timezone.now().timestamp(), timeout=300)


