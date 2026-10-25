# Module 05: Chat & Team Messaging

## 1. Purpose
Provides real-time team communication, public/private discussion channels, 1-on-1 direct messages, file attachments, emoji reactions, message pinning, and in-chat audio/video calling triggers.

## 2. Implementation Status
* **Status**: **Implemented and Tested**
* **Evidence**: `chat/models.py`, `chat/views.py`, `chat/consumers.py`, `chat/routing.py`, `chat/tests.py`.

## 3. Main User Workflows
1. **Channel Discussion**: Team members navigate to workspace channels (`#general`, `#dev-updates`).
2. **Real-Time Messaging**: Messages post and deliver in real-time over WebSockets without page reload (`ChatConsumer`).
3. **1-on-1 Direct Messaging (DM)**: Users message peers directly. System maintains canonical user-pair ordering in `DirectMessageConversation`.
4. **Emoji Reactions**: Users add reactions (👍, ❤️, 🚀, 👀); reactions group reactively with total counts.
5. **Asset Pinning & Attachments**: Important messages are pinned (`is_pinned=True`) for quick access in the channel details drawer. Files stream to Supabase Storage.
6. **Channel Visual Identity**: Space owners/admins configure custom channel identity in Channel Details:
   - Curated built-in icons (14 options: `#`, `</>`, `🚀`, `✨`, `📢`, `💬`, `💼`, `💡`, `🪲`, `📁`, `🔒`, `🌐`, `🛡️`, `🧊`) selected via compact responsive grid (4 cols mobile, 6 cols desktop).
   - Custom square image uploads (PNG/JPG/WEBP/SVG up to 2MB).
   - Default initials/hash fallback with seamless one-click reset.
   - Enforced backend allowlist validation (`ALLOWED_CHANNEL_ICONS`) and server-side RBAC.
7. **In-Chat Calling Trigger**:
   - In Channels: Form submit posts a joinable meeting card to the stream and redirects host to room.
   - In DMs: Click Voice / Video button dispatches `aetherspace:initiate_call` CustomEvent, ringing peer globally.

## 4. User Roles & Permissions
* **Workspace Admin & Manager**: Can create channels, archive channels, pin messages, and post in `ADMIN_ONLY` restricted announcement channels.
* **Workspace Contributor**: Can join public channels, send messages, attach files, add reactions, and initiate 1-on-1 DMs. Private channels require an invitation.

## 5. Pages & Templates
* `templates/chat/channel_view.html`: Channel stream, message input, live status indicator, and header actions.
* `templates/chat/direct_message.html`: 1-on-1 DM thread with Google Chat-style audio/video calling buttons.
* `templates/chat/channel_details.html`: Channel members, pinned assets, and topic management.
* `templates/chat/shared_files.html`: In-chat file browser.

## 6. URLs, Views, Services & Models
* **URLs**: `chat/urls.py` (`channel_view`, `dm_view`, `create_channel`, `channel_members`, `pinned_assets`).
* **Views**: `chat/views.py` (`channel_view`, `direct_message_view`, `post_message_api`).
* **Consumers**: `chat/consumers.py` (`ChatConsumer` at `ws/chat/c/<id>/` and `ws/chat/dm/<id>/`).
* **Models**: `Channel`, `ChannelMembership`, `DirectMessageConversation`, `Message`, `MessageAttachment`, `MessageReaction`.

## 7. Business Rules & Invariants
* Deterministic DM Pairing: `DirectMessageConversation.clean()` enforces `participant1.id < participant2.id` to guarantee that exactly one conversation exists per pair.
* Soft Deletion: Deleted messages set `is_deleted = True` rather than removing records from PostgreSQL.
* Content Sanitization: All message bodies pass through `bleach.clean()` to neutralize malicious scripts before broadcasting.

## 8. Database Relationships
* `Channel` belongs to `Workspace` (CASCADE).
* `DirectMessageConversation` belongs to `Workspace` (CASCADE).
* `Message` belongs to `Workspace` and optionally `Channel` or `DirectMessageConversation`.
* `Message` has many `MessageAttachment` and `MessageReaction` (CASCADE).

## 9. API & WebSocket Interactions
* **WebSocket Routes**:
  - `ws/chat/c/<uuid:channel_id>/`
  - `ws/chat/dm/<uuid:conversation_id>/`
* **JSON Event Payload**:
  ```json
  {
    "type": "chat_message",
    "message": "Hello team!",
    "sender_id": "<uuid>",
    "sender_name": "Alex Chen",
    "avatar": "...",
    "created_at": "2026-10-10T12:00:00Z"
  }
  ```

## 10. Notifications & Integrations
* Mentions (@Alex) extract contributor IDs and trigger `NotificationCategory.MENTION` alerts.
* Unread badges compute dynamically using `ChannelMembership.last_read_at`.

## 11. Error States & Edge Cases
* Posting to private channel without membership -> `403 Forbidden` / WebSocket code `4003`.
* Disconnected WebSocket -> Alpine.js toggles status badge to "Polling" and falls back to HTTP interval fetching.

## 12. Tests & Verification Evidence
* `chat/tests.py`: Unit tests covering channel access control, DM canonical pairing, message broadcasting, and emoji reactions.

## 13. Known Limitations
* Rich text editor uses formatted Markdown and Alpine.js preview rather than a heavy WYSIWYG editor.

## 14. Future Work
* Threaded message replies (Slack-style side drawer).
