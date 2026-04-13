"""
Investors serializers.
"""

from rest_framework import serializers
from .models import (
    Investor, InvestorContract,
    InvestorProfitRecord, InvestorSummary,
)


class InvestorSerializer(serializers.ModelSerializer):
    contracts_count = serializers.SerializerMethodField()

    class Meta:
        model = Investor
        fields = [
            'id', 'user', 'name', 'phone', 'email',
            'notes', 'is_active', 'contracts_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_contracts_count(self, obj):
        return obj.contracts.filter(status='active').count()


class InvestorCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=50, required=False, default='')
    email = serializers.EmailField(required=False, default='')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class InvestorContractSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(
        source='investor.name', read_only=True,
    )

    class Meta:
        model = InvestorContract
        fields = [
            'id', 'investor', 'investor_name',
            'contract_type', 'default_profit_ratio',
            'status', 'start_date', 'closed_at',
            'final_settlement', 'notes',
            'created_at',
        ]
        read_only_fields = [
            'id', 'status', 'closed_at',
            'final_settlement', 'created_at',
        ]


class InvestorContractCreateSerializer(serializers.Serializer):
    investor_id = serializers.IntegerField()
    contract_type = serializers.ChoiceField(choices=['MUDARABA', 'MUSHARAKA'])
    default_profit_ratio = serializers.DecimalField(
        max_digits=5, decimal_places=4, min_value=0, max_value=1,
    )
    start_date = serializers.DateField()
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class InvestorProfitRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestorProfitRecord
        fields = [
            'id', 'contract', 'investor',
            'record_type', 'amount',
            'source_type', 'source_id',
            'lot', 'description',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class InvestorSummarySerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(
        source='investor.name', read_only=True,
    )
    contract_type = serializers.CharField(
        source='contract.contract_type', read_only=True,
    )

    class Meta:
        model = InvestorSummary
        fields = [
            'id', 'investor', 'investor_name',
            'contract', 'contract_type',
            'total_invested', 'in_stock_value',
            'total_sold_revenue', 'total_profit',
            'total_losses', 'turnover_ratio',
            'business_owes', 'last_updated',
        ]
        read_only_fields = fields
