from django.contrib import admin
from .models import ProductPerformance, AgingReport


@admin.register(ProductPerformance)
class ProductPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'product', 'period_start', 'period_end',
        'units_sold', 'revenue', 'gross_profit',
    )
    list_filter = ('period_start',)


@admin.register(AgingReport)
class AgingReportAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'report_type', 'entity_name',
        'bucket_0_30', 'bucket_31_60',
        'bucket_61_90', 'bucket_90_plus',
        'total', 'computed_at',
    )
    list_filter = ('report_type',)
