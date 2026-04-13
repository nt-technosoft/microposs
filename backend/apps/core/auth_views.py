"""Auth API views."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Business
from apps.core.permissions import ensure_request_tenant, resolve_user_role


class CurrentUserView(APIView):
    """Returns current authenticated user context for frontend guards."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = ensure_request_tenant(request)
        tenant_name = None

        if tenant_id is not None:
            tenant_name = (
                Business.objects
                .filter(id=tenant_id)
                .values_list('name', flat=True)
                .first()
            )

        return Response({
            'id': request.user.id,
            'username': request.user.username,
            'role': resolve_user_role(request.user),
            'active_tenant_id': tenant_id,
            'tenant_name': tenant_name or '',
        })
