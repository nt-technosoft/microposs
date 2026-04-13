"""
Analytics serializers.
"""

from rest_framework import serializers
from .models import ProductPerformance, AgingReport


class ProductPerformanceSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source='product.name', read_only=True,
    )

    class Meta:
        model = ProductPerformance
        fields = [
            'id', 'product', 'product_name',
            'period_start', 'period_end',
            'units_sold', 'revenue', 'cogs', 'gross_profit',
            'units_returned', 'units_written_off',
        ]
        read_only_fields = fields


class AgingReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgingReport
        fields = [
            'id', 'report_type', 'entity_id', 'entity_name',
            'bucket_0_30', 'bucket_31_60',
            'bucket_61_90', 'bucket_90_plus',
            'total', 'computed_at',
        ]
        read_only_fields = fields
