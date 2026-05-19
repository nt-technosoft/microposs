"""
Partnerships domain — E07 procurement workspace and investment layer.

Legacy procurement-attached contract/balance classes remain only as reference
while the target workspace services are rebuilt.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel, ImmutableMixin
from apps.core.exceptions import ImmutableRecordError


class AgreementActionSource(models.TextChoices):
    BUSINESS_RECORDED = 'BUSINESS_RECORDED', 'Зафиксировано бизнесом'
    INVESTOR_SUBMITTED = 'INVESTOR_SUBMITTED', 'Отправлено инвестором'
    SYSTEM = 'SYSTEM', 'Система'


class AgreementConfirmationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Ожидает подтверждения'
    CONFIRMED = 'CONFIRMED', 'Подтверждено'
    DISPUTED = 'DISPUTED', 'Оспаривается'
    CANCELLED = 'CANCELLED', 'Отменено'


class InvestmentAgreement(TenantModel):
    """Parent investment agreement that can fund multiple concrete procurements."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        PROPOSED = 'PROPOSED', 'Предложен'
        ACCEPTED = 'ACCEPTED', 'Принят'
        REJECTED = 'REJECTED', 'Отклонён'
        OPEN = 'OPEN', 'Открыт'
        ACTIVE = 'ACTIVE', 'Активен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    class LegalMode(models.TextChoices):
        MUDARABA = 'MUDARABA', 'Мудараба'
        MUSHARAKA = 'MUSHARAKA', 'Мушарака'
        HYBRID = 'HYBRID', 'Гибрид'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    legal_mode = models.CharField(
        max_length=20,
        choices=LegalMode.choices,
        null=True,
        blank=True,
        help_text='Legal/contract label only; not a procurement type.',
    )
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

    @property
    def balances(self) -> dict:
        """
        Derived per-currency balance map. Source of truth is the append-only
        event triad: AgreementContribution (+), AgreementWithdrawal (-),
        AgreementAllocation (- TO_PROCUREMENT / + otherwise). Returns
        {currency: 'decimal_string'} to keep the previous JSON shape that
        API callers expect.
        """
        from decimal import Decimal as _D
        totals: dict[str, _D] = {}

        def _bump(cur: str, delta: _D) -> None:
            key = str(cur or 'UZS').upper()
            totals[key] = totals.get(key, _D('0')) + delta

        for c in self.contributions.all():
            _bump(c.currency, _D(str(c.amount)))
        for w in self.withdrawals.all():
            _bump(w.currency, -_D(str(w.amount)))
        for a in self.allocations.all():
            amt = _D(str(a.amount))
            if a.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
                _bump(a.currency, -amt)
            else:
                _bump(a.currency, amt)

        return {
            cur: str(value.quantize(_D('0.01')))
            for cur, value in totals.items()
        }


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


