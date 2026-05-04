"""Project-level deployment checks."""

from django.conf import settings
from django.core.checks import Error, Tags, register


INSECURE_SECRET_KEY_MARKERS = (
    'change-me',
    'replace-with',
    'django-insecure',
)


@register(Tags.security, deploy=True)
def production_secret_key_check(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    secret_key = str(getattr(settings, 'SECRET_KEY', '') or '').strip()
    normalized = secret_key.lower()
    if (
        not secret_key
        or len(secret_key) < 32
        or any(marker in normalized for marker in INSECURE_SECRET_KEY_MARKERS)
    ):
        return [
            Error(
                'Production SECRET_KEY is missing, too short, or still uses a placeholder.',
                hint='Set a long random SECRET_KEY in Dokploy/server environment before deploy.',
                id='core.E001',
            )
        ]
    return []
