"""
Partnerships domain — Procurement (partnership-level purchase),
InvestmentContract (Musharaka+Mudaraba hybrid), ProcurementBalance (common pot).

Lives alongside legacy inventory.Receipt during migration (PR-2..PR-9).
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel, ImmutableMixin


class InvestmentAgreement(TenantModel):
    """Parent investment agreement that can fund multiple concrete procurements."""

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        ACTIVE = 'ACTIVE', 'Активен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='investment_agreements',
    )
    mudaraba_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        help_text='m in [0..1]; investor profit = capital * m',
    )
    loss_rule = models.CharField(
        max_length=20,
        choices=[('BY_CAPITAL', 'По доле капитала')],
        default='BY_CAPITAL',
    )
    planned_budget = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    balances = models.JSONField(default=dict, help_text='Map<currency, decimal_string>')
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_investment_agreement'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'opened_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_investment_agreement_idempotent',
            ),
        ]

    def __str__(self):
        return f"InvestmentAgreement#{self.pk} {self.status}"


class AgreementPartner(TenantModel):
    """A partner participating in a parent investment agreement."""

    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='partners',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    planned_capital_share = models.DecimalField(max_digits=14, decimal_places=2)
    profit_share = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal('0'))

    class Meta:
        db_table = 'partnerships_agreement_partner'
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['agreement', 'partner', 'role'],
                name='uq_agreement_partner_role',
            ),
        ]


class Procurement(ImmutableMixin, TenantModel):
    """
    A procurement event — umbrella over items, expenses, balance and
    (optionally) an InvestmentContract for partnership-financed procurements.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Частично оприходовано'
        RECEIVED = 'RECEIVED', 'Получен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    class Type(models.TextChoices):
        OWN_FUNDS = 'OWN_FUNDS', 'Собственные средства'
        PARTNERSHIP = 'PARTNERSHIP', 'Партнёрский'
        MUSHARAKA = 'MUSHARAKA', 'Мушарака'
        DISTRIBUTOR = 'DISTRIBUTOR', 'Дистрибуторский'  # frozen: DISTRIBUTOR is deferred, do not develop

    procurement_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    opened_at = models.DateTimeField()
    received_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurements',
    )
    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurements',
    )
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_procurement'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'procurement_type']),
            models.Index(fields=['tenant', 'agreement']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_procurement_idempotent',
            ),
        ]

    def __str__(self):
        return f"Procurement#{self.pk} {self.procurement_type}/{self.status}"


