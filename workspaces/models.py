import uuid
import secrets
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.utils.text import slugify


class WorkspaceRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Admin'
    MANAGER = 'MANAGER', 'Manager'
    CONTRIBUTOR = 'CONTRIBUTOR', 'Contributor'


class WorkspaceStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ARCHIVED = 'ARCHIVED', 'Archived'
    SUSPENDED = 'SUSPENDED', 'Suspended'


class MembershipStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    SUSPENDED = 'SUSPENDED', 'Suspended'


class InvitationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REVOKED = 'REVOKED', 'Revoked'
    EXPIRED = 'EXPIRED', 'Expired'


class AccessRequestStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


class Workspace(models.Model):
    """
    Isolated collaborative workspace for teams of 5-15 members.
    All tasks, bugs, channels, meetings, and files are scoped to a Workspace.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    description = models.TextField(blank=True, default='')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='owned_workspaces'
    )
    status = models.CharField(
        max_length=20,
        choices=WorkspaceStatus.choices,
        default=WorkspaceStatus.ACTIVE,
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Workspace'
        verbose_name_plural = 'Workspaces'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or 'workspace'
            slug = base_slug
            counter = 1
            while Workspace.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('workspaces:workspace_dashboard', kwargs={'slug': self.slug})

    @property
    def is_active(self):
        return self.status == WorkspaceStatus.ACTIVE

    @property
    def member_count(self):
        return self.memberships.filter(status=MembershipStatus.ACTIVE).count()

    def get_user_membership(self, user):
        if not user.is_authenticated:
            return None
        return self.memberships.filter(user=user, status=MembershipStatus.ACTIVE).first()

    def has_user(self, user):
        if not user.is_authenticated:
            return False
        if user.is_superuser or getattr(user, 'is_admin_role', False):
            return True
        return self.memberships.filter(user=user, status=MembershipStatus.ACTIVE).exists()


class WorkspaceMembership(models.Model):
    """
    Relates a User to a Workspace with a specific Role (Admin, Manager, Contributor).
    A user can belong to multiple workspaces with identical or different roles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=WorkspaceRole.choices,
        default=WorkspaceRole.CONTRIBUTOR,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('workspace', 'user')
        ordering = ['-role', 'joined_at']
        indexes = [
            models.Index(fields=['workspace', 'user']),
            models.Index(fields=['workspace', 'role']),
        ]

    def __str__(self):
        return f"{self.user} in {self.workspace} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == WorkspaceRole.ADMIN

    @property
    def is_manager(self):
        return self.role == WorkspaceRole.MANAGER

    @property
    def is_contributor(self):
        return self.role == WorkspaceRole.CONTRIBUTOR

    @property
    def can_manage_workspace(self):
        """Only workspace Admins can modify workspace settings and members."""
        return self.is_admin

    @property
    def can_manage_content(self):
        """Admins and Managers can orchestrate workspace tasks, bugs, and schedules."""
        return self.role in [WorkspaceRole.ADMIN, WorkspaceRole.MANAGER]


class WorkspaceInvitation(models.Model):
    """
    Secure invitation for a user to join a workspace with a specified role.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    email = models.EmailField(db_index=True)
    role = models.CharField(
        max_length=20,
        choices=WorkspaceRole.choices,
        default=WorkspaceRole.CONTRIBUTOR
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_workspace_invitations'
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite for {self.email} to {self.workspace} ({self.role})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        return (
            self.status == InvitationStatus.PENDING and
            self.expires_at > timezone.now()
        )

    def accept(self, user):
        """Accepts the invitation and creates/updates WorkspaceMembership."""
        if not self.is_valid:
            return False, "Invitation has expired or is no longer valid."
        
        membership, created = WorkspaceMembership.objects.get_or_create(
            workspace=self.workspace,
            user=user,
            defaults={
                'role': self.role,
                'status': MembershipStatus.ACTIVE,
            }
        )
        if not created and membership.status != MembershipStatus.ACTIVE:
            membership.status = MembershipStatus.ACTIVE
            membership.role = self.role
            membership.save(update_fields=['status', 'role'])

        self.status = InvitationStatus.ACCEPTED
        self.save(update_fields=['status'])
        return True, "Successfully joined workspace."


class WorkspaceAccessRequest(models.Model):
    """
    Access request created when an unauthorized user attempts to view a protected workspace
    or clicks 'Request Access' on the 403 Forbidden page.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='access_requests'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_access_requests'
    )
    message = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=AccessRequestStatus.choices,
        default=AccessRequestStatus.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_access_requests'
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('workspace', 'user', 'status')

    def __str__(self):
        return f"Request by {self.user} for {self.workspace} ({self.status})"
