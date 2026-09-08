import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from .models import Channel, DirectMessageConversation, Message, MessageReaction
from .services import post_channel_message, post_direct_message, toggle_reaction


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time WebSocket consumer for AetherSpace Chat.
    Handles channel broadcasts, 1-on-1 DM streaming, typing indicators, and emoji reactions.
    """

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        kwargs = self.scope["url_route"]["kwargs"]
        self.channel_id = kwargs.get("channel_id")
        self.conversation_id = kwargs.get("conversation_id")

        if self.channel_id:
            has_perm = await self.check_channel_access(self.channel_id, self.user)
            if not has_perm:
                await self.close(code=4003)
                return
            self.room_group_name = f"chat_channel_{self.channel_id}"

        elif self.conversation_id:
            has_perm = await self.check_dm_access(self.conversation_id, self.user)
            if not has_perm:
                await self.close(code=4003)
                return
            self.room_group_name = f"chat_dm_{self.conversation_id}"

        else:
            await self.close(code=4000)
            return

        # Join the channel layer group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Send connection established event
        await self.send_json({
            "type": "connection_status",
            "status": "connected",
            "user_id": str(self.user.id),
        })

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get("type", "chat_message")

        if msg_type in ("chat_message", "send_message"):
            text = content.get("content", "").strip()
            if not text:
                return

            try:
                msg_data = await self.save_message(text)
                # Broadcast message to all group participants
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat_broadcast",
                        "event": "new_message",
                        "message": msg_data,
                    }
                )
            except Exception as e:
                await self.send_json({
                    "type": "error",
                    "message": str(e),
                })


        elif msg_type == "typing":
            # Broadcast typing indicator
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_broadcast",
                    "event": "typing",
                    "user_id": str(self.user.id),
                    "user_name": self.user.full_name or self.user.email,
                }
            )

        elif msg_type == "reaction":
            message_id = content.get("message_id")
            emoji = content.get("emoji", "").strip()
            if message_id and emoji:
                reaction_data = await self.handle_reaction(message_id, emoji)
                if reaction_data:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            "type": "chat_broadcast",
                            "event": "reaction_updated",
                            "data": reaction_data,
                        }
                    )

    async def chat_broadcast(self, event):
        """Pass group broadcast messages down to WebSocket client."""
        await self.send_json(event)

    @database_sync_to_async
    def check_channel_access(self, channel_id, user):
        try:
            channel = Channel.objects.select_related("workspace").get(id=channel_id)
            return channel.has_member(user)
        except Channel.DoesNotExist:
            return False

    @database_sync_to_async
    def check_dm_access(self, conversation_id, user):
        try:
            conv = DirectMessageConversation.objects.select_related("workspace").get(id=conversation_id)
            return conv.has_participant(user)
        except DirectMessageConversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, text):
        if self.channel_id:
            channel = Channel.objects.select_related("workspace").get(id=self.channel_id)
            msg = post_channel_message(channel, self.user, content=text)
        else:
            conv = DirectMessageConversation.objects.select_related("workspace", "participant1", "participant2").get(id=self.conversation_id)
            msg = post_direct_message(conv, self.user, content=text)

        sender_initial = (self.user.full_name or self.user.email)[:1].upper()
        return {
            "id": str(msg.id),
            "content": msg.content,
            "sender_id": str(self.user.id),
            "sender_name": self.user.full_name or self.user.email,
            "sender_initial": sender_initial,
            "created_at": msg.created_at.strftime("%I:%M %p"),
            "is_pinned": msg.is_pinned,
            "attachments": [],
            "reactions": {},
        }

    @database_sync_to_async
    def handle_reaction(self, message_id, emoji):
        try:
            msg = Message.objects.select_related("workspace").get(id=message_id)
            added, count = toggle_reaction(msg, self.user, emoji)
            return {
                "message_id": str(msg.id),
                "emoji": emoji,
                "user_id": str(self.user.id),
                "added": added,
                "total_count": count,
            }
        except (Message.DoesNotExist, PermissionDenied):
            return None
