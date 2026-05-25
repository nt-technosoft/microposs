"""Credential lifecycle services."""

from argon2 import PasswordHasher
from django.utils import timezone

from .models import IntegrationCredential, _generate_key_parts

_ph = PasswordHasher()


def create_credential(*, tenant_id: int, vendor: str, created_by_id: int) -> tuple[IntegrationCredential, str]:
    """Create a new active credential. Returns (credential, full_key). full_key shown once."""
    full_key, key_prefix = _generate_key_parts(vendor)
    key_hash = _ph.hash(full_key)
    cred = IntegrationCredential.objects.create(
        tenant_id=tenant_id,
        vendor=vendor,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=['integration:read', 'integration:write'],
        status=IntegrationCredential.Status.ACTIVE,
        created_by_id=created_by_id,
    )
    return cred, full_key


def revoke_credential(cred: IntegrationCredential) -> None:
    cred.status = IntegrationCredential.Status.REVOKED
    cred.revoked_at = timezone.now()
    cred.save(update_fields=['status', 'revoked_at', 'updated_at'])
