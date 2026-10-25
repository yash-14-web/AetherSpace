import os
import io
import logging
from PIL import Image

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from files.services import SupabaseStorageService
from .models import (
    Channel, ChannelMembership, ChannelRole, PostingPermission,
    DirectMessageConversation, Message, MessageAttachment, MessageReaction
)

logger = logging.getLogger(__name__)

MAX_CHANNEL_AVATAR_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB hard limit
ALLOWED_CHANNEL_AVATAR_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'svg', 'gif'}
ALLOWED_CHANNEL_ICONS = {
    'hash', 'terminal', 'rocket', 'sparkles', 'megaphone', 'chat',
    'briefcase', 'bulb', 'bug', 'folder', 'lock', 'globe', 'shield', 'cube'
}


def ensure_default_channels(workspace, creator=None):
    """
    Ensure standard default channels exist for the workspace:
    - #general: General workspace-wide team chat
    - #project-updates: Important milestone and sprint updates
    """
    defaults = [
        {
            'name': 'general',
            'topic': 'General team discussions, announcements, and watercooler chat.',
            'description': 'Default public channel for all team members.',
            'who_can_post': PostingPermission.ALL,
        },
        {
            'name': 'project-updates',
            'topic': 'All important updates, sprint milestones, and deployment announcements.',
            'description': 'Channel dedicated to project status and delivery updates.',
            'who_can_post': PostingPermission.ADMIN_ONLY,
        },
    ]

    channels = []
    for d in defaults:
        channel, created = Channel.objects.get_or_create(
            workspace=workspace,
            slug=d['name'],
            defaults={
                'name': d['name'],
                'topic': d['topic'],
                'description': d['description'],
                'is_private': False,
                'who_can_post': d['who_can_post'],
                'created_by': creator,
            }
        )
        if created and creator:
            ChannelMembership.objects.get_or_create(
                channel=channel,
                user=creator,
                defaults={'role': ChannelRole.OWNER}
            )
        channels.append(channel)
    return channels


def get_or_create_dm_conversation(workspace, user_a, user_b):
    """
    Deterministically retrieve or create a 1-on-1 direct message conversation
    between two registered users within a workspace chat context.
    Does NOT auto-enroll external participants into the workspace membership roster.
    """
    if user_a.id == user_b.id:
        raise ValidationError("Cannot create a direct message conversation with oneself.")

    p1, p2 = (user_a, user_b) if str(user_a.id) < str(user_b.id) else (user_b, user_a)

    conversation, _ = DirectMessageConversation.objects.get_or_create(
        workspace=workspace,
        participant1=p1,
        participant2=p2,
    )
    return conversation



@transaction.atomic
def post_channel_message(channel, sender, content='', files=None):
    """
    Send a message to a workspace channel with permission validation.
    """
    if not channel.can_post(sender):
        raise PermissionDenied("You do not have permission to post in this channel.")

    clean_content = (content or '').strip()
    if not clean_content and not files:
        raise ValidationError("Message content or attachment is required.")

    message = Message.objects.create(
        workspace=channel.workspace,
        channel=channel,
        sender=sender,
        content=clean_content,
    )

    if files:
        for f in files:
            is_img = f.content_type.startswith('image/') if hasattr(f, 'content_type') and f.content_type else False
            MessageAttachment.objects.create(
                message=message,
                file=f,
                file_name=f.name,
                file_size=f.size,
                mime_type=getattr(f, 'content_type', '') or '',
                is_image=is_img,
            )

    # Update sender's last_read_at in channel
    ChannelMembership.objects.filter(channel=channel, user=sender).update(last_read_at=timezone.now())

    # Detect mentions in message content
    try:
        import re
        from django.contrib.auth import get_user_model
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        User = get_user_model()

        mentions = re.findall(r'@([a-zA-Z0-9_.+-]+)', clean_content)
        if mentions:
            sender_name = sender.full_name or sender.get_full_name() or sender.username or sender.email
            for m in set(mentions):
                user_match = User.objects.filter(
                    Q(username__iexact=m) | Q(contributor_id__iexact=m) | Q(email__iexact=m) | Q(first_name__iexact=m) | Q(full_name__iexact=m),
                    workspace_memberships__workspace=channel.workspace,
                    workspace_memberships__status='ACTIVE'
                ).exclude(id=sender.id).first()

                if user_match:
                    create_notification(
                        recipient=user_match,
                        category=NotificationCategory.MENTION,
                        notification_type=NotificationType.CHAT_MENTION,
                        title=f"{sender_name} mentioned you in #{channel.name}",
                        body=clean_content[:120],
                        workspace=channel.workspace,
                        actor=sender,
                        action_url=f"/chat/w/{channel.workspace.slug}/c/{channel.slug}/"
                    )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to create chat mention notification: {e}")

    return message