class ProcurementItem(TenantModel):
    """A line item on a procurement — product variant + planned quantity."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        PAID = 'PAID', 'Оплачено'
        RECEIVED = 'RECEIVED', 'Оприходовано'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='procurement_items',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price = models.DecimalField(max_digits=14, decimal_places=6)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_item'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'status']),
        ]


class ProcurementExpense(TenantModel):
    """Landed cost components — logistics, duties, fees, etc."""

    class ExpenseType(models.TextChoices):
        LOGISTICS = 'LOGISTICS', 'Логистика'
        CUSTOMS = 'CUSTOMS', 'Таможня'
        FEE = 'FEE', 'Комиссия'
        OTHER = 'OTHER', 'Прочее'

    class AllocationMethod(models.TextChoices):
        BY_VALUE = 'BY_VALUE', 'Пропорционально стоимости'
        BY_QUANTITY = 'BY_QUANTITY', 'Пропорционально количеству'
        BY_WEIGHT = 'BY_WEIGHT', 'Пропорционально весу'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        PAID = 'PAID', 'Оплачено'
        RECEIVED = 'RECEIVED', 'Оприходовано'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.CASCADE,
        related_name='expenses',
    )
    expense_type = models.CharField(max_length=20, choices=ExpenseType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    allocation_method = models.CharField(
        max_length=20,
        choices=AllocationMethod.choices,
        default=AllocationMethod.BY_VALUE,
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_expense'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'status']),
        ]


class ProcurementExpenseTarget(TenantModel):
    """Explicit item scope for a procurement expense. Empty target set means all items."""

    expense = models.ForeignKey(
        ProcurementExpense,
        on_delete=models.CASCADE,
        related_name='targets',
    )
    item = models.ForeignKey(
        ProcurementItem,
        on_delete=models.CASCADE,
        related_name='expense_targets',
    )

    class Meta:
        db_table = 'partnerships_procurement_expense_target'
        indexes = [
            models.Index(fields=['expense']),
            models.Index(fields=['item']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['expense', 'item'],
                name='uq_procurement_expense_target',
            ),
        ]


class ProcurementReceiveBatch(TenantModel):
    """One physical receive operation inside a procurement."""

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='receive_batches',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='procurement_receive_batches',
    )
    received_at = models.DateTimeField()
    items_count = models.PositiveIntegerField(default=0)
    total_inventory_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))

    class Meta:
        db_table = 'partnerships_procurement_receive_batch'
        ordering = ['-received_at', '-id']
        indexes = [
            models.Index(fields=['procurement', 'received_at'], name='partnership_procure_f0a2ed_idx'),
            models.Index(fields=['warehouse'], name='partnership_warehou_3f31c8_idx'),
        ]


class ProcurementReceiveBatchLine(TenantModel):
    """A received procurement item snapshot inside a receive batch."""

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    item = models.ForeignKey(
        ProcurementItem,
        on_delete=models.PROTECT,
        related_name='receive_batch_lines',
    )
    lot = models.OneToOneField(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='receive_batch_line',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    allocated_expense_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    landed_cost_per_unit_uzs = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_line'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_5e6e1d_idx'),
            models.Index(fields=['item'], name='partnership_item_id_bf9414_idx'),
            models.Index(fields=['lot'], name='partnership_lot_id_776a8e_idx'),
        ]


class ProcurementReceiveBatchExpense(TenantModel):
    """Expense amount fixed into a receive batch."""

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='expenses',
    )
    expense = models.ForeignKey(
        ProcurementExpense,
        on_delete=models.PROTECT,
        related_name='receive_batch_expenses',
    )
    allocated_amount_uzs = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_expense'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_2b88d7_idx'),
            models.Index(fields=['expense'], name='partnership_expense_cebc8a_idx'),
        ]


class ProcurementReceiveBatchCapitalAllocation(TenantModel):
    """Capital/profit snapshot fixed for one receive batch."""

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='capital_allocations',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='procurement_receive_batch_allocations',
    )
    role = models.CharField(max_length=20, choices=[('INVESTOR', 'Инвестор'), ('OPERATOR', 'Оператор')])
    amount_contract_currency = models.DecimalField(max_digits=20, decimal_places=2)
    capital_share = models.DecimalField(max_digits=8, decimal_places=6)
    profit_share = models.DecimalField(max_digits=8, decimal_places=6)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_capital_allocation'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_19d320_idx'),
            models.Index(fields=['partner'], name='partnership_partner_32d0cb_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'partner'],
                name='uq_receive_batch_capital_partner',
            ),
        ]


class InvestmentContract(TenantModel):
    """
    Musharaka+Mudaraba hybrid contract attached to a partnership procurement.
    Profit formula:
      profit_investor_i = capital_i * mudaraba_ratio
      profit_operator = capital_op + Σ(capital_investor_i * (1 - mudaraba_ratio))
    Loss rule: by capital share (shariah hardcode).
    """

    class LossRule(models.TextChoices):
        BY_CAPITAL = 'BY_CAPITAL', 'По доле капитала'

    procurement = models.OneToOneField(
        Procurement,
        on_delete=models.CASCADE,
        related_name='contract',
    )
    mudaraba_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        help_text='m in [0..1]; investor profit = capital * m',
    )
    loss_rule = models.CharField(
        max_length=20,
        choices=LossRule.choices,
        default=LossRule.BY_CAPITAL,
    )
    planned_budget = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')

    class Meta:
        db_table = 'partnerships_investment_contract'


class ContractPartner(TenantModel):
    """A single partner participating in an InvestmentContract."""

    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'

    contract = models.ForeignKey(
        InvestmentContract,
        on_delete=models.CASCADE,
        related_name='contract_partners',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='contract_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    planned_capital_share = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Planned capital in contract currency',
    )
    profit_share = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        help_text='Derived profit ratio (snapshot) — recomputed on receive',
        default=Decimal('0'),
    )

    class Meta:
        db_table = 'partnerships_contract_partner'
        indexes = [
            models.Index(fields=['contract']),
            models.Index(fields=['partner']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'partner', 'role'],
                name='uq_contract_partner_role',
            ),
        ]


class ProcurementBalance(TenantModel):
    """
    Common pot for a procurement — multi-currency balance map.
    Contributions and withdrawals mutate the `balances` JSON field.
    """

    procurement = models.OneToOneField(
        Procurement,
        on_delete=models.CASCADE,
        related_name='balance',
    )
    balances = models.JSONField(
        default=dict,
        help_text='Map<currency, decimal_string>',
    )

    class Meta:
        db_table = 'partnerships_procurement_balance'


class BalanceContribution(TenantModel):
    """A partner adds capital into the procurement balance."""

    balance = models.ForeignKey(
        ProcurementBalance,
        on_delete=models.CASCADE,
        related_name='contributions',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='contributions',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_balance_contribution'
        indexes = [
            models.Index(fields=['balance']),
            models.Index(fields=['partner']),
        ]


class BalanceWithdrawal(TenantModel):
    """A spend from the common pot to pay for an item or expense."""

    balance = models.ForeignKey(
        ProcurementBalance,
        on_delete=models.CASCADE,
        related_name='withdrawals',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='withdrawals',
        help_text='Set when withdrawal attributed to a specific partner',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_balance_withdrawal'
        indexes = [
            models.Index(fields=['balance']),
        ]


class ProcurementBalanceExchange(TenantModel):
    """Explicit FX conversion inside a procurement balance."""

    balance = models.ForeignKey(
        ProcurementBalance,
        on_delete=models.CASCADE,
        related_name='exchanges',
    )
    from_currency = models.CharField(max_length=3, default='UZS')
    from_amount = models.DecimalField(max_digits=14, decimal_places=2)
    to_currency = models.CharField(max_length=3, default='USD')
    to_amount = models.DecimalField(max_digits=14, decimal_places=2)
    rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_balance_exchange'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['balance']),
        ]


class AgreementContribution(TenantModel):
    """A partner adds money into the parent investment agreement balance."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='contributions',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_contributions',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_agreement_contribution'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
        ]


