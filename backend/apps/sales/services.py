"""
Sales business logic — sale creation, profit distribution, returns.
"""

from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import (
    CreditSaleRequiresCustomerError,
    InsufficientStockError,
    DuplicateRequestError,
)
from apps.inventory.services import get_lots_for_sale, deduct_lot_quantity, restore_lot_quantity
from apps.inventory.models import Lot, StockMovement

from .models import (
    Sale, SaleLine, SaleReturn, SaleReturnLine, PosSession,
)


def create_sale(
    tenant_id: int,
    pos_session_id: int,
    sold_by_id: int,
    payment_method: str,
    customer_id: int | None,
    lines: list[dict],
    client_request_id: str | None = None,
    notes: str = '',
) -> Sale:
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

        # Create sale
        sale = Sale.objects.create(
            tenant_id=tenant_id,
            pos_session=session,
            sold_by_id=sold_by_id,
            payment_method=payment_method,
            customer_id=customer_id,
            customer_has_existing_debt=customer_has_debt,
            client_request_id=client_request_id,
            notes=notes,
            status=Sale.SaleStatus.DRAFT,
        )

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

            # Resolve lots (FIFO or manual)
            if lot_id:
                lot = Lot.objects.select_for_update().get(
                    pk=lot_id, tenant_id=tenant_id,
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
                    price_changed=(unit_price != base_price),
                    discount_reason_id=discount_reason_id if unit_price != base_price else None,
                    cost_per_unit=lot.cost_per_unit,
                )

                # Deduct from lot
                deduct_lot_quantity(lot, alloc_qty)

                # Record stock movement
                StockMovement.objects.create(
                    tenant_id=tenant_id,
                    lot=lot,
                    movement_type=StockMovement.MovementType.SALE,
                    quantity=-alloc_qty,
                    from_location=session.location,
                    reference_type='sale',
                    reference_id=sale.pk,
                )

                total_amount += unit_price * alloc_qty
                total_cogs += lot.cost_per_unit * alloc_qty

        # Update sale totals and complete
        sale.total_amount = total_amount
        sale.total_cogs = total_cogs
        sale.status = Sale.SaleStatus.COMPLETED
        sale.save(update_fields=[
            'total_amount', 'total_cogs', 'status', 'updated_at',
        ])

        # Update customer balance for credit sales
        if payment_method == 'credit' and customer_id:
            from apps.customers.models import Customer
            Customer.objects.filter(
                pk=customer_id,
            ).update(
                outstanding_balance=models.F('outstanding_balance') + total_amount,
            )

        # Publish event
        publish_event(
            event_type='sale.completed',
            payload={
                'sale_id': sale.pk,
                'total_amount': str(total_amount),
                'payment_method': payment_method,
                'lines_count': sale.lines.count(),
                'date': sale.created_at.isoformat(),
            },
            tenant_id=tenant_id,
        )

    return sale


def calculate_profit_distribution(lot: Lot, sale_line: SaleLine) -> list[dict]:
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

        for rl_data in return_lines:
            sale_line = SaleLine.objects.get(
                pk=rl_data['sale_line_id'],
                sale=sale,
            )

            return_line = SaleReturnLine.objects.create(
                tenant_id=tenant_id,
                sale_return=sale_return,
                sale_line=sale_line,
                quantity=rl_data['quantity'],
                condition=rl_data['condition'],
            )

            # Restore lot quantity
            restore_lot_quantity(sale_line.lot, rl_data['quantity'])

            # Record stock movement
            StockMovement.objects.create(
                tenant_id=tenant_id,
                lot=sale_line.lot,
                movement_type=StockMovement.MovementType.RETURN,
                quantity=rl_data['quantity'],
                to_location=sale.pos_session.location,
                reference_type='sale_return',
                reference_id=sale_return.pk,
            )

            # If damaged, create risk event
            if rl_data['condition'] == 'damaged':
                from apps.risk.models import RiskEvent
                receipt = sale_line.lot.receipt
                RiskEvent.objects.create(
                    tenant_id=tenant_id,
                    event_type=RiskEvent.EventType.RETURN,
                    lot=sale_line.lot,
                    quantity=rl_data['quantity'],
                    monetary_impact=sale_line.cost_per_unit * rl_data['quantity'],
                    affects_investor=receipt.receipt_type in ('MUDARABA', 'MUSHARAKA'),
                    reason=f'Damaged return from sale #{sale.pk}',
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
    return PosSession.objects.create(
        tenant_id=tenant_id,
        location_id=location_id,
        opened_by_id=opened_by_id,
        opening_cash=opening_cash,
        status=PosSession.SessionStatus.OPEN,
    )


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

    return session
