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
from apps.finance.services import resolve_fx_rate_snapshot

from .models import (
    Sale, SaleLine, Return, ReturnLine, PosSession,
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


def _resolve_default_cash_account_id(
    *,
    tenant_id: int,
    payment_method: str,
    currency: str,
) -> int | None:
    """
    Resolve a default operational account for sale payments when the UI does not
    explicitly pass one yet.
    """
    from apps.finance.models import CashAccount

    method = str(payment_method or '').upper()
    normalized_currency = str(currency or 'UZS').upper()
    kind_map = {
        'CASH': CashAccount.Kind.CASH,
        'CARD': CashAccount.Kind.CARD_TERMINAL,
        'TRANSFER': CashAccount.Kind.BANK,
    }
    account_kind = kind_map.get(method)
    if account_kind is None:
        return None

    account = (
        CashAccount.objects
        .filter(
            tenant_id=tenant_id,
            kind=account_kind,
            currency=normalized_currency,
            is_active=True,
        )
        .order_by('id')
        .first()
    )
    return int(account.id) if account else None


def create_sale(
    *,
    tenant_id: int,
    pos_session_id: int,
    location_id: int | None,
    sold_by_id: int,
    customer_id: int | None,
    lines: list[dict],
    payments: list[dict] | None = None,
    client_request_id: str | None = None,
    notes: str = '',
    date=None,
) -> Sale:
    """
    Create a completed sale under the vacuum model.

    Each line: {product_variant_id, quantity, unit_price, discount_reason_id?}.
    FIFO allocation of LotStock at `location_id`. For every allocation slice
    one SaleLine is created with unit_purchase_price, unit_landed_cost, and
    profit_distribution_snapshot computed from lot.contract_snapshot.

    Each payment: {amount, currency, fx_rate, method, account_id?}. Payment
    method 'CREDIT' requires customer_id.
    """
    from apps.customers.services import accrue_debt
    from apps.finance.models import CashAccount, CashEntry
    from apps.finance.services import (
        create_cash_entry,
        record_sale_cogs_journal,
        record_sale_settlement_journal,
        record_sale_journal,
    )
    from apps.inventory.services import allocate_lot
    from apps.inventory.models import LotStock, StockMovement
    from apps.partnerships.models import PartnerLedgerEntry
    from apps.partnerships.services import (
        get_or_create_ledger, append_ledger_entry,
    )
    from apps.sales.models import SalePayment
    from apps.catalog.models import ProductVariant

    payments = payments or []

    # Credit invariant
    has_credit = any(
        p.get('method') == SalePayment.Method.CREDIT for p in payments
    )
    if has_credit and not customer_id:
        raise CreditSaleRequiresCustomerError()

    if date is None:
        date = timezone.now()
    with transaction.atomic():
        if client_request_id:
            existing = Sale.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        session = PosSession.objects.select_related('location').get(
            pk=pos_session_id,
            tenant_id=tenant_id,
            status=PosSession.SessionStatus.OPEN,
        )
        if location_id is not None and int(location_id) != session.location_id:
            raise ValueError('Продажа должна оформляться из точки открытой смены.')

        sale_location_id = session.location_id

        sale = Sale.objects.create(
            tenant_id=tenant_id,
            status=Sale.SaleStatus.DRAFT,
            location_id=sale_location_id,
            date=date,
            pos_session=session,
            customer_id=customer_id,
            sold_by_id=sold_by_id,
            client_request_id=client_request_id,
            notes=notes,
        )

        total_amount = Decimal('0')
        total_cogs = Decimal('0')

        for line_data in lines:
            variant_id = line_data['product_variant_id']
            quantity = int(line_data['quantity'])
            unit_price = Decimal(str(line_data['unit_price']))
            discount_reason_id = line_data.get('discount_reason_id')

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

            allocations = allocate_lot(
                product_variant_id=variant_id,
                warehouse_id=sale_location_id,
                quantity=quantity,
                tenant_id=tenant_id,
            )

            for alloc in allocations:
                lot = alloc['lot']
                lot_stock = alloc['lot_stock']
                alloc_qty = int(alloc['quantity'])

                locked_stock = LotStock.objects.select_for_update().get(
                    pk=lot_stock.pk,
                )
                if locked_stock.quantity_remaining < alloc_qty:
                    from apps.core.exceptions import InsufficientStockError
                    raise InsufficientStockError(
                        f'LotStock {locked_stock.pk} drained concurrently.'
                    )

                unit_landed_cost = Decimal(str(lot.landed_cost_per_unit))
                unit_purchase = Decimal(str(lot.unit_purchase_price))
                gross_line_profit = (unit_price - unit_landed_cost) * alloc_qty

                profit_snapshot = calculate_profit_distribution(
                    lot=lot,
                    unit_price=unit_price,
                    quantity=alloc_qty,
                    unit_landed_cost=unit_landed_cost,
                )

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
                    unit_purchase_price=unit_purchase,
                    unit_landed_cost=unit_landed_cost,
                    profit_distribution_snapshot=profit_snapshot,
                )

                locked_stock.quantity_remaining -= alloc_qty
                locked_stock.save(update_fields=['quantity_remaining', 'updated_at'])

                total_lot_remaining = (
                    LotStock.objects
                    .filter(lot=lot)
                    .aggregate(total=models.Sum('quantity_remaining'))['total']
                    or 0
                )
                if total_lot_remaining == 0:
                    type(lot).objects.filter(pk=lot.pk).update(is_active=False)

                StockMovement.objects.create(
                    tenant_id=tenant_id,
                    lot=lot,
                    movement_type=StockMovement.MovementType.SALE,
                    quantity=-alloc_qty,
                    from_location_id=location_id,
                    reference_type='sale',
                    reference_id=sale.pk,
                )

                total_amount += unit_price * alloc_qty
                total_cogs += unit_landed_cost * alloc_qty

                # PartnerLedger: PROFIT_ACCRUED per partner.
                procurement_id = None
                if lot.procurement_item_id:
                    procurement_id = lot.procurement_item.procurement_id
                if procurement_id and gross_line_profit > 0:
                    for partner_id_str, amount_str in profit_snapshot.items():
                        try:
                            partner_id = int(partner_id_str)
                        except (TypeError, ValueError):
                            continue
                        amount = Decimal(str(amount_str))
                        if amount <= 0:
                            continue
                        ledger = get_or_create_ledger(
                            procurement_id=procurement_id,
                            partner_id=partner_id,
                            tenant_id=tenant_id,
                        )
                        append_ledger_entry(
                            ledger=ledger,
                            entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=amount,
                            currency='UZS',
                            source_ref=f'sale_line:{sale_line.pk}',
                            date=date,
                        )

        # SalePayments
        credit_amount = Decimal('0')
        settlement_journals: list[dict] = []
        for pay in payments:
            amount = Decimal(str(pay['amount']))
            currency = str(pay.get('currency', 'UZS')).upper()
            fx_rate = resolve_fx_rate_snapshot(
                tenant_id=tenant_id,
                operation_currency=currency,
                operation_at=date,
                fx_rate_snapshot=pay.get('fx_rate'),
            )
            account_id = pay.get('account_id')
            if account_id is None:
                account_id = _resolve_default_cash_account_id(
                    tenant_id=tenant_id,
                    payment_method=pay['method'],
                    currency=currency,
                )
            payment = SalePayment.objects.create(
                tenant_id=tenant_id,
                sale=sale,
                date=date,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                method=pay['method'],
                role=SalePayment.Role.INCOMING,
                account_id=account_id,
            )

            if payment.method == SalePayment.Method.CREDIT:
                credit_amount += amount
                settlement_journals.append({
                    'amount': amount,
                    'payment_method': payment.method,
                    'debit_account_code': None,
                    'description': f'Sale credit #{sale.pk}',
                })
                continue

            debit_account_code = None
            if payment.account_id is None:
                settlement_journals.append({
                    'amount': amount,
                    'payment_method': payment.method,
                    'debit_account_code': debit_account_code,
                    'description': f'Sale payment #{payment.pk}',
                })
                continue

            account = CashAccount.objects.select_for_update().filter(
                pk=payment.account_id,
                tenant_id=tenant_id,
            ).first()
            if account is not None:
                if account.currency != currency:
                    raise ValueError(
                        f'Payment currency {currency} does not match cash account '
                        f'{account.name} currency {account.currency}.'
                    )

                create_cash_entry(
                    tenant_id=tenant_id,
                    account=account,
                    direction=CashEntry.Direction.IN,
                    amount=amount,
                    date=date,
                    source_ref_type='sale_payment',
                    source_ref_id=payment.pk,
                )
                if account.linked_account_id:
                    debit_account_code = account.linked_account.code

            settlement_journals.append({
                'amount': amount,
                'payment_method': payment.method,
                'debit_account_code': debit_account_code,
                'description': f'Sale payment #{payment.pk}',
            })

        if credit_amount > 0 and customer_id is not None:
            accrue_debt(
                tenant_id=tenant_id,
                customer_id=customer_id,
                amount=credit_amount,
                currency='UZS',
                fx_rate=Decimal('1'),
                source_ref=f'sale:{sale.pk}',
                date=date,
            )

        sale.total_amount = total_amount
        sale.total_cogs = total_cogs
        sale.status = Sale.SaleStatus.COMPLETED
        sale.save(update_fields=[
            'total_amount', 'total_cogs', 'status', 'updated_at',
        ])

        if not payments:
            record_sale_journal(
                tenant_id=tenant_id,
                sale_id=sale.pk,
                total_amount=total_amount,
                total_cogs=total_cogs,
                payment_method='credit',
                date=date,
            )
        else:
            for journal in settlement_journals:
                record_sale_settlement_journal(
                    tenant_id=tenant_id,
                    sale_id=sale.pk,
                    amount=journal['amount'],
                    payment_method=journal['payment_method'],
                    debit_account_code=journal['debit_account_code'],
                    description=journal['description'],
                    date=date,
                )
            record_sale_cogs_journal(
                tenant_id=tenant_id,
                sale_id=sale.pk,
                total_cogs=total_cogs,
                date=date,
            )

        publish_event(
            event_type='sale.completed',
            payload={
                'sale_id': sale.pk,
                'total_amount': str(total_amount),
                'total_cogs': str(total_cogs),
                'lines_count': sale.lines.count(),
                'payments_count': len(payments),
                'date': date.isoformat(),
            },
            tenant_id=tenant_id,
        )

    return sale


