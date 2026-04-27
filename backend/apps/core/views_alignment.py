"""Read-only owner reconciliation endpoints."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwner
from apps.core.reconciliation import build_operational_reconciliation_summary


class ReconciliationLatestView(APIView):
    """Owner-only latest operational reconciliation summary."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        return Response(
            build_operational_reconciliation_summary(tenant_id=request.tenant_id),
        )
