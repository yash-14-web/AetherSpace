import uuid
import secrets
from django.db import models
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


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
    EXPIRED = 'EXPIRED', 'Expired'


class AccessRequestAction(models.TextChoices):
    TASK_CREATE = 'task.create', _('Create Task')
    TASK_EDIT = 'task.edit', _('Edit Task')
    TASK_DELETE = 'task.delete', _('Delete Task')
    BUG_CREATE = 'bug.create', _('Raise Bug')
    BUG_EDIT = 'bug.edit', _('Edit Bug')
    FILE_UPLOAD = 'file.upload', _('Upload File')
    CALENDAR_CREATE = 'calendar.create', _('Create Event')
    MEETING_CREATE = 'meeting.create', _('Schedule Meeting')
    WORKSPACE_ACCESS = 'workspace.access', _('Workspace Access')
    CUSTOM = 'custom', _('Custom Action')


class AccessRequestUrgency(models.TextChoices):
    NORMAL = 'NORMAL', _('Normal')
    URGENT = 'URGENT', _('Urgent')
    EMERGENCY = 'EMERGENCY', _('Emergency')


class AccessDurationChoice(models.TextChoices):
    ONE_TIME = 'ONE_TIME', _('One-time Action')
    ONE_HOUR = '1_HOUR', _('1 Hour')
    FOUR_HOURS = '4_HOURS', _('4 Hours')
    TODAY = 'TODAY', _('Today (Until Midnight)')
    CUSTOM = 'CUSTOM', _('Custom Duration')


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
    max_seats = models.PositiveIntegerField(
        default=15,
        help_text="Maximum member seats allocated to this workspace (teams of 5-15, expandable)."
    )
    storage_quota_mb = models.PositiveIntegerField(
        default=50,
        help_text="Allocated storage quota in megabytes (MB) for Supabase Free Tier (default 50 MB)."
    )
    tech_stack = models.CharField(
        max_length=500,
        blank=True,
        default='Python 3.12, Django 5.x, PostgreSQL, Supabase Storage, Tailwind CSS, Alpine.js, WebRTC',
        help_text="Comma-separated tech stack badges"
    )
    project_scope = models.TextField(
        blank=True,
        default='',
        help_text="Comprehensive project scope and initiative details"
    )
    architecture_notes = models.TextField(
        blank=True,
        default='',
        help_text="Architecture and engineering guidelines for the workspace"
    )
    security_mode = models.CharField(
        max_length=50,
        blank=True,
        default='Strict RBAC',
        help_text="Security isolation mode (e.g. Strict RBAC, Enterprise Multi-Tenant)"
    )
    storage_provider = models.CharField(
        max_length=50,
        blank=True,
        default='Supabase Storage',
        help_text="File and asset storage provider"
    )
    logo = models.CharField(
        max_length=1024,
        blank=True,
        default='',
        help_text="Supabase storage URL, storage path, or external link for workspace logo"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def logo_url(self):
        """Returns the accessible URL for the workspace logo, or empty string if not configured."""
        if not self.logo:
            return ''
        logo_str = self.logo.strip()
        if logo_str.startswith(('http://', 'https://', '/media/', '/static/')):
            return logo_str
        # If Supabase is configured with bucket and base URL
        if getattr(settings, 'SUPABASE_URL', '') and getattr(settings, 'SUPABASE_STORAGE_BUCKET', ''):
            import urllib.parse
            base_url = settings.SUPABASE_URL.rstrip('/')
            bucket = urllib.parse.quote(settings.SUPABASE_STORAGE_BUCKET)
            return f"{base_url}/storage/v1/object/public/{bucket}/{logo_str}"
        return f"{settings.MEDIA_URL.rstrip('/')}/{logo_str.lstrip('/')}"

    @property
    def tech_stack_list(self):
        """Returns parsed list of tech stack tags."""
        if not self.tech_stack:
            return [
                'Python 3.12',
                'Django 5.x',
                'PostgreSQL',
                'Supabase Storage',
                'Tailwind CSS',
                'Alpine.js',
                'WebRTC'
            ]
        return [tag.strip() for tag in self.tech_stack.split(',') if tag.strip()]

    @property
    def effective_scope(self):
        """Returns project scope or the default agile workspace overview."""
        if self.project_scope and self.project_scope.strip():
            return self.project_scope.strip()
        return (
            f"This workspace provides an isolated agile software environment for the {self.name} initiative. "
            "It brings together backlog sprint management, standardized 6-digit task tracking, "
            "B-prefix bug triage, real-time team chat, and WebRTC standup conferencing."
        )

    @property
    def effective_architecture(self):
        """Returns architecture notes or the default data persistence overview."""
        if self.architecture_notes and self.architecture_notes.strip():
            return self.architecture_notes.strip()
        return (
            "Data persistence and storage isolation are securely separated by workspace boundaries, "
            "enforcing strict role-based access control across Administrators, Managers, and Contributors."
        )

    @property
    def storage_quota_bytes(self):
        """Allocated storage quota in bytes."""
        return (self.storage_quota_mb or 50) * 1024 * 1024

    @property
    def storage_quota_formatted(self):
        """Human-readable formatted storage quota (e.g. 50 MB or 1.0 GB)."""
        mb = self.storage_quota_mb or 50
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb} MB"

    @property
    def seats_assigned(self):
        """Current number of active members in this workspace."""
        return self.memberships.filter(status=MembershipStatus.ACTIVE).count()

    @property
    def seats_remaining(self):
        """Available unfilled seats in this workspace."""
        return max(0, self.max_seats - self.seats_assigned)

    @property
    def seats_percentage(self):
        """Percentage of allocated seats currently in use."""
        if self.max_seats <= 0:
            return 100
        return min(100, int((self.seats_assigned / self.max_seats) * 100))

    @property
    def is_seats_full(self):
        """Returns True if all allocated seats are currently assigned."""
        return self.seats_assigned >= self.max_seats

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
    functional_role = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Functional designation/job title, e.g. Frontend Developer, Backend Developer, Support Engineer"
    )
    role_tag = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Role domain tag, e.g. Frontend, Backend, Support, Design, DevOps, QA, Product"
    )
    reporting_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='direct_reports',
        help_text="The person this member reports to within the workspace (defaults to Workspace Owner / Admin)."
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

    @property
    def effective_reporting_to(self):
        """
        Returns the assigned reporting member, or defaults to the workspace owner/lead admin/manager
        if this member is not the top lead themselves.
        """
        if self.reporting_to_id and self.reporting_to and self.reporting_to.status == MembershipStatus.ACTIVE:
            return self.reporting_to
        if self.workspace.owner_id and self.user_id == self.workspace.owner_id:
            return None
        if self.workspace.owner_id:
            owner_membership = self.workspace.memberships.filter(
                user_id=self.workspace.owner_id,
                status=MembershipStatus.ACTIVE
            ).first()
            if owner_membership and owner_membership.pk != self.pk:
                return owner_membership
        admin_membership = self.workspace.memberships.filter(
            role=WorkspaceRole.ADMIN,
            status=MembershipStatus.ACTIVE
        ).exclude(pk=self.pk).order_by('joined_at').first()
        if admin_membership:
            return admin_membership
        if self.role == WorkspaceRole.CONTRIBUTOR:
            manager_membership = self.workspace.memberships.filter(
                role=WorkspaceRole.MANAGER,
                status=MembershipStatus.ACTIVE
            ).exclude(pk=self.pk).order_by('joined_at').first()
            if manager_membership:
                return manager_membership
        return None

    @property
    def direct_reports_count(self):
        return self.direct_reports.filter(status=MembershipStatus.ACTIVE).count()


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


