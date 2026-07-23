"""
E09 Phase 2 — авто-обязательство поставщику при продаже CONSIGNED Lot.

Вызывается синхронно из sales/services.py:create_sale в той же
транзакции. Если SaleLine соответствует CONSIGNED Lot, создаёт
SupplierPayable с reason=CONSIGNMENT_SALE.
"""

from __future__ import annotations

from decimal import Decimal

from .models import SupplierPayable


def record_consignment_obligation_for_sale_line(sale_line) -> SupplierPayable | None:
    """
    Если sale_line продаёт CONSIGNED товар — создать обязательство поставщику.
    Иначе вернуть None.

    Должна вызываться внутри transaction.atomic() из create_sale.
    """
    lot = sale_line.lot
    if lot.is_owned:
        return None

    procurement = lot.procurement_item.procurement
    supplier_id = procurement.supplier_id
    if supplier_id is None:
        raise ValueError(
            f'Cannot create consignment obligation: Lot#{lot.pk} '
            f'has no supplier on its procurement.'
        )

    cost_slice, currency, fx_rate = _resolve_sale_line_cost(sale_line)

    payable = SupplierPayable.objects.create(
        tenant_id=sale_line.tenant_id,
        supplier_id=supplier_id,
        procurement=procurement,
        settlement=getattr(procurement, 'terms', None),
        original_amount=cost_slice,
        currency_of_obligation=currency,
        fx_rate_at_obligation=fx_rate,
        status=SupplierPayable.Status.OPEN,
        reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
    )

    from apps.core.services import publish_event
    publish_event(
        event_type='consignment_obligation.created',
        payload={
            'sale_line_id': sale_line.id,
            'lot_id': lot.id,
            'supplier_id': supplier_id,
            'procurement_id': procurement.id,
            'payable_id': payable.id,
            'amount': str(cost_slice),
            'currency': currency,
        },
        tenant_id=sale_line.tenant_id,
    )
    return payable


def _resolve_sale_line_cost(sale_line) -> tuple[Decimal, str, Decimal]:
    """
    Cost slice для supplier-обязательства — в операционной валюте
    procurement_item-а (т.е. в валюте, в которой согласовалась цена с
    поставщиком). FX-rate тоже снапшот procurement_item-а.
    """
    item = sale_line.lot.procurement_item
    if item is None:
        raise ValueError(
            f'Sale line #{sale_line.pk}: lot has no procurement_item; '
            f'cannot resolve consignment cost.'
        )
    cost_slice = (
        Decimal(str(item.unit_purchase_price)) * Decimal(str(sale_line.quantity))
    ).quantize(Decimal('0.01'))
    currency = str(item.currency or 'UZS').upper()
    fx_rate = Decimal(str(item.fx_rate or 1))
    return cost_slice, currency, fx_rate
