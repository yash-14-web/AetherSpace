from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'
    verbose_name = 'Notifications & Alerts'

    def ready(self):
        try:
            import notifications.checks  # noqa: F401
        except ImportError:
            pass
