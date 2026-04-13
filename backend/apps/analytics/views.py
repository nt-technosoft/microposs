"""
Analytics API views — product performance, aging reports.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsOwner

from .models import ProductPerformance, AgingReport
from .serializers import ProductPerformanceSerializer, AgingReportSerializer


class ProductPerformanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Product performance metrics."""

    serializer_class = ProductPerformanceSerializer
    permission_classes = [IsOwner]
    ordering = ['-revenue']

    def get_queryset(self):
        qs = ProductPerformance.objects.filter(
            tenant_id=self.request.tenant_id,
        ).select_related('product')

        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)

        period_start = self.request.query_params.get('period_start')
        period_end = self.request.query_params.get('period_end')
        if period_start:
            qs = qs.filter(period_start__gte=period_start)
        if period_end:
            qs = qs.filter(period_end__lte=period_end)

        return qs


class AgingReportViewSet(viewsets.ReadOnlyModelViewSet):
    """Pre-computed aging buckets for A/R and A/P."""

    serializer_class = AgingReportSerializer
    permission_classes = [IsOwner]
    ordering = ['-total']

    def get_queryset(self):
        qs = AgingReport.objects.filter(
            tenant_id=self.request.tenant_id,
        )

        report_type = self.request.query_params.get('type')
        if report_type:
            qs = qs.filter(report_type=report_type)

        return qs
