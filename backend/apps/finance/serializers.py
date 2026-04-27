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
    CashAccount,
    CashEntry,
    CurrencyExchange,
    Refund,
    OwnerContribution,
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


class SaleProfitabilitySerializer(serializers.Serializer):
    sale_id = serializers.IntegerField()
    date = serializers.DateTimeField()
    location_id = serializers.IntegerField()
    location_name = serializers.CharField()
    customer_id = serializers.IntegerField(allow_null=True)
    customer_name = serializers.CharField(allow_null=True, allow_blank=True)
    payment_methods = serializers.ListField(child=serializers.CharField())
    line_count = serializers.IntegerField()
    quantity_sold = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=20, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    markup_percent = serializers.DecimalField(max_digits=8, decimal_places=2)


class ProductProfitabilitySerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    product_name = serializers.CharField()
    current_unit_price = serializers.DecimalField(max_digits=20, decimal_places=2)
    quantity_sold = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=20, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    markup_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    remaining_quantity = serializers.IntegerField()
    remaining_landed_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)


class ProcurementProfitabilitySerializer(serializers.Serializer):
    procurement_id = serializers.IntegerField()
    procurement_type = serializers.CharField()
    status = serializers.CharField()
    opened_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField(allow_null=True)
    supplier_name = serializers.CharField(allow_null=True, allow_blank=True)
    item_count = serializers.IntegerField()
    quantity_sold = serializers.IntegerField()
    remaining_quantity = serializers.IntegerField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=20, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    markup_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    remaining_landed_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)


class ProcurementProfitabilityItemSerializer(serializers.Serializer):
    procurement_item_id = serializers.IntegerField()
    product_variant_id = serializers.IntegerField()
    product_name = serializers.CharField()
    current_unit_price = serializers.DecimalField(max_digits=20, decimal_places=2)
    purchased_quantity = serializers.IntegerField()
    sold_quantity = serializers.IntegerField()
    remaining_quantity = serializers.IntegerField()
    unit_purchase_price = serializers.DecimalField(max_digits=20, decimal_places=2)
    landed_cost_per_unit = serializers.DecimalField(max_digits=20, decimal_places=2)
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=20, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    markup_percent = serializers.DecimalField(max_digits=8, decimal_places=2)
    remaining_landed_cost = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_gross_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_investor_profit = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_business_profit = serializers.DecimalField(max_digits=20, decimal_places=2)


class ProcurementProfitabilityDetailSerializer(serializers.Serializer):
    procurement = ProcurementProfitabilitySerializer()
    items = ProcurementProfitabilityItemSerializer(many=True)


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


class CashAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashAccount
        fields = ['id', 'name', 'currency', 'balance', 'kind', 'linked_account', 'is_active']
        read_only_fields = ['id', 'balance']


class CashAccountCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    currency = serializers.CharField(max_length=3, default='UZS')
    kind = serializers.ChoiceField(choices=CashAccount.Kind.choices, required=False, default=CashAccount.Kind.CASH)
    linked_account_id = serializers.IntegerField(required=False, allow_null=True)


class CashEntrySerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = CashEntry
        fields = ['id', 'account', 'account_name', 'direction', 'amount', 'date', 'source_ref_type', 'source_ref_id']
        read_only_fields = ['id']


class CurrencyExchangeSerializer(serializers.ModelSerializer):
    from_account_name = serializers.CharField(source='from_account.name', read_only=True)
    to_account_name = serializers.CharField(source='to_account.name', read_only=True)

    class Meta:
        model = CurrencyExchange
        fields = [
            'id', 'from_account', 'from_account_name', 'to_account', 'to_account_name',
            'from_amount', 'from_currency', 'to_amount', 'to_currency',
            'effective_rate', 'date', 'notes',
        ]
        read_only_fields = ['id']


class CurrencyExchangeCreateSerializer(serializers.Serializer):
    from_account_id = serializers.IntegerField()
    to_account_id = serializers.IntegerField()
    from_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    rate = serializers.DecimalField(max_digits=14, decimal_places=6, min_value=Decimal('0.000001'))
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ['id', 'customer', 'date', 'amount', 'currency', 'fx_rate', 'account', 'method', 'return_ref']
        read_only_fields = ['id']


class RefundCreateSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    sale_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    method = serializers.ChoiceField(choices=Refund.Method.choices)
    account_id = serializers.IntegerField(required=False, allow_null=True)
    return_ref_id = serializers.IntegerField(required=False, allow_null=True)


class OwnerContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerContribution
        fields = ['id', 'amount', 'currency', 'to_account', 'date', 'notes']
        read_only_fields = ['id']


class OwnerContributionCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    to_account_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')