@transaction.atomic
def post_direct_message(conversation, sender, content='', files=None):
    """
    Send a 1-on-1 direct message between workspace participants.
    """
    if not conversation.has_participant(sender):
        raise PermissionDenied("You are not a participant in this direct message conversation.")

    clean_content = (content or '').strip()
    if not clean_content and not files:
        raise ValidationError("Message content or attachment is required.")

    recipient = conversation.get_other_participant(sender)

    message = Message.objects.create(
        workspace=conversation.workspace,
        conversation=conversation,
        sender=sender,
        recipient=recipient,
        content=clean_content,
    )

    if files:
        for f in files:
            is_img = f.content_type.startswith('image/') if hasattr(f, 'content_type') and f.content_type else False
            MessageAttachment.objects.create(
                message=message,
                file=f,
                file_name=f.name,
                file_size=f.size,
                mime_type=getattr(f, 'content_type', '') or '',
                is_image=is_img,
            )

    # Touch conversation updated_at for ordering
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=['updated_at'])

    # Notify DM recipient
    try:
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        sender_name = sender.full_name or sender.get_full_name() or sender.username or sender.email
        create_notification(
            recipient=recipient,
            category=NotificationCategory.MENTION,
            notification_type=NotificationType.CHAT_DM,
            title=f"New message from {sender_name}",
            body=clean_content[:120] if clean_content else "Sent an attachment",
            workspace=conversation.workspace,
            actor=sender,
            action_url=f"/chat/w/{conversation.workspace.slug}/dm/{sender.id}/"
        )
    except Exception:
        pass

    return message


def toggle_pin_message(message, user):
    """
    Toggle pinned status of a message.
    Admins, managers, or channel owners/admins can pin channel messages.
    Either participant can pin in a DM conversation.
    """
    membership = message.workspace.get_user_membership(user)
    if not membership:
        raise PermissionDenied("You must be a member of the workspace.")

    if message.channel:
        can_pin = (
            membership.is_admin or
            membership.is_manager or
            message.channel.created_by_id == user.id or
            message.channel.memberships.filter(user=user, role__in=[ChannelRole.OWNER, ChannelRole.ADMIN]).exists()
        )
        if not can_pin:
            raise PermissionDenied("Only workspace Admins, Managers, or channel moderators can pin messages.")
    elif message.conversation:
        if not message.conversation.has_participant(user):
            raise PermissionDenied("You must be a participant to pin messages in this conversation.")

    if message.is_pinned:
        message.is_pinned = False
        message.pinned_by = None
        message.pinned_at = None
    else:
        message.is_pinned = True
        message.pinned_by = user
        message.pinned_at = timezone.now()

    message.save(update_fields=['is_pinned', 'pinned_by', 'pinned_at'])
    return message.is_pinned


