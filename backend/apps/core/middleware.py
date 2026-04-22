"""Middleware for tenant isolation and request context."""

import logging

from django.core.exceptions import SuspiciousOperation
from django.utils.deprecation import MiddlewareMixin


from .permissions import resolve_tenant_id_for_user

logger = logging.getLogger('micropos.request_debug')


class ApiBadRequestLoggingMiddleware(MiddlewareMixin):
    """Log exact context for opaque HTML 400 responses in production."""

    @staticmethod
    def _auth_marker(request) -> str:
        header = request.headers.get('Authorization', '')
        return 'present' if header.startswith('Bearer ') else 'absent'

    def process_exception(self, request, exception):
        if not request.path.startswith('/api/'):
            return None

        if isinstance(exception, SuspiciousOperation):
            logger.error(
                'api_suspicious_operation path=%s method=%s host=%s x_forwarded_host=%s '
                'x_forwarded_proto=%s origin=%s referer=%s auth=%s query=%s exc=%s',
                request.path,
                request.method,
                request.META.get('HTTP_HOST', ''),
                request.META.get('HTTP_X_FORWARDED_HOST', ''),
                request.META.get('HTTP_X_FORWARDED_PROTO', ''),
                request.META.get('HTTP_ORIGIN', ''),
                request.META.get('HTTP_REFERER', ''),
                self._auth_marker(request),
                request.META.get('QUERY_STRING', ''),
                repr(exception),
            )
        return None

    def process_response(self, request, response):
        if request.path.startswith('/api/') and response.status_code == 400:
            logger.error(
                'api_bad_request_response path=%s method=%s status=%s content_type=%s '
                'host=%s x_forwarded_host=%s x_forwarded_proto=%s origin=%s referer=%s auth=%s query=%s',
                request.path,
                request.method,
                response.status_code,
                response.headers.get('Content-Type', ''),
                request.META.get('HTTP_HOST', ''),
                request.META.get('HTTP_X_FORWARDED_HOST', ''),
                request.META.get('HTTP_X_FORWARDED_PROTO', ''),
                request.META.get('HTTP_ORIGIN', ''),
                request.META.get('HTTP_REFERER', ''),
                self._auth_marker(request),
                request.META.get('QUERY_STRING', ''),
            )
        return response


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
