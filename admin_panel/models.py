import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class AuditActionStatus(models.TextChoices):
    SUCCESS = 'SUCCESS', _('Success')
    FAILURE = 'FAILURE', _('Failure')
    WARNING = 'WARNING', _('Warning')


class AuditLog(models.Model):
    """
    Immutable audit log recording platform-wide administrative and security actions.
    Strict rule: Never record passwords, tokens, API keys, or raw secrets in metadata.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_audit_logs'
    )
    actor_email = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=50, blank=True, db_index=True)
    target_id = models.CharField(max_length=255, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_audit_logs'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=AuditActionStatus.choices,
        default=AuditActionStatus.SUCCESS
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['target_type', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
        ]

    def __str__(self):
        actor_name = self.actor_email or (self.actor.email if self.actor else "System")
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {actor_name} -> {self.action} ({self.status})"


class AlertSeverity(models.TextChoices):
    CRITICAL = 'CRITICAL', _('Critical')
    WARNING = 'WARNING', _('Warning')
    INFO = 'INFO', _('Info')
    RESOLVED = 'RESOLVED', _('Resolved')


class AlertCategory(models.TextChoices):
    STORAGE = 'STORAGE', _('Storage & Files')
    SECURITY = 'SECURITY', _('Security & Auth')
    BUGS = 'BUGS', _('Critical Bugs')
    ACCESS = 'ACCESS', _('Workspace Requests')
    SYSTEM = 'SYSTEM', _('System & Runtime')


class AdminAlert(models.Model):
    """
    Actionable administrative alert for tracking system, security, storage, or operational issues.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    severity = models.CharField(
        max_length=20,
        choices=AlertSeverity.choices,
        default=AlertSeverity.INFO,
        db_index=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=AlertCategory.choices,
        default=AlertCategory.SYSTEM,
        db_index=True
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='admin_alerts'
    )
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_admin_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['is_resolved', '-created_at']
        indexes = [
            models.Index(fields=['severity', 'is_resolved', '-created_at']),
            models.Index(fields=['category', 'is_resolved']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"
