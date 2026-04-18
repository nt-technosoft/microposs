"""
Partnerships domain — Procurement (partnership-level purchase),
InvestmentContract (Musharaka+Mudaraba hybrid), ProcurementBalance (common pot).

Lives alongside legacy inventory.Receipt during migration (PR-2..PR-9).
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel, ImmutableMixin


class Procurement(ImmutableMixin, TenantModel):
    """
    A procurement event — umbrella over items, expenses, balance and
    (optionally) an InvestmentContract for partnership-financed procurements.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
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
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_procurement'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'procurement_type']),
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
    unit_purchase_price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))

    class Meta:
        db_table = 'partnerships_procurement_item'
        indexes = [
            models.Index(fields=['procurement']),
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

    class Meta:
        db_table = 'partnerships_procurement_expense'
        indexes = [
            models.Index(fields=['procurement']),
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
        max_digits=6,
        decimal_places=4,
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