def toggle_reaction(message, user, emoji):
    """
    Toggle an emoji reaction on a message. Returns (added: bool, total_count: int).
    """
    if not emoji or not isinstance(emoji, str):
        raise ValidationError("Emoji reaction cannot be empty.")

    emoji = emoji.strip()
    if not emoji:
        raise ValidationError("Emoji reaction cannot be empty.")

    if len(emoji) > 32:
        raise ValidationError("Emoji reaction exceeds maximum allowed length.")

    if not message.workspace.has_user(user):
        raise PermissionDenied("User is not a member of this workspace.")

    reaction = MessageReaction.objects.filter(message=message, user=user, emoji=emoji).first()
    if reaction:
        reaction.delete()
        added = False
    else:
        MessageReaction.objects.create(message=message, user=user, emoji=emoji)
        added = True

    count = MessageReaction.objects.filter(message=message, emoji=emoji).count()
    return added, count


def mark_channel_as_read(channel, user):
    """Mark a channel as read by updating last_read_at."""
    if not user.is_authenticated:
        return
    membership, _ = ChannelMembership.objects.get_or_create(
        channel=channel,
        user=user,
        defaults={'role': ChannelRole.MEMBER}
    )
    membership.last_read_at = timezone.now()
    membership.save(update_fields=['last_read_at'])


DEFAULT_CHANNEL_SLUGS = ('general', 'project-updates')


def is_default_channel(channel):
    """Check if the channel is a protected default workspace channel."""
    return channel.slug in DEFAULT_CHANNEL_SLUGS


