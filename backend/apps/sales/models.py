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
        'inventory.Location',
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
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sales_pos_session'

    def __str__(self):
        return f"Session #{self.pk} ({self.status})"


class Sale(ImmutableMixin, TenantModel):
    """
    A completed sale transaction.
    Immutable after status = completed.
    """

    class SaleStatus(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        COMPLETED = 'completed', 'Завершена'
        RETURNED = 'returned', 'Возвращена'

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличные'
        CARD = 'card', 'Карта'
        CREDIT = 'credit', 'В долг'

    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.DRAFT,
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
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
        help_text='Sum of cost_per_unit * quantity for all lines.',
    )
    customer_has_existing_debt = models.BooleanField(
        default=False,
        help_text='Warning flag for UI.',
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
        self.soft_delete()


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
        help_text='Actual sale price per unit.',
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
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Snapshot from lot.cost_per_unit.',
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
        return self.cost_per_unit * self.quantity

    @property
    def gross_profit(self):
        return self.total - self.total_cogs


class SaleReturn(TenantModel):
    """Return operation linked to a specific sale."""

    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name='returns',
    )
    processed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'sales_sale_return'


class SaleReturnLine(TenantModel):
    """Single line in a return."""

    class ReturnCondition(models.TextChoices):
        GOOD = 'good', 'Исправный'
        DAMAGED = 'damaged', 'Повреждённый'

    sale_return = models.ForeignKey(
        SaleReturn,
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
    condition = models.CharField(
        max_length=10,
        choices=ReturnCondition.choices,
    )

    class Meta:
        db_table = 'sales_sale_return_line'
