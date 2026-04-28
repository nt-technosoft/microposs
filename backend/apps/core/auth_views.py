"""Auth API views."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.models import Business, BusinessRegistrationRequest
from apps.core.permissions import ensure_request_tenant, resolve_user_role


class PendingAwareTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT auth with clearer messages for pending business registration requests."""

    def validate(self, attrs):
        username = str(attrs.get(self.username_field, '')).strip()
        try:
            return super().validate(attrs)
        except AuthenticationFailed as error:
            latest_request = (
                BusinessRegistrationRequest.objects
                .filter(username=username)
                .order_by('-created_at')
                .first()
            )
            if latest_request is not None:
                if latest_request.status == BusinessRegistrationRequest.Status.PENDING:
                    raise AuthenticationFailed('Заявка ещё не подтверждена.') from error
                if latest_request.status == BusinessRegistrationRequest.Status.REJECTED:
                    raise AuthenticationFailed('Заявка была отклонена.') from error
            raise


class PendingAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = PendingAwareTokenObtainPairSerializer


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
            'role': resolve_user_role(request.user, tenant_id),
            'active_tenant_id': tenant_id,
            'tenant_name': tenant_name or '',
        })
