from django.contrib import admin
from .models import PosSession, Sale, SaleLine, SalePayment, Return, ReturnLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    readonly_fields = (
        'product_variant', 'lot', 'quantity',
        'unit_price', 'base_price',
        'unit_purchase_price', 'unit_landed_cost',
        'price_changed', 'discount_reason',
    )


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0
    readonly_fields = ('date', 'amount', 'currency', 'fx_rate', 'method', 'role')


class ReturnLineInline(admin.TabularInline):
    model = ReturnLine
    extra = 0
    readonly_fields = ('sale_line', 'quantity')


@admin.register(PosSession)
class PosSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'location', 'status', 'opened_by',
        'opening_cash', 'expected_cash', 'actual_cash',
        'cash_difference', 'opened_at', 'closed_at',
    )
    list_filter = ('status',)
    readonly_fields = ('expected_cash', 'cash_difference', 'opened_at', 'closed_at')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status', 'date', 'location', 'customer',
        'total_amount', 'total_cogs', 'pos_session',
        'sold_by', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('notes',)
    readonly_fields = ('client_request_id', 'created_at', 'updated_at')
    inlines = [SaleLineInline, SalePaymentInline]


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'resolution', 'reason', 'processed_by', 'date', 'created_at')
    list_filter = ('resolution', 'reason')
    readonly_fields = ('created_at',)
    inlines = [ReturnLineInline]