class WorkspaceModule(models.Model):
    """
    Workspace-scoped functional module/subsystem (e.g. Authentication, Billing, Chat).
    Allows teams to categorize defects and features specific to their product domain.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='modules'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['workspace', 'name'],
                name='unique_workspace_module_name'
            )
        ]
        verbose_name = 'Workspace Module'
        verbose_name_plural = 'Workspace Modules'

    def __str__(self):
        return self.name

    @property
    def bug_count(self):
        return getattr(self, 'bugs', None).count() if hasattr(self, 'bugs') else 0

    @property
    def active_bug_count(self):
        return getattr(self, 'bugs', None).filter(status__in=['OPEN', 'IN_PROGRESS']).count() if hasattr(self, 'bugs') else 0


Module = WorkspaceModule


class GlobalAccessRequest(models.Model):
    """
    Unified, extensible Access Request system.
    Supports requesting specific action privileges (task.create, bug.create, etc.)
    or general workspace access without permanent role elevation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='global_access_requests'
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='global_access_requests',
        null=True,
        blank=True
    )
    action = models.CharField(
        max_length=50,
        choices=AccessRequestAction.choices,
        default=AccessRequestAction.TASK_CREATE,
        db_index=True
    )
    target_resource_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Optional ID or code of specific task, bug, file, or resource"
    )
    reason = models.TextField(help_text="Detailed justification for access request")
    goal_description = models.TextField(
        blank=True,
        default='',
        help_text="What are you trying to accomplish (required for emergency/action requests)"
    )
    urgency = models.CharField(
        max_length=20,
        choices=AccessRequestUrgency.choices,
        default=AccessRequestUrgency.NORMAL,
        db_index=True
    )
    evidence_url = models.URLField(max_length=1024, blank=True, default='')
    evidence_file = models.CharField(
        max_length=1024,
        blank=True,
        default='',
        help_text="Storage path or reference to uploaded evidence screenshot"
    )
    requested_duration = models.CharField(
        max_length=30,
        choices=AccessDurationChoice.choices,
        default=AccessDurationChoice.ONE_HOUR
    )
    status = models.CharField(
        max_length=20,
        choices=AccessRequestStatus.choices,
        default=AccessRequestStatus.PENDING,
        db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_global_access_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, default='')
    rejection_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'urgency', '-created_at']),
            models.Index(fields=['workspace', 'action', 'status']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        ws_name = self.workspace.name if self.workspace else 'Global'
        return f"[{self.get_urgency_display()}] {self.user.email} -> {self.get_action_display()} in {ws_name} ({self.get_status_display()})"


class TemporaryAccessGrant(models.Model):
    """
    Auditable, time-bounded permission grant scoped strictly to a user, workspace, and action.
    Does NOT modify user's permanent role (Contributor remains Contributor).
    Automatically expires when expires_at has passed.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='temporary_access_grants'
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='temporary_access_grants'
    )
    action = models.CharField(max_length=50, db_index=True)
    target_resource_id = models.CharField(max_length=255, blank=True, default='')
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='granted_temporary_access_grants'
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_revoked = models.BooleanField(default=False, db_index=True)
    reason = models.TextField(blank=True, default='')
    access_request = models.ForeignKey(
        GlobalAccessRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='grants'
    )

    class Meta:
        ordering = ['-granted_at']
        indexes = [
            models.Index(fields=['user', 'workspace', 'action', 'expires_at']),
            models.Index(fields=['expires_at', 'is_revoked']),
        ]

    def __str__(self):
        return f"Grant: {self.user.email} -> {self.action} in {self.workspace.name} (expires {self.expires_at:%Y-%m-%d %H:%M})"

    @property
    def is_active(self):
        return not self.is_revoked and self.expires_at > timezone.now()

    @classmethod
    def has_active_grant(cls, user, workspace, action, target_resource_id=None):
        if not user or not user.is_authenticated or not workspace:
            return False
        now = timezone.now()
        qs = cls.objects.filter(
            user=user,
            workspace=workspace,
            action=action,
            is_revoked=False,
            expires_at__gt=now
        )
        if target_resource_id:
            qs = qs.filter(Q(target_resource_id=str(target_resource_id)) | Q(target_resource_id=''))
        return qs.exists()


AccessRequest = GlobalAccessRequest
