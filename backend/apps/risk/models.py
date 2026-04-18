"""
Risk domain — risk events, inventory checks.
"""

from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TenantModel


class RiskEvent(TenantModel):
    """
    Risk Event Log — any event that may affect investors or financials.
    Auto-created on writeoffs, damage, returns, inventory mismatches.
    """

    class EventType(models.TextChoices):
        WRITEOFF = 'writeoff', 'Списание'
        DAMAGE = 'damage', 'Брак'
        LOSS = 'loss', 'Пропажа'
        RETURN = 'return', 'Возврат'
        STOCK_MISMATCH = 'stock_mismatch', 'Расхождение при инвентаризации'
        ADJUSTMENT = 'adjustment', 'Корректировка'
        CASH_MISMATCH = 'cash_mismatch', 'Расхождение кассы'

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
    )
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='risk_events',
    )
    quantity = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    monetary_impact = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text='Financial impact (cost of lost goods, cash difference, etc.).',
    )
    affects_investor = models.BooleanField(
        default=False,
        help_text='Auto-set: True if lot belongs to MUDARABA/MUSHARAKA receipt.',
    )
    negligence = models.BooleanField(
        default=False,
        help_text='Manager negligence flag. Affects loss distribution in future.',
    )
    responsible_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True, default='')
    resolution = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'risk_event'
        indexes = [
            models.Index(fields=['tenant', 'event_type', 'created_at']),
            models.Index(fields=['lot']),
        ]

    def __str__(self):
        return f"RiskEvent #{self.pk} ({self.event_type})"


class InventoryCheck(TenantModel):
    """Planned inventory check (stocktaking)."""

    class CheckStatus(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'В процессе'
        COMPLETED = 'completed', 'Завершена'

    location = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='inventory_checks',
    )
    status = models.CharField(
        max_length=20,
        choices=CheckStatus.choices,
        default=CheckStatus.IN_PROGRESS,
    )
    checked_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'risk_inventory_check'


class InventoryCheckLine(TenantModel):
    """Single product line in an inventory check."""

    inventory_check = models.ForeignKey(
        InventoryCheck,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
    )
    expected_quantity = models.PositiveIntegerField()
    actual_quantity = models.PositiveIntegerField()
    difference = models.IntegerField(
        help_text='actual - expected. Negative = shortage.',
    )

    class Meta:
        db_table = 'risk_inventory_check_line'
