from django.db import models
from django.conf import settings


class ModuleStatus(models.Model):
    """
    Global Admin-controlled operational status and maintenance flag for AetherSpace features.
    Provides server-side enforcement and user-facing status banners across the platform.
    """

    MODULE_CHOICES = [
        ('meetings', 'Meet Hub'),
        ('chat', 'Team Chat'),
        ('calendars', 'Calendar & Agenda'),
        ('files', 'Files & Storage'),
        ('tasks', 'Tasks & Kanban'),
        ('bugs', 'Bug Tracker'),
        ('notifications', 'Notifications'),
        ('timetracking', 'Time Tracking'),
    ]

    STATUS_AVAILABLE = 'AVAILABLE'
    STATUS_MAINTENANCE = 'MAINTENANCE'
    STATUS_COMING_SOON = 'COMING_SOON'

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, 'Available'),
        (STATUS_MAINTENANCE, 'Under Maintenance'),
        (STATUS_COMING_SOON, 'Coming Soon'),
    ]

    DEFAULT_MESSAGES = {
        'AVAILABLE': 'Module is fully operational.',
        'MAINTENANCE': 'Meet Hub is temporarily unavailable while we complete improvements.',
        'COMING_SOON': 'This feature is currently under active development and will be available soon.',
    }

    module_key = models.CharField(
        max_length=50,
        unique=True,
        choices=MODULE_CHOICES,
        help_text="Unique programmatic identifier for the module."
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable module name."
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_AVAILABLE,
        db_index=True,
        help_text="Current operational availability."
    )
    public_message = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Public status message displayed to all users."
    )
    maintenance_explanation = models.TextField(
        blank=True,
        default='',
        help_text="Optional technical or operational explanation for administrators."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_module_statuses',
        help_text="Administrator who last updated this module status."
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Module Status"
        verbose_name_plural = "Module Statuses"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_available(self):
        return self.status == self.STATUS_AVAILABLE

    @property
    def is_under_maintenance(self):
        return self.status == self.STATUS_MAINTENANCE

    @property
    def is_coming_soon(self):
        return self.status == self.STATUS_COMING_SOON

    @property
    def effective_message(self):
        if self.public_message and self.public_message.strip():
            return self.public_message.strip()
        default_msg = self.DEFAULT_MESSAGES.get(
            self.status,
            f"{self.name} is temporarily unavailable while we complete improvements."
        )
        if self.status == self.STATUS_MAINTENANCE:
            return f"{self.name} is temporarily unavailable while we complete improvements."
        return default_msg

    @classmethod
    def get_status_obj(cls, module_key):
        """Retrieve status record for module, returning an in-memory fallback if not found in database."""
        try:
            return cls.objects.filter(module_key=module_key).first()
        except Exception:
            return None

    @classmethod
    def is_module_available(cls, module_key):
        """Quick boolean check if a module is currently operational."""
        obj = cls.get_status_obj(module_key)
        if obj is None:
            return True
        return obj.is_available

    @classmethod
    def get_all_statuses(cls):
        """Return a dictionary of {module_key: ModuleStatus} for fast template / middleware lookup."""
        result = {}
        for key, name in cls.MODULE_CHOICES:
            result[key] = cls(
                module_key=key,
                name=name,
                status=cls.STATUS_AVAILABLE,
                public_message=cls.DEFAULT_MESSAGES['AVAILABLE']
            )

        try:
            for obj in cls.objects.all():
                result[obj.module_key] = obj
        except Exception:
            pass

        return result

