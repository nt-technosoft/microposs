"""
Finance serializers.
"""

from rest_framework import serializers
from .models import Account, JournalEntry, JournalLine, DailySummary, CashFlowSummary


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
            'cash_out_purchases', 'cash_out_supplier_payments',
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
