from django.contrib import admin
from .models import (
    Warehouse, Receipt, ReceiptLine, ReceiptParticipant,
    Lot, LotStock, StockMovement,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'kind', 'is_active')
    list_filter = ('kind', 'is_active')


class ReceiptLineInline(admin.TabularInline):
    model = ReceiptLine
    extra = 0
    readonly_fields = ('product_variant', 'quantity', 'cost_per_unit')


class ReceiptParticipantInline(admin.TabularInline):
    model = ReceiptParticipant
    extra = 0


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'receipt_type', 'status', 'date', 'destination', 'created_at')
    list_filter = ('receipt_type', 'status')
    inlines = [ReceiptLineInline, ReceiptParticipantInline]
    readonly_fields = ('client_request_id',)


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'product_variant',
        'quantity_initial',
        'unit_purchase_price', 'landed_cost_per_unit', 'is_active',
    )
    list_filter = ('is_active',)
    search_fields = ('product_variant__product__name',)


@admin.register(LotStock)
class LotStockAdmin(admin.ModelAdmin):
    list_display = ('id', 'lot', 'warehouse', 'quantity_remaining')
    list_filter = ('warehouse',)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id', 'lot', 'movement_type', 'quantity', 'from_location', 'to_location', 'created_at')
    list_filter = ('movement_type',)
