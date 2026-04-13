"""Middleware for tenant isolation and request context."""

from django.utils.deprecation import MiddlewareMixin

from .permissions import resolve_tenant_id_for_user


class TenantMiddleware(MiddlewareMixin):
    """
    Extracts tenant_id from JWT claims and attaches to request.
    All views can then access request.tenant_id.
    """

    @staticmethod
    def _coerce_tenant_id(raw_value):
        if raw_value in (None, ''):
            return None
        try:
            tenant_id = int(raw_value)
        except (TypeError, ValueError):
            return None
        return tenant_id if tenant_id > 0 else None

    def process_request(self, request):
        header_tenant_id = request.headers.get('X-Tenant-ID')
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.tenant_id = resolve_tenant_id_for_user(
                request.user,
                header_tenant_id=header_tenant_id,
            )
            return

        request.tenant_id = self._coerce_tenant_id(header_tenant_id)
