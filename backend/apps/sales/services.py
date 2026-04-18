"""
Sales business logic — sale creation, profit distribution, returns.
"""

from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from typing import TYPE_CHECKING

from apps.core.services import publish_event
from apps.core.exceptions import (
    CreditSaleRequiresCustomerError,
    DiscountReasonRequiredError,
    InvalidDiscountReasonError,
    InvalidUnitPriceError,
    PricingModeViolationError,
)
from apps.inventory.services import (
    record_sale_stock_movement,
    record_return_stock_movement,
)
from apps.finance.services import resolve_fx_rate_snapshot

from .models import (
    Sale, SaleLine, SaleReturn, SaleReturnLine, PosSession,
)

if TYPE_CHECKING:
    from apps.inventory.models import Lot


def _validate_unit_price(unit_price: Decimal) -> None:
    if unit_price <= 0:
        raise InvalidUnitPriceError()


def _resolve_discount_reason_id(
    *,
    tenant_id: int,
    discount_reason_id: int | None,
    price_changed: bool,
) -> int | None:
    """Resolve and validate discount reason when price changed."""
    if not price_changed:
        return None

    from apps.catalog.models import DiscountReason

    if discount_reason_id is not None:
        exists = DiscountReason.objects.filter(
            tenant_id=tenant_id,
            pk=discount_reason_id,
            is_active=True,
        ).exists()
        if not exists:
            raise InvalidDiscountReasonError()
        return int(discount_reason_id)

    default_reason = (
        DiscountReason.objects
        .filter(tenant_id=tenant_id, is_active=True, is_default=True)
        .order_by('id')
        .first()
    )
    if default_reason is None:
        default_reason = (
            DiscountReason.objects
            .filter(tenant_id=tenant_id, name='Торг')
            .order_by('id')
            .first()
        )
        if default_reason is None:
            default_reason = DiscountReason.objects.create(
                tenant_id=tenant_id,
                name='Торг',
                is_default=True,
                is_active=True,
            )
        elif not default_reason.is_active or not default_reason.is_default:
            default_reason.is_active = True
            default_reason.is_default = True
            default_reason.save(update_fields=['is_active', 'is_default', 'updated_at'])

    if default_reason is None:
        raise DiscountReasonRequiredError()

    return int(default_reason.id)


def _validate_line_pricing_policy(
    *,
    tenant_id: int,
    pricing_mode: str,
    unit_price: Decimal,
    base_price: Decimal,
    discount_reason_id: int | None,
) -> tuple[bool, int | None]:
    """
    Enforce pricing mode policy for sales.

    Returns:
      (price_changed, resolved_discount_reason_id)
    """
    _validate_unit_price(unit_price)

    if pricing_mode == 'FIXED' and unit_price != base_price:
        raise PricingModeViolationError(
            detail='Fixed price product cannot be sold with a different price.'
        )

    if pricing_mode == 'ALWAYS_ASK' and unit_price <= 0:
        raise InvalidUnitPriceError(
            detail='Price must be provided for ALWAYS_ASK products.'
        )

    price_changed = unit_price != base_price
    resolved_discount_reason_id = _resolve_discount_reason_id(
        tenant_id=tenant_id,
        discount_reason_id=discount_reason_id,
        price_changed=price_changed,
    )
    return price_changed, resolved_discount_reason_id


