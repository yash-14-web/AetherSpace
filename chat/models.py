import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify


class ChannelRole(models.TextChoices):
    OWNER = 'OWNER', 'Owner'
    ADMIN = 'ADMIN', 'Admin'
    MEMBER = 'MEMBER', 'Member'


class PostingPermission(models.TextChoices):
    ALL = 'ALL', 'All members'
    ADMIN_ONLY = 'ADMIN_ONLY', 'Admins & Managers only'


class Channel(models.Model):
    """
    Workspace-scoped discussion channel (e.g. #general, #project-updates, #dev-discussion).
    Supports public (open to all workspace members) and private (invite-only) channels.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='channels'
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True, default='')
    topic = models.CharField(max_length=255, blank=True, default='')
    is_private = models.BooleanField(default=False)
    who_can_post = models.CharField(
        max_length=20,
        choices=PostingPermission.choices,
        default=PostingPermission.ALL
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_channels'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'slug'],
                name='unique_workspace_channel_slug'
            )
        ]
        indexes = [
            models.Index(fields=['workspace', 'slug']),
            models.Index(fields=['workspace', 'is_private']),
        ]

    def __str__(self):
        return f"#{self.name} in {self.workspace.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            clean_name = self.name.lstrip('#').strip().lower()
            base_slug = slugify(clean_name) or 'channel'
            slug = base_slug
            counter = 1
            while Channel.objects.filter(workspace=self.workspace, slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return f"#{self.name.lstrip('#')}"

    @property
    def member_count(self):
        if not self.is_private:
            return self.workspace.memberships.filter(status='ACTIVE').count()
        return self.memberships.count()

    @property
    def pinned_count(self):
        return self.messages.filter(is_pinned=True, is_deleted=False).count()

    @property
    def files_count(self):
        return MessageAttachment.objects.filter(message__channel=self, message__is_deleted=False).count()

    def has_member(self, user):
        """Check if user has access to this channel."""
        if not user.is_authenticated:
            return False
        # Must belong to workspace first
        if not self.workspace.has_user(user):
            return False
        # Public channels are accessible to all workspace members
        if not self.is_private:
            return True
        # Admins can access any channel in their workspace
        membership = self.workspace.get_user_membership(user)
        if membership and (membership.is_admin or membership.is_manager):
            return True
        return self.memberships.filter(user=user).exists()

    def can_post(self, user):
        """Determine if a user can send messages to this channel."""
        if not self.has_member(user):
            return False
        if self.who_can_post == PostingPermission.ALL:
            return True
        # Restricted to Admins & Managers
        membership = self.workspace.get_user_membership(user)
        if membership and (membership.is_admin or membership.is_manager):
            return True
        return self.memberships.filter(user=user, role__in=[ChannelRole.OWNER, ChannelRole.ADMIN]).exists()


class ChannelMembership(models.Model):
    """
    Explicit membership record for a user in a channel.
    Tracks join date, channel-level role, and read position for unread counting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='channel_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=ChannelRole.choices,
        default=ChannelRole.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['joined_at']
        constraints = [
            models.UniqueConstraint(
                fields=['channel', 'user'],
                name='unique_channel_membership'
            )
        ]

    def __str__(self):
        return f"{self.user} in {self.channel} ({self.role})"


class DirectMessageConversation(models.Model):
    """
    1-on-1 private messaging thread between two workspace members.
    Ensures deterministic user ordering so exactly one thread exists per user pair.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='dm_conversations'
    )
    participant1 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dm_threads_as_p1'
    )
    participant2 = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dm_threads_as_p2'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'participant1', 'participant2'],
                name='unique_workspace_dm_pair'
            )
        ]

    def __str__(self):
        return f"DM: {self.participant1} & {self.participant2} ({self.workspace.name})"

    def clean(self):
        super().clean()
        # Enforce canonical ordering of participant IDs to prevent duplicate reversed threads
        if str(self.participant1_id) > str(self.participant2_id):
            self.participant1, self.participant2 = self.participant2, self.participant1

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def get_other_participant(self, user):
        """Return the other participant in this 1-on-1 conversation."""
        if self.participant1_id == user.id:
            return self.participant2
        return self.participant1

    def has_participant(self, user):
        return user.id in (self.participant1_id, self.participant2_id)


class Message(models.Model):
    """
    Chat message belonging to either a Channel or a DirectMessageConversation.
    Supports file attachments, emoji reactions, message pinning, and soft deletion.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    channel = models.ForeignKey(
        Channel,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='messages'
    )
    conversation = models.ForeignKey(
        DirectMessageConversation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_chat_messages'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='received_chat_messages'
    )
    content = models.TextField(blank=True, default='')
    is_pinned = models.BooleanField(default=False, db_index=True)
    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pinned_messages'
    )
    pinned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['channel', 'created_at']),
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['workspace', 'is_pinned']),
        ]

    def __str__(self):
        target = self.channel.display_name if self.channel else f"DM with {self.recipient}"
        return f"{self.sender} in {target}: {self.content[:30]}"

    @property
    def has_attachments(self):
        return self.attachments.exists()


class MessageAttachment(models.Model):
    """
    File or image asset attached to a chat message.
    Metadata is recorded in PostgreSQL with the binary payload stored in Supabase Storage.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='chat/%Y/%m/')
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)  # bytes
    mime_type = models.CharField(max_length=100, blank=True, default='')
    is_image = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.file_name} ({self.file_size} bytes)"

    @property
    def formatted_size(self):
        """Format byte size into human readable string (KB / MB)."""
        bytes_val = self.file_size
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        return f"{bytes_val / (1024 * 1024):.1f} MB"


class MessageReaction(models.Model):
    """
    Emoji reaction left by a team member on a message (e.g. 👍, ❤️, 🎉, 🚀, 👀).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_reactions'
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['message', 'user', 'emoji'],
                name='unique_message_reaction'
            )
        ]

    def __str__(self):
        return f"{self.user} reacted {self.emoji} on {self.message_id}"
