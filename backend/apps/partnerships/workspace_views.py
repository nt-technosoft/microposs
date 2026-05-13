from rest_framework import status
from rest_framework.exceptions import ValidationError
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


class ProcurementWorkspaceListCreateView(APIView):
    permission_classes = [IsOwner | IsWarehouse]

    def get(self, request):
        rows = [
            build_workspace_payload(procurement)
            for procurement in workspace_queryset(request.tenant_id)[:50]
        ]
        return Response(rows)

    def post(self, request):
        payload = request.data or {}
        funding_source = (
            payload.get('funding_source')
            or Procurement.FundingSource.OWN_FUNDS
        )
        try:
            procurement = create_workspace(
                tenant_id=request.tenant_id,
                funding_source=funding_source,
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
        return workspace_queryset(request.tenant_id).get(pk=pk)

    def get(self, request, pk: int):
        return Response(build_workspace_payload(self.get_object(request, pk)))


class ProcurementWorkspaceActionView(APIView):
    permission_classes = [IsOwner | IsWarehouse]

    def post(self, request, pk: int, action: str):
        procurement = workspace_queryset(request.tenant_id).get(pk=pk)
        try:
            procurement = dispatch_workspace_action(
                tenant_id=request.tenant_id,
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