def can_manage_channel(channel, user):
    """
    Check if user has administrative rights over the channel:
    - Workspace Admin or Manager
    - Channel Creator
    - Channel Owner or Admin
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True

    ws_membership = channel.workspace.get_user_membership(user)
    if not ws_membership or ws_membership.status != 'ACTIVE':
        return False

    if ws_membership.is_admin or ws_membership.is_manager:
        return True

    if channel.created_by_id == user.id:
        return True

    return channel.memberships.filter(
        user=user,
        role__in=[ChannelRole.OWNER, ChannelRole.ADMIN]
    ).exists()


def can_delete_channel(channel, user):
    """
    Check if user has rights to delete the space:
    - Default channels cannot be deleted
    - Must be workspace Admin/Manager, Channel Creator, or Channel Owner
    """
    if is_default_channel(channel):
        return False

    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True

    ws_membership = channel.workspace.get_user_membership(user)
    if not ws_membership or ws_membership.status != 'ACTIVE':
        return False

    if ws_membership.is_admin or ws_membership.is_manager:
        return True

    if channel.created_by_id == user.id:
        return True

    return channel.memberships.filter(
        user=user,
        role=ChannelRole.OWNER
    ).exists()


@transaction.atomic
def add_channel_member(channel, user_to_add, added_by, role=ChannelRole.MEMBER):
    """
    Add a user to a channel.
    - User must be a member of the workspace.
    - If private channel, added_by must have permission to manage the channel.
    """
    if not channel.workspace.has_user(user_to_add):
        raise ValidationError("User is not an active member of this workspace.")

    if channel.is_private and not can_manage_channel(channel, added_by):
        raise PermissionDenied("You do not have permission to invite members to this private space.")

    membership, created = ChannelMembership.objects.get_or_create(
        channel=channel,
        user=user_to_add,
        defaults={'role': role}
    )

    if not created and membership.role != role:
        membership.role = role
        membership.save(update_fields=['role'])

    # Optional: Send notification
    try:
        from notifications.services import create_notification
        from notifications.models import NotificationCategory, NotificationType
        actor_name = added_by.full_name or added_by.email
        create_notification(
            recipient=user_to_add,
            category=NotificationCategory.WORKSPACE,
            notification_type=NotificationType.WORKSPACE_INVITE,
            title=f"Added to #{channel.name}",
            body=f"{actor_name} added you to the #{channel.name} space.",
            workspace=channel.workspace,
            actor=added_by,
            action_url=f"/chat/w/{channel.workspace.slug}/c/{channel.slug}/"
        )
    except Exception:
        pass

    return membership, created


@transaction.atomic
def remove_channel_member(channel, user_to_remove, removed_by):
    """
    Remove a member from a channel.
    - removed_by must have permission to manage the channel.
    - Cannot remove the channel creator or sole owner.
    """
    if not can_manage_channel(channel, removed_by):
        raise PermissionDenied("You do not have permission to remove members from this space.")

    if channel.created_by_id == user_to_remove.id:
        raise ValidationError("The space creator cannot be removed from the channel.")

    mem = channel.memberships.filter(user=user_to_remove).first()
    if not mem:
        return False

    if mem.role == ChannelRole.OWNER:
        owner_count = channel.memberships.filter(role=ChannelRole.OWNER).count()
        if owner_count <= 1:
            raise ValidationError("Cannot remove the sole space owner. Transfer ownership first.")

    mem.delete()
    return True


@transaction.atomic
def leave_channel(channel, user):
    """
    Voluntarily leave a channel.
    - Cannot leave default channels (#general, #project-updates).
    - Sole owner of a private channel cannot leave without transferring ownership.
    """
    if is_default_channel(channel):
        raise ValidationError("You cannot leave default workspace channels.")

    mem = channel.memberships.filter(user=user).first()
    if not mem:
        return False

    if mem.role == ChannelRole.OWNER:
        owner_count = channel.memberships.filter(role=ChannelRole.OWNER).count()
        if owner_count <= 1:
            raise ValidationError("You are the sole owner of this space. Please assign another owner or delete the space.")

    mem.delete()
    return True


@transaction.atomic
def delete_channel(channel, deleted_by):
    """
    Delete a channel and all associated resources.
    - Default channels cannot be deleted.
    - deleted_by must have deletion rights.
    """
    if is_default_channel(channel):
        raise ValidationError("Default workspace channels (#general, #project-updates) cannot be deleted.")

    if not can_delete_channel(channel, deleted_by):
        raise PermissionDenied("You do not have permission to delete this space.")

    channel_name = channel.name
    channel.delete()
    return channel_name


def process_and_save_channel_avatar(channel, file_obj=None, avatar_url=None, icon_key=None, remove_avatar=False):
    """
    Process, validate, compress, and store the channel avatar or selected icon:
    1. If remove_avatar is True: Clears both channel.avatar and channel.icon, restoring default identity.
    2. If icon_key is provided: Validates against ALLOWED_CHANNEL_ICONS, clears old avatar file,
       and updates channel.icon.
    3. If avatar_url is provided: Validates the external/cloud URL, clears icon, and updates channel.avatar.
    4. If file_obj is provided: Validates size (<= 2 MB) and format, optimizes raster images,
       clears icon, and stores in Supabase Storage (with local fallback).
    """
    if remove_avatar:
        old_avatar = channel.avatar
        if old_avatar and not old_avatar.startswith(('http://', 'https://')):
            try:
                clean_path = old_avatar.lstrip('/')
                if clean_path.startswith('media/'):
                    clean_path = clean_path[len('media/'):]
                if default_storage.exists(clean_path):
                    default_storage.delete(clean_path)
            except Exception as e:
                logger.warning(f"Failed deleting old avatar {old_avatar}: {e}")

        channel.avatar = ''
        channel.icon = ''
        channel.save(update_fields=['avatar', 'icon'])
        return True, "Channel visual identity reset to default."

    if icon_key is not None:
        clean_key = str(icon_key).strip().lower().replace('icon:', '')
        if clean_key:
            if clean_key not in ALLOWED_CHANNEL_ICONS:
                return False, f"Invalid icon identifier '{clean_key}'. Please select a supported icon."
            # Clear previous raster avatar file if present
            if channel.avatar:
                old_avatar = channel.avatar
                if old_avatar and not old_avatar.startswith(('http://', 'https://')):
                    try:
                        clean_path = old_avatar.lstrip('/')
                        if clean_path.startswith('media/'):
                            clean_path = clean_path[len('media/'):]
                        if default_storage.exists(clean_path):
                            default_storage.delete(clean_path)
                    except Exception as e:
                        logger.warning(f"Failed deleting old avatar {old_avatar}: {e}")
                channel.avatar = ''
            channel.icon = clean_key
            channel.save(update_fields=['icon', 'avatar'])
            return True, f"Channel icon updated to '{clean_key}'."

    if avatar_url:
        from core.utils import validate_image_url
        is_valid, clean_url, err_msg = validate_image_url(avatar_url)
        if not is_valid:
            return False, err_msg or "Please enter a valid HTTP/HTTPS image URL."
        channel.avatar = clean_url
        channel.icon = ''
        channel.save(update_fields=['avatar', 'icon'])
        return True, "Channel avatar URL updated successfully."

    if file_obj:
        if file_obj.size > MAX_CHANNEL_AVATAR_SIZE_BYTES:
            size_kb = round(file_obj.size / 1024)
            return False, f"File size ({size_kb} KB) exceeds the maximum allowed limit of 2 MB."

        ext = os.path.splitext(file_obj.name)[1].lstrip('.').lower()
        if ext not in ALLOWED_CHANNEL_AVATAR_EXTENSIONS:
            return False, f"Unsupported file format '.{ext}'. Allowed formats: PNG, JPG, WEBP, SVG, GIF."

        try:
            content_type = 'image/png'
            filename = f"avatar_{channel.slug}.png"
            final_bytes = None

            if ext == 'svg':
                file_obj.seek(0)
                svg_content = file_obj.read()
                svg_text = svg_content.decode('utf-8', errors='ignore')
                if '<script' in svg_text.lower():
                    return False, "SVG files containing scripts are rejected for security."
                content_type = 'image/svg+xml'
                filename = f"avatar_{channel.slug}.svg"
                final_bytes = svg_content
            else:
                file_obj.seek(0)
                image = Image.open(file_obj)

                if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                    image = image.convert('RGBA')
                    save_format = 'PNG'
                    content_type = 'image/png'
                    filename = f"avatar_{channel.slug}.png"
                else:
                    image = image.convert('RGB')
                    save_format = 'JPEG'
                    content_type = 'image/jpeg'
                    filename = f"avatar_{channel.slug}.jpg"

                width, height = image.size
                min_dim = min(width, height)
                left = (width - min_dim) / 2
                top = (height - min_dim) / 2
                right = (width + min_dim) / 2
                bottom = (height + min_dim) / 2
                image = image.crop((left, top, right, bottom))
                image.thumbnail((256, 256), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                if save_format == 'PNG':
                    image.save(buffer, format='PNG', optimize=True)
                else:
                    image.save(buffer, format='JPEG', quality=90, optimize=True)
                final_bytes = buffer.getvalue()

            content_file = ContentFile(final_bytes)
            uploaded_storage_path = SupabaseStorageService.upload_file(
                file_obj=content_file,
                workspace_id=str(channel.workspace_id),
                filename=filename,
                content_type=content_type
            )

            # Ensure local storage also has a copy for instant fallback & local development
            if default_storage.exists(uploaded_storage_path):
                default_storage.delete(uploaded_storage_path)
            saved_local = default_storage.save(uploaded_storage_path, ContentFile(final_bytes))

            if SupabaseStorageService.is_supabase_configured():
                from urllib.parse import quote
                base_url = settings.SUPABASE_URL.rstrip('/')
                bucket = quote(settings.SUPABASE_STORAGE_BUCKET)
                public_url = f"{base_url}/storage/v1/object/public/{bucket}/{uploaded_storage_path}"
            else:
                channel.avatar = default_storage.url(saved_local)

            channel.icon = ''
            channel.save(update_fields=['avatar', 'icon'])
            return True, "Channel avatar uploaded successfully."
        except Exception as e:
            logger.error(f"Error processing channel avatar for {channel}: {e}", exc_info=True)
            return False, f"Failed to process image: {str(e)}"

    return True, "No changes made."


