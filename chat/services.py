from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from .models import (
    Channel, ChannelMembership, ChannelRole, PostingPermission,
    DirectMessageConversation, Message, MessageAttachment, MessageReaction
)


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
    between two workspace members. If a registered user is not yet a member
    of this workspace, auto-enroll them as a Contributor.
    """
    if user_a.id == user_b.id:
        raise ValidationError("Cannot create a direct message conversation with oneself.")

    from workspaces.models import WorkspaceMembership, WorkspaceRole, MembershipStatus
    if not workspace.has_user(user_a):
        WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=user_a,
            defaults={'role': WorkspaceRole.CONTRIBUTOR, 'status': MembershipStatus.ACTIVE}
        )
    if not workspace.has_user(user_b):
        WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=user_b,
            defaults={'role': WorkspaceRole.CONTRIBUTOR, 'status': MembershipStatus.ACTIVE}
        )

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
