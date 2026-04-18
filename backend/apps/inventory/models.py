"""
Inventory domain — locations, receipts, lots, stock movements.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel, ImmutableMixin


class Warehouse(TenantModel):
    """Storage facility or retail point."""

    class WarehouseKind(models.TextChoices):
        STORAGE = 'STORAGE', 'Склад'
        SHOP = 'SHOP', 'Магазин'

    name = models.CharField(max_length=255)
    kind = models.CharField(
        max_length=20,
        choices=WarehouseKind.choices,
        default=WarehouseKind.SHOP,
    )
    address = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_warehouse'

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
        Warehouse,
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
    Batch/Lot — created automatically when a Procurement is received
    (legacy: Receipt.confirm). Cost snapshot + immutable contract snapshot.
    Multi-warehouse quantity tracked in LotStock.
    Physical delete is FORBIDDEN.
    """

    # Legacy linkage to the old Receipt domain (kept nullable for
    # backward compatibility until PR-9 drops it).
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.PROTECT,
        related_name='lots',
        null=True,
        blank=True,
    )
    receipt_line = models.OneToOneField(
        ReceiptLine,
        on_delete=models.PROTECT,
        related_name='lot',
        null=True,
        blank=True,
    )
    # New linkage — procurement-driven lots.
    procurement_item = models.ForeignKey(
        'partnerships.ProcurementItem',
        on_delete=models.PROTECT,
        related_name='lots',
        null=True,
        blank=True,
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='lots',
    )
    quantity_initial = models.PositiveIntegerField()
    unit_purchase_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Supplier price at receipt time — no landed costs allocated.',
    )
    landed_cost_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Unit purchase price + allocated landed expenses. Immutable.',
    )
    contract_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Immutable snapshot of partner shares at receive time. '
            'Shape: {mudaraba_ratio, loss_rule, partners: [{partner_id, role, capital_share, profit_share}]}'
        ),
    )
    received_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text='False when total quantity_remaining across warehouses == 0.',
    )

    class Meta:
        db_table = 'inventory_lot'
        indexes = [
            models.Index(fields=['product_variant', 'is_active']),
            models.Index(fields=['receipt']),
            models.Index(fields=['procurement_item']),
        ]

    def __str__(self):
        return f"Lot #{self.pk} ({self.product_variant})"

    def delete(self, *args, **kwargs):
        self.soft_delete()


class LotStock(TenantModel):
    """
    Per-warehouse remaining quantity for a Lot.
    Invariant: sum(LotStock.quantity_remaining for a lot) <= Lot.quantity_initial.
    """

    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name='stocks',
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='lot_stocks',
    )
    quantity_remaining = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'inventory_lot_stock'
        indexes = [
            models.Index(fields=['warehouse', 'quantity_remaining']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['lot', 'warehouse'],
                name='uq_lotstock_lot_warehouse',
            ),
        ]

    def __str__(self):
        return f"LotStock lot={self.lot_id} wh={self.warehouse_id} qty={self.quantity_remaining}"


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
        Warehouse,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movements_from',
    )
    to_location = models.ForeignKey(
        Warehouse,
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


class StockDisposal(TenantModel):
    """
    Disposal of inventory — damaged return (DISPOSE), writeoff, expiry.
    Append-only operational record; loss distribution handled by PartnerLedger.
    Stock effect: Lot.quantity_initial is decremented (LotStock unchanged since goods
    never came back on-shelf). For pure writeoffs without a prior sale, LotStock is
    also decremented at the chosen warehouse.
    """

    class Reason(models.TextChoices):
        DEFECT = 'DEFECT', 'Брак'
        EXPIRED = 'EXPIRED', 'Срок годности'
        DAMAGED_RETURN = 'DAMAGED_RETURN', 'Возврат брака'
        WRITEOFF = 'WRITEOFF', 'Списание'
        OTHER = 'OTHER', 'Другое'

    lot = models.ForeignKey(
        Lot,
        on_delete=models.PROTECT,
        related_name='disposals',
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='disposals',
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=20, choices=Reason.choices)
    loss_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='quantity × landed_cost_per_unit at disposal time.',
    )
    return_ref = models.ForeignKey(
        'sales.Return',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disposals',
    )
    risk_event_ref = models.ForeignKey(
        'risk.RiskEvent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disposals',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'inventory_stock_disposal'
        indexes = [
            models.Index(fields=['lot', 'reason']),
            models.Index(fields=['tenant', 'created_at']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('StockDisposal is append-only. Physical delete forbidden.')

    def __str__(self):
        return f"Disposal lot={self.lot_id} qty={self.quantity} reason={self.reason}"
