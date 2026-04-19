from decimal import Decimal

from rest_framework import serializers

from .models import (
    BalanceContribution,
    BalanceWithdrawal,
    ContractPartner,
    DividendPayment,
    InvestmentContract,
    PartnerLedgerEntry,
    Procurement,
    ProcurementBalance,
    ProcurementExpense,
    ProcurementItem,
    ProcurementPartnerLedger,
)


class ProcurementItemSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(source='product_variant.__str__', read_only=True)

    class Meta:
        model = ProcurementItem
        fields = [
            'id', 'product_variant', 'product_variant_name', 'quantity',
            'unit_purchase_price', 'currency', 'fx_rate',
        ]
        read_only_fields = ['id']


class ProcurementExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementExpense
        fields = [
            'id', 'expense_type', 'amount', 'currency', 'fx_rate',
            'allocation_method', 'notes',
        ]
        read_only_fields = ['id']


class ContractPartnerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)

    class Meta:
        model = ContractPartner
        fields = [
            'id', 'partner', 'partner_name', 'role',
            'planned_capital_share', 'profit_share',
        ]
        read_only_fields = ['id']


class InvestmentContractSerializer(serializers.ModelSerializer):
    partners = ContractPartnerSerializer(source='contract_partners', many=True, read_only=True)

    class Meta:
        model = InvestmentContract
        fields = [
            'id', 'mudaraba_ratio', 'loss_rule', 'planned_budget',
            'currency', 'partners',
        ]
        read_only_fields = ['id']


class ProcurementBalanceSerializer(serializers.ModelSerializer):
    is_zero = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementBalance
        fields = ['balances', 'is_zero']

    def get_is_zero(self, obj):
        balances = obj.balances or {}
        return all(Decimal(str(value)) == Decimal('0') for value in balances.values())


class PartnerLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerLedgerEntry
        fields = ['id', 'date', 'amount', 'currency', 'entry_type', 'source_ref']
        read_only_fields = ['id']


class ProcurementLedgerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    entries = PartnerLedgerEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementPartnerLedger
        fields = ['id', 'partner', 'partner_name', 'entries']
        read_only_fields = ['id']


class ProcurementListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items_count = serializers.SerializerMethodField()
    is_receive_ready = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'procurement_type', 'status', 'opened_at', 'received_at',
            'supplier', 'supplier_name', 'items_count', 'is_receive_ready', 'notes',
        ]
        read_only_fields = ['id']

    def get_items_count(self, obj):
        return obj.items.count()

    def get_is_receive_ready(self, obj):
        balance = getattr(obj, 'balance', None)
        if balance is None:
            return False
        balances = balance.balances or {}
        return all(Decimal(str(value)) == Decimal('0') for value in balances.values())


class ProcurementDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = ProcurementItemSerializer(many=True, read_only=True)
    expenses = ProcurementExpenseSerializer(many=True, read_only=True)
    contract = InvestmentContractSerializer(read_only=True)
    balance = ProcurementBalanceSerializer(read_only=True)

    class Meta:
        model = Procurement
        fields = [
            'id', 'procurement_type', 'status', 'opened_at', 'received_at', 'closed_at',
            'supplier', 'supplier_name', 'notes', 'client_request_id',
            'items', 'expenses', 'contract', 'balance',
        ]
        read_only_fields = ['id']


class ContractPartnerInputSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ContractPartner.Role.choices)
    planned_capital_share = serializers.DecimalField(max_digits=14, decimal_places=2)
    profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False, default='0')


class InvestmentContractInputSerializer(serializers.Serializer):
    mudaraba_ratio = serializers.DecimalField(max_digits=6, decimal_places=6)
    planned_budget = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    partners = ContractPartnerInputSerializer(many=True)


class ProcurementItemInputSerializer(serializers.Serializer):
    product_variant_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')


class ProcurementExpenseInputSerializer(serializers.Serializer):
    expense_type = serializers.ChoiceField(choices=ProcurementExpense.ExpenseType.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    allocation_method = serializers.ChoiceField(
        choices=ProcurementExpense.AllocationMethod.choices,
        required=False,
        default=ProcurementExpense.AllocationMethod.BY_VALUE,
    )
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ProcurementCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    procurement_type = serializers.ChoiceField(choices=Procurement.Type.choices)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    contract = InvestmentContractInputSerializer(required=False, allow_null=True)
    items = ProcurementItemInputSerializer(many=True, required=False, default=list)
    expenses = ProcurementExpenseInputSerializer(many=True, required=False, default=list)


class BalanceContributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceContribution
        fields = ['id', 'partner', 'amount', 'currency', 'fx_rate', 'date', 'notes']
        read_only_fields = ['id', 'date']


class BalanceContributionCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class BalanceWithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceWithdrawal
        fields = ['id', 'partner', 'amount', 'currency', 'fx_rate', 'date', 'reason']
        read_only_fields = ['id', 'date']


class BalanceWithdrawalCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class ReceiveProcurementSerializer(serializers.Serializer):
    destination_warehouse_id = serializers.IntegerField()


class DividendPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DividendPayment
        fields = [
            'id', 'partner', 'procurement', 'amount', 'currency',
            'fx_rate', 'paid_from_account_id', 'date',
        ]
        read_only_fields = ['id', 'date']


class DividendPaymentCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    procurement_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    paid_from_account_id = serializers.IntegerField(required=False, allow_null=True)