def calculate_profit_distribution(
    *,
    lot: 'Lot',
    unit_price: Decimal,
    quantity: int,
    unit_landed_cost: Decimal,
) -> dict:
    """
    Compute profit per partner for a single sale line slice.

    Uses lot.contract_snapshot:
      {mudaraba_ratio, loss_rule, partners: [{partner_id, role, capital_share, profit_share}]}

    Contract formula (Musharaka+Mudaraba):
      profit_investor_i = gross * capital_share_i * mudaraba_ratio
      profit_operator   = gross * capital_share_op +
                          gross * (1 - mudaraba_ratio) * Σ capital_share_investors

    Returns {partner_id_str: Decimal_str} to be stored in SaleLine.profit_distribution_snapshot.
    Returns {} for lots without a contract snapshot (own-funds path).
    """
    unit_price = Decimal(str(unit_price))
    unit_landed_cost = Decimal(str(unit_landed_cost))
    gross = (unit_price - unit_landed_cost) * Decimal(quantity)
    if gross <= 0:
        return {}

    snapshot = lot.contract_snapshot or {}
    partners = snapshot.get('partners') or []
    if not partners:
        return {}

    mudaraba_ratio = Decimal(str(snapshot.get('mudaraba_ratio', '0')))
    operator_entry = next(
        (p for p in partners if p.get('role') == 'OPERATOR'), None,
    )
    result: dict[str, str] = {}

    investor_capital_total = sum(
        (Decimal(str(p.get('capital_share', '0')))
         for p in partners if p.get('role') == 'INVESTOR'),
        Decimal('0'),
    )

    for partner in partners:
        partner_id = partner.get('partner_id')
        if partner_id is None:
            continue
        capital_share = Decimal(str(partner.get('capital_share', '0')))
        role = partner.get('role')
        if role == 'INVESTOR':
            share = gross * capital_share * mudaraba_ratio
        elif role == 'OPERATOR':
            share = (
                gross * capital_share
                + gross * (Decimal('1') - mudaraba_ratio) * investor_capital_total
            )
        else:
            share = Decimal('0')
        share = share.quantize(Decimal('0.01'))
        if share != 0:
            result[str(partner_id)] = str(share)

    # Rounding residue → operator (shariah-neutral: operator bears residue).
    if operator_entry is not None:
        distributed = sum(
            (Decimal(v) for v in result.values()), Decimal('0'),
        )
        residue = (gross.quantize(Decimal('0.01')) - distributed)
        if residue != 0:
            op_id = str(operator_entry['partner_id'])
            current = Decimal(result.get(op_id, '0'))
            result[op_id] = str((current + residue).quantize(Decimal('0.01')))

    return result


