from django.contrib import admin
from .models import (
    Location, Receipt, ReceiptLine, ReceiptParticipant,
    Lot, StockMovement,
)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'location_type', 'is_active')
    list_filter = ('location_type', 'is_active')


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
        'id', 'product_variant', 'location',
        'quantity_initial', 'quantity_remaining',
        'cost_per_unit', 'is_active',
    )
    list_filter = ('is_active', 'location')
    search_fields = ('product_variant__product__name',)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id', 'lot', 'movement_type', 'quantity', 'from_location', 'to_location', 'created_at')
    list_filter = ('movement_type',)
