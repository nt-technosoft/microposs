from decimal import Decimal

from rest_framework import serializers

from .models import (
    BalanceContribution,
    ProcurementBalanceExchange,
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
from .services import build_procurement_cost_preview, build_receive_plan


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
            'unit_purchase_price', 'currency', 'fx_rate', 'status',
        ]
        read_only_fields = ['id']


class ProcurementExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementExpense
        fields = [
            'id', 'expense_type', 'amount', 'currency', 'fx_rate',
            'allocation_method', 'notes', 'status',
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
    exchanges = serializers.SerializerMethodField()
    is_zero = serializers.SerializerMethodField()
    contributions = serializers.SerializerMethodField()
    withdrawals = serializers.SerializerMethodField()
    participant_totals = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementBalance
        fields = [
            'balances',
            'is_zero',
            'exchanges',
            'contributions',
            'withdrawals',
            'participant_totals',
            'history',
        ]

    def get_is_zero(self, obj):
        balances = obj.balances or {}
        return all(Decimal(str(value)) == Decimal('0') for value in balances.values())

    def get_exchanges(self, obj):
        return ProcurementBalanceExchangeSerializer(obj.exchanges.all(), many=True).data

    def get_contributions(self, obj):
        return BalanceContributionSerializer(obj.contributions.all().order_by('-date', '-id'), many=True).data

    def get_withdrawals(self, obj):
        return BalanceWithdrawalSerializer(obj.withdrawals.all().order_by('-date', '-id'), many=True).data

    def get_participant_totals(self, obj):
        contract = getattr(obj.procurement, 'contract', None)
        if contract is None:
            return []

        partners = list(contract.contract_partners.all())
        contract_currency = str(contract.currency or 'UZS').upper()
        rows: dict[int, dict] = {
            partner.partner_id: {
                'partner_id': partner.partner_id,
                'partner_name': partner.partner.display_name,
                'role': partner.role,
                'contract_currency': contract_currency,
                'planned_capital_share': str(_money(Decimal(str(partner.planned_capital_share)))),
                'planned_profit_share': str(_ratio(Decimal(str(partner.profit_share)))),
                'contributed_amount': '0.00',
                'withdrawn_amount': '0.00',
                'net_capital': '0.00',
                'actual_capital_share': '0.000000',
            }
            for partner in partners
        }

        for contribution in obj.contributions.all():
            if contribution.partner_id not in rows:
                continue
            current = Decimal(rows[contribution.partner_id]['contributed_amount'])
            rows[contribution.partner_id]['contributed_amount'] = str(_money(
                current + _to_contract_currency(
                    contribution.amount,
                    contribution.currency,
                    contribution.fx_rate,
                    contract_currency,
                )
            ))

        for withdrawal in obj.withdrawals.filter(partner_id__isnull=False):
            if withdrawal.partner_id not in rows:
                continue
            current = Decimal(rows[withdrawal.partner_id]['withdrawn_amount'])
            rows[withdrawal.partner_id]['withdrawn_amount'] = str(_money(
                current + _to_contract_currency(
                    withdrawal.amount,
                    withdrawal.currency,
                    withdrawal.fx_rate,
                    contract_currency,
                )
            ))

        net_total = Decimal('0.00')
        for row in rows.values():
            net_amount = _money(Decimal(row['contributed_amount']) - Decimal(row['withdrawn_amount']))
            row['net_capital'] = str(net_amount)
            if net_amount > 0:
                net_total += net_amount

        if net_total > 0:
            for row in rows.values():
                net_amount = Decimal(row['net_capital'])
                row['actual_capital_share'] = str(_ratio(net_amount / net_total)) if net_amount > 0 else '0.000000'

        return sorted(rows.values(), key=lambda item: (item['role'], item['partner_id']))

    def get_history(self, obj):
        entries: list[dict] = []

        for contribution in obj.contributions.all():
            entries.append({
                'id': f'contribution-{contribution.id}',
                'kind': 'CONTRIBUTION',
                'date': contribution.date,
                'title': 'Пополнение баланса',
                'partner_id': contribution.partner_id,
                'partner_name': contribution.partner.display_name,
                'partner_role': contribution.partner.role,
                'amount': str(_money(Decimal(str(contribution.amount)))),
                'currency': str(contribution.currency).upper(),
                'secondary_amount': None,
                'secondary_currency': None,
                'fx_rate': str(contribution.fx_rate),
                'note': contribution.notes,
            })

        for withdrawal in obj.withdrawals.all():
            reason = str(withdrawal.reason or '')
            title = 'Списание баланса'
            if withdrawal.partner_id is None and 'Item payment' in reason:
                title = 'Оплата товаров'
            elif withdrawal.partner_id is None and 'Expense payment' in reason:
                title = 'Оплата расходов'
            elif withdrawal.partner_id is not None:
                title = 'Возврат излишка'

            entries.append({
                'id': f'withdrawal-{withdrawal.id}',
                'kind': 'WITHDRAWAL',
                'date': withdrawal.date,
                'title': title,
                'partner_id': withdrawal.partner_id,
                'partner_name': withdrawal.partner.display_name if withdrawal.partner_id else None,
                'partner_role': withdrawal.partner.role if withdrawal.partner_id else None,
                'amount': str(_money(Decimal(str(withdrawal.amount)))),
                'currency': str(withdrawal.currency).upper(),
                'secondary_amount': None,
                'secondary_currency': None,
                'fx_rate': str(withdrawal.fx_rate),
                'note': reason,
            })

        for exchange in obj.exchanges.all():
            entries.append({
                'id': f'exchange-{exchange.id}',
                'kind': 'EXCHANGE',
                'date': exchange.date,
                'title': 'Обмен валют',
                'partner_id': None,
                'partner_name': None,
                'partner_role': None,
                'amount': str(_money(Decimal(str(exchange.from_amount)))),
                'currency': str(exchange.from_currency).upper(),
                'secondary_amount': str(_money(Decimal(str(exchange.to_amount)))),
                'secondary_currency': str(exchange.to_currency).upper(),
                'fx_rate': str(exchange.rate),
                'note': exchange.notes,
            })

        return sorted(entries, key=lambda item: (item['date'], item['id']), reverse=True)


class ProcurementBalanceExchangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcurementBalanceExchange
        fields = [
            'id', 'from_currency', 'from_amount', 'to_currency', 'to_amount',
            'rate', 'date', 'notes',
        ]
        read_only_fields = ['id', 'date']


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
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items_count = serializers.SerializerMethodField()
    is_receive_ready = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    receive_status = serializers.SerializerMethodField()
    receive_message = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'procurement_type', 'status', 'opened_at', 'received_at',
            'supplier', 'supplier_name', 'items_count', 'is_receive_ready',
            'total_amount', 'notes', 'receive_status', 'receive_message',
        ]
        read_only_fields = ['id']

    def get_items_count(self, obj):
        return obj.items.count()

    def _receive_plan(self, obj):
        cache = self.context.setdefault('_receive_plan_cache', {})
        if obj.pk not in cache:
            cache[obj.pk] = build_receive_plan(obj)
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
        return self._receive_plan(obj)['status'] in ('READY', 'AUTO_SURPLUS')

    def get_receive_status(self, obj):
        return self._receive_plan(obj)['status']

    def get_receive_message(self, obj):
        return self._receive_plan(obj)['message']


class ProcurementDetailSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    items = ProcurementItemSerializer(many=True, read_only=True)
    expenses = ProcurementExpenseSerializer(many=True, read_only=True)
    contract = InvestmentContractSerializer(read_only=True)
    balance = ProcurementBalanceSerializer(read_only=True)
    receive_plan = serializers.SerializerMethodField()
    cost_preview = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            'id', 'procurement_type', 'status', 'opened_at', 'received_at', 'closed_at',
            'supplier', 'supplier_name', 'notes', 'client_request_id',
            'items', 'expenses', 'contract', 'balance', 'receive_plan', 'cost_preview',
        ]
        read_only_fields = ['id']

    def get_receive_plan(self, obj):
        return build_receive_plan(obj)

    def get_cost_preview(self, obj):
        return build_procurement_cost_preview(obj)


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
    partner_name = serializers.CharField(source='partner.display_name', read_only=True)
    partner_role = serializers.CharField(source='partner.role', read_only=True)

    class Meta:
        model = BalanceContribution
        fields = ['id', 'partner', 'partner_name', 'partner_role', 'amount', 'currency', 'fx_rate', 'date', 'notes']
        read_only_fields = ['id', 'date']


class BalanceContributionCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class BalanceWithdrawalSerializer(serializers.ModelSerializer):
    partner_name = serializers.SerializerMethodField()
    partner_role = serializers.SerializerMethodField()

    class Meta:
        model = BalanceWithdrawal
        fields = ['id', 'partner', 'partner_name', 'partner_role', 'amount', 'currency', 'fx_rate', 'date', 'reason']
        read_only_fields = ['id', 'date']

    def get_partner_name(self, obj):
        return getattr(obj.partner, 'display_name', None)

    def get_partner_role(self, obj):
        return getattr(obj.partner, 'role', None)


class BalanceWithdrawalCreateSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField(max_length=3, required=False, default='UZS')
    fx_rate = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default='1')
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class BalanceExchangeCreateSerializer(serializers.Serializer):
    from_currency = serializers.CharField(max_length=3)
    from_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    to_currency = serializers.CharField(max_length=3)
    rate = serializers.DecimalField(max_digits=14, decimal_places=6)
    notes = serializers.CharField(required=False, default='', allow_blank=True)


class ReceiveProcurementSerializer(serializers.Serializer):
    destination_warehouse_id = serializers.IntegerField()


class PayProcurementItemsSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, default='', allow_blank=True)


class PayProcurementExpensesSerializer(serializers.Serializer):
    expense_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
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
