"""
AetherSpace Email & SMTP Configuration System Checks.
Validates email settings safely without leaking credentials.
"""
from django.conf import settings
from django.core.checks import Warning, Info, register, Tags


@register(Tags.compatibility)
def check_email_configuration(app_configs, **kwargs):
    """
    Checks email backend and credentials configuration.
    Warns if an SMTP backend is active but credentials are missing or incomplete.
    """
    warnings = []
    backend = getattr(settings, 'EMAIL_BACKEND', '')

    if 'smtp.EmailBackend' in backend:
        host = getattr(settings, 'EMAIL_HOST', '')
        user = getattr(settings, 'EMAIL_HOST_USER', '')
        password = getattr(settings, 'EMAIL_HOST_PASSWORD', '')

        if not host:
            warnings.append(
                Warning(
                    "EMAIL_HOST is not configured while using SMTP backend.",
                    hint="Set EMAIL_HOST=smtp-relay.brevo.com in .env or environment.",
                    id="aetherspace.notifications.W001",
                )
            )
        if not user:
            warnings.append(
                Warning(
                    "EMAIL_HOST_USER is missing or empty while using SMTP backend.",
                    hint="Set EMAIL_HOST_USER in .env or environment.",
                    id="aetherspace.notifications.W002",
                )
            )
        if not password:
            warnings.append(
                Warning(
                    "EMAIL_HOST_PASSWORD is missing or empty while using SMTP backend.",
                    hint="Set EMAIL_HOST_PASSWORD in .env or environment.",
                    id="aetherspace.notifications.W003",
                )
            )
    return warnings
