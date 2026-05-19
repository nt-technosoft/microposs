"""
Suppliers domain — suppliers, payments, payables, payment schedules, consignment agreements.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel


class PaymentTerms(models.TextChoices):
    """Standard payment terms for procurement / supplier defaults."""
    PREPAID = 'PREPAID', 'Полная предоплата'
    PARTIAL = 'PARTIAL', 'Частичная оплата'
    DEFERRED = 'DEFERRED', 'Отсрочка'
    INSTALLMENT = 'INSTALLMENT', 'Рассрочка'
    CONSIGNMENT = 'CONSIGNMENT', 'Консигнация (реализация)'


class Supplier(TenantModel):
    """Supplier entity."""

    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    default_payment_terms = models.CharField(
        max_length=16,
        choices=PaymentTerms.choices,
        default=PaymentTerms.PREPAID,
        help_text='Default payment terms suggested when creating a procurement.',
    )
    default_currency = models.CharField(
        max_length=3,
        default='UZS',
        help_text='Default obligation currency for this supplier.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppliers_supplier'

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self) -> Decimal:
        """
        Derived A/P aggregate: sum of remaining UZS-equivalent across all
        open payables. Source of truth is `finance.Payment`. Not stored.
        """
        total = Decimal('0')
        for payable in self.payables.filter(
            status__in=[
                SupplierPayable.Status.OPEN,
                SupplierPayable.Status.PARTIALLY_PAID,
            ],
        ):
            remaining_in_obligation = payable.remaining_amount
            rate = Decimal(str(payable.fx_rate_at_obligation or 1))
            total += remaining_in_obligation * rate
        return total.quantize(Decimal('0.01'))


class SupplierPayable(TenantModel):
    """
    A/P obligation to a supplier, created when a procurement is confirmed
    on non-PREPAID terms, or via an amendment, or as a manual penalty.

    USD obligations are fixed at `fx_rate_at_obligation` and not revalued —
    any FX delta at payment time is journalled separately.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Частично оплачен'
        FULLY_PAID = 'FULLY_PAID', 'Полностью оплачен'
        CANCELLED = 'CANCELLED', 'Отменён'

    class Reason(models.TextChoices):
        PROCUREMENT = 'PROCUREMENT', 'Из приёмки'
        AMENDMENT = 'AMENDMENT', 'Изменение условий'
        PENALTY = 'PENALTY', 'Штраф/пеня'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='payables',
    )
    procurement = models.ForeignKey(
        'partnerships.Procurement',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payables',
    )
    settlement = models.ForeignKey(
        'partnerships.ProcurementTerms',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payables',
        help_text='E07 supplier settlement source. Nullable during reset for older payables.',
    )
    original_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency_of_obligation = models.CharField(max_length=3, default='UZS')
    fx_rate_at_obligation = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Snapshot of FX rate at the moment the obligation was created.',
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    reason = models.CharField(
        max_length=16,
        choices=Reason.choices,
        default=Reason.PROCUREMENT,
    )
    deadline_date = models.DateField(
        null=True,
        blank=True,
        help_text='For DEFERRED procurements; may be null for INSTALLMENT (use schedule).',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppliers_payable'
        indexes = [
            models.Index(fields=['tenant', 'supplier', 'status']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'deadline_date']),
        ]

    def __str__(self):
        return (
            f"Payable#{self.pk} {self.supplier.name} "
            f"{self.remaining_amount}/{self.original_amount} {self.currency_of_obligation}"
        )

    @property
    def paid_amount(self) -> Decimal:
        """
        Derived: sum of finance.Payment rows that flowed against the same
        underlying obligation — both PROCUREMENT_COST payments made against
        the procurement before this payable existed, and SUPPLIER_PAYABLE
        payments made directly against this payable after.

        The two targets represent two phases of the same supplier obligation
        (upfront partial + post-receive remainder); pay_workspace_costs is
        gated to OPEN procurement, so post-receive PROCUREMENT_COST writes
        cannot double-count.

        Functional UZS sum is then divided by `fx_rate_at_obligation`
        (snapshot at obligation creation) to land in obligation currency —
        the contractual rate, fixed and not revalued, per Islamic
        accounting principle.
        """
        from apps.finance.models import Payment
        from django.db.models import F, Q, Sum

        targets = Q(
            target_type=Payment.TargetType.SUPPLIER_PAYABLE,
            target_id=self.pk,
        )
        if self.procurement_id is not None:
            targets = targets | Q(
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=self.procurement_id,
            )
        agg = (
            Payment.objects
            .filter(
                tenant_id=self.tenant_id,
                status=Payment.Status.POSTED,
            )
            .filter(targets)
            .aggregate(total_uzs=Sum(F('amount') * F('fx_rate')))
        )
        total_uzs = agg['total_uzs'] or Decimal('0')
        rate = Decimal(str(self.fx_rate_at_obligation or 1))
        if rate == 0:
            return Decimal('0')
        return (Decimal(str(total_uzs)) / rate).quantize(Decimal('0.01'))

    @property
    def remaining_amount(self) -> Decimal:
        return (Decimal(str(self.original_amount or 0)) - self.paid_amount).quantize(Decimal('0.01'))


