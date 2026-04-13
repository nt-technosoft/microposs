"""
Analytics domain — read-only views / denormalized tables.
Populated by Celery tasks.
"""

from django.db import models
from decimal import Decimal

from apps.core.models import TenantModel


class ProductPerformance(TenantModel):
    """Aggregated product performance metrics."""

    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.CASCADE,
        related_name='performance',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    units_sold = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cogs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    units_returned = models.IntegerField(default=0)
    units_written_off = models.IntegerField(default=0)

    class Meta:
        db_table = 'analytics_product_performance'
        unique_together = [('product', 'period_start', 'period_end')]


class AgingReport(TenantModel):
    """Pre-computed aging buckets for A/R and A/P."""

    class ReportType(models.TextChoices):
        CUSTOMER = 'customer', 'Клиент (A/R)'
        SUPPLIER = 'supplier', 'Поставщик (A/P)'

    report_type = models.CharField(max_length=10, choices=ReportType.choices)
    entity_id = models.IntegerField()
    entity_name = models.CharField(max_length=255)
    bucket_0_30 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    bucket_31_60 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    bucket_61_90 = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    bucket_90_plus = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'analytics_aging_report'
        unique_together = [('tenant', 'report_type', 'entity_id')]
