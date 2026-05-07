"""Auth API views."""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.models import Business, BusinessRegistrationRequest, UserPreference
from apps.core.permissions import ensure_request_tenant, resolve_user_role


def _locale_from_request(request):
    raw_header = str(request.headers.get('Accept-Language', '')).lower()
    valid_locales = {choice for choice, _label in UserPreference.Locale.choices}
    for chunk in raw_header.split(','):
        candidate = chunk.split(';', 1)[0].strip().split('-', 1)[0]
        if candidate in valid_locales:
            return candidate
    return UserPreference.Locale.RU


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
    throttle_classes = []

    @staticmethod
    def _payload(request):
        tenant_id = ensure_request_tenant(request)
        tenant_name = None
        preferences, _ = UserPreference.objects.get_or_create(
            user=request.user,
            defaults={'locale': _locale_from_request(request)},
        )

        if tenant_id is not None:
            tenant_name = (
                Business.objects
                .filter(id=tenant_id)
                .values_list('name', flat=True)
                .first()
            )

        return {
            'id': request.user.id,
            'username': request.user.username,
            'role': resolve_user_role(request.user, tenant_id),
            'active_tenant_id': tenant_id,
            'tenant_name': tenant_name or '',
            'locale': preferences.locale,
        }

    def get(self, request):
        return Response(self._payload(request))


class UserPreferenceView(APIView):
    """Read/update authenticated user UI preferences."""

    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def patch(self, request):
        raw_locale = str(request.data.get('locale', '')).strip().lower()
        valid_locales = {choice for choice, _label in UserPreference.Locale.choices}
        if raw_locale not in valid_locales:
            return Response(
                {'detail': 'Unsupported locale.', 'code': 'unsupported_locale'},
                status=400,
            )

        preferences, _ = UserPreference.objects.get_or_create(user=request.user)
        preferences.locale = raw_locale
        preferences.save(update_fields=['locale', 'updated_at'])
        return Response(CurrentUserView._payload(request))
