from django.contrib import admin
from .models import RiskEvent, InventoryCheck, InventoryCheckLine


class InventoryCheckLineInline(admin.TabularInline):
    model = InventoryCheckLine
    extra = 0
    readonly_fields = ('product_variant', 'expected_quantity', 'actual_quantity', 'difference')


@admin.register(RiskEvent)
class RiskEventAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'event_type', 'lot', 'quantity',
        'monetary_impact', 'affects_investor',
        'negligence', 'created_at',
    )
    list_filter = ('event_type', 'affects_investor', 'negligence')


@admin.register(InventoryCheck)
class InventoryCheckAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'location', 'status', 'checked_by',
        'completed_at', 'created_at',
    )
    list_filter = ('status',)
    inlines = [InventoryCheckLineInline]
