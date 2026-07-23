"""Integration credential model — API key auth for external systems."""

import uuid
import base64
import secrets

from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField

from apps.core.models import BaseModel


def _generate_key_parts(vendor: str, env: str = 'live') -> tuple[str, str]:
    """Return (full_key, key_prefix). full_key shown once, prefix stored."""
    random_bytes = secrets.token_bytes(24)  # 24 bytes → 32 base64url chars
    random_part = base64.urlsafe_b64encode(random_bytes).decode('ascii')
    full_key = f"ssk_{vendor}_{env}_{random_part}"
    key_prefix = full_key[:12]
    return full_key, key_prefix


class IntegrationCredential(BaseModel):
    """An API key credential for a third-party integration vendor."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        REVOKED = 'revoked', 'Revoked'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'core.Business',
        on_delete=models.PROTECT,
        related_name='integration_credentials',
    )
    vendor = models.CharField(max_length=64)
    key_prefix = models.CharField(max_length=12, db_index=True)
    key_hash = models.TextField()
    scopes = models.JSONField(default=list)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_integration_credentials',
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    source_ip_allowlist = ArrayField(
        models.GenericIPAddressField(), null=True, blank=True,
    )

    class Meta:
        db_table = 'integrations_credential'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'vendor'],
                condition=models.Q(status='active'),
                name='uq_active_credential_per_tenant_vendor',
            ),
        ]

    def __str__(self) -> str:
        return f"{self.vendor}/{self.key_prefix}… ({self.status})"
