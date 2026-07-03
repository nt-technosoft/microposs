from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwner, IsWarehouse

from .models import Procurement
from .workspace import (
    build_workspace_payload,
    create_workspace,
    dispatch_workspace_action,
    workspace_queryset,
)


def _require_tenant(request) -> int:
    tenant_id = getattr(request, 'tenant_id', None)
    if tenant_id is None:
        raise PermissionDenied('Business context is required for procurement workspace operations.')
    return tenant_id


class ProcurementWorkspaceListCreateView(APIView):
    permission_classes = [IsOwner | IsWarehouse]

    def get(self, request):
        tenant_id = _require_tenant(request)
        rows = [
            build_workspace_payload(procurement)
            for procurement in workspace_queryset(tenant_id)[:50]
        ]
        return Response(rows)

    def post(self, request):
        tenant_id = _require_tenant(request)
        payload = request.data or {}
        funding_source = (
            payload.get('funding_source')
            or Procurement.FundingSource.OWN_FUNDS
        )
        try:
            procurement = create_workspace(
                tenant_id=tenant_id,
                funding_source=funding_source,
                primary_currency=payload.get('primary_currency') or 'UZS',
                supplier_id=payload.get('supplier_id'),
                agreement_id=payload.get('investment_agreement_id') or payload.get('agreement_id'),
                notes=payload.get('notes', ''),
                client_request_id=payload.get('client_request_id'),
            )
        except ValueError as error:
            raise ValidationError({'detail': str(error)}) from error
        return Response(build_workspace_payload(procurement), status=status.HTTP_201_CREATED)


class ProcurementWorkspaceDetailView(APIView):
    permission_classes = [IsOwner | IsWarehouse]

    def get_object(self, request, pk: int):
        tenant_id = _require_tenant(request)
        return get_object_or_404(workspace_queryset(tenant_id), pk=pk)

    def get(self, request, pk: int):
        return Response(build_workspace_payload(self.get_object(request, pk)))


class ProcurementWorkspaceActionView(APIView):
    permission_classes = [IsOwner | IsWarehouse]

    def post(self, request, pk: int, action: str):
        tenant_id = _require_tenant(request)
        procurement = get_object_or_404(workspace_queryset(tenant_id), pk=pk)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=tenant_id,
                procurement=procurement,
                action=action,
                payload=request.data or {},
                user_id=request.user.id if request.user.is_authenticated else None,
            )
        except ValueError as error:
            raise ValidationError({
                'detail': str(error),
                'workspace': build_workspace_payload(procurement),
            }) from error
        return Response(build_workspace_payload(procurement))
