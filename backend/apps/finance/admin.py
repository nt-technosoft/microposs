from django.contrib import admin
from .models import (
    Account,
    JournalEntry,
    JournalLine,
    DailySummary,
    CashFlowSummary,
    ExchangeRate,
)


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ('account', 'debit', 'credit', 'description')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'name', 'account_type', 'is_system', 'is_active')
    list_filter = ('account_type', 'is_system', 'is_active')
    search_fields = ('code', 'name')


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'operation_type', 'operation_id',
        'description', 'date', 'is_reversal', 'created_at',
    )
    list_filter = ('operation_type', 'is_reversal')
    readonly_fields = ('created_at',)
    inlines = [JournalLineInline]


@admin.register(DailySummary)
class DailySummaryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'date', 'total_revenue', 'total_cogs',
        'gross_profit', 'net_business_profit',
        'total_sales_count',
    )
    list_filter = ('date',)


@admin.register(CashFlowSummary)
class CashFlowSummaryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'date', 'cash_in_sales',
        'cash_out_purchases', 'net_cash_flow',
    )
    list_filter = ('date',)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'tenant',
        'base_currency',
        'quote_currency',
        'rate_date',
        'rate',
        'source',
        'is_manual',
        'created_at',
    )
    list_filter = (
        'base_currency',
        'quote_currency',
        'source',
        'is_manual',
        'rate_date',
    )
    search_fields = ('base_currency', 'quote_currency', 'notes')