def create_sale(
    tenant_id: int,
    pos_session_id: int,
    sold_by_id: int,
    payment_method: str,
    customer_id: int | None,
    lines: list[dict],
    client_request_id: str | None = None,
    notes: str = '',
    operation_date=None,
    operation_currency: str = 'UZS',
    operation_amount: Decimal | None = None,
    fx_rate_snapshot: Decimal | None = None,
    functional_amount_uzs: Decimal | None = None,
) -> Sale:
    raise NotImplementedError(
        'create_sale awaits PR-4 (Sale rework: SalePayment, location, profit_distribution_snapshot). '
        'Old Lot.location / Lot.cost_per_unit path is gone.'
    )
    # legacy body kept below for reference until PR-4

    """
    Create and complete a sale.
    Each line: product_variant_id, quantity, unit_price, lot_id (optional), discount_reason_id.
    If lot_id is None, FIFO selection is used.
    """
    # Validate credit sale
    if payment_method == 'credit' and not customer_id:
        raise CreditSaleRequiresCustomerError()

    with transaction.atomic():
        # Idempotency check
        if client_request_id:
            existing = Sale.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        # Check customer debt (warning only, no blocking in MVP)
        customer_has_debt = False
        if customer_id:
            from apps.customers.models import Customer
            customer = Customer.objects.filter(
                pk=customer_id, tenant_id=tenant_id,
            ).first()
            if customer and customer.outstanding_balance > 0:
                customer_has_debt = True

        # Get POS session
        session = PosSession.objects.get(
            pk=pos_session_id,
            tenant_id=tenant_id,
            status=PosSession.SessionStatus.OPEN,
        )

        currency = str(operation_currency or 'UZS').upper()
        resolved_rate = resolve_fx_rate_snapshot(
            tenant_id=tenant_id,
            operation_currency=currency,
            operation_at=operation_date or timezone.now(),
            fx_rate_snapshot=fx_rate_snapshot,
        )

        # Create sale
        sale = Sale.objects.create(
            tenant_id=tenant_id,
            pos_session=session,
            sold_by_id=sold_by_id,
            payment_method=payment_method,
            customer_id=customer_id,
            customer_has_existing_debt=customer_has_debt,
            operation_currency=currency,
            operation_amount=operation_amount,
            fx_rate_snapshot=resolved_rate,
            functional_amount_uzs=functional_amount_uzs,
            client_request_id=client_request_id,
            notes=notes,
            status=Sale.SaleStatus.DRAFT,
        )

        if operation_date is not None:
            Sale.objects.filter(pk=sale.pk).update(
                created_at=operation_date,
                updated_at=operation_date,
            )
            sale.refresh_from_db()

        total_amount = Decimal('0')
        total_cogs = Decimal('0')

        for line_data in lines:
            variant_id = line_data['product_variant_id']
            quantity = line_data['quantity']
            unit_price = Decimal(str(line_data['unit_price']))
            lot_id = line_data.get('lot_id')
            discount_reason_id = line_data.get('discount_reason_id')

            # Get base price snapshot
            from apps.catalog.models import ProductVariant
            variant = ProductVariant.objects.get(
                pk=variant_id, tenant_id=tenant_id,
            )
            base_price = variant.effective_price or Decimal('0')
            price_changed, resolved_discount_reason_id = _validate_line_pricing_policy(
                tenant_id=tenant_id,
                pricing_mode=variant.product.pricing_mode,
                unit_price=unit_price,
                base_price=base_price,
                discount_reason_id=discount_reason_id,
            )

            # Resolve lots (FIFO or manual)
            if lot_id:
                lot = get_locked_lot(
                    lot_id=lot_id,
                    tenant_id=tenant_id,
                )
                lot_allocations = [{'lot': lot, 'quantity': quantity}]
            else:
                lot_allocations = get_lots_for_sale(
                    product_variant_id=variant_id,
                    location_id=session.location_id,
                    quantity=quantity,
                    tenant_id=tenant_id,
                )

            # Create sale lines per lot allocation
            for alloc in lot_allocations:
                lot = alloc['lot']
                alloc_qty = alloc['quantity']

                sale_line = SaleLine.objects.create(
                    tenant_id=tenant_id,
                    sale=sale,
                    lot=lot,
                    product_variant=variant,
                    quantity=alloc_qty,
                    unit_price=unit_price,
                    base_price=base_price,
                    price_changed=price_changed,
                    discount_reason_id=resolved_discount_reason_id,
                    cost_per_unit=lot.cost_per_unit,
                )

                # Deduct from lot
                deduct_lot_quantity(lot, alloc_qty)

                # Record stock movement
                record_sale_stock_movement(
                    tenant_id=tenant_id,
                    lot=lot,
                    quantity=alloc_qty,
                    from_location=session.location,
                    sale_id=sale.pk,
                )

                total_amount += unit_price * alloc_qty
                total_cogs += lot.cost_per_unit * alloc_qty

        # Update sale totals and complete
        sale.total_amount = total_amount
        sale.total_cogs = total_cogs
        if sale.operation_amount is None:
            if currency == 'UZS':
                sale.operation_amount = total_amount
            else:
                sale.operation_amount = (
                    total_amount / sale.fx_rate_snapshot
                ).quantize(Decimal('0.01'))
        if sale.fx_rate_snapshot is None:
            sale.fx_rate_snapshot = resolved_rate
        if sale.functional_amount_uzs is None:
            sale.functional_amount_uzs = total_amount
        sale.status = Sale.SaleStatus.COMPLETED
        sale.save(update_fields=[
            'total_amount',
            'total_cogs',
            'operation_amount',
            'fx_rate_snapshot',
            'functional_amount_uzs',
            'status',
            'updated_at',
        ])

        # Update customer balance for credit sales
        if payment_method == 'credit' and customer_id:
            from apps.customers.models import Customer
            Customer.objects.filter(
                pk=customer_id,
            ).update(
                outstanding_balance=models.F('outstanding_balance') + total_amount,
            )

        from apps.finance.services import record_sale_journal
        record_sale_journal(
            tenant_id=tenant_id,
            sale_id=sale.pk,
            total_amount=total_amount,
            total_cogs=total_cogs,
            payment_method=payment_method,
            date=operation_date or sale.created_at,
        )

        # Publish event
        publish_event(
            event_type='sale.completed',
            payload={
                'sale_id': sale.pk,
                'total_amount': str(total_amount),
                'payment_method': payment_method,
                'lines_count': sale.lines.count(),
                'date': (operation_date or sale.created_at).isoformat(),
            },
            tenant_id=tenant_id,
        )

    return sale


