"""Merchant-facing credential management endpoints (session/JWT auth)."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status

from apps.core.permissions import resolve_tenant_id_for_user
from .models import IntegrationCredential
from .services import create_credential, revoke_credential

_ALLOWED_VENDORS = {'yespos'}


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def credentials_list_create(request: Request) -> Response:
    tenant_id = resolve_tenant_id_for_user(request.user)

    if request.method == 'GET':
        qs = (
            IntegrationCredential.objects
            .filter(tenant_id=tenant_id, deleted_at__isnull=True)
            .order_by('-created_at')
        )
        data = [
            {
                'id': str(c.id),
                'vendor': c.vendor,
                'prefix': c.key_prefix,
                'status': c.status,
                'scopes': c.scopes,
                'created_at': c.created_at,
                'last_used_at': c.last_used_at,
            }
            for c in qs
        ]
        return Response(data)

    # POST — create
    vendor = request.data.get('vendor', '')
    if vendor not in _ALLOWED_VENDORS:
        return Response(
            {'detail': f"Unsupported vendor. Allowed: {sorted(_ALLOWED_VENDORS)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # One active credential per vendor (DB constraint). Surface a clear reason
    # instead of a generic 500 when an active key already exists.
    if IntegrationCredential.objects.filter(
        tenant_id=tenant_id, vendor=vendor,
        status=IntegrationCredential.Status.ACTIVE,
    ).exists():
        return Response(
            {'detail': 'У этого провайдера уже есть активный ключ. Сначала отзовите его, затем создайте новый.'},
            status=status.HTTP_409_CONFLICT,
        )

    cred, full_key = create_credential(
        tenant_id=tenant_id,
        vendor=vendor,
        created_by_id=request.user.id,
    )
    return Response(
        {
            'id': str(cred.id),
            'prefix': cred.key_prefix,
            'full_key': full_key,
            'created_at': cred.created_at,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def credential_revoke(request: Request, pk: str) -> Response:
    tenant_id = resolve_tenant_id_for_user(request.user)
    try:
        cred = IntegrationCredential.objects.get(id=pk, tenant_id=tenant_id)
    except IntegrationCredential.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if cred.status != IntegrationCredential.Status.ACTIVE:
        return Response({'detail': 'Credential is not active.'}, status=status.HTTP_409_CONFLICT)

    revoke_credential(cred)
    return Response({'status': 'revoked'})
