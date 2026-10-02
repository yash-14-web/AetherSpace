import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.db.models import Q
from workspaces.models import Workspace, WorkspaceMembership, MembershipStatus
from .models import Meeting, MeetingParticipant, MeetingStatus, ParticipantRole

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

        # Broadcast peer_joined to all other participants in the room
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
            # Notify peers that this user left
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "room_peer_left",
                    "peer_id": str(self.user.id),
                    "peer_name": getattr(self, "user_display_name", str(self.user)),
                    "sender_channel": self.channel_name,
                }
            )

            # Record leave in database
            if hasattr(self, "meeting_id"):
                await self.record_leave(self.meeting_id, self.user.id)

            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get("type")
        sender_id = str(self.user.id)

        # 1. Peer-to-Peer WebRTC Signaling: Offer
        if msg_type == "signal_offer":
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

        # 2. Peer-to-Peer WebRTC Signaling: Answer
        elif msg_type == "signal_answer":
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

        # 3. Peer-to-Peer WebRTC Signaling: ICE Candidate
        elif msg_type == "signal_ice":
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

        # 9. Host Action: End Meeting for All
        elif msg_type == "end_meeting":
            if self.is_host:
                await self.close_meeting_in_db(self.meeting_id)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "room_meeting_ended",
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

    async def room_meeting_ended(self, event):
        """Notifies all participants that the host has ended the meeting."""
        await self.send_json({
            "type": "meeting_ended",
            "message": "This meeting has been ended by the host.",
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

        participant, _ = MeetingParticipant.objects.get_or_create(
            meeting=meeting,
            user=user,
            defaults={
                "role": ParticipantRole.HOST if meeting.host == user else ParticipantRole.ATTENDEE,
                "joined_at": now,
            }
        )
        participant.left_at = None
        participant.is_removed = False
        participant.save(update_fields=["left_at", "is_removed"])

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
        for p in active_ps:
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
    def record_leave(self, meeting_id, user_id):
        now = timezone.now()
        MeetingParticipant.objects.filter(
            meeting_id=meeting_id,
            user_id=user_id,
            left_at__isnull=True
        ).update(left_at=now, is_hand_raised=False)

        # If no active participants remain, close meeting
        meeting = Meeting.objects.filter(id=meeting_id).first()
        if meeting and not meeting.participants.filter(left_at__isnull=True).exists():
            meeting.status = MeetingStatus.ENDED
            meeting.actual_end = now
            meeting.save(update_fields=["status", "actual_end", "updated_at"])

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
    def close_meeting_in_db(self, meeting_id):
        now = timezone.now()
        meeting = Meeting.objects.filter(id=meeting_id).first()
        if meeting:
            meeting.status = MeetingStatus.ENDED
            meeting.actual_end = now
            meeting.save(update_fields=["status", "actual_end", "updated_at"])
            meeting.participants.filter(left_at__isnull=True).update(left_at=now)
