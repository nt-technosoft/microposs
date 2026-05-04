"""
Sales domain — POS sessions, sales, cart, returns.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel, ImmutableMixin


class PosSession(TenantModel):
    """
    POS shift/session. Opened at start of work, closed at end.
    Tracks cash reconciliation.
    """

    class SessionStatus(models.TextChoices):
        OPEN = 'open', 'Открыта'
        CLOSED = 'closed', 'Закрыта'

    location = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='pos_sessions',
    )
    opened_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='opened_sessions',
    )
    closed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='closed_sessions',
    )
    status = models.CharField(
        max_length=10,
        choices=SessionStatus.choices,
        default=SessionStatus.OPEN,
    )
    opening_cash = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
    )
    expected_cash = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Calculated on close: opening + cash sales.',
    )
    actual_cash = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Entered by cashier on close.',
    )
    cash_difference = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='actual - expected. Logged in RiskEvent if != 0.',
    )
    opening_cash_by_currency = models.JSONField(
        default=dict,
        blank=True,
        help_text='Native opening cash by currency, e.g. {"UZS": "100000.00", "USD": "20.00"}.',
    )
    expected_cash_by_currency = models.JSONField(
        default=dict,
        blank=True,
        help_text='Native expected cash by currency calculated on close.',
    )
    actual_cash_by_currency = models.JSONField(
        default=dict,
        blank=True,
        help_text='Native actual cash by currency entered on close.',
    )
    cash_difference_by_currency = models.JSONField(
        default=dict,
        blank=True,
        help_text='Native cash difference by currency.',
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sales_pos_session'

    def __str__(self):
        return f"Session #{self.pk} ({self.status})"


class Sale(ImmutableMixin, TenantModel):
    """
    A sale transaction — multi-payment, bound to a warehouse.
    Immutable after status = completed.
    """

    class SaleStatus(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        COMPLETED = 'completed', 'Завершена'
        PARTIALLY_RETURNED = 'partially_returned', 'Частично возвращена'
        RETURNED = 'returned', 'Возвращена'

    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.DRAFT,
    )
    location = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='sales',
    )
    date = models.DateTimeField()
    pos_session = models.ForeignKey(
        PosSession,
        on_delete=models.PROTECT,
        related_name='sales',
    )
    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='sales',
    )
    sold_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='sales',
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
    )
    total_cogs = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Sum of unit_landed_cost * quantity for all lines.',
    )
    client_request_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'sales_sale'
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'pos_session']),
            models.Index(fields=['tenant', 'location', 'date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                name='uq_sale_idempotent',
                condition=models.Q(client_request_id__isnull=False),
            ),
        ]

    def __str__(self):
        return f"Sale #{self.pk} ({self.status})"

    def delete(self, *args, **kwargs):
        raise ValueError('Physical delete forbidden for Sale.')


class SalePayment(TenantModel):
    """
    Single payment tied to a Sale. A sale can have 0..N payments
    (multi-currency, multi-method, partial — any combination).
    """

    class Method(models.TextChoices):
        CASH = 'CASH', 'Наличные'
        CARD = 'CARD', 'Карта'
        TRANSFER = 'TRANSFER', 'Перевод'
        CREDIT = 'CREDIT', 'В долг'

    class Role(models.TextChoices):
        INCOMING = 'INCOMING', 'Приход'
        REFUND = 'REFUND', 'Возврат'

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('1'),
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.INCOMING,
    )
    # FK to finance.CashAccount lands in PR-7; keep as nullable int for now.
    account_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'sales_sale_payment'
        indexes = [
            models.Index(fields=['sale']),
            models.Index(fields=['tenant', 'date']),
        ]


class SaleLine(TenantModel):
    """
    Single line in a sale. ALWAYS references a Lot.
    Stores price snapshots at sale time.
    """

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='sale_lines',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='sale_lines',
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Functional UZS sale price per unit.',
    )
    operation_currency = models.CharField(max_length=3, default='UZS')
    operation_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Native sale price per unit as entered by cashier.',
    )
    fx_rate_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Immutable FX snapshot used to convert operation price to UZS.',
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Snapshot of product price at sale time.',
    )
    price_changed = models.BooleanField(
        default=False,
        help_text='True if unit_price != base_price.',
    )
    discount_reason = models.ForeignKey(
        'catalog.DiscountReason',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sale_lines',
    )
    unit_purchase_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Snapshot from lot.unit_purchase_price.',
    )
    unit_landed_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Snapshot from lot.landed_cost_per_unit.',
    )
    profit_distribution_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Immutable profit allocation at sale time. '
            'Shape: {partner_id: decimal_string, ...}'
        ),
    )

    class Meta:
        db_table = 'sales_sale_line'
        indexes = [
            models.Index(fields=['lot']),
            models.Index(fields=['sale']),
        ]

    @property
    def total(self):
        return self.unit_price * self.quantity

    @property
    def total_cogs(self):
        return self.unit_landed_cost * self.quantity

    @property
    def gross_profit(self):
        return self.total - self.total_cogs


class Return(TenantModel):
    """
    Return operation linked to a specific sale.
    resolution RESTOCK → goods re-enter stock (LotStock += qty).
    resolution DISPOSE → goods are disposed (StockDisposal + LOSS_INCURRED).
    """

    class Resolution(models.TextChoices):
        RESTOCK = 'RESTOCK', 'Оприходовать обратно'
        DISPOSE = 'DISPOSE', 'Утилизировать'

    class Reason(models.TextChoices):
        DEFECT = 'DEFECT', 'Брак'
        CLIENT_REFUSE = 'CLIENT_REFUSE', 'Отказ клиента'
        OTHER = 'OTHER', 'Другое'

    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name='returns',
    )
    processed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
    )
    resolution = models.CharField(
        max_length=10,
        choices=Resolution.choices,
        default=Resolution.RESTOCK,
    )
    reason = models.CharField(
        max_length=20,
        choices=Reason.choices,
        default=Reason.CLIENT_REFUSE,
    )
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'sales_return'
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['sale', 'resolution']),
        ]

    def __str__(self):
        return f"Return #{self.pk} (sale={self.sale_id}, {self.resolution})"


class ReturnLine(TenantModel):
    """Single line in a return. No per-line condition (resolution is Return-level)."""

    return_doc = models.ForeignKey(
        Return,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    sale_line = models.ForeignKey(
        SaleLine,
        on_delete=models.PROTECT,
        related_name='return_lines',
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )

    class Meta:
        db_table = 'sales_return_line'
