"""
Inventory business logic — receipt confirmation, lot creation,
stock transfer, FIFO lot selection.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import (
    ImmutableRecordError,
    InsufficientStockError,
)

from .models import (
    Receipt, ReceiptLine, ReceiptParticipant, Lot, StockMovement, Location,
)
from .validators import validate_participant_ratios


def confirm_receipt(receipt: Receipt) -> Receipt:
    """
    Confirm a receipt: validate, create lots, publish event.
    After confirmation the receipt is IMMUTABLE.
    """
    if receipt.status == Receipt.ReceiptStatus.CONFIRMED:
        raise ImmutableRecordError("Receipt is already confirmed")

    with transaction.atomic():
        # Lock the receipt row
        receipt = Receipt.objects.select_for_update().get(pk=receipt.pk)

        if receipt.status == Receipt.ReceiptStatus.CONFIRMED:
            raise ImmutableRecordError("Receipt is already confirmed")

        # Validate participants for MUDARABA / MUSHARAKA
        if receipt.receipt_type in (
            Receipt.ReceiptType.MUDARABA,
            Receipt.ReceiptType.MUSHARAKA,
        ):
            participants = list(receipt.participants.all())
            if not participants:
                raise ValueError(
                    f"Receipt type {receipt.receipt_type} requires participants"
                )
            validate_participant_ratios([
                {
                    'profit_ratio': str(p.profit_ratio),
                    'capital_amount': str(p.capital_amount),
                }
                for p in participants
            ])

            # Auto-calculate capital_ratio
            total_capital = sum(p.capital_amount for p in participants)
            for p in participants:
                p.capital_ratio = p.capital_amount / total_capital
                p.save(update_fields=['capital_ratio', 'updated_at'])

        # Create lots for each receipt line
        lines = list(receipt.lines.select_related('product_variant').all())
        lots_created = []

        for line in lines:
            lot = Lot.objects.create(
                tenant_id=receipt.tenant_id,
                receipt=receipt,
                receipt_line=line,
                product_variant=line.product_variant,
                location=receipt.destination,
                quantity_initial=line.quantity,
                quantity_remaining=line.quantity,
                cost_per_unit=line.cost_per_unit,
                is_active=True,
            )
            lots_created.append(lot)

            # Record stock movement
            StockMovement.objects.create(
                tenant_id=receipt.tenant_id,
                lot=lot,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity=line.quantity,
                to_location=receipt.destination,
                reference_type='receipt',
                reference_id=receipt.pk,
            )

        # Set status to confirmed (now immutable)
        receipt.status = Receipt.ReceiptStatus.CONFIRMED
        receipt.save(update_fields=['status', 'updated_at'])

        # Publish outbox event
        publish_event(
            event_type='receipt.confirmed',
            payload={
                'receipt_id': receipt.pk,
                'receipt_type': receipt.receipt_type,
                'date': receipt.date.isoformat(),
                'lines_count': len(lines),
                'lots_created': [lot.pk for lot in lots_created],
            },
            tenant_id=receipt.tenant_id,
        )

    return receipt


def get_lots_for_sale(
    product_variant_id: int,
    location_id: int,
    quantity: int,
    tenant_id: int,
) -> list[dict]:
    """
    FIFO lot selection — find lots to fulfill requested quantity.
    Returns list of {lot, quantity} dicts.
    """
    lots = Lot.objects.filter(
        product_variant_id=product_variant_id,
        location_id=location_id,
        is_active=True,
        quantity_remaining__gt=0,
        tenant_id=tenant_id,
    ).select_related('receipt').order_by('receipt__date')

    result = []
    remaining = quantity

    for lot in lots:
        take = min(lot.quantity_remaining, remaining)
        result.append({'lot': lot, 'quantity': take})
        remaining -= take
        if remaining == 0:
            break

    if remaining > 0:
        raise InsufficientStockError(
            f"Not enough stock for variant {product_variant_id} "
            f"at location {location_id}: {remaining} units short"
        )

    return result


def deduct_lot_quantity(lot: Lot, quantity: int) -> Lot:
    """
    Deduct quantity from a lot. Uses SELECT FOR UPDATE for safety.
    """
    with transaction.atomic():
        lot = Lot.objects.select_for_update().get(pk=lot.pk)

        if lot.quantity_remaining < quantity:
            raise InsufficientStockError(
                f"Lot {lot.pk} has only {lot.quantity_remaining} units, "
                f"requested {quantity}"
            )

        lot.quantity_remaining -= quantity
        if lot.quantity_remaining == 0:
            lot.is_active = False

        lot.save(update_fields=[
            'quantity_remaining', 'is_active', 'updated_at',
        ])

    return lot


def restore_lot_quantity(lot: Lot, quantity: int) -> Lot:
    """Restore quantity to a lot (for returns)."""
    with transaction.atomic():
        lot = Lot.objects.select_for_update().get(pk=lot.pk)
        lot.quantity_remaining += quantity
        lot.is_active = True
        lot.save(update_fields=[
            'quantity_remaining', 'is_active', 'updated_at',
        ])
    return lot


def transfer_lot(
    lot: Lot,
    to_location: Location,
    quantity: int | None = None,
    tenant_id: int | None = None,
) -> Lot:
    """
    Transfer a lot (or part of it) to another location.
    Lot ownership and participants do NOT change.
    """
    with transaction.atomic():
        lot = Lot.objects.select_for_update().get(pk=lot.pk)
        from_location = lot.location

        if quantity is None or quantity == lot.quantity_remaining:
            # Move entire lot
            lot.location = to_location
            lot.save(update_fields=['location', 'updated_at'])
            moved_quantity = lot.quantity_remaining
        else:
            # Split: reduce original, create new lot at destination
            if quantity > lot.quantity_remaining:
                raise InsufficientStockError(
                    f"Cannot transfer {quantity}, only {lot.quantity_remaining} available"
                )
            lot.quantity_remaining -= quantity
            if lot.quantity_remaining == 0:
                lot.is_active = False
            lot.save(update_fields=[
                'quantity_remaining', 'is_active', 'updated_at',
            ])

            # Create new lot at destination
            Lot.objects.create(
                tenant_id=lot.tenant_id,
                receipt=lot.receipt,
                receipt_line=lot.receipt_line,
                product_variant=lot.product_variant,
                location=to_location,
                quantity_initial=quantity,
                quantity_remaining=quantity,
                cost_per_unit=lot.cost_per_unit,
                is_active=True,
            )
            moved_quantity = quantity

        # Record movement
        StockMovement.objects.create(
            tenant_id=lot.tenant_id,
            lot=lot,
            movement_type=StockMovement.MovementType.TRANSFER,
            quantity=moved_quantity,
            from_location=from_location,
            to_location=to_location,
            reference_type='transfer',
        )

    return lot


def get_stock_summary(
    tenant_id: int,
    location_id: int | None = None,
) -> list[dict]:
    """
    Get stock summary grouped by product variant.
    Optionally filtered by location.
    """
    from django.db.models import Sum

    qs = Lot.objects.filter(
        tenant_id=tenant_id,
        is_active=True,
        quantity_remaining__gt=0,
    )
    if location_id:
        qs = qs.filter(location_id=location_id)

    return list(
        qs.values(
            'product_variant_id',
            'product_variant__product__name',
            'location_id',
            'location__name',
        ).annotate(
            total_quantity=Sum('quantity_remaining'),
        ).order_by('product_variant__product__name')
    )
