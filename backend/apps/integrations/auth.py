"""API-key authentication for integration endpoints."""

import re
import threading

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import IntegrationCredential

_ph = PasswordHasher()

# ssk_<vendor>_<env>_<random>
_KEY_PREFIX_RE = re.compile(r'^ssk_([a-z0-9]+)_')


def _parse_vendor(key: str) -> str | None:
    m = _KEY_PREFIX_RE.match(key)
    return m.group(1) if m else None


def _get_client_ip(request) -> str | None:
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _update_last_used(credential_id) -> None:
    try:
        IntegrationCredential.objects.filter(id=credential_id).update(
            last_used_at=timezone.now()
        )
    except Exception:
        pass  # fire-and-forget


class IntegrationKeyAuthentication(BaseAuthentication):
    """
    DRF authentication class for X-Integration-Key header.

    On success sets request.tenant_id, request.vendor,
    request.integration_scopes, request.credential_id.
    Returns (None, credential) so DRF treats the request as unauthenticated
    at the user level but the integration context is available.
    """

    def authenticate(self, request):
        key = request.META.get('HTTP_X_INTEGRATION_KEY', '').strip()
        if not key:
            return None  # allow DRF to try next authenticator

        vendor = _parse_vendor(key)
        if not vendor:
            raise AuthenticationFailed('Invalid key format.')

        key_prefix = key[:12]
        try:
            cred = IntegrationCredential.objects.get(
                key_prefix=key_prefix, status=IntegrationCredential.Status.ACTIVE,
            )
        except IntegrationCredential.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked integration key.')

        if cred.vendor != vendor:
            raise AuthenticationFailed('Vendor mismatch.')

        try:
            _ph.verify(cred.key_hash, key)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            raise AuthenticationFailed('Invalid integration key.')

        client_ip = _get_client_ip(request)
        if cred.source_ip_allowlist:
            if client_ip not in cred.source_ip_allowlist:
                raise AuthenticationFailed('Source IP not allowed.')

        # Inject integration context onto request
        request.tenant_id = cred.tenant_id
        request.vendor = cred.vendor
        request.integration_scopes = cred.scopes
        request.credential_id = cred.id

        # Non-blocking last_used_at update
        threading.Thread(
            target=_update_last_used, args=(cred.id,), daemon=True,
        ).start()

        return (None, cred)

    def authenticate_header(self, request):
        return 'IntegrationKey realm="api"'