def process_return(
    sale: Sale,
    return_lines: list[dict],
    resolution: str,
    reason: str,
    processed_by_id: int,
    tenant_id: int,
    notes: str = '',
    date=None,
    refund: dict | None = None,
) -> Return:
    """
    Process a return for a completed sale with shariah-correct partner impact.

    resolution RESTOCK:
      - LotStock at sale.location += qty, reactivate Lot.
      - PROFIT_REVERSED per partner, proportional to returned qty.

    resolution DISPOSE:
      - StockDisposal record (reason=DAMAGED_RETURN).
      - Lot.quantity_initial -= qty (goods never return to stock).
      - PROFIT_REVERSED per partner (proportional to returned qty).
      - LOSS_INCURRED per partner distributed by capital_share from contract_snapshot.

    Monetary refund:
      If `refund` is provided — {method, currency?, fx_rate?, account_id?} — a Refund
      is issued for the full line-level refund total via finance.refund_customer.
      If `refund` is None, the caller is responsible for the monetary side.

    Invariant: Σ ReturnLine.qty per sale_line ≤ SaleLine.qty (including prior returns).
    """
    from apps.inventory.models import Lot, LotStock, StockDisposal
    from apps.partnerships.models import PartnerLedgerEntry
    from apps.partnerships.services import append_ledger_entry, get_or_create_ledger

    if date is None:
        date = timezone.now()

    if resolution not in (Return.Resolution.RESTOCK, Return.Resolution.DISPOSE):
        raise ValueError(f'Invalid resolution: {resolution}')

    with transaction.atomic():
        return_doc = Return.objects.create(
            tenant_id=tenant_id,
            sale=sale,
            processed_by_id=processed_by_id,
            resolution=resolution,
            reason=reason,
            date=date,
            notes=notes,
        )

        total_refund = Decimal('0')
        total_loss = Decimal('0')

        for rl_data in return_lines:
            sale_line = SaleLine.objects.select_related('lot').get(
                pk=rl_data['sale_line_id'],
                sale=sale,
                tenant_id=tenant_id,
            )
            qty = int(rl_data['quantity'])
            if qty < 1:
                raise ValueError('Return line quantity must be >= 1.')

            already_returned = (
                ReturnLine.objects
                .filter(sale_line=sale_line)
                .aggregate(total=models.Sum('quantity'))['total']
            ) or 0
            if already_returned + qty > sale_line.quantity:
                raise ValueError(
                    f'Return exceeds sold quantity for sale_line #{sale_line.pk}: '
                    f'sold={sale_line.quantity}, already returned={already_returned}, '
                    f'requested={qty}.'
                )

            ReturnLine.objects.create(
                tenant_id=tenant_id,
                return_doc=return_doc,
                sale_line=sale_line,
                quantity=qty,
            )

            lot = sale_line.lot
            qty_ratio = Decimal(qty) / Decimal(sale_line.quantity)
            line_refund = sale_line.unit_price * qty
            line_loss = sale_line.unit_landed_cost * qty
            total_refund += line_refund

            # Proportional PROFIT_REVERSED per partner
            distribution = sale_line.profit_distribution_snapshot or {}
            contract_snapshot = lot.contract_snapshot or {}
            partners_meta = {
                str(p.get('partner_id')): p
                for p in contract_snapshot.get('partners', [])
                if p.get('partner_id') is not None
            }
            procurement_id = None
            if lot.procurement_item_id:
                procurement_id = lot.procurement_item.procurement_id

            if procurement_id and distribution:
                for partner_id_str, profit_str in distribution.items():
                    try:
                        partner_id = int(partner_id_str)
                    except (TypeError, ValueError):
                        continue
                    profit_amount = Decimal(str(profit_str))
                    reversed_amount = (profit_amount * qty_ratio).quantize(Decimal('0.01'))
                    if reversed_amount <= 0:
                        continue
                    ledger = get_or_create_ledger(
                        procurement_id=procurement_id,
                        partner_id=partner_id,
                        tenant_id=tenant_id,
                    )
                    append_ledger_entry(
                        ledger=ledger,
                        entry_type=PartnerLedgerEntry.EntryType.PROFIT_REVERSED,
                        amount=reversed_amount,
                        currency='UZS',
                        source_ref=f'return:{return_doc.pk}:line:{sale_line.pk}',
                        date=date,
                    )

            if resolution == Return.Resolution.RESTOCK:
                stock, _ = LotStock.objects.select_for_update().get_or_create(
                    tenant_id=tenant_id,
                    lot=lot,
                    warehouse=sale.location,
                    defaults={'quantity_remaining': 0},
                )
                stock.quantity_remaining = stock.quantity_remaining + qty
                stock.save(update_fields=['quantity_remaining', 'updated_at'])

                if not lot.is_active:
                    Lot.objects.filter(pk=lot.pk).update(is_active=True)

            else:  # DISPOSE
                StockDisposal.objects.create(
                    tenant_id=tenant_id,
                    lot=lot,
                    warehouse=sale.location,
                    quantity=qty,
                    reason=StockDisposal.Reason.DAMAGED_RETURN,
                    loss_amount=line_loss,
                    return_ref=return_doc,
                    notes=f'Dispose from Return #{return_doc.pk}',
                )
                Lot.objects.filter(pk=lot.pk).update(
                    quantity_initial=models.F('quantity_initial') - qty,
                )
                total_loss += line_loss

                # LOSS_INCURRED per partner by capital_share
                if procurement_id and partners_meta:
                    for partner_id_str, meta in partners_meta.items():
                        try:
                            partner_id = int(partner_id_str)
                        except (TypeError, ValueError):
                            continue
                        capital_share = Decimal(str(meta.get('capital_share', '0')))
                        if capital_share <= 0:
                            continue
                        loss_share = (line_loss * capital_share).quantize(Decimal('0.01'))
                        if loss_share <= 0:
                            continue
                        ledger = get_or_create_ledger(
                            procurement_id=procurement_id,
                            partner_id=partner_id,
                            tenant_id=tenant_id,
                        )
                        append_ledger_entry(
                            ledger=ledger,
                            entry_type=PartnerLedgerEntry.EntryType.LOSS_INCURRED,
                            amount=loss_share,
                            currency='UZS',
                            source_ref=f'return:{return_doc.pk}:line:{sale_line.pk}',
                            date=date,
                        )

        if refund and total_refund > 0:
            from apps.finance.services import refund_customer
            if sale.customer_id is None:
                raise ValueError(
                    'Cannot issue refund: sale has no customer. Remove refund kwarg or set customer.'
                )
            refund_customer(
                tenant_id=tenant_id,
                customer_id=sale.customer_id,
                sale_id=sale.pk,
                amount=total_refund,
                currency=str(refund.get('currency', 'UZS')).upper(),
                fx_rate=Decimal(str(refund.get('fx_rate', '1'))),
                method=refund['method'],
                account_id=refund.get('account_id'),
                return_ref_id=return_doc.pk,
                date=date,
            )

        publish_event(
            event_type='sale.returned',
            payload={
                'sale_id': sale.pk,
                'return_id': return_doc.pk,
                'resolution': resolution,
                'reason': reason,
                'lines_count': len(return_lines),
                'refund_amount': str(total_refund),
                'refund_issued': bool(refund and total_refund > 0),
                'loss_amount': str(total_loss),
            },
            tenant_id=tenant_id,
        )

    return return_doc


