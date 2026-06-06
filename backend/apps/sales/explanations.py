"""Read models for sale-level audit and explainability."""

from decimal import Decimal

from apps.core.models import Partner
from apps.customers.models import ReceivableEntry
from apps.finance.models import CashEntry, JournalEntry
from apps.partnerships.models import ProcurementSaleRealization
from apps.sales.currency import payment_functional_amount_uzs


_ZERO = Decimal('0.00')


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal('0.00')
    return ((numerator / denominator) * Decimal('100')).quantize(Decimal('0.01'))


def _contract_partner_meta(line) -> dict[str, dict]:
    contract_snapshot = line.lot.contract_snapshot or {}
    return {
        str(item.get('partner_id')): {
            'partner_id': item.get('partner_id'),
            'role': item.get('role'),
            'capital_share': item.get('capital_share'),
            'profit_share': item.get('profit_share'),
        }
        for item in contract_snapshot.get('partners', []) or []
        if item.get('partner_id') is not None
    }


def _line_partner_split(line, partners_by_id: dict[int, Partner], realization_rows: list) -> list[dict]:
    """E17 T-1.4: per-partner split from venture realization events (single
    source of truth), net of any reversals. Shows recovered capital, provisional
    profit and loss — not the legacy per-line gross-profit-by-profit-share."""
    gross_profit = _money(line.gross_profit)
    partner_meta = _contract_partner_meta(line)

    agg: dict[int, dict] = {}
    for event in realization_rows:
        sign = (
            Decimal('-1')
            if event.event_type == ProcurementSaleRealization.EventType.REVERSAL
            else Decimal('1')
        )
        bucket = agg.setdefault(event.partner_id, {
            'role': event.role,
            'capital_recovered': _ZERO,
            'provisional_profit': _ZERO,
            'loss': _ZERO,
        })
        bucket['capital_recovered'] += sign * _money(event.capital_recovered_uzs)
        bucket['provisional_profit'] += sign * _money(event.provisional_profit_uzs)
        bucket['loss'] += _money(event.loss_uzs)

    rows: list[dict] = []
    for partner_id, values in agg.items():
        meta = partner_meta.get(str(partner_id), {})
        partner = partners_by_id.get(partner_id)
        rows.append({
            'partner_id': partner_id,
            'partner_name': partner.display_name if partner is not None else f'Партнёр #{partner_id}',
            'role': meta.get('role') or values['role'] or (partner.role if partner is not None else 'UNKNOWN'),
            'capital_share': str(meta.get('capital_share')) if meta.get('capital_share') is not None else None,
            'profit_share': str(meta.get('profit_share')) if meta.get('profit_share') is not None else None,
            'capital_recovered': str(_money(values['capital_recovered'])),
            'provisional_profit': str(_money(values['provisional_profit'])),
            'loss': str(_money(values['loss'])),
            'profit_amount': str(_money(values['provisional_profit'])),
        })

    if not rows and gross_profit != _ZERO:
        rows.append({
            'partner_id': None,
            'partner_name': 'Бизнес',
            'role': 'OPERATOR',
            'capital_share': None,
            'profit_share': None,
            'capital_recovered': str(_ZERO),
            'provisional_profit': str(gross_profit),
            'loss': str(_ZERO),
            'profit_amount': str(gross_profit),
        })

    return sorted(rows, key=lambda item: (item['role'] != 'INVESTOR', item['partner_name']))