class AgreementWithdrawal(TenantModel):
    """Money returned from the parent investment agreement to a partner."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='withdrawals',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_withdrawals',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    reason = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_agreement_withdrawal'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
        ]


class AgreementAllocation(TenantModel):
    """Capital moved between parent agreement balance and a concrete procurement."""

    class Direction(models.TextChoices):
        TO_PROCUREMENT = 'TO_PROCUREMENT', 'В приход'
        FROM_PROCUREMENT = 'FROM_PROCUREMENT', 'Из прихода'

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.PROTECT,
        related_name='allocations',
    )
    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='agreement_allocations',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_allocations',
    )
    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.TO_PROCUREMENT,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_agreement_allocation'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['procurement']),
            models.Index(fields=['partner']),
        ]


# ─── Partner Ledger ────────────────────────────────────────────────────────────

class ProcurementPartnerLedger(TenantModel):
    """
    Per-procurement ledger for a single partner.
    Accumulates capital in/out, accrued profit, dividends paid, losses.
    Replaces the old denormalized InvestorSummary.
    """

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='partner_ledgers',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='ledgers',
    )

    class Meta:
        db_table = 'partnerships_partner_ledger'
        constraints = [
            models.UniqueConstraint(
                fields=['procurement', 'partner'],
                name='uq_ledger_procurement_partner',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'partner']),
        ]

    def __str__(self):
        return f"Ledger procurement={self.procurement_id} partner={self.partner_id}"


class PartnerLedgerEntry(TenantModel):
    """
    Immutable double-entry line on a partner ledger.
    Always append-only — never update or delete.
    """

    class EntryType(models.TextChoices):
        CAPITAL_IN = 'CAPITAL_IN', 'Внос капитала'
        CAPITAL_OUT = 'CAPITAL_OUT', 'Вывод капитала'
        PROFIT_ACCRUED = 'PROFIT_ACCRUED', 'Начислена прибыль'
        PROFIT_REVERSED = 'PROFIT_REVERSED', 'Сторно прибыли'
        DIVIDEND_PAID = 'DIVIDEND_PAID', 'Выплачен дивиденд'
        LOSS_INCURRED = 'LOSS_INCURRED', 'Зафиксирован убыток'

    ledger = models.ForeignKey(
        ProcurementPartnerLedger,
        on_delete=models.PROTECT,
        related_name='entries',
    )
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Snapshot rate to UZS for this ledger entry.',
    )
    functional_amount_uzs = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Entry amount converted to tenant functional currency (UZS).',
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    source_ref = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='E.g. "sale_line:42", "risk_event:7", "contribution:3"',
    )

    class Meta:
        db_table = 'partnerships_ledger_entry'
        indexes = [
            models.Index(fields=['ledger', 'entry_type']),
            models.Index(fields=['tenant', 'date']),
        ]

    def save(self, *args, **kwargs):
        if self.amount and not self.functional_amount_uzs:
            if str(self.currency).upper() == 'UZS':
                self.fx_rate = Decimal('1')
                self.functional_amount_uzs = Decimal(str(self.amount)).quantize(Decimal('0.01'))
            else:
                self.functional_amount_uzs = (
                    Decimal(str(self.amount)) * Decimal(str(self.fx_rate or Decimal('1')))
                ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('PartnerLedgerEntry is append-only. Physical delete forbidden.')


class DividendPayment(TenantModel):
    """
    Actual dividend payout to a partner from procurement profit.
    Invariant enforced in services: amount <= profit_pending_payout.
    """

    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='dividend_payments',
    )
    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='dividend_payments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    # FK to finance.CashAccount lands in PR-7; int placeholder for now.
    paid_from_account_id = models.IntegerField(null=True, blank=True)
    date = models.DateTimeField()

    class Meta:
        db_table = 'partnerships_dividend_payment'
        indexes = [
            models.Index(fields=['partner', 'date']),
            models.Index(fields=['procurement']),
        ]
