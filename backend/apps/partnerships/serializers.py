from decimal import Decimal

from rest_framework import serializers

from .models import (
    AgreementAllocation,
    AgreementContribution,
    AgreementEvent,
    AgreementPartner,
    AgreementWithdrawal,
    CapitalCommitment,
    InvestmentAgreement,
    ContractPartner,
    DividendPayment,
    InvestmentContract,
    PartnerLedgerEntry,
    Procurement,
    ProcurementExpense,
    ProcurementExpenseTarget,
    ProcurementItem,
    ProcurementPartnerLedger,
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
    ProcurementTermsAmendment,
)
from .workspace import build_workspace_payload
from apps.core.models import Partner
from apps.suppliers.models import PaymentSchedule


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _ratio(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.000001'))


def _to_contract_currency(amount, currency: str, fx_rate, contract_currency: str) -> Decimal:
    amount_dec = Decimal(str(amount))
    rate_dec = Decimal(str(fx_rate or '1'))
    source = str(currency or contract_currency).upper()
    target = str(contract_currency or 'UZS').upper()
    if source == target:
        return _money(amount_dec)
    if source == 'USD' and target == 'UZS':
        return _money(amount_dec * rate_dec)
    if source == 'UZS' and target == 'USD':
        if rate_dec <= 0:
            return Decimal('0.00')
        return _money(amount_dec / rate_dec)
    return _money(amount_dec)


class ProcurementItemSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(source='product_variant.__str__', read_only=True)

    class Meta:
        model = ProcurementItem
        fields = [
            'id', 'product_variant', 'product_variant_name', 'quantity',
            'unit_purchase_price', 'currency', 'fx_rate', 'goods_ownership',
            'lifecycle_state',
        ]
        read_only_fields = ['id']


class ProcurementExpenseSerializer(serializers.ModelSerializer):
    target_item_ids = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementExpense
        fields = [
            'id', 'expense_type', 'amount', 'currency', 'fx_rate',
            'allocation_method', 'notes', 'lifecycle_state', 'target_item_ids',
        ]
        read_only_fields = ['id']

    def get_target_item_ids(self, obj):
        return list(obj.targets.values_list('item_id', flat=True))


class ProcurementReceiveBatchLineSerializer(serializers.ModelSerializer):
    product_variant_name = serializers.CharField(source='item.product_variant.__str__', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchLine
        fields = [
            'id', 'item', 'lot', 'product_variant_name',
            'quantity_planned', 'quantity_received', 'discrepancy_reason',
            'unit_purchase_price_uzs', 'allocated_expense_uzs', 'landed_cost_per_unit_uzs',
        ]
        read_only_fields = ['id']


class ProcurementReceiveBatchExpenseSerializer(serializers.ModelSerializer):
    expense_type = serializers.CharField(source='expense.expense_type', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchExpense
        fields = ['id', 'expense', 'expense_type', 'allocated_amount_uzs']
        read_only_fields = ['id']


class ProcurementReceiveBatchCapitalAllocationSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)

    class Meta:
        model = ProcurementReceiveBatchCapitalAllocation
        fields = [
            'id', 'partner', 'partner_name', 'role',
            'amount_contract_currency', 'capital_share', 'profit_share',
        ]
        read_only_fields = ['id']


class ProcurementReceiveBatchSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    lines = ProcurementReceiveBatchLineSerializer(many=True, read_only=True)
    expenses = ProcurementReceiveBatchExpenseSerializer(many=True, read_only=True)
    capital_allocations = ProcurementReceiveBatchCapitalAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementReceiveBatch
        fields = [
            'id', 'warehouse', 'warehouse_name', 'received_at',
            'items_count', 'total_inventory_uzs', 'lines', 'expenses',
            'capital_allocations',
        ]
        read_only_fields = ['id']


class PaymentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentSchedule
        fields = [
            'id', 'sequence_number', 'due_date', 'amount',
            'currency', 'status', 'paid_at', 'paid_amount',
        ]
        read_only_fields = ['id']


class ProcurementTermsSerializer(serializers.ModelSerializer):
    schedule = PaymentScheduleSerializer(source='schedule_entries', many=True, read_only=True)
    paid_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )
    remaining_amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True,
    )

    class Meta:
        model = ProcurementTerms
        fields = [
            'id', 'type', 'currency_of_obligation', 'fx_rate_at_obligation',
            'total_amount_due', 'paid_amount', 'remaining_amount', 'status',
            'deadline_date', 'consignment_agreement', 'notes', 'schedule',
        ]
        read_only_fields = ['id', 'paid_amount', 'remaining_amount']


class AgreementPartnerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)

    class Meta:
        model = AgreementPartner
        fields = [
            'id', 'partner', 'partner_name', 'role',
            'planned_capital_share', 'profit_share',
        ]
        read_only_fields = ['id']


class CapitalCommitmentSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = CapitalCommitment
        fields = [
            'id', 'partner', 'partner_name', 'partner_role',
            'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'created_by_name', 'actor_partner_name']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementContributionSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementContribution
        fields = [
            'id', 'partner', 'partner_name', 'partner_role',
            'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementWithdrawalSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementWithdrawal
        fields = [
            'id', 'partner', 'partner_name', 'partner_role',
            'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'reason', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementAllocationSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementAllocation
        fields = [
            'id', 'procurement', 'partner', 'partner_name', 'partner_role',
            'direction', 'amount', 'currency', 'fx_rate', 'date',
            'source', 'confirmation_status', 'created_by',
            'created_by_name', 'actor_partner', 'actor_partner_name',
            'notes', 'client_request_id',
        ]
        read_only_fields = ['id', 'date']

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class AgreementEventSerializer(serializers.ModelSerializer):
    actor_user_name = serializers.SerializerMethodField()
    actor_partner_name = serializers.CharField(source='actor_partner.display_name', read_only=True)

    class Meta:
        model = AgreementEvent
        fields = [
            'id', 'event_type', 'occurred_at',
            'actor_user', 'actor_user_name', 'actor_partner',
            'actor_partner_name', 'source', 'related_model',
            'related_id', 'payload',
        ]
        read_only_fields = fields

    def get_actor_user_name(self, obj):
        user = getattr(obj, 'actor_user', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class InvestmentAgreementListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    partners_count = serializers.SerializerMethodField()
    procurements_count = serializers.SerializerMethodField()
    investor_names = serializers.SerializerMethodField()
    operator_names = serializers.SerializerMethodField()
    investor_shares = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentAgreement
        fields = [
            'id', 'status', 'opened_at', 'closed_at', 'supplier', 'supplier_name',
            'planned_budget', 'currency', 'mudaraba_ratio', 'balances',
            'partners_count', 'investor_names', 'operator_names',
            'investor_shares', 'procurements_count', 'notes',
        ]
        read_only_fields = ['id']

    def get_partners_count(self, obj):
        return obj.partners.count()

    def get_investor_names(self, obj):
        return [
            row.partner.display_name
            for row in obj.partners.all()
            if row.role == AgreementPartner.Role.INVESTOR
        ]

    def get_operator_names(self, obj):
        return [
            row.partner.display_name
            for row in obj.partners.all()
            if row.role == AgreementPartner.Role.OPERATOR
        ]

    def get_procurements_count(self, obj):
        return obj.procurements.count()

    def get_investor_shares(self, obj):
        investor = next(
            (row for row in obj.partners.all() if row.role == AgreementPartner.Role.INVESTOR),
            None,
        )
        if investor is None:
            return None
        budget = float(obj.planned_budget or 0)
        capital = float(investor.planned_capital_share or 0)
        return {
            'capital_percent': round(capital / budget * 100) if budget else 0,
            'profit_percent': round(float(investor.profit_share or 0) * 100),
        }


class InvestmentAgreementDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    partners = AgreementPartnerSerializer(many=True, read_only=True)
    commitments = CapitalCommitmentSerializer(many=True, read_only=True)
    contributions = AgreementContributionSerializer(many=True, read_only=True)
    withdrawals = AgreementWithdrawalSerializer(many=True, read_only=True)
    allocations = AgreementAllocationSerializer(many=True, read_only=True)
    events = AgreementEventSerializer(many=True, read_only=True)
    procurements = serializers.SerializerMethodField()
    participant_totals = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = InvestmentAgreement
        fields = [
            'id', 'status', 'opened_at', 'closed_at', 'supplier', 'supplier_name',
            'mudaraba_ratio', 'loss_rule', 'planned_budget', 'currency',
            'balances', 'notes', 'client_request_id', 'partners',
            'commitments', 'contributions', 'withdrawals', 'allocations',
            'events', 'procurements', 'participant_totals', 'history',
        ]
        read_only_fields = ['id']

    def get_procurements(self, obj):
        return ProcurementListSerializer(obj.procurements.all(), many=True, context=self.context).data

    def get_participant_totals(self, obj):
        rows = {
            partner.partner_id: {
                'partner_id': partner.partner_id,
                'partner_name': partner.partner.display_name,
                'role': partner.role,
                'planned_capital_share': str(_money(partner.planned_capital_share)),
                'planned_profit_share': str(_ratio(partner.profit_share)),
                'contributed_amount': Decimal('0.00'),
                'withdrawn_amount': Decimal('0.00'),
                'allocated_amount': Decimal('0.00'),
                'returned_amount': Decimal('0.00'),
            }
            for partner in obj.partners.all()
        }
        target_currency = str(obj.currency or 'UZS').upper()
        for contribution in obj.contributions.all():
            if contribution.partner_id in rows:
                rows[contribution.partner_id]['contributed_amount'] += _to_contract_currency(
                    contribution.amount, contribution.currency, contribution.fx_rate, target_currency,
                )
        for withdrawal in obj.withdrawals.all():
            if withdrawal.partner_id in rows:
                rows[withdrawal.partner_id]['withdrawn_amount'] += _to_contract_currency(
                    withdrawal.amount, withdrawal.currency, withdrawal.fx_rate, target_currency,
                )
        for allocation in obj.allocations.all():
            if allocation.partner_id not in rows:
                continue
            amount = _to_contract_currency(allocation.amount, allocation.currency, allocation.fx_rate, target_currency)
            if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
                rows[allocation.partner_id]['allocated_amount'] += amount
            else:
                rows[allocation.partner_id]['returned_amount'] += amount
        result = []
        for row in rows.values():
            row['available_amount'] = (
                row['contributed_amount']
                - row['withdrawn_amount']
                - row['allocated_amount']
                + row['returned_amount']
            )
            for key in ['contributed_amount', 'withdrawn_amount', 'allocated_amount', 'returned_amount', 'available_amount']:
                row[key] = str(_money(row[key]))
            result.append(row)
        return sorted(result, key=lambda item: (item['role'], item['partner_id']))

    def get_history(self, obj):
        entries = []
        for contribution in obj.contributions.all():
            entries.append({
                'id': f'contribution-{contribution.id}',
                'kind': 'CONTRIBUTION',
                'date': contribution.date,
                'title': 'Пополнение договора',
                'partner_id': contribution.partner_id,
                'partner_name': contribution.partner.display_name,
                'partner_role': contribution.partner.role,
                'amount': str(_money(contribution.amount)),
                'currency': str(contribution.currency).upper(),
                'procurement_id': None,
                'note': contribution.notes,
            })
        for withdrawal in obj.withdrawals.all():
            entries.append({
                'id': f'withdrawal-{withdrawal.id}',
                'kind': 'WITHDRAWAL',
                'date': withdrawal.date,
                'title': 'Возврат из договора',
                'partner_id': withdrawal.partner_id,
                'partner_name': withdrawal.partner.display_name,
                'partner_role': withdrawal.partner.role,
                'amount': str(_money(withdrawal.amount)),
                'currency': str(withdrawal.currency).upper(),
                'procurement_id': None,
                'note': withdrawal.reason,
            })
        for allocation in obj.allocations.all():
            entries.append({
                'id': f'allocation-{allocation.id}',
                'kind': allocation.direction,
                'date': allocation.date,
                'title': 'В приход' if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT else 'Возврат из прихода',
                'partner_id': allocation.partner_id,
                'partner_name': allocation.partner.display_name,
                'partner_role': allocation.partner.role,
                'amount': str(_money(allocation.amount)),
                'currency': str(allocation.currency).upper(),
                'procurement_id': allocation.procurement_id,
                'note': allocation.notes,
            })
        return sorted(entries, key=lambda item: (item['date'], item['id']), reverse=True)

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


class PartnerLedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerLedgerEntry
        fields = [
            'id', 'date', 'amount', 'currency', 'fx_rate',
            'functional_amount_uzs', 'entry_type', 'source_ref',
        ]
        read_only_fields = ['id']


class ProcurementLedgerSerializer(serializers.ModelSerializer):
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    entries = PartnerLedgerEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProcurementPartnerLedger
        fields = ['id', 'partner', 'partner_name', 'entries']
        read_only_fields = ['id']


class ProcurementListSerializer(serializers.ModelSerializer):
    funding_source = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    agreement_label = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()
    is_receive_ready = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    receive_status = serializers.SerializerMethodField()
    receive_message = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'funding_source', 'status', 'opened_at', 'received_at',
            'supplier', 'supplier_name', 'agreement', 'agreement_label',
            'items_count', 'is_receive_ready',
            'total_amount', 'notes', 'receive_status', 'receive_message',
        ]
        read_only_fields = ['id']

    def get_items_count(self, obj):
        return obj.items.count()

    def get_agreement_label(self, obj):
        if not obj.agreement_id:
            return None
        return f'Инвестдоговор #{obj.agreement_id}'

    def _receive_plan(self, obj):
        cache = self.context.setdefault('_workspace_payload_cache', {})
        if obj.pk not in cache:
            cache[obj.pk] = build_workspace_payload(obj)
        return cache[obj.pk]

    def get_total_amount(self, obj):
        item_total = sum(
            (
                Decimal(str(item.quantity))
                * Decimal(str(item.unit_purchase_price))
                * Decimal(str(item.fx_rate))
                for item in obj.items.all()
            ),
            Decimal('0'),
        )
        expense_total = sum(
            (
                Decimal(str(expense.amount))
                * Decimal(str(expense.fx_rate))
                for expense in obj.expenses.all()
            ),
            Decimal('0'),
        )
        return str((item_total + expense_total).quantize(Decimal('0.01')))

    def get_is_receive_ready(self, obj):
        return bool(self._receive_plan(obj)['readiness']['receive_ready']['ok'])

    def get_receive_status(self, obj):
        return 'READY' if self.get_is_receive_ready(obj) else 'BLOCKED'

    def get_receive_message(self, obj):
        return self._receive_plan(obj)['readiness']['receive_ready']['message']


class ProcurementDetailSerializer(serializers.ModelSerializer):
    funding_source = serializers.CharField(read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    agreement_label = serializers.SerializerMethodField()
    items = ProcurementItemSerializer(many=True, read_only=True)
    expenses = ProcurementExpenseSerializer(many=True, read_only=True)
    contract = InvestmentContractSerializer(read_only=True)
    terms = ProcurementTermsSerializer(read_only=True)
    receive_batches = ProcurementReceiveBatchSerializer(many=True, read_only=True)
    receive_plan = serializers.SerializerMethodField()
    cost_preview = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'funding_source', 'status', 'opened_at', 'received_at', 'closed_at',
            'supplier', 'supplier_name', 'agreement', 'agreement_label',
            'notes', 'client_request_id',
            'items', 'expenses', 'contract', 'balance', 'terms',
            'receive_batches', 'receive_plan', 'cost_preview',
        ]
        read_only_fields = ['id']

    def get_agreement_label(self, obj):
        if not obj.agreement_id:
            return None
        return f'Инвестдоговор #{obj.agreement_id}'

    def get_receive_plan(self, obj):
        payload = build_workspace_payload(obj)
        return {
            'status': 'READY' if payload['readiness']['receive_ready']['ok'] else 'BLOCKED',
            'message': payload['readiness']['receive_ready']['message'],
            'readiness': payload['readiness'],
            'policy': payload['policy'],
        }

    def get_cost_preview(self, obj):
        payload = build_workspace_payload(obj)
        return {
            'items_total_uzs': payload['summaries']['items_total_uzs'],
            'expenses_total_uzs': payload['summaries']['expenses_total_uzs'],
            'payables_total': payload['summaries']['payables_total'],
            'receive_batches_count': payload['summaries']['receive_batches_count'],
        }


class ContractPartnerInputSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=ContractPartner.Role.choices)
    planned_capital_share = serializers.DecimalField(max_digits=14, decimal_places=2)
    profit_share = serializers.DecimalField(max_digits=7, decimal_places=6, required=False, default='0')


class InvestmentContractInputSerializer(serializers.Serializer):
    mudaraba_ratio = serializers.DecimalField(max_digits=7, decimal_places=6)
    planned_budget = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    partners = ContractPartnerInputSerializer(many=True)


class InvestmentAgreementCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    mudaraba_ratio = serializers.DecimalField(max_digits=7, decimal_places=6, required=False)
    planned_budget = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    investor_partner_id = serializers.IntegerField(required=False)
    investor_planned_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    investor_capital_percent = serializers.DecimalField(max_digits=7, decimal_places=4, required=False)
    investor_profit_percent = serializers.DecimalField(max_digits=7, decimal_places=4, required=False)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    partners = ContractPartnerInputSerializer(many=True, required=False)

    def validate(self, attrs):
        if attrs.get('partners'):
            if 'planned_budget' not in attrs or 'mudaraba_ratio' not in attrs:
                raise serializers.ValidationError({
                    'detail': 'Explicit partners payload requires planned_budget and mudaraba_ratio.',
                })
            return attrs

        required = [
            'investor_partner_id',
            'investor_planned_amount',
            'investor_capital_percent',
            'investor_profit_percent',
        ]
        missing = [field for field in required if attrs.get(field) in (None, '')]
        if missing:
            raise serializers.ValidationError({field: 'This field is required.' for field in missing})

        request = self.context.get('request')
        tenant_id = getattr(request, 'tenant_id', None)
        if tenant_id is None:
            raise serializers.ValidationError({'detail': 'Tenant context is required.'})

        operator = Partner.objects.filter(
            tenant_id=tenant_id,
            role=Partner.Role.OPERATOR,
            is_active=True,
        ).first()
        if operator is None:
            raise serializers.ValidationError({'detail': 'Active business operator partner is required.'})

        investor_id = int(attrs['investor_partner_id'])
        if not Partner.objects.filter(
            tenant_id=tenant_id,
            id=investor_id,
            role=Partner.Role.INVESTOR,
            is_active=True,
        ).exists():
            raise serializers.ValidationError({'investor_partner_id': 'Active investor partner is required.'})

        investor_amount = _money(attrs['investor_planned_amount'])
        capital_percent = Decimal(str(attrs['investor_capital_percent']))
        profit_percent = Decimal(str(attrs['investor_profit_percent']))
        if investor_amount <= 0:
            raise serializers.ValidationError({'investor_planned_amount': 'Must be greater than 0.'})
        if capital_percent <= 0 or capital_percent >= 100:
            raise serializers.ValidationError({'investor_capital_percent': 'Must be between 0 and 100.'})
        if profit_percent < 0 or profit_percent > 100:
            raise serializers.ValidationError({'investor_profit_percent': 'Must be between 0 and 100.'})

        investor_capital_share = (capital_percent / Decimal('100')).quantize(Decimal('0.000001'))
        investor_profit_share = (profit_percent / Decimal('100')).quantize(Decimal('0.000001'))
        mudaraba_ratio = (investor_profit_share / investor_capital_share).quantize(Decimal('0.000001'))
        if mudaraba_ratio < 0 or mudaraba_ratio > 1:
            raise serializers.ValidationError({
                'investor_profit_percent': 'Profit formula cannot exceed investor capital ratio in MVP.',
            })

        planned_budget = _money(investor_amount / investor_capital_share)
        operator_amount = _money(planned_budget - investor_amount)
        attrs['planned_budget'] = planned_budget
        attrs['mudaraba_ratio'] = mudaraba_ratio
        attrs['partners'] = [
            {
                'partner_id': investor_id,
                'role': 'INVESTOR',
                'planned_capital_share': investor_amount,
                'profit_share': investor_profit_share,
            },
            {
                'partner_id': operator.id,
                'role': 'OPERATOR',
                'planned_capital_share': operator_amount,
                'profit_share': Decimal('1') - investor_profit_share,
            },
        ]
        return attrs


class AgreementAllocationRowSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class AgreementAllocationCreateSerializer(serializers.Serializer):
    procurement_id = serializers.IntegerField()
    allocations = AgreementAllocationRowSerializer(many=True)


class ProcurementItemInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    product_variant_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price = serializers.DecimalField(max_digits=14, decimal_places=6)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')


class ProcurementExpenseInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
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
    target_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class ProcurementItemSplitSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class ProcurementExpenseTargetsSerializer(serializers.Serializer):
    expense_id = serializers.IntegerField()
    target_item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class PaymentScheduleInputSerializer(serializers.Serializer):
    sequence_number = serializers.IntegerField(required=False)
    due_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)


class ProcurementTermsInputSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=ProcurementTerms.Type.choices)
    currency_of_obligation = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate_at_obligation = serializers.DecimalField(max_digits=16, decimal_places=6, required=False, default='1')
    total_amount_due = serializers.DecimalField(max_digits=16, decimal_places=2)
    deadline_date = serializers.DateField(required=False, allow_null=True)
    consignment_agreement_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ProcurementCreateSerializer(serializers.Serializer):
    client_request_id = serializers.UUIDField(required=False)
    funding_source = serializers.ChoiceField(choices=Procurement.FundingSource.choices, required=False)
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    agreement_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    contract = InvestmentContractInputSerializer(required=False, allow_null=True)
    items = ProcurementItemInputSerializer(many=True, required=False, default=list)
    expenses = ProcurementExpenseInputSerializer(many=True, required=False, default=list)
    terms = ProcurementTermsInputSerializer(required=False, allow_null=True)
    schedule = PaymentScheduleInputSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if not attrs.get('funding_source'):
            raise serializers.ValidationError({'funding_source': 'This field is required.'})
        return attrs


class AgreementContributionCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)


class AgreementWithdrawalCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class ReceiveProcurementSerializer(serializers.Serializer):
    destination_warehouse_id = serializers.IntegerField()
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    capital_allocations = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )
    # E01 — optional terms / schedule for the procurement
    terms_payload = serializers.DictField(required=False, allow_null=True)
    schedule_payload = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
    )


class TermsAmendmentSerializer(serializers.Serializer):
    """Payload for POST /procurements/{id}/terms/amend/"""
    new_fields = serializers.DictField()
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class ProcurementTermsAmendmentSerializer(serializers.ModelSerializer):
    changed_by_user_name = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementTermsAmendment
        fields = [
            'id', 'amended_at', 'changed_by_user',
            'changed_by_user_name', 'change_payload', 'reason',
        ]
        read_only_fields = fields

    def get_changed_by_user_name(self, obj):
        user = getattr(obj, 'changed_by_user', None)
        if user is None:
            return ''
        return user.get_full_name() or user.get_username()


class ConsignmentReturnLineSerializer(serializers.Serializer):
    lot_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    disposition = serializers.ChoiceField(choices=[
        'RETURN_TO_SUPPLIER',
        'DISPOSE_SUPPLIER_LOSS',
        'DISPOSE_BUSINESS_LOSS',
        'CONVERT_TO_OWN',
    ])
    agreed_price_per_unit = serializers.DecimalField(max_digits=14, decimal_places=6)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ConsignmentReturnCreateSerializer(serializers.Serializer):
    """Payload for POST /procurements/{id}/consignment-return/"""
    warehouse_id = serializers.IntegerField()
    lines = ConsignmentReturnLineSerializer(many=True)
    notes = serializers.CharField(required=False, default='', allow_blank=True)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)


class PayProcurementItemsSerializer(serializers.Serializer):
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class PayProcurementExpensesSerializer(serializers.Serializer):
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    cash_account_id = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, default='', allow_blank=True)


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