class CapitalCommitment(TenantModel):
    """Planned capital intent by a participant before actual money is received."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='commitments',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='capital_commitments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='capital_commitments_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='capital_commitments_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_capital_commitment'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_capital_commitment_idempotent',
            ),
        ]


class Procurement(ImmutableMixin, TenantModel):
    """
    E07 purchase/workspace root.

    Funding source, supplier settlement, payments, investment agreement and
    receive batches are separate documents coordinated by workspace services.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Частично оприходовано'
        RECEIVED = 'RECEIVED', 'Получен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    class FundingSource(models.TextChoices):
        OWN_FUNDS = 'OWN_FUNDS', 'Собственные средства'
        PARTNERSHIP = 'PARTNERSHIP', 'Партнёрский капитал'

    funding_source = models.CharField(
        max_length=20,
        choices=FundingSource.choices,
        default=FundingSource.OWN_FUNDS,
        help_text='E07 target funding axis.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    primary_currency = models.CharField(
        max_length=3,
        default='UZS',
        help_text='Workspace display/default currency for item and expense drafts.',
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
            models.Index(fields=['tenant', 'funding_source']),
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
        return f"Procurement#{self.pk} {self.funding_source}/{self.status}"


class ProcurementItem(TenantModel):
    """A line item on a procurement — product variant + planned quantity."""

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        READY_FOR_RECEIVE = 'READY_FOR_RECEIVE', 'Готово к приёмке'
        RECEIVED = 'RECEIVED', 'Оприходовано'
        CANCELLED = 'CANCELLED', 'Отменено'

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
    lifecycle_state = models.CharField(
        max_length=24,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_item'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'lifecycle_state']),
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

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        READY_FOR_RECEIVE = 'READY_FOR_RECEIVE', 'Готово к приёмке'
        RECEIVED = 'RECEIVED', 'Оприходовано'
        CANCELLED = 'CANCELLED', 'Отменено'

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
    lifecycle_state = models.CharField(
        max_length=24,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_expense'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'lifecycle_state']),
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

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatch is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatch is append-only.')


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

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchLine is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchLine is append-only.')


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

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchExpense is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchExpense is append-only.')


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

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchCapitalAllocation is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchCapitalAllocation is append-only.')


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
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_contributions_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_contributions_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_contribution'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_agreement_contribution_idempotent',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementContribution is append-only. Record a reversal instead.')


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
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_withdrawals_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_withdrawals_acted',
    )
    reason = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_withdrawal'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_agreement_withdrawal_idempotent',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementWithdrawal is append-only. Record a reversal instead.')


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
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_allocations_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_allocations_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_allocation'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['procurement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
            models.Index(fields=['tenant', 'client_request_id']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementAllocation is append-only. Record a reversal instead.')


class AgreementEvent(TenantModel):
    """Append-only audit event for agreement-level workflow and money facts."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='events',
    )
    event_type = models.CharField(max_length=80)
    occurred_at = models.DateTimeField()
    actor_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_events',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_events',
    )
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    related_model = models.CharField(max_length=80, blank=True, default='')
    related_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        db_table = 'partnerships_agreement_event'
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['agreement', 'event_type']),
            models.Index(fields=['tenant', 'occurred_at']),
            models.Index(fields=['related_model', 'related_id']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementEvent is append-only. Physical delete forbidden.')


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
    paid_from_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    date = models.DateTimeField()

    class Meta:
        db_table = 'partnerships_dividend_payment'
        indexes = [
            models.Index(fields=['partner', 'date']),
            models.Index(fields=['procurement']),
        ]


# =========================================================================
# E01 — Procurement Terms, Amendments, Consignment Returns
# =========================================================================


class ProcurementTerms(TenantModel):
    """
    Payment terms attached to a Procurement (OneToOne).

    Captures the obligation structure: type (PREPAID/PARTIAL/DEFERRED/
    INSTALLMENT/CONSIGNMENT), obligation currency with FX snapshot, total
    amount due, and (for DEFERRED) deadline / (for INSTALLMENT) a schedule
    in `suppliers.PaymentSchedule`.

    For CONSIGNMENT, references the existing `suppliers.ConsignmentAgreement`.
    """

    class Type(models.TextChoices):
        PREPAID = 'PREPAID', 'Полная предоплата'
        PARTIAL = 'PARTIAL', 'Частичная оплата'
        DEFERRED = 'DEFERRED', 'Отсрочка'
        INSTALLMENT = 'INSTALLMENT', 'Рассрочка'
        CONSIGNMENT = 'CONSIGNMENT', 'Консигнация'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыты'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Частично оплачены'
        FULLY_PAID = 'FULLY_PAID', 'Полностью оплачены'
        CANCELLED = 'CANCELLED', 'Отменены'

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        ACTIVE = 'ACTIVE', 'Активный'

    procurement = models.OneToOneField(
        Procurement,
        on_delete=models.CASCADE,
        related_name='terms',
    )
    type = models.CharField(max_length=16, choices=Type.choices)
    lifecycle_state = models.CharField(
        max_length=8,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
        help_text=(
            'DRAFT — terms still being negotiated, fully mutable. '
            'ACTIVE — locked after first finance.Payment or ReceiveBatch; '
            'semantic changes require ProcurementTermsAmendment.'
        ),
    )
    currency_of_obligation = models.CharField(max_length=3, default='UZS')
    fx_rate_at_obligation = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Snapshot of FX rate at obligation date; not revalued.',
    )
    total_amount_due = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        help_text='Total obligation in `currency_of_obligation` (Σ items × prices × fx).',
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    deadline_date = models.DateField(
        null=True,
        blank=True,
        help_text='Only for DEFERRED type. Null otherwise (schedule covers INSTALLMENT).',
    )
    consignment_agreement = models.ForeignKey(
        'suppliers.ConsignmentAgreement',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurement_terms',
        help_text='Only for CONSIGNMENT type.',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_procurement_terms'
        indexes = [
            models.Index(fields=['tenant', 'type', 'status']),
            models.Index(fields=['tenant', 'status', 'deadline_date']),
        ]

    def __str__(self):
        return f"Terms#{self.pk} type={self.type} status={self.status}"

    _MUTABLE_AFTER_ACTIVATION = frozenset({
        'status', 'lifecycle_state', 'updated_at',
    })

    def save(self, *args, **kwargs):
        if self.pk:
            original = ProcurementTerms.objects.filter(pk=self.pk).first()
            if original is not None and original.lifecycle_state == self.LifecycleState.ACTIVE:
                update_fields = kwargs.get('update_fields')
                if update_fields is not None:
                    changing = set(update_fields) - self._MUTABLE_AFTER_ACTIVATION
                else:
                    changing = set()
                    for f in self._meta.fields:
                        name = f.name
                        if name in self._MUTABLE_AFTER_ACTIVATION:
                            continue
                        if getattr(original, name) != getattr(self, name):
                            changing.add(name)
                if changing:
                    from apps.core.exceptions import ImmutableRecordError
                    raise ImmutableRecordError(
                        f"ProcurementTerms#{self.pk} is ACTIVE; "
                        f"cannot modify {sorted(changing)}. Use "
                        f"ProcurementTermsAmendment for semantic changes."
                    )
        super().save(*args, **kwargs)

    def activate(self) -> bool:
        """
        Idempotent transition DRAFT → ACTIVE. Returns True if transition
        happened, False if already ACTIVE. Called at the boundary moments
        (first Payment, first ReceiveBatch) — see workspace_support for the
        canonical activation points.
        """
        if self.lifecycle_state == self.LifecycleState.ACTIVE:
            return False
        self.lifecycle_state = self.LifecycleState.ACTIVE
        self.save(update_fields=['lifecycle_state', 'updated_at'])
        return True

    @property
    def paid_amount(self) -> Decimal:
        """
        Derived: sum of linked finance.Payment(target=PROCUREMENT_COST,
        target_id=self.procurement_id) functional UZS, converted to
        obligation currency via `fx_rate_at_obligation` snapshot.

        Special case: PREPAID terms represent a synthetic full-settlement at
        terms creation (supplier paid in cash before the document existed),
        so paid_amount == total_amount_due without requiring a linked
        Payment. All other types derive from finance.Payment events.

        See SupplierPayable.paid_amount for rationale on snapshot rate.
        """
        if self.type == self.Type.PREPAID:
            return Decimal(str(self.total_amount_due or 0))

        from apps.finance.models import Payment
        from django.db.models import F, Sum

        agg = Payment.objects.filter(
            tenant_id=self.tenant_id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=self.procurement_id,
            status=Payment.Status.POSTED,
        ).aggregate(total_uzs=Sum(F('amount') * F('fx_rate')))
        total_uzs = agg['total_uzs'] or Decimal('0')
        rate = Decimal(str(self.fx_rate_at_obligation or 1))
        if rate == 0:
            return Decimal('0')
        capped = min(
            Decimal(str(self.total_amount_due or 0)),
            (Decimal(str(total_uzs)) / rate).quantize(Decimal('0.01')),
        )
        return capped

    @property
    def remaining_amount(self) -> Decimal:
        return (Decimal(str(self.total_amount_due or 0)) - self.paid_amount).quantize(Decimal('0.01'))


class ProcurementTermsAmendment(TenantModel):
    """
    Explicit amendment to a ProcurementTerms after the procurement has been
    received. Captures before/after snapshot for audit. Silent edits to
    ProcurementTerms are forbidden — every change must produce an amendment.
    """

    terms = models.ForeignKey(
        ProcurementTerms,
        on_delete=models.PROTECT,
        related_name='amendments',
    )
    amended_at = models.DateTimeField()
    changed_by_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurement_terms_amendments',
    )
    change_payload = models.JSONField(
        help_text='Snapshot {before: {...}, after: {...}} of changed fields.',
    )
    reason = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_procurement_terms_amendment'
        indexes = [
            models.Index(fields=['terms', 'amended_at']),
        ]


class ConsignmentReturn(TenantModel):
    """
    A return document for a CONSIGNMENT-typed procurement. Each return can
    contain multiple lines, each with its own `disposition` — allowing mixed
    scenarios (some lines returned to supplier, some disposed, some converted
    to owned inventory).
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        CONFIRMED = 'CONFIRMED', 'Подтверждён'
        CANCELLED = 'CANCELLED', 'Отменён'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='consignment_returns',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='consignment_returns',
    )
    return_date = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_consignment_return'
        indexes = [
            models.Index(fields=['tenant', 'procurement']),
            models.Index(fields=['tenant', 'status', 'return_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_consignment_return_idempotent',
            ),
        ]


class ConsignmentReturnLine(TenantModel):
    """
    A single line of a ConsignmentReturn. The `disposition` determines what
    happens to this quantity of this lot:

    - RETURN_TO_SUPPLIER     stock -, payable - (supplier takes goods back)
    - DISPOSE_SUPPLIER_LOSS  stock -, payable - (supplier eats the loss)
    - DISPOSE_BUSINESS_LOSS  stock -, no payable change (business eats loss)
    - CONVERT_TO_OWN         split lot: old consignment lot quantity -,
                             new owned Lot created at `agreed_price_per_unit`
                             + payable + for the conversion
    """

    class Disposition(models.TextChoices):
        RETURN_TO_SUPPLIER = 'RETURN_TO_SUPPLIER', 'Возврат поставщику'
        DISPOSE_SUPPLIER_LOSS = 'DISPOSE_SUPPLIER_LOSS', 'Списание (на поставщике)'
        DISPOSE_BUSINESS_LOSS = 'DISPOSE_BUSINESS_LOSS', 'Списание (на бизнесе)'
        CONVERT_TO_OWN = 'CONVERT_TO_OWN', 'Перевод в собственность'

    consignment_return = models.ForeignKey(
        ConsignmentReturn,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='consignment_return_lines',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text='Quantity from the lot being processed under this disposition.',
    )
    disposition = models.CharField(
        max_length=24,
        choices=Disposition.choices,
    )
    agreed_price_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        help_text=(
            'Agreed unit price for the disposition. '
            'For RETURN/DISPOSE_*: amount of payable reduction per unit. '
            'For CONVERT_TO_OWN: buyout price per unit.'
        ),
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_consignment_return_line'
        indexes = [
            models.Index(fields=['consignment_return']),
            models.Index(fields=['lot']),
        ]