def calculate_profit_distribution(lot: 'Lot', sale_line: SaleLine) -> list[dict]:
    raise NotImplementedError(
        'calculate_profit_distribution awaits PR-4/PR-5 (uses Lot.contract_snapshot).'
    )
    """
    Calculate who gets what from a single sale line.
    Returns list of {entity_type, entity_id, amount}.
    """
    revenue = sale_line.unit_price * sale_line.quantity
    cogs = lot.cost_per_unit * sale_line.quantity
    gross_profit = revenue - cogs

    receipt = lot.receipt
    distributions = []

    if receipt.receipt_type == 'BUSINESS_OWNED':
        distributions.append({
            'entity_type': 'business',
            'entity_id': receipt.tenant_id,
            'amount': gross_profit,
        })

    elif receipt.receipt_type == 'MUDARABA':
        for participant in receipt.participants.all():
            amount = gross_profit * participant.profit_ratio
            distributions.append({
                'entity_type': participant.participant_type,
                'entity_id': participant.entity_id,
                'amount': amount,
            })

    elif receipt.receipt_type == 'MUSHARAKA':
        for participant in receipt.participants.all():
            amount = gross_profit * participant.profit_ratio
            distributions.append({
                'entity_type': participant.participant_type,
                'entity_id': participant.entity_id,
                'amount': amount,
            })

    elif receipt.receipt_type == 'CONSIGNMENT':
        rule = receipt.consignment_rule or {}
        if rule.get('type') == 'margin':
            business_amount = (sale_line.unit_price - lot.cost_per_unit) * sale_line.quantity
        else:
            commission = Decimal(str(rule.get('value', '0')))
            business_amount = revenue * commission
        supplier_amount = revenue - business_amount

        distributions.append({
            'entity_type': 'business',
            'entity_id': receipt.tenant_id,
            'amount': business_amount,
        })
        distributions.append({
            'entity_type': 'supplier',
            'entity_id': receipt.supplier_id,
            'amount': supplier_amount,
        })

    elif receipt.receipt_type == 'SUPPLIER_PURCHASE':
        distributions.append({
            'entity_type': 'business',
            'entity_id': receipt.tenant_id,
            'amount': gross_profit,
        })

    return distributions