class PaymentSchedule(TenantModel):
    """
    Installment schedule for a procurement on INSTALLMENT terms.
    Each entry represents one scheduled payment.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает'
        PAID = 'PAID', 'Оплачен'
        OVERDUE = 'OVERDUE', 'Просрочен'
        CANCELLED = 'CANCELLED', 'Отменён'

    procurement_terms = models.ForeignKey(
        'partnerships.ProcurementTerms',
        on_delete=models.CASCADE,
        related_name='schedule_entries',
    )
    sequence_number = models.PositiveIntegerField(
        help_text='1-based ordinal within the schedule.',
    )
    due_date = models.DateField()
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(max_length=3, default='UZS')
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal('0'),
    )

    class Meta:
        db_table = 'suppliers_payment_schedule'
        constraints = [
            models.UniqueConstraint(
                fields=['procurement_terms', 'sequence_number'],
                name='uq_payment_schedule_sequence',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'status', 'due_date']),
            models.Index(fields=['procurement_terms', 'sequence_number']),
        ]

    def __str__(self):
        return f"Schedule#{self.pk} seq={self.sequence_number} {self.amount} {self.currency} @ {self.due_date}"


class SupplierPayment(TenantModel):
    """
    Payment to a supplier (reduces A/P).

    Supports multi-cash allocations: one logical payment can be split across
    several CashAccounts and/or currencies. The `allocations` JSON holds
    `[{cash_account_id, amount, currency}, ...]`. Single-cash payments may
    leave `allocations` empty and use the `payment_method`/legacy fields.
    """

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличные'
        BANK = 'bank', 'Банковский перевод'
        MIXED = 'mixed', 'Смешанный (мульти-касса)'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    payable = models.ForeignKey(
        SupplierPayable,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payments',
    )
    payment = models.ForeignKey(
        'finance.Payment',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='supplier_payment_records',
        help_text='E07 generic payment document backing this supplier payment.',
    )
    schedule_entry = models.ForeignKey(
        PaymentSchedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payments',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    operation_currency = models.CharField(max_length=3, default='UZS')
    operation_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fx_rate_snapshot = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        null=True,
        blank=True,
    )
    functional_amount_uzs = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        null=True,
        blank=True,
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
    )
    allocations = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            'Optional multi-cash allocation: '
            '[{cash_account_id, amount, currency}, ...]. '
            'Empty/null for single-cash payments.'
        ),
    )
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'suppliers_payment'
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_supplier_payment_idempotent',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'supplier', 'date']),
            models.Index(fields=['tenant', 'payable']),
        ]


class ConsignmentAgreement(TenantModel):
    """Terms for consignment with a specific supplier."""

    class RuleType(models.TextChoices):
        FIXED_SUPPLIER_PRICE = 'FIXED_SUPPLIER_PRICE', 'Фиксированная цена поставщика'
        MARGIN = 'margin', 'Фиксированная маржа'
        COMMISSION = 'commission', 'Процент комиссии'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='consignment_agreements',
    )
    rule_type = models.CharField(
        max_length=20,
        choices=RuleType.choices,
    )
    rule_value = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        help_text='Margin amount or commission percentage.',
    )
    damage_liability_on_business = models.BooleanField(
        default=True,
        help_text='If True, damage/loss of consignment goods is on business.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppliers_consignment_agreement'