def build_sale_explanation(*, sale, tenant_id: int) -> dict:
    payments = sorted(
        [payment for payment in sale.payments.all() if payment.role == payment.Role.INCOMING],
        key=lambda payment: (payment.date, payment.id),
    )
    lines = sorted(list(sale.lines.all()), key=lambda line: line.id)

    partner_ids: set[int] = set()
    for line in lines:
        for partner_id_str in (line.profit_distribution_snapshot or {}).keys():
            try:
                partner_ids.add(int(partner_id_str))
            except (TypeError, ValueError):
                continue
        for partner_meta in (line.lot.contract_snapshot or {}).get('partners', []) or []:
            try:
                partner_ids.add(int(partner_meta.get('partner_id')))
            except (TypeError, ValueError):
                continue

    partners_by_id = {
        partner.id: partner
        for partner in Partner.objects.filter(
            tenant_id=tenant_id,
            id__in=partner_ids,
        )
    }

    payment_ids = [payment.id for payment in payments]
    payment_by_id = {payment.id: payment for payment in payments}

    cash_entries = list(
        CashEntry.objects.filter(
            tenant_id=tenant_id,
            source_ref_type='sale_payment',
            source_ref_id__in=payment_ids,
        )
        .select_related('account')
        .order_by('date', 'id')
    ) if payment_ids else []

    receivable_entries = list(
        ReceivableEntry.objects.filter(
            tenant_id=tenant_id,
            source_ref=f'sale:{sale.id}',
        ).order_by('date', 'id')
    )

    journal_entries = list(
        JournalEntry.objects.filter(
            tenant_id=tenant_id,
            operation_type=JournalEntry.OperationType.SALE,
            operation_id=sale.id,
        )
        .prefetch_related('lines__account')
        .order_by('date', 'id')
    )

    line_ids = [line.id for line in lines]
    realization_entries = list(
        ProcurementSaleRealization.objects.filter(
            tenant_id=tenant_id,
            sale_line_id__in=line_ids,
        )
        .select_related('partner', 'procurement')
        .order_by('created_at', 'id')
    ) if line_ids else []
    realizations_by_line: dict[int, list] = {}
    for event in realization_entries:
        realizations_by_line.setdefault(event.sale_line_id, []).append(event)

    sale_payment_methods: list[str] = []
    paid_total = _ZERO
    credit_total = _ZERO
    for payment in payments:
        paid_total += payment_functional_amount_uzs(payment)
        if payment.method not in sale_payment_methods:
            sale_payment_methods.append(payment.method)
        if payment.method == payment.Method.CREDIT:
            credit_total += payment_functional_amount_uzs(payment)

    investor_profit = _ZERO
    business_profit = _ZERO
    line_rows: list[dict] = []
    for line in lines:
        revenue = _money(line.total)
        purchase_cost = _money(line.unit_purchase_price * line.quantity)
        landed_cost = _money(line.total_cogs)
        gross_profit = _money(line.gross_profit)
        margin_percent = _percent(gross_profit, revenue)
        lot = line.lot
        procurement = getattr(getattr(lot, 'procurement_item', None), 'procurement', None)
        partner_split = _line_partner_split(
            line, partners_by_id, realizations_by_line.get(line.id, []),
        )
        line_investor_profit = sum(
            (
                _money(item['profit_amount'])
                for item in partner_split
                if item['role'] == 'INVESTOR'
            ),
            _ZERO,
        )
        line_business_profit = gross_profit - line_investor_profit
        investor_profit += line_investor_profit
        business_profit += line_business_profit

        line_rows.append({
            'sale_line_id': line.id,
            'product_name': str(line.product_variant),
            'quantity': line.quantity,
            'unit_price': str(_money(line.unit_price)),
            'operation_currency': line.operation_currency,
            'operation_unit_price': str(_money(line.operation_unit_price or line.unit_price)),
            'fx_rate_snapshot': str(line.fx_rate_snapshot),
            'revenue': str(revenue),
            'unit_purchase_price': str(_money(line.unit_purchase_price)),
            'purchase_cost': str(purchase_cost),
            'unit_landed_cost': str(_money(line.unit_landed_cost)),
            'landed_cost': str(landed_cost),
            'gross_profit': str(gross_profit),
            'margin_percent': str(margin_percent),
            'lot': {
                'id': lot.id,
                'received_at': lot.received_at,
                'quantity_initial': lot.quantity_initial,
                'quantity_remaining': sum(stock.quantity_remaining for stock in lot.stocks.all()),
                'unit_purchase_price': str(_money(lot.unit_purchase_price)),
                'landed_cost_per_unit': str(_money(lot.landed_cost_per_unit)),
            },
            'procurement': {
                'id': procurement.id,
                'funding_source': procurement.funding_source,
                'status': procurement.status,
                'opened_at': procurement.opened_at,
                'received_at': procurement.received_at,
                'supplier_name': getattr(procurement.supplier, 'name', None),
            } if procurement is not None else None,
            'partner_split': partner_split,
        })

    return {
        'sale': {
            'id': sale.id,
            'date': sale.date,
            'created_at': sale.created_at,
            'status': sale.status,
            'location_name': sale.location.name,
            'customer_name': getattr(sale.customer, 'name', None),
            'pos_session_id': sale.pos_session_id,
            'payment_methods': sale_payment_methods,
            'paid_total': str(_money(paid_total)),
            'credit_total': str(_money(credit_total)),
            'revenue': str(_money(sale.total_amount)),
            'landed_cost': str(_money(sale.total_cogs)),
            'gross_profit': str(_money(sale.total_amount - sale.total_cogs)),
            'investor_profit': str(_money(investor_profit)),
            'business_profit': str(_money(business_profit)),
            'margin_percent': str(_percent(_money(sale.total_amount - sale.total_cogs), _money(sale.total_amount))),
            'notes': sale.notes,
        },
        'payments': [
            {
                'id': payment.id,
                'date': payment.date,
                'method': payment.method,
                'amount': str(_money(payment.amount)),
                'currency': payment.currency,
                'fx_rate': str(payment.fx_rate),
                'functional_amount_uzs': str(payment_functional_amount_uzs(payment)),
                'account_id': payment.account_id,
            }
            for payment in payments
        ],
        'cash_entries': [
            {
                'id': entry.id,
                'date': entry.date,
                'payment_id': entry.source_ref_id,
                'payment_method': payment_by_id.get(entry.source_ref_id).method if entry.source_ref_id in payment_by_id else None,
                'account_name': entry.account.name,
                'currency': entry.account.currency,
                'direction': entry.direction,
                'amount': str(_money(entry.amount)),
            }
            for entry in cash_entries
        ],
        'receivable_entries': [
            {
                'id': entry.id,
                'date': entry.date,
                'entry_type': entry.entry_type,
                'amount': str(_money(entry.amount)),
                'currency': entry.currency,
                'fx_rate': str(entry.fx_rate),
                'source_ref': entry.source_ref,
            }
            for entry in receivable_entries
        ],
        'journal_entries': [
            {
                'id': journal.id,
                'date': journal.date,
                'description': journal.description,
                'total_debit': str(_money(sum(line.debit for line in journal.lines.all()))),
                'total_credit': str(_money(sum(line.credit for line in journal.lines.all()))),
                'lines': [
                    {
                        'id': line.id,
                        'account_code': line.account.code,
                        'account_name': line.account.name,
                        'debit': str(_money(line.debit)),
                        'credit': str(_money(line.credit)),
                        'description': line.description,
                    }
                    for line in journal.lines.all()
                ],
            }
            for journal in journal_entries
        ],
        'realization_entries': [
            {
                'id': event.id,
                'date': event.created_at,
                'event_type': event.event_type,
                'capital_recovered_uzs': str(_money(event.capital_recovered_uzs)),
                'provisional_profit_uzs': str(_money(event.provisional_profit_uzs)),
                'loss_uzs': str(_money(event.loss_uzs)),
                'is_partner_liability': event.is_partner_liability,
                'source_ref': event.source_ref,
                'partner_id': event.partner_id,
                'partner_name': event.partner.display_name if event.partner_id else None,
                'partner_role': event.role,
                'procurement_id': event.procurement_id,
            }
            for event in realization_entries
        ],
        'lines': line_rows,
    }