def process_return(
    sale: Sale,
    return_lines: list[dict],
    processed_by_id: int,
    tenant_id: int,
    notes: str = '',
) -> SaleReturn:
    raise NotImplementedError(
        'process_return awaits PR-8 (Return rework with RESTOCK/DISPOSE + PartnerLedger).'
    )
    """
    Process a return for a completed sale.
    Each line: sale_line_id, quantity, condition (good/damaged).
    """
    with transaction.atomic():
        sale_return = SaleReturn.objects.create(
            tenant_id=tenant_id,
            sale=sale,
            processed_by_id=processed_by_id,
            notes=notes,
        )

        refund_amount = Decimal('0')
        cogs_amount = Decimal('0')

        for rl_data in return_lines:
            sale_line = SaleLine.objects.get(
                pk=rl_data['sale_line_id'],
                sale=sale,
            )

            quantity = rl_data['quantity']

            return_line = SaleReturnLine.objects.create(
                tenant_id=tenant_id,
                sale_return=sale_return,
                sale_line=sale_line,
                quantity=quantity,
                condition=rl_data['condition'],
            )
            _ = return_line

            # Restore lot quantity
            restore_lot_quantity(sale_line.lot, quantity)

            # Record stock movement
            record_return_stock_movement(
                tenant_id=tenant_id,
                lot=sale_line.lot,
                quantity=quantity,
                to_location=sale.pos_session.location,
                sale_return_id=sale_return.pk,
            )

            refund_amount += sale_line.unit_price * quantity
            cogs_amount += sale_line.cost_per_unit * quantity

            # If damaged, create risk event
            if rl_data['condition'] == 'damaged':
                from apps.risk.models import RiskEvent
                receipt = sale_line.lot.receipt
                RiskEvent.objects.create(
                    tenant_id=tenant_id,
                    event_type=RiskEvent.EventType.RETURN,
                    lot=sale_line.lot,
                    quantity=quantity,
                    monetary_impact=sale_line.cost_per_unit * quantity,
                    affects_investor=receipt.receipt_type in ('MUDARABA', 'MUSHARAKA'),
                    reason=f'Damaged return from sale #{sale.pk}',
                )

        from apps.finance.services import record_return_journal
        record_return_journal(
            tenant_id=tenant_id,
            sale_return_id=sale_return.pk,
            refund_amount=refund_amount,
            cogs_amount=cogs_amount,
            payment_method=sale.payment_method,
            date=sale_return.created_at,
        )

        # Publish event
        publish_event(
            event_type='sale.returned',
            payload={
                'sale_id': sale.pk,
                'return_id': sale_return.pk,
                'lines_count': len(return_lines),
            },
            tenant_id=tenant_id,
        )

    return sale_return


def open_pos_session(
    tenant_id: int,
    location_id: int,
    opened_by_id: int,
    opening_cash: Decimal = Decimal('0'),
) -> PosSession:
    """Open a new POS session (shift)."""
    session = PosSession.objects.create(
        tenant_id=tenant_id,
        location_id=location_id,
        opened_by_id=opened_by_id,
        opening_cash=opening_cash,
        status=PosSession.SessionStatus.OPEN,
    )
    publish_event(
        event_type='pos_session.opened',
        payload={
            'session_id': session.pk,
            'location_id': location_id,
            'opened_by_id': opened_by_id,
            'opening_cash': str(opening_cash),
            'opened_at': session.opened_at.isoformat(),
        },
        tenant_id=tenant_id,
    )
    return session


def close_pos_session(
    session: PosSession,
    closed_by_id: int,
    actual_cash: Decimal,
) -> PosSession:
    """
    Close a POS session with cash reconciliation.
    Creates RiskEvent if there's a difference.
    """
    from django.db.models import Sum, Q

    with transaction.atomic():
        session = PosSession.objects.select_for_update().get(pk=session.pk)

        # Calculate expected cash
        cash_sales_total = Sale.objects.filter(
            pos_session=session,
            status=Sale.SaleStatus.COMPLETED,
            payment_method=Sale.PaymentMethod.CASH,
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')

        expected_cash = session.opening_cash + cash_sales_total

        session.expected_cash = expected_cash
        session.actual_cash = actual_cash
        session.cash_difference = actual_cash - expected_cash
        session.closed_by_id = closed_by_id
        session.closed_at = timezone.now()
        session.status = PosSession.SessionStatus.CLOSED
        session.save()

        # Log mismatch as risk event
        if session.cash_difference != 0:
            from apps.risk.models import RiskEvent
            RiskEvent.objects.create(
                tenant_id=session.tenant_id,
                event_type=RiskEvent.EventType.CASH_MISMATCH,
                quantity=0,
                monetary_impact=abs(session.cash_difference),
                responsible_user_id=closed_by_id,
                    reason=f'Cash mismatch at session close: expected {expected_cash}, actual {actual_cash}',
            )

        publish_event(
            event_type='pos_session.closed',
            payload={
                'session_id': session.pk,
                'location_id': session.location_id,
                'closed_by_id': closed_by_id,
                'expected_cash': str(expected_cash),
                'actual_cash': str(actual_cash),
                'cash_difference': str(session.cash_difference),
                'closed_at': session.closed_at.isoformat() if session.closed_at else None,
            },
            tenant_id=session.tenant_id,
        )

    return session
