"""
Inventory business logic — LotStock FIFO allocation, transfer.

Receipt confirmation is DEPRECATED as of PR-3; lot creation is now
the responsibility of partnerships.receive_procurement (PR-4+).
"""

from django.db import transaction, models

from apps.core.services import publish_event
from apps.core.exceptions import InsufficientStockError

from .models import Lot, LotStock, StockMovement, Warehouse


def allocate_lot(
    *,
    product_variant_id: int,
    warehouse_id: int,
    quantity: int,
    tenant_id: int,
) -> list[dict]:
    """
    FIFO lot allocation for a sale — queries LotStock at the given warehouse.
    Returns [{'lot': Lot, 'lot_stock': LotStock, 'quantity': int}, ...].

    Raises InsufficientStockError if the warehouse cannot satisfy the request.
    """
    stocks = (
        LotStock.objects
        .filter(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            quantity_remaining__gt=0,
            lot__product_variant_id=product_variant_id,
            lot__is_active=True,
            lot__reversed=False,
        )
        .select_related('lot', 'lot__receipt')
        .order_by('lot__received_at', 'lot__id')
    )

    result = []
    remaining = quantity
    for stock in stocks:
        take = min(stock.quantity_remaining, remaining)
        result.append({'lot': stock.lot, 'lot_stock': stock, 'quantity': take})
        remaining -= take
        if remaining == 0:
            break

    if remaining > 0:
        raise InsufficientStockError(
            f'Not enough stock for variant {product_variant_id} '
            f'at warehouse {warehouse_id}: {remaining} units short'
        )
    return result


def get_locked_lot_stock(*, lot_stock_id: int, tenant_id: int) -> LotStock:
    return LotStock.objects.select_for_update().get(
        pk=lot_stock_id,
        tenant_id=tenant_id,
    )


def deduct_lot_stock(lot_stock: LotStock, quantity: int) -> LotStock:
    with transaction.atomic():
        lot_stock = LotStock.objects.select_for_update().get(pk=lot_stock.pk)
        if lot_stock.quantity_remaining < quantity:
            raise InsufficientStockError(
                f'LotStock {lot_stock.pk} has {lot_stock.quantity_remaining} units, '
                f'requested {quantity}'
            )
        lot_stock.quantity_remaining -= quantity
        lot_stock.save(update_fields=['quantity_remaining', 'updated_at'])

        total_remaining = (
            LotStock.objects
            .filter(lot_id=lot_stock.lot_id)
            .aggregate(total=models.Sum('quantity_remaining'))['total'] or 0
        )
        if total_remaining == 0:
            Lot.objects.filter(pk=lot_stock.lot_id).update(is_active=False)
    return lot_stock


def restore_lot_stock(lot_stock: LotStock, quantity: int) -> LotStock:
    with transaction.atomic():
        lot_stock = LotStock.objects.select_for_update().get(pk=lot_stock.pk)
        lot_stock.quantity_remaining += quantity
        lot_stock.save(update_fields=['quantity_remaining', 'updated_at'])
        Lot.objects.filter(pk=lot_stock.lot_id).update(is_active=True)
    return lot_stock


def transfer_lot_stock(
    *,
    tenant_id: int,
    lot: Lot,
    from_warehouse: Warehouse,
    to_warehouse: Warehouse,
    quantity: int,
) -> LotStock:
    """
    Move `quantity` units of `lot` from one warehouse to another.
    Lot ownership and contract snapshot are untouched — only LotStock rows change.
    """
    with transaction.atomic():
        src = LotStock.objects.select_for_update().get(
            tenant_id=tenant_id,
            lot=lot,
            warehouse=from_warehouse,
        )
        if quantity <= 0 or quantity > src.quantity_remaining:
            raise InsufficientStockError(
                f'Cannot transfer {quantity}, only {src.quantity_remaining} available'
            )
        src.quantity_remaining -= quantity
        src.save(update_fields=['quantity_remaining', 'updated_at'])

        dst, _ = LotStock.objects.select_for_update().get_or_create(
            tenant_id=tenant_id,
            lot=lot,
            warehouse=to_warehouse,
            defaults={'quantity_remaining': 0},
        )
        dst.quantity_remaining += quantity
        dst.save(update_fields=['quantity_remaining', 'updated_at'])

        StockMovement.objects.create(
            tenant_id=tenant_id,
            lot=lot,
            movement_type=StockMovement.MovementType.TRANSFER,
            quantity=quantity,
            from_location=from_warehouse,
            to_location=to_warehouse,
            reference_type='transfer',
        )

        publish_event(
            event_type='lot.transfer',
            payload={
                'lot_id': lot.pk,
                'from_warehouse_id': from_warehouse.pk,
                'to_warehouse_id': to_warehouse.pk,
                'quantity': quantity,
            },
            tenant_id=tenant_id,
        )
    return dst


def get_stock_summary(
    tenant_id: int,
    warehouse_id: int | None = None,
) -> list[dict]:
    """
    Stock summary grouped by product variant + warehouse,
    aggregated from LotStock.
    """
    qs = LotStock.objects.filter(
        tenant_id=tenant_id,
        quantity_remaining__gt=0,
        lot__is_active=True,
    )
    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    return list(
        qs.values(
            'lot__product_variant_id',
            'lot__product_variant__product__name',
            'warehouse_id',
            'warehouse__name',
        ).annotate(
            total_quantity=models.Sum('quantity_remaining'),
            total_landed_cost=models.Sum(
                models.F('quantity_remaining') * models.F('lot__landed_cost_per_unit'),
                output_field=models.DecimalField(max_digits=20, decimal_places=2),
            ),
        ).order_by('lot__product_variant__product__name')
    )