def open_pos_session(
    tenant_id: int,
    location_id: int,
    opened_by_id: int,
    opening_cash: Decimal = Decimal('0'),
) -> PosSession:
    """Open a new POS session (shift)."""
    from apps.inventory.models import Warehouse

    location = Warehouse.objects.get(pk=location_id, tenant_id=tenant_id)
    if location.kind != Warehouse.WarehouseKind.SHOP:
        raise ValueError('Смену можно открыть только на магазине.')

    existing_open_session = PosSession.objects.filter(
        tenant_id=tenant_id,
        location_id=location_id,
        status=PosSession.SessionStatus.OPEN,
    ).first()
    if existing_open_session:
        raise ValueError('На этой точке уже есть открытая смена.')

    existing_user_session = PosSession.objects.filter(
        tenant_id=tenant_id,
        opened_by_id=opened_by_id,
        status=PosSession.SessionStatus.OPEN,
    ).first()
    if existing_user_session:
        raise ValueError('У вас уже есть открытая смена.')

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
        if session.status != PosSession.SessionStatus.OPEN:
            raise ValueError('Можно закрыть только открытую смену.')

        # Calculate expected cash from incoming cash payments.
        from apps.sales.models import SalePayment

        cash_sales_total = SalePayment.objects.filter(
            sale__pos_session=session,
            sale__status=Sale.SaleStatus.COMPLETED,
            role=SalePayment.Role.INCOMING,
            method=SalePayment.Method.CASH,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

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
