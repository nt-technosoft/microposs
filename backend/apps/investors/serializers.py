"""
Investors serializers.
"""

from decimal import Decimal

from rest_framework import serializers
from .models import Investor, InvestorContract


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
        max_digits=5, decimal_places=4,
        min_value=Decimal('0'),
        max_value=Decimal('1'),
    )
    start_date = serializers.DateField()
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class LedgerTotalsSerializer(serializers.Serializer):
    capital_in = serializers.DecimalField(max_digits=20, decimal_places=2)
    capital_out = serializers.DecimalField(max_digits=20, decimal_places=2)
    capital_net = serializers.DecimalField(max_digits=20, decimal_places=2)
    profit_accrued = serializers.DecimalField(max_digits=20, decimal_places=2)
    profit_reversed = serializers.DecimalField(max_digits=20, decimal_places=2)
    losses_incurred = serializers.DecimalField(max_digits=20, decimal_places=2)
    dividends_paid = serializers.DecimalField(max_digits=20, decimal_places=2)
    profit_pending_payout = serializers.DecimalField(max_digits=20, decimal_places=2)


class InvestorCapitalStateSerializer(serializers.Serializer):
    sold_cost_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    in_stock_cost_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    tracked_cost_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    sold_revenue_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_revenue_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    projected_partner_profit_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)


class InvestorDashboardAggregateSerializer(LedgerTotalsSerializer):
    partner_id = serializers.IntegerField()
    summary_currency = serializers.CharField()
    functional_uzs = LedgerTotalsSerializer()
    by_currency = serializers.DictField(child=LedgerTotalsSerializer())
    capital_state = InvestorCapitalStateSerializer()


class InvestorLedgerEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    date = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6)
    functional_amount_uzs = serializers.DecimalField(max_digits=20, decimal_places=2)
    entry_type = serializers.CharField()
    source_ref = serializers.CharField()


class InvestorLedgerSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    partner_name = serializers.CharField()
    entries = InvestorLedgerEntrySerializer(many=True)


class InvestorProcurementListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    procurement_type = serializers.CharField()
    status = serializers.CharField()
    opened_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField(allow_null=True)
    supplier_name = serializers.CharField(allow_blank=True, allow_null=True)


class InvestorProcurementDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    procurement_type = serializers.CharField()
    status = serializers.CharField()
    opened_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField(allow_null=True)
    supplier_name = serializers.CharField(allow_blank=True, allow_null=True)
    notes = serializers.CharField(allow_blank=True)
    investor_aggregate = InvestorDashboardAggregateSerializer()
    capital_state = InvestorCapitalStateSerializer()
    investor_ledger = InvestorLedgerSerializer()


# InvestorProfitRecordSerializer and InvestorSummarySerializer removed in PR-5.
# Aggregate data is now computed via partnerships.services.get_partner_aggregate()
# and returned as a plain dict from InvestorContractViewSet.summary().
