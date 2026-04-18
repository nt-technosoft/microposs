"""Read-only alignment/reconciliation endpoints."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ExcelImportBatch, ExcelImportRow
from apps.core.permissions import IsOwner


class ReconciliationLatestView(APIView):
    """Owner-only latest reconciliation summary from alignment batches."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        batch = (
            ExcelImportBatch.objects
            .filter(
                tenant_id=request.tenant_id,
                mode=ExcelImportBatch.Mode.RECONCILE,
                status=ExcelImportBatch.Status.COMPLETED,
            )
            .order_by('-finished_at', '-id')
            .first()
        )
        if batch is None:
            return Response(
                {'detail': 'No completed reconcile batch found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        failed_rows = ExcelImportRow.objects.filter(
            tenant_id=request.tenant_id,
            batch=batch,
            status=ExcelImportRow.Status.FAILED,
        )
        gap_summary: dict[str, int] = {}
        for row in failed_rows:
            key = row.failure_category or ExcelImportRow.FailureCategory.OTHER
            gap_summary[key] = gap_summary.get(key, 0) + 1

        totals = batch.totals or {}
        return Response({
            'batch_id': batch.id,
            'batch_mode': batch.mode,
            'finished_at': batch.finished_at,
            'computed': totals.get('computed') or {},
            'expected': totals.get('expected') or {},
            'deltas': totals.get('deltas') or {},
            'gap_summary': gap_summary,
        })
