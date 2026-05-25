"""Permissions for integration endpoints."""

from rest_framework.permissions import BasePermission


class IntegrationKeyRequired(BasePermission):
    """Requires successful IntegrationKeyAuthentication (credential_id set on request)."""

    def has_permission(self, request, view) -> bool:
        return bool(getattr(request, 'credential_id', None))
