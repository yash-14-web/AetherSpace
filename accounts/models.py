import secrets
import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    ADMIN = 'ADMIN', _('Admin')
    MANAGER = 'MANAGER', _('Manager')
    CONTRIBUTOR = 'CONTRIBUTOR', _('Contributor')


class ApprovalStatus(models.TextChoices):
    PENDING = 'PENDING', _('Pending')
    APPROVED = 'APPROVED', _('Approved')
    REJECTED = 'REJECTED', _('Rejected')
    SUSPENDED = 'SUSPENDED', _('Suspended')


def generate_unique_contributor_id():
    """
    Generate a collision-safe Contributor ID formatted as #####C (e.g. 26457C).
    Always 5 numeric digits followed by 'C'.
    """
    for _ in range(100):
        number = secrets.randbelow(90000) + 10000
        cid = f"{number}C"
        if not User.objects.filter(contributor_id=cid).exists():
            return cid
    raise RuntimeError("Failed to generate unique Contributor ID after 100 attempts.")


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for auth."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        extra_fields.setdefault('username', email)
        extra_fields.setdefault('role', UserRole.CONTRIBUTOR)
        extra_fields.setdefault('approval_status', ApprovalStatus.PENDING)
        if 'contributor_id' not in extra_fields or not extra_fields['contributor_id']:
            extra_fields['contributor_id'] = generate_unique_contributor_id()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', UserRole.ADMIN)
        extra_fields.setdefault('approval_status', ApprovalStatus.APPROVED)
        if 'contributor_id' not in extra_fields or not extra_fields['contributor_id']:
            extra_fields['contributor_id'] = generate_unique_contributor_id()

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Authoritative Custom User Model for AetherSpace.
    Uses UUID primary key, Contributor ID (#####C) as the primary login identifier,
    and maintains strict separation between System Role and Account Approval Status.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_('email address'), unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    contributor_id = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        blank=True,
        help_text="Unique 5-digit numeric identifier with C suffix (e.g. 26457C)"
    )
    avatar = models.CharField(max_length=1024, blank=True, help_text="Supabase storage path or URL")
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CONTRIBUTOR,
        help_text="System/Platform role"
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
        help_text="Account approval state: Pending, Approved, Rejected, Suspended"
    )
    approved_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_users'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(
        default=False,
        help_text="Designates whether this user has verified their email address."
    )
    timezone = models.CharField(max_length=50, default='UTC')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['approval_status']),
        ]

    @property
    def is_approved(self):
        return self.approval_status == ApprovalStatus.APPROVED or self.is_superuser

    @property
    def is_pending_approval(self):
        return self.approval_status == ApprovalStatus.PENDING and not self.is_superuser

    @property
    def is_admin_role(self):
        return self.role == UserRole.ADMIN or self.is_superuser

    @property
    def is_manager_role(self):
        return self.role == UserRole.MANAGER

    @property
    def is_contributor_role(self):
        return self.role == UserRole.CONTRIBUTOR

    def __str__(self):
        cid_str = f" [{self.contributor_id}]" if self.contributor_id else ""
        return f"{self.full_name or self.email}{cid_str}"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        if not self.contributor_id:
            self.contributor_id = generate_unique_contributor_id()
        if self.is_superuser and self.approval_status == ApprovalStatus.PENDING:
            self.approval_status = ApprovalStatus.APPROVED
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    """Extended user profile containing personal metadata and preferences."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    headline = models.CharField(max_length=255, blank=True)
    banner = models.CharField(max_length=1024, blank=True, default='', help_text="Supabase storage path, image URL, or gradient preset")
    preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user.email}"
