"""
Inventory domain — locations, receipts, lots, stock movements.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel, ImmutableMixin


class Location(TenantModel):
    """Warehouse or point of sale."""

    class LocationType(models.TextChoices):
        WAREHOUSE = 'warehouse', 'Склад'
        STORE = 'store', 'Точка продаж'

    name = models.CharField(max_length=255)
    location_type = models.CharField(
        max_length=20,
        choices=LocationType.choices,
        default=LocationType.STORE,
    )
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_location'

    def __str__(self):
        return self.name


class Receipt(ImmutableMixin, TenantModel):
    """
    Intake/Receipt — the ONLY way products enter the system.
    Type determines ownership, financing, and profit distribution.
    """

    class ReceiptType(models.TextChoices):
        BUSINESS_OWNED = 'BUSINESS_OWNED', 'Собственный'
        MUDARABA = 'MUDARABA', 'Мудараба'
        MUSHARAKA = 'MUSHARAKA', 'Мушарака'
        SUPPLIER_PURCHASE = 'SUPPLIER_PURCHASE', 'Закупка у поставщика'
        CONSIGNMENT = 'CONSIGNMENT', 'Консигнация'

    class ReceiptStatus(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        CONFIRMED = 'confirmed', 'Подтверждён'

    receipt_type = models.CharField(
        max_length=20,
        choices=ReceiptType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=ReceiptStatus.choices,
        default=ReceiptStatus.DRAFT,
    )
    date = models.DateTimeField()
    destination = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='receipts',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='receipts',
    )
    investor_contract = models.ForeignKey(
        'investors.InvestorContract',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='receipts',
    )
    payable_terms = models.JSONField(
        null=True,
        blank=True,
        help_text='For SUPPLIER_PURCHASE: {type: paid|credit, due_date: date}',
    )
    consignment_rule = models.JSONField(
        null=True,
        blank=True,
        help_text='For CONSIGNMENT: {type: margin|commission, value: decimal}',
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
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        db_table = 'inventory_receipt'
        indexes = [
            models.Index(fields=['tenant', 'receipt_type', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                name='uq_receipt_idempotent',
                condition=models.Q(client_request_id__isnull=False),
            ),
        ]

    def __str__(self):
        return f"Receipt #{self.pk} ({self.receipt_type})"


class ReceiptLine(TenantModel):
    """Single line item in a receipt."""

    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='receipt_lines',
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )

    class Meta:
        db_table = 'inventory_receipt_line'

    @property
    def total_cost(self):
        return self.cost_per_unit * self.quantity


class ReceiptParticipant(TenantModel):
    """
    Participant in MUDARABA/MUSHARAKA receipt.
    Tracks capital contribution and agreed profit share.
    """

    class ParticipantType(models.TextChoices):
        BUSINESS = 'business', 'Бизнес'
        INVESTOR = 'investor', 'Инвестор'

    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    participant_type = models.CharField(
        max_length=20,
        choices=ParticipantType.choices,
    )
    entity_id = models.IntegerField(
        help_text='ID of Investor or Business.',
    )
    capital_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    capital_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text='Auto-calculated: capital_amount / total_capital.',
    )
    profit_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        help_text='Agreed profit share (0..1). Sum of all must = 1.0.',
    )

    class Meta:
        db_table = 'inventory_receipt_participant'


class Lot(TenantModel):
    """
    Batch/Lot — created automatically when Receipt is confirmed.
    One ReceiptLine = one Lot. Tracks remaining quantity and cost snapshot.
    Physical delete is FORBIDDEN.
    """

    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.PROTECT,
        related_name='lots',
    )
    receipt_line = models.OneToOneField(
        ReceiptLine,
        on_delete=models.PROTECT,
        related_name='lot',
        null=True,
        blank=True,
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='lots',
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name='lots',
    )
    quantity_initial = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Snapshot at receipt time. NEVER changes.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='False when quantity_remaining == 0.',
    )

    class Meta:
        db_table = 'inventory_lot'
        indexes = [
            models.Index(
                fields=['product_variant', 'location', 'is_active'],
                name='idx_lot_sale_lookup',
                condition=models.Q(is_active=True),
            ),
            models.Index(fields=['receipt']),
        ]

    def __str__(self):
        return (
            f"Lot #{self.pk} "
            f"({self.product_variant}) "
            f"qty={self.quantity_remaining}/{self.quantity_initial}"
        )

    def delete(self, *args, **kwargs):
        self.soft_delete()


class StockMovement(TenantModel):
    """Log of every stock movement (receipt, sale, transfer, writeoff)."""

    class MovementType(models.TextChoices):
        RECEIPT = 'receipt', 'Приход'
        SALE = 'sale', 'Продажа'
        TRANSFER = 'transfer', 'Перемещение'
        RETURN = 'return', 'Возврат'
        WRITEOFF = 'writeoff', 'Списание'
        ADJUSTMENT = 'adjustment', 'Корректировка'

    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name='movements',
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )
    quantity = models.IntegerField(
        help_text='Positive = in, Negative = out.',
    )
    from_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movements_from',
    )
    to_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movements_to',
    )
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='E.g., sale, receipt, risk_event.',
    )
    reference_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='ID of the related object.',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'inventory_stock_movement'
        indexes = [
            models.Index(fields=['lot', 'movement_type']),
            models.Index(fields=['tenant', 'created_at']),
        ]
