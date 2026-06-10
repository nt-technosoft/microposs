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
from apps.finance.fx_rates import resolve_fx_rate_snapshot, resolve_fx_rate_snapshot_details
from apps.partnerships.formulas import calculate_lot_profit_distribution
from apps.sales.currency import functional_amount_uzs, money

from .models import (
    Sale, SaleLine, SalePayment, Return, ReturnLine, PosSession,
)

if TYPE_CHECKING:
    from apps.inventory.models import Lot


SALE_ACCOUNTING_STATUSES = (
    Sale.SaleStatus.COMPLETED,
    Sale.SaleStatus.PARTIALLY_RETURNED,
    Sale.SaleStatus.RETURNED,
)


def _currency_map(value: dict | None, *, fallback_uzs: Decimal | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    if value:
        for currency, amount in value.items():
            normalized = str(currency or '').upper()
            if not normalized:
                continue
            result[normalized] = str(money(amount or '0'))
    if fallback_uzs is not None and 'UZS' not in result:
        result['UZS'] = str(money(fallback_uzs))
    return result


def _sum_currency_maps(left: dict[str, str], right: dict[str, Decimal | str]) -> dict[str, str]:
    totals: dict[str, Decimal] = {
        str(currency).upper(): money(amount)
        for currency, amount in left.items()
    }
    for currency, amount in right.items():
        normalized = str(currency or '').upper()
        if not normalized:
            continue
        totals[normalized] = money(totals.get(normalized, Decimal('0')) + Decimal(str(amount or '0')))
    return {currency: str(money(amount)) for currency, amount in sorted(totals.items())}


def _diff_currency_maps(actual: dict[str, str], expected: dict[str, str]) -> dict[str, str]:
    currencies = set(actual.keys()) | set(expected.keys())
    return {
        currency: str(money(Decimal(str(actual.get(currency, '0'))) - Decimal(str(expected.get(currency, '0')))))
        for currency in sorted(currencies)
    }


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
    from apps.partnerships.venture import record_sale_line_realization
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
        consignment_legs: list[dict] = []

        for line_data in lines:
            variant_id = line_data['product_variant_id']
            quantity = int(line_data['quantity'])
            operation_currency = str(line_data.get('operation_currency') or 'UZS').upper()
            operation_unit_price_raw = line_data.get('operation_unit_price')
            has_operation_price = operation_unit_price_raw is not None or operation_currency != 'UZS'
            operation_unit_price = Decimal(str(
                operation_unit_price_raw
                if operation_unit_price_raw is not None
                else line_data['unit_price']
            ))
            line_fx_snapshot = resolve_fx_rate_snapshot_details(
                tenant_id=tenant_id,
                operation_currency=operation_currency,
                operation_at=date,
                fx_rate_snapshot=line_data.get('fx_rate'),
            )
            unit_price = (
                functional_amount_uzs(
                    amount=operation_unit_price,
                    currency=operation_currency,
                    fx_rate=line_fx_snapshot.rate,
                )
                if has_operation_price
                else Decimal(str(line_data['unit_price'])).quantize(Decimal('0.01'))
            )
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
                    operation_currency=operation_currency,
                    operation_unit_price=operation_unit_price,
                    fx_rate_snapshot=line_fx_snapshot.rate,
                    fx_rate_source=line_fx_snapshot.source,
                    fx_rate_date=line_fx_snapshot.rate_date,
                    price_changed=price_changed,
                    discount_reason_id=resolved_discount_reason_id,
                    unit_purchase_price=unit_purchase,
                    unit_landed_cost=unit_landed_cost,
                    profit_distribution_snapshot=profit_snapshot,
                )

                # E09 Phase 2 — auto-obligation for CONSIGNED Lot sales
                from apps.suppliers.consignment_obligations import (
                    record_consignment_obligation_for_sale_line,
                )
                consignment_payable = record_consignment_obligation_for_sale_line(sale_line)
                if consignment_payable is not None:
                    leg_cogs_uzs = (
                        Decimal(str(lot.landed_cost_per_unit)) * Decimal(str(alloc_qty))
                    ).quantize(Decimal('0.01'))
                    consignment_legs.append({
                        'payable_id': consignment_payable.id,
                        'amount_uzs': leg_cogs_uzs,
                    })

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
                    from_location_id=sale_location_id,
                    reference_type='sale',
                    reference_id=sale.pk,
                )

                total_amount += unit_price * alloc_qty
                total_cogs += unit_landed_cost * alloc_qty

                # E17 T-1.5: partner profit/capital economics are recorded only
                # as venture realization events (single source of truth). The
                # legacy PROFIT_ACCRUED ledger write is intentionally gone — it
                # split per-line gross profit by profit_share and ignored later
                # losses, overstating distributable profit.
                record_sale_line_realization(sale_line=sale_line)

        # SalePayments
        payment_functional_total = Decimal('0')
        credit_payments: list[dict] = []
        settlement_journals: list[dict] = []
        for pay in payments:
            amount = Decimal(str(pay['amount']))
            currency = str(pay.get('currency', 'UZS')).upper()
            payment_fx_snapshot = resolve_fx_rate_snapshot_details(
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
                fx_rate=payment_fx_snapshot.rate,
                fx_rate_source=payment_fx_snapshot.source,
                fx_rate_date=payment_fx_snapshot.rate_date,
                method=pay['method'],
                role=SalePayment.Role.INCOMING,
                account_id=account_id,
            )
            functional_amount = functional_amount_uzs(
                amount=amount,
                currency=currency,
                fx_rate=payment_fx_snapshot.rate,
            )
            payment_functional_total += functional_amount

            if payment.method == SalePayment.Method.CREDIT:
                credit_payments.append({
                    'amount': amount,
                    'currency': currency,
                    'fx_rate': payment_fx_snapshot.rate,
                    'fx_rate_source': payment_fx_snapshot.source,
                    'fx_rate_date': payment_fx_snapshot.rate_date,
                })
                settlement_journals.append({
                    'amount': functional_amount,
                    'payment_method': payment.method,
                    'debit_account_code': None,
                    'description': f'Sale credit #{sale.pk}',
                })
                continue

            debit_account_code = None
            if payment.account_id is None:
                settlement_journals.append({
                    'amount': functional_amount,
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
                'amount': functional_amount,
                'payment_method': payment.method,
                'debit_account_code': debit_account_code,
                'description': f'Sale payment #{payment.pk}',
            })

        if payments and money(payment_functional_total) != money(total_amount):
            raise ValueError(
                'Сумма оплат в UZS-эквиваленте не совпадает с суммой продажи.'
            )

        for credit in credit_payments:
            accrue_debt(
                tenant_id=tenant_id,
                customer_id=customer_id,
                amount=credit['amount'],
                currency=credit['currency'],
                fx_rate=credit['fx_rate'],
                fx_rate_source=credit.get('fx_rate_source', ''),
                fx_rate_date=credit.get('fx_rate_date'),
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
                consignment_legs=consignment_legs or None,
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
    return calculate_lot_profit_distribution(
        contract_snapshot=lot.contract_snapshot,
        unit_price=unit_price,
        quantity=quantity,
        unit_landed_cost=unit_landed_cost,
    )


def _returned_quantity_for_line(sale_line: SaleLine) -> int:
    return int(
        ReturnLine.objects
        .filter(sale_line=sale_line)
        .aggregate(total=models.Sum('quantity'))['total']
        or 0
    )


def _returned_quantity_by_resolution(sale_line: SaleLine, resolution: str) -> int:
    return int(
        ReturnLine.objects
        .filter(sale_line=sale_line, return_doc__resolution=resolution)
        .aggregate(total=models.Sum('quantity'))['total']
        or 0
    )


def sale_financial_effect(sale: Sale) -> dict:
    """
    Net sale effect after returns.

    Revenue is reduced by every returned item. COGS is reduced only when the
    item returns to stock. Returned disposed goods remain a business loss.
    """
    revenue = Decimal('0')
    cogs = Decimal('0')
    returned_amount = Decimal('0')
    restock_cogs = Decimal('0')
    disposal_loss = Decimal('0')
    quantity_sold = 0
    quantity_returned = 0

    for line in sale.lines.all():
        returned_total = _returned_quantity_for_line(line)
        restock_qty = _returned_quantity_by_resolution(line, Return.Resolution.RESTOCK)
        dispose_qty = _returned_quantity_by_resolution(line, Return.Resolution.DISPOSE)
        net_qty = max(int(line.quantity) - returned_total, 0)

        revenue += Decimal(str(line.unit_price)) * Decimal(net_qty)
        cogs += Decimal(str(line.unit_landed_cost)) * Decimal(int(line.quantity) - restock_qty)
        returned_amount += Decimal(str(line.unit_price)) * Decimal(returned_total)
        restock_cogs += Decimal(str(line.unit_landed_cost)) * Decimal(restock_qty)
        disposal_loss += Decimal(str(line.unit_landed_cost)) * Decimal(dispose_qty)
        quantity_sold += net_qty
        quantity_returned += returned_total

    gross_profit = revenue - cogs
    return {
        'revenue': money(revenue),
        'cogs': money(cogs),
        'gross_profit': money(gross_profit),
        'returned_amount': money(returned_amount),
        'restock_cogs': money(restock_cogs),
        'disposal_loss': money(disposal_loss),
        'quantity_sold': quantity_sold,
        'quantity_returned': quantity_returned,
    }


def _sync_sale_return_status(sale: Sale) -> None:
    total_qty = int(
        sale.lines.aggregate(total=models.Sum('quantity'))['total']
        or 0
    )
    returned_qty = int(
        ReturnLine.objects
        .filter(return_doc__sale=sale)
        .aggregate(total=models.Sum('quantity'))['total']
        or 0
    )
    if returned_qty <= 0:
        next_status = Sale.SaleStatus.COMPLETED
    elif returned_qty >= total_qty:
        next_status = Sale.SaleStatus.RETURNED
    else:
        next_status = Sale.SaleStatus.PARTIALLY_RETURNED

    if sale.status != next_status:
        Sale.objects.filter(pk=sale.pk).update(status=next_status, updated_at=timezone.now())
        sale.status = next_status


def _profit_reversal_for_line(sale_line: SaleLine, qty: int) -> Decimal:
    if sale_line.quantity <= 0:
        return Decimal('0.00')
    qty_ratio = Decimal(qty) / Decimal(sale_line.quantity)
    return money(
        sum(
            (
                Decimal(str(amount)) * qty_ratio
                for amount in (sale_line.profit_distribution_snapshot or {}).values()
            ),
            Decimal('0'),
        )
    )


def _build_selected_return_effect(
    *,
    sale: Sale,
    return_lines: list[dict] | None,
    resolution: str,
) -> dict:
    selected_by_line = {
        int(line['sale_line_id']): int(line.get('quantity') or 0)
        for line in (return_lines or [])
    }
    selected_refund = Decimal('0')
    selected_cogs = Decimal('0')
    selected_profit_reversal = Decimal('0')

    line_payloads = []
    for sale_line in sale.lines.select_related('product_variant__product', 'lot').all():
        already_returned = _returned_quantity_for_line(sale_line)
        available_qty = max(int(sale_line.quantity) - already_returned, 0)
        requested_qty = selected_by_line.get(sale_line.pk, 0)
        if requested_qty < 0 or requested_qty > available_qty:
            raise ValueError(
                f'Return quantity for sale_line #{sale_line.pk} must be between 0 and {available_qty}.'
            )
        if requested_qty:
            selected_refund += Decimal(str(sale_line.unit_price)) * Decimal(requested_qty)
            selected_cogs += Decimal(str(sale_line.unit_landed_cost)) * Decimal(requested_qty)
            selected_profit_reversal += _profit_reversal_for_line(sale_line, requested_qty)

        product = sale_line.product_variant.product
        line_payloads.append({
            'sale_line_id': sale_line.pk,
            'product_name': product.name,
            'variant_name': str(sale_line.product_variant),
            'lot_id': sale_line.lot_id,
            'sold_quantity': int(sale_line.quantity),
            'already_returned_quantity': already_returned,
            'available_quantity': available_qty,
            'selected_quantity': requested_qty,
            'unit_price_uzs': str(money(sale_line.unit_price)),
            'unit_landed_cost_uzs': str(money(sale_line.unit_landed_cost)),
            'operation_currency': sale_line.operation_currency,
            'operation_unit_price': str(sale_line.operation_unit_price or sale_line.unit_price),
            'fx_rate_snapshot': str(sale_line.fx_rate_snapshot),
        })

    cogs_effect_key = (
        'restock_cogs_uzs'
        if resolution == Return.Resolution.RESTOCK
        else 'disposal_loss_uzs'
    )
    return {
        'lines': line_payloads,
        'selected': {
            'refund_amount_uzs': str(money(selected_refund)),
            'profit_reversal_uzs': str(money(selected_profit_reversal)),
            'restock_cogs_uzs': str(money(selected_cogs if resolution == Return.Resolution.RESTOCK else Decimal('0'))),
            'disposal_loss_uzs': str(money(selected_cogs if resolution == Return.Resolution.DISPOSE else Decimal('0'))),
            cogs_effect_key: str(money(selected_cogs)),
        },
    }


def build_return_preview(
    *,
    sale: Sale,
    tenant_id: int,
    return_lines: list[dict] | None = None,
    resolution: str = Return.Resolution.RESTOCK,
) -> dict:
    """Preview returnable lines, refund capacity and financial effect."""
    if sale.tenant_id != tenant_id:
        raise ValueError('Sale does not belong to tenant.')
    if resolution not in (Return.Resolution.RESTOCK, Return.Resolution.DISPOSE):
        raise ValueError(f'Invalid resolution: {resolution}')

    effect = _build_selected_return_effect(
        sale=sale,
        return_lines=return_lines,
        resolution=resolution,
    )
    incoming_by_currency: dict[str, Decimal] = {}
    refunded_by_currency: dict[str, Decimal] = {}
    for payment in sale.payments.all():
        currency = str(payment.currency or 'UZS').upper()
        if payment.role == SalePayment.Role.INCOMING:
            incoming_by_currency[currency] = incoming_by_currency.get(currency, Decimal('0')) + Decimal(str(payment.amount))
        elif payment.role == SalePayment.Role.REFUND:
            refunded_by_currency[currency] = refunded_by_currency.get(currency, Decimal('0')) + Decimal(str(payment.amount))

    remaining_refundable = {
        currency: str(money(amount - refunded_by_currency.get(currency, Decimal('0'))))
        for currency, amount in sorted(incoming_by_currency.items())
    }
    return {
        'sale_id': sale.pk,
        'sale_status': sale.status,
        'resolution': resolution,
        'status': 'READY',
        'remaining_refundable_by_currency': remaining_refundable,
        **effect,
    }


def _refund_method_to_sale_method(method: str) -> str:
    normalized = str(method or '').upper()
    if normalized in {'CASH', 'НАЛИЧНЫЕ'}:
        return SalePayment.Method.CASH
    if normalized in {'CARD', 'PLASTIK', 'ПЛАСТИК'}:
        return SalePayment.Method.CARD
    if normalized in {'TRANSFER', 'BANK', 'ПЕРЕВОД'}:
        return SalePayment.Method.TRANSFER
    if normalized in {'CREDIT', 'RECEIVABLE_OFFSET'}:
        return SalePayment.Method.CREDIT
    raise ValueError(f'Invalid refund method: {method}')


def _refund_method_to_finance_method(method: str) -> str:
    from apps.finance.models import Refund

    sale_method = _refund_method_to_sale_method(method)
    if sale_method == SalePayment.Method.CASH:
        return Refund.Method.CASH
    if sale_method == SalePayment.Method.CARD:
        return Refund.Method.PLASTIK
    if sale_method == SalePayment.Method.TRANSFER:
        return Refund.Method.TRANSFER
    return Refund.Method.RECEIVABLE_OFFSET


def _validate_refund_currency_capacity(
    *,
    sale: Sale,
    refund_payments: list[dict],
) -> None:
    incoming: dict[str, Decimal] = {}
    refunded: dict[str, Decimal] = {}
    requested: dict[str, Decimal] = {}
    for payment in sale.payments.all():
        currency = str(payment.currency or 'UZS').upper()
        if payment.role == SalePayment.Role.INCOMING:
            incoming[currency] = incoming.get(currency, Decimal('0')) + Decimal(str(payment.amount))
        elif payment.role == SalePayment.Role.REFUND:
            refunded[currency] = refunded.get(currency, Decimal('0')) + Decimal(str(payment.amount))
    for payload in refund_payments:
        currency = str(payload.get('currency') or 'UZS').upper()
        requested[currency] = requested.get(currency, Decimal('0')) + money(payload['amount'])
    for currency, amount in requested.items():
        if refunded.get(currency, Decimal('0')) + amount > incoming.get(currency, Decimal('0')):
            raise ValueError(
                f'Refund {amount} {currency} exceeds remaining paid amount '
                f'{incoming.get(currency, Decimal("0")) - refunded.get(currency, Decimal("0"))} {currency}.'
            )


def _issue_return_refund(
    *,
    sale: Sale,
    return_doc: Return,
    tenant_id: int,
    payment_payload: dict,
    date,
):
    from apps.customers.models import Customer, ReceivableEntry
    from apps.customers.services import get_or_create_receivable
    from apps.finance.models import CashAccount, CashEntry, Refund
    from apps.finance.services import create_cash_entry, create_journal_entry

    method = _refund_method_to_sale_method(payment_payload['method'])
    finance_method = _refund_method_to_finance_method(payment_payload['method'])
    amount = money(payment_payload['amount'])
    currency = str(payment_payload.get('currency') or 'UZS').upper()
    fx_snapshot = resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id,
        operation_currency=currency,
        operation_at=date,
        fx_rate_snapshot=payment_payload.get('fx_rate'),
    )
    functional_amount = functional_amount_uzs(
        amount=amount,
        currency=currency,
        fx_rate=fx_snapshot.rate,
    )
    if amount <= 0:
        raise ValueError('Refund amount must be > 0.')

    account = None
    if method != SalePayment.Method.CREDIT:
        account_id = payment_payload.get('account_id')
        if account_id is None:
            account_id = _resolve_default_cash_account_id(
                tenant_id=tenant_id,
                payment_method=method,
                currency=currency,
            )
        if account_id is None:
            raise ValueError(f'Не найден счёт для возврата {method} {currency}.')
        account = CashAccount.objects.select_for_update().get(
            pk=account_id,
            tenant_id=tenant_id,
        )
        if account.currency != currency:
            raise ValueError(
                f'Refund currency {currency} does not match cash account {account.name} currency {account.currency}.'
            )
        if account.balance < amount:
            raise ValueError(
                f'Недостаточно денег на счёте {account.name}: есть {account.balance}, нужно {amount}.'
            )
    elif sale.customer_id is None:
        raise ValueError('Зачёт долга возможен только для продажи с клиентом.')

    refund = Refund.objects.create(
        tenant_id=tenant_id,
        customer_id=sale.customer_id,
        date=date,
        amount=amount,
        currency=currency,
        fx_rate=fx_snapshot.rate,
        fx_rate_source=fx_snapshot.source,
        fx_rate_date=fx_snapshot.rate_date,
        account=account,
        method=finance_method,
        return_ref=return_doc,
    )

    SalePayment.objects.create(
        tenant_id=tenant_id,
        sale=sale,
        date=date,
        amount=amount,
        currency=currency,
        fx_rate=fx_snapshot.rate,
        fx_rate_source=fx_snapshot.source,
        fx_rate_date=fx_snapshot.rate_date,
        method=method,
        role=SalePayment.Role.REFUND,
        account_id=account.pk if account else None,
    )

    if method == SalePayment.Method.CREDIT:
        customer_obj = Customer.objects.get(pk=sale.customer_id, tenant_id=tenant_id)
        receivable = get_or_create_receivable(customer_obj, tenant_id)
        receivable = type(receivable).objects.select_for_update().get(pk=receivable.pk)
        balances = dict(receivable.balances)
        current = Decimal(str(balances.get(currency, '0')))
        balances[currency] = str(money(current - amount))
        receivable.balances = balances
        receivable.save(update_fields=['balances', 'updated_at'])
        ReceivableEntry.objects.create(
            tenant_id=tenant_id,
            receivable=receivable,
            date=date,
            amount=-amount,
            currency=currency,
            fx_rate=fx_snapshot.rate,
            fx_rate_source=fx_snapshot.source,
            fx_rate_date=fx_snapshot.rate_date,
            entry_type=ReceivableEntry.EntryType.ADJUSTMENT,
            source_ref=f'refund:{refund.pk}',
        )
        credit_code = '1200'
    else:
        create_cash_entry(
            tenant_id=tenant_id,
            account=account,
            direction=CashEntry.Direction.OUT,
            amount=amount,
            date=date,
            source_ref_type='refund',
            source_ref_id=refund.pk,
        )
        credit_code = account.linked_account.code if account and account.linked_account_id else (
            '1000' if method == SalePayment.Method.CASH else '1010'
        )

    create_journal_entry(
        tenant_id=tenant_id,
        operation_type='return',
        operation_id=refund.pk,
        lines=[
            {
                'account_code': '4000',
                'debit': functional_amount,
                'credit': Decimal('0'),
                'description': f'Return refund #{refund.pk} revenue reversal',
            },
            {
                'account_code': credit_code,
                'debit': Decimal('0'),
                'credit': functional_amount,
                'description': f'Return refund #{refund.pk}',
            },
        ],
        description=f'Sale return refund #{refund.pk}',
        date=date,
    )

    publish_event(
        event_type='finance.refund',
        payload={
            'refund_id': refund.pk,
            'return_id': return_doc.pk,
            'sale_id': sale.pk,
            'customer_id': sale.customer_id,
            'amount': str(amount),
            'currency': currency,
            'method': finance_method,
            'date': date.isoformat(),
        },
        tenant_id=tenant_id,
    )
    return refund


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
    refund_payments: list[dict] | None = None,
    client_request_id=None,
) -> Return:
    """
    Process a return for a completed sale with shariah-correct partner impact.

    resolution RESTOCK:
      - LotStock at sale.location += qty, reactivate Lot.
      - Venture realization reversed proportionally (append-only REVERSAL events).

    resolution DISPOSE:
      - StockDisposal record (reason=DAMAGED_RETURN).
      - Lot.quantity_initial -= qty (goods never return to stock).
      - Venture realization reversed + damaged-return loss by capital share, all as
        append-only REVERSAL events (single source of truth = venture model).

    Monetary refund:
      If `refund_payments` is provided, each item creates SalePayment(role=REFUND),
      CashEntry/ReceivableEntry and revenue reversal journal in functional UZS.
      Legacy `refund` is still accepted and converted into a single refund payment.

    Invariant: Σ ReturnLine.qty per sale_line ≤ SaleLine.qty (including prior returns).
    """
    from apps.inventory.models import Lot, LotStock, StockDisposal, StockMovement
    from apps.partnerships.venture import record_sale_line_return_realization
    from apps.finance.services import create_journal_entry

    if date is None:
        date = timezone.now()

    if resolution not in (Return.Resolution.RESTOCK, Return.Resolution.DISPOSE):
        raise ValueError(f'Invalid resolution: {resolution}')

    refund_payments = list(refund_payments or [])
    if refund and not refund_payments:
        refund_payments = [{
            'method': refund['method'],
            'currency': refund.get('currency', 'UZS'),
            'fx_rate': refund.get('fx_rate', '1'),
            'account_id': refund.get('account_id'),
            'amount': refund.get('amount'),
        }]

    with transaction.atomic():
        # E17 T-4.1: idempotent on client_request_id — a repeat submit returns the
        # existing Return without creating a second one or re-moving any money.
        if client_request_id:
            existing = Return.objects.filter(
                tenant_id=tenant_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing

        sale = Sale.objects.select_for_update().get(pk=sale.pk, tenant_id=tenant_id)
        if sale.status not in (
            Sale.SaleStatus.COMPLETED,
            Sale.SaleStatus.PARTIALLY_RETURNED,
        ):
            raise ValueError('Возврат можно оформить только по завершённой продаже.')

        # E17 T-3.3: a closed procurement venture is read-only — no returns.
        from apps.partnerships.venture import assert_procurement_open
        for rl_data in return_lines:
            line = SaleLine.objects.select_related('lot__procurement_item__procurement').get(
                pk=rl_data['sale_line_id'], sale=sale, tenant_id=tenant_id,
            )
            procurement = getattr(getattr(line.lot, 'procurement_item', None), 'procurement', None)
            if procurement is not None:
                assert_procurement_open(procurement)

        return_doc = Return.objects.create(
            tenant_id=tenant_id,
            sale=sale,
            processed_by_id=processed_by_id,
            resolution=resolution,
            reason=reason,
            date=date,
            notes=notes,
            client_request_id=str(client_request_id) if client_request_id else None,
        )

        total_refund = Decimal('0')
        total_restock_cogs = Decimal('0')
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
            line_refund = sale_line.unit_price * qty
            line_loss = sale_line.unit_landed_cost * qty
            total_refund += line_refund

            # E17 T-1.5: returns reverse partner economics only through venture
            # realization events (see record_sale_line_return_realization below).
            # The legacy PROFIT_REVERSED / LOSS_INCURRED ledger writes are gone.

            if resolution == Return.Resolution.RESTOCK:
                record_sale_line_return_realization(
                    sale_line=sale_line,
                    quantity=qty,
                    source_ref=f'return:{return_doc.pk}:line:{sale_line.pk}',
                    disposed=False,
                )
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

                StockMovement.objects.create(
                    tenant_id=tenant_id,
                    lot=lot,
                    movement_type=StockMovement.MovementType.RETURN,
                    quantity=qty,
                    to_location=sale.location,
                    reference_type='return',
                    reference_id=return_doc.pk,
                )
                total_restock_cogs += line_loss

            else:  # DISPOSE
                record_sale_line_return_realization(
                    sale_line=sale_line,
                    quantity=qty,
                    source_ref=f'return:{return_doc.pk}:line:{sale_line.pk}',
                    disposed=True,
                )
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

        if total_restock_cogs > 0:
            create_journal_entry(
                tenant_id=tenant_id,
                operation_type='return',
                operation_id=return_doc.pk,
                lines=[
                    {
                        'account_code': '1100',
                        'debit': total_restock_cogs,
                        'credit': Decimal('0'),
                        'description': f'Return #{return_doc.pk} inventory restore',
                    },
                    {
                        'account_code': '5000',
                        'debit': Decimal('0'),
                        'credit': total_restock_cogs,
                        'description': f'Return #{return_doc.pk} COGS reversal',
                    },
                ],
                description=f'Sale return #{return_doc.pk} COGS reversal',
                date=date,
            )

        if refund_payments and total_refund > 0:
            if len(refund_payments) == 1 and refund_payments[0].get('amount') in (None, ''):
                refund_payments[0]['amount'] = total_refund
                refund_payments[0].setdefault('currency', 'UZS')
                refund_payments[0].setdefault('fx_rate', Decimal('1'))

            _validate_refund_currency_capacity(
                sale=sale,
                refund_payments=refund_payments,
            )
            functional_refund_total = money(sum(
                (
                    functional_amount_uzs(
                        amount=money(payment['amount']),
                        currency=str(payment.get('currency') or 'UZS').upper(),
                        fx_rate=resolve_fx_rate_snapshot(
                            tenant_id=tenant_id,
                            operation_currency=str(payment.get('currency') or 'UZS').upper(),
                            operation_at=date,
                            fx_rate_snapshot=payment.get('fx_rate'),
                        ),
                    )
                    for payment in refund_payments
                ),
                Decimal('0'),
            ))
            if functional_refund_total != money(total_refund):
                raise ValueError(
                    'Сумма возврата в UZS-эквиваленте не совпадает с суммой возвращаемых строк.'
                )
            for payment in refund_payments:
                _issue_return_refund(
                    sale=sale,
                    return_doc=return_doc,
                    tenant_id=tenant_id,
                    payment_payload=payment,
                    date=date,
                )

        _sync_sale_return_status(sale)

        publish_event(
            event_type='sale.returned',
            payload={
                'sale_id': sale.pk,
                'return_id': return_doc.pk,
                'resolution': resolution,
                'reason': reason,
                'lines_count': len(return_lines),
                'refund_amount': str(total_refund),
                'refund_issued': bool(refund_payments and total_refund > 0),
                'restock_cogs': str(total_restock_cogs),
                'loss_amount': str(total_loss),
                'date': date.isoformat(),
            },
            tenant_id=tenant_id,
        )

    return return_doc


def open_pos_session(
    tenant_id: int,
    location_id: int,
    opened_by_id: int,
    opening_cash: Decimal = Decimal('0'),
    opening_cash_by_currency: dict | None = None,
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
        opening_cash_by_currency=_currency_map(
            opening_cash_by_currency,
            fallback_uzs=opening_cash,
        ),
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
    actual_cash_by_currency: dict | None = None,
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

        # Calculate expected cash from incoming cash payments minus cash refunds.
        cash_payments = SalePayment.objects.filter(
            sale__pos_session=session,
            sale__status__in=SALE_ACCOUNTING_STATUSES,
            method=SalePayment.Method.CASH,
        )
        cash_sales_by_currency: dict[str, Decimal] = {}
        for payment in cash_payments:
            currency = str(payment.currency or 'UZS').upper()
            signed_amount = Decimal(str(payment.amount))
            if payment.role == SalePayment.Role.REFUND:
                signed_amount *= Decimal('-1')
            cash_sales_by_currency[currency] = (
                cash_sales_by_currency.get(currency, Decimal('0'))
                + signed_amount
            )

        opening_by_currency = _currency_map(
            session.opening_cash_by_currency or None,
            fallback_uzs=session.opening_cash,
        )
        expected_by_currency = _sum_currency_maps(opening_by_currency, cash_sales_by_currency)
        actual_by_currency = _currency_map(actual_cash_by_currency, fallback_uzs=actual_cash)
        difference_by_currency = _diff_currency_maps(actual_by_currency, expected_by_currency)

        expected_cash = Decimal(str(expected_by_currency.get('UZS', '0')))

        session.expected_cash = expected_cash
        session.actual_cash = Decimal(str(actual_by_currency.get('UZS', actual_cash)))
        session.cash_difference = Decimal(str(difference_by_currency.get('UZS', '0')))
        session.expected_cash_by_currency = expected_by_currency
        session.actual_cash_by_currency = actual_by_currency
        session.cash_difference_by_currency = difference_by_currency
        session.closed_by_id = closed_by_id
        session.closed_at = timezone.now()
        session.status = PosSession.SessionStatus.CLOSED
        session.save()

        # Log mismatch as risk event
        if any(Decimal(str(amount)) != 0 for amount in difference_by_currency.values()):
            from apps.risk.models import RiskEvent
            impact = sum(
                abs(Decimal(str(amount)))
                for amount in difference_by_currency.values()
            )
            RiskEvent.objects.create(
                tenant_id=session.tenant_id,
                event_type=RiskEvent.EventType.CASH_MISMATCH,
                quantity=0,
                monetary_impact=impact,
                responsible_user_id=closed_by_id,
                reason=(
                    'Cash mismatch at session close: '
                    f'expected {expected_by_currency}, actual {actual_by_currency}'
                ),
            )

        publish_event(
            event_type='pos_session.closed',
            payload={
                'session_id': session.pk,
                'location_id': session.location_id,
                'closed_by_id': closed_by_id,
                'expected_cash': str(expected_cash),
                'actual_cash': str(session.actual_cash),
                'cash_difference': str(session.cash_difference),
                'expected_cash_by_currency': expected_by_currency,
                'actual_cash_by_currency': actual_by_currency,
                'cash_difference_by_currency': difference_by_currency,
                'closed_at': session.closed_at.isoformat() if session.closed_at else None,
            },
            tenant_id=session.tenant_id,
        )

    return session
