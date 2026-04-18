"""
Finance serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import (
    Account,
    JournalEntry,
    JournalLine,
    Expense,
    DailySummary,
    CashFlowSummary,
    ExchangeRate,
)


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type',
            'parent', 'is_system', 'is_active',
        ]
        read_only_fields = ['id']


class AccountCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=255)
    account_type = serializers.ChoiceField(
        choices=['asset', 'liability', 'equity', 'income', 'expense'],
    )
    parent_id = serializers.IntegerField(required=False, allow_null=True)


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = JournalLine
        fields = [
            'id', 'account', 'account_code', 'account_name',
            'debit', 'credit', 'description',
        ]
        read_only_fields = ['id']


class JournalEntryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = [
            'id', 'operation_type', 'operation_id',
            'description', 'date', 'is_reversal',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class JournalEntryDetailSerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'operation_type', 'operation_id',
            'status', 'description', 'date',
            'is_reversal', 'reversed_entry',
            'lines', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            'id',
            'title',
            'category',
            'payment_method',
            'source_account_code',
            'operation_currency',
            'operation_amount',
            'fx_rate_snapshot',
            'functional_amount_uzs',
            'occurred_at',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ExpenseCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    category = serializers.CharField(max_length=120, required=False, allow_blank=True, default='')
    payment_method = serializers.ChoiceField(choices=['cash', 'bank'])
    operation_currency = serializers.CharField(max_length=3, required=False, default='UZS')
    operation_amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    fx_rate_snapshot = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    functional_amount_uzs = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    occurred_at = serializers.DateTimeField()
    source_account_code = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default='',
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class DailySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailySummary
        fields = [
            'id', 'date', 'total_revenue', 'total_cogs',
            'gross_profit', 'investor_share',
            'net_business_profit',
            'total_sales_count', 'total_returns_count',
            'total_writeoffs',
        ]
        read_only_fields = fields


class CashFlowSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowSummary
        fields = [
            'id', 'date',
            'cash_in_sales', 'cash_in_debt_payments', 'cash_in_investor',
            'cash_out_purchases', 'cash_out_supplier_payments', 'cash_out_expenses',
            'cash_out_investor_payments',
            'net_cash_flow',
        ]
        read_only_fields = fields


class TrialBalanceSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    account_type = serializers.CharField()
    balance = serializers.DecimalField(max_digits=14, decimal_places=2)


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = [
            'id',
            'base_currency',
            'quote_currency',
            'rate_date',
            'rate',
            'source',
            'is_manual',
            'fetched_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'source',
            'is_manual',
            'fetched_at',
            'created_at',
            'updated_at',
        ]


class ExchangeRateManualCreateSerializer(serializers.Serializer):
    base_currency = serializers.CharField(max_length=3, default='USD')
    quote_currency = serializers.CharField(max_length=3, default='UZS')
    rate_date = serializers.DateField()
    rate = serializers.DecimalField(
        max_digits=16,
        decimal_places=6,
        min_value=Decimal('0.000001'),
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_base_currency(self, value):
        return value.upper()

    def validate_quote_currency(self, value):
        return value.upper()


class ExchangeRateRefreshSerializer(serializers.Serializer):
    base_currency = serializers.CharField(max_length=3, default='USD')
    quote_currency = serializers.CharField(max_length=3, default='UZS')
    rate_date = serializers.DateField(required=False)
    overwrite_manual = serializers.BooleanField(required=False, default=False)

    def validate_base_currency(self, value):
        return value.upper()

    def validate_quote_currency(self, value):
        return value.upper()
