"""Middleware for tenant isolation and request context."""

from django.utils.deprecation import MiddlewareMixin


class TenantMiddleware(MiddlewareMixin):
    """
    Extracts tenant_id from JWT claims and attaches to request.
    All views can then access request.tenant_id.
    """

    def process_request(self, request):
        request.tenant_id = None

        if hasattr(request, 'user') and request.user.is_authenticated:
            tenant_id = getattr(request.user, 'active_tenant_id', None)
            if tenant_id is None:
                tenant_id = request.headers.get('X-Tenant-ID')
            request.tenant_id = tenant_id
