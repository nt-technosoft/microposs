"""Procurement venture realization and position helpers.

E16 treats each partnership procurement as an economic venture. Sale lines create
realization events; final entitlement is later determined by venture settlement.
"""

from decimal import Decimal

from django.db import models, transaction
from django.db.models import Sum

from .formulas import (
    calculate_sale_realization_distribution,
    distribute_loss_by_capital_from_snapshot,
    profit_shares_from_capital,
)
from .models import (
    AgreementWithdrawal,
    PartnerLedgerEntry,
    Procurement,
    ProcurementReceiveBatch,
    ProcurementSaleRealization,
    ProcurementVentureSettlement,
)

_ZERO = Decimal('0')
_CENTS = Decimal('0.01')
_RATIO = Decimal('0.000001')


def _money(value) -> Decimal:
    return Decimal(str(value or '0')).quantize(_CENTS)


def _ratio(value) -> Decimal:
    return Decimal(str(value or '0')).quantize(_RATIO)


def _native_amount_from_uzs(amount_uzs: Decimal, currency: str, fx_rate) -> Decimal:
    currency = str(currency or 'UZS').upper()
    amount = _money(amount_uzs)
    if currency == 'UZS':
        return amount
    rate = Decimal(str(fx_rate or '1'))
    if rate <= 0:
        return Decimal('0.00')
    return (amount / rate).quantize(_CENTS)


def _resolve_cost_fx_for_sale_line(*, sale_line, cost_currency: str, sale_currency: str, sale_fx: Decimal) -> Decimal:
    cost_currency = str(cost_currency or 'UZS').upper()
    sale_currency = str(sale_currency or 'UZS').upper()
    if cost_currency == 'UZS':
        return Decimal('1')
    if cost_currency == sale_currency:
        return sale_fx

    from apps.finance.fx_rates import resolve_fx_rate_snapshot

    return resolve_fx_rate_snapshot(
        tenant_id=sale_line.tenant_id,
        operation_currency=cost_currency,
        operation_at=getattr(getattr(sale_line, 'sale', None), 'date', None),
    )


def _native_landed_cost_amount(*, sale_line, cost_currency: str, historical_cost_uzs: Decimal) -> Decimal:
    cost_currency = str(cost_currency or 'UZS').upper()
    if cost_currency == 'UZS':
        return _money(historical_cost_uzs)

    item = getattr(sale_line.lot, 'procurement_item', None)
    buy_fx = Decimal(str(getattr(item, 'fx_rate', Decimal('0')) or '0'))
    if buy_fx > 0:
        return (historical_cost_uzs / buy_fx).quantize(_CENTS)
    return _native_amount_from_uzs(historical_cost_uzs, cost_currency, Decimal('1'))


def _sale_line_money(sale_line) -> dict[str, Decimal | str]:
    sale_currency = str(getattr(sale_line, 'operation_currency', 'UZS') or 'UZS').upper()
    sale_fx = Decimal(str(getattr(sale_line, 'fx_rate_snapshot', Decimal('1')) or '1'))
    sale_amount = _money(
        Decimal(str(getattr(sale_line, 'operation_unit_price', None) or sale_line.unit_price))
        * Decimal(str(sale_line.quantity)),
    )
    sale_uzs = _money(Decimal(str(sale_line.unit_price)) * Decimal(str(sale_line.quantity)))

    item = getattr(sale_line.lot, 'procurement_item', None)
    cost_currency = str(getattr(item, 'currency', None) or sale_currency or 'UZS').upper()
    # Cross-currency capital preservation uses an explicit sale-time FX
    # snapshot for the cost currency. Historical buy FX remains visible via
    # cost_basis_uzs and fx_gain_loss_uzs captures the measurement drift.
    cost_fx = _resolve_cost_fx_for_sale_line(
        sale_line=sale_line,
        cost_currency=cost_currency,
        sale_currency=sale_currency,
        sale_fx=sale_fx,
    )
    cost_uzs = _money(Decimal(str(sale_line.unit_landed_cost)) * Decimal(str(sale_line.quantity)))
    cost_amount = _native_landed_cost_amount(
        sale_line=sale_line,
        cost_currency=cost_currency,
        historical_cost_uzs=cost_uzs,
    )
    cost_at_sale_uzs = _money(cost_amount * cost_fx) if cost_currency != 'UZS' else cost_uzs

    return {
        'sale_currency': sale_currency,
        'sale_amount': sale_amount,
        'sale_fx': sale_fx,
        'sale_uzs': sale_uzs,
        'cost_currency': cost_currency,
        'cost_amount': cost_amount,
        'cost_fx': cost_fx,
        'cost_uzs': cost_uzs,
        'cost_at_sale_uzs': cost_at_sale_uzs,
        'fx_gain_loss_uzs': _money(cost_at_sale_uzs - cost_uzs),
    }


def _partner_meta_by_id(snapshot: dict | None) -> dict[int, dict]:
    snapshot = snapshot or {}
    partners = list(snapshot.get('partners') or [])
    if not partners:
        return {}

    fallback_profit_shares = (
        {}
        if all('profit_share' in partner for partner in partners)
        else profit_shares_from_capital(partners, Decimal(str(snapshot.get('mudaraba_ratio', '0'))))
    )
    result: dict[int, dict] = {}
    for partner in partners:
        partner_id = partner.get('partner_id')
        if partner_id is None:
            continue
        pid = int(partner_id)
        result[pid] = {
            'role': str(partner.get('role') or ''),
            'capital_share': _ratio(partner.get('capital_share', '0')),
            'profit_share': _ratio(partner.get('profit_share', fallback_profit_shares.get(pid, _ZERO))),
        }
    return result


def _profile_key_from_rows(rows) -> tuple:
    return tuple(
        sorted(
            (
                row.partner_id,
                str(_ratio(row.capital_share)),
                str(_ratio(row.profit_share)),
                str(row.role or ''),
            )
            for row in rows
        )
    )


def _net_profit_entitlements(procurement: Procurement) -> dict[int, Decimal]:
    """Net realized P&L by immutable share profile, then split net.

    This is the core sharia/venture rule: profitable and losing sale slices from
    the same ownership snapshot are netted first. Only positive net P&L is split
    by profit shares. Negative net remains capital loss by capital shares.
    """

    profiles: dict[tuple, Decimal] = {}
    profile_rows: dict[tuple, list[ProcurementSaleRealization]] = {}
    for rows in _realization_groups(procurement).values():
        if rows[0].event_type == ProcurementSaleRealization.EventType.LOSS and rows[0].is_partner_liability:
            continue
        profile_source = _group_profile_source(rows)
        profile_key = _profile_key_from_rows(profile_source)
        if not profile_key:
            continue
        first = rows[0]
        sign = Decimal('-1') if first.event_type == ProcurementSaleRealization.EventType.REVERSAL else Decimal('1')
        if first.event_type == ProcurementSaleRealization.EventType.LOSS:
            net = -_money(first.cost_basis_uzs)
        else:
            net = _money(first.sale_proceeds_uzs - first.cost_basis_at_sale_uzs)
        group_impact = sign * net
        if first.event_type == ProcurementSaleRealization.EventType.REVERSAL:
            group_impact -= _money(sum((row.loss_uzs for row in rows), _ZERO))
        profiles[profile_key] = profiles.get(profile_key, _ZERO) + group_impact
        profile_rows.setdefault(profile_key, profile_source)

    entitlements: dict[int, Decimal] = {}
    for profile_key, net in profiles.items():
        if net <= 0:
            continue
        rows = profile_rows.get(profile_key, [])
        distributed = _ZERO
        operator_id = None
        for row in rows:
            if row.role == 'OPERATOR':
                operator_id = row.partner_id
            amount = _money(net * Decimal(str(row.profit_share)))
            entitlements[row.partner_id] = entitlements.get(row.partner_id, _ZERO) + amount
            distributed += amount
        residue = _money(net - distributed)
        if residue and operator_id is not None:
            entitlements[operator_id] = entitlements.get(operator_id, _ZERO) + residue
    return entitlements


def _realization_groups(procurement: Procurement) -> dict[tuple, list[ProcurementSaleRealization]]:
    events = (
        ProcurementSaleRealization.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement)
        .select_related('partner')
        .order_by('sale_line_id', 'source_ref', 'id')
    )
    grouped: dict[tuple, list[ProcurementSaleRealization]] = {}
    for event in events:
        if event.event_type == ProcurementSaleRealization.EventType.LOSS:
            source = ('loss', event.source_ref or event.id)
        else:
            source = ('sale', event.sale_line_id, event.source_ref or '')
        grouped.setdefault(source, []).append(event)
    return grouped


def _group_profile_source(rows: list[ProcurementSaleRealization]) -> list[ProcurementSaleRealization]:
    return [row for row in rows if row.event_type != ProcurementSaleRealization.EventType.REVERSAL] or rows


def _net_capital_loss_entitlements(procurement: Procurement) -> dict[int, dict[str, Decimal]]:
    """Settlement capital/loss true-up by share profile.

    Interim recovered capital stays conservative and per-sale. Once a
    constructive/final settlement exists, ordinary sale gains and losses are
    netted symmetrically: recovered capital = min(net proceeds, net cost), and
    only the remaining negative net becomes capital loss. Partner-liability
    losses are excluded because they are a receivable from the responsible
    partner, not venture market loss.
    """

    profile_totals: dict[tuple, dict[str, Decimal]] = {}
    profile_rows: dict[tuple, list[ProcurementSaleRealization]] = {}

    for rows in _realization_groups(procurement).values():
        if not rows:
            continue
        if rows[0].event_type == ProcurementSaleRealization.EventType.LOSS and rows[0].is_partner_liability:
            continue

        profile_source = _group_profile_source(rows)
        profile_key = _profile_key_from_rows(profile_source)
        if not profile_key:
            continue

        first = rows[0]
        total_loss = _money(sum((row.loss_uzs for row in rows), _ZERO))
        if first.event_type == ProcurementSaleRealization.EventType.LOSS:
            proceeds = _ZERO
            cost = _money(first.cost_basis_uzs)
        elif first.event_type == ProcurementSaleRealization.EventType.REVERSAL:
            proceeds = -_money(first.sale_proceeds_uzs)
            cost = -_money(first.cost_basis_at_sale_uzs) + total_loss
        else:
            proceeds = _money(first.sale_proceeds_uzs)
            cost = _money(first.cost_basis_at_sale_uzs)

        totals = profile_totals.setdefault(profile_key, {'proceeds': _ZERO, 'cost': _ZERO})
        totals['proceeds'] += proceeds
        totals['cost'] += cost
        profile_rows.setdefault(profile_key, profile_source)

    entitlements: dict[int, dict[str, Decimal]] = {}
    for profile_key, totals in profile_totals.items():
        recovered_total = max(_ZERO, min(_money(totals['proceeds']), _money(totals['cost'])))
        loss_total = max(_ZERO, _money(totals['cost'] - totals['proceeds']))
        rows = profile_rows.get(profile_key, [])
        recovered_distributed = _ZERO
        loss_distributed = _ZERO
        operator_id = None
        for row in rows:
            if row.role == 'OPERATOR':
                operator_id = row.partner_id
            partner_row = entitlements.setdefault(row.partner_id, {
                'capital_recovered_uzs': _ZERO,
                'loss_uzs': _ZERO,
            })
            recovered = _money(recovered_total * Decimal(str(row.capital_share)))
            loss = _money(loss_total * Decimal(str(row.capital_share)))
            partner_row['capital_recovered_uzs'] += recovered
            partner_row['loss_uzs'] += loss
            recovered_distributed += recovered
            loss_distributed += loss

        if operator_id is not None:
            recovered_residue = _money(recovered_total - recovered_distributed)
            loss_residue = _money(loss_total - loss_distributed)
            operator_row = entitlements.setdefault(operator_id, {
                'capital_recovered_uzs': _ZERO,
                'loss_uzs': _ZERO,
            })
            operator_row['capital_recovered_uzs'] += recovered_residue
            operator_row['loss_uzs'] += loss_residue

    return entitlements


def _liability_capital_recovery_entitlements(procurement: Procurement) -> dict[int, Decimal]:
    """Capital restored to non-liable partners by partner-liability losses."""

    entitlements: dict[int, Decimal] = {}
    for rows in _realization_groups(procurement).values():
        if not rows:
            continue
        first = rows[0]
        if first.event_type != ProcurementSaleRealization.EventType.LOSS or not first.is_partner_liability:
            continue

        liable_partner_ids = {row.partner_id for row in rows}
        partner_meta = _partner_meta_by_id(getattr(first.lot, 'contract_snapshot', None))
        if not partner_meta:
            continue
        total_loss = _money(first.cost_basis_uzs)
        distributed = _ZERO
        operator_id = None

        for partner_id, meta in partner_meta.items():
            if meta.get('role') == 'OPERATOR':
                operator_id = partner_id
            if partner_id in liable_partner_ids:
                continue
            recovered = _money(total_loss * Decimal(str(meta.get('capital_share', _ZERO))))
            entitlements[partner_id] = _money(entitlements.get(partner_id, _ZERO) + recovered)
            distributed += recovered

        residue = _money(total_loss - distributed)
        if operator_id is not None and operator_id not in liable_partner_ids:
            entitlements[operator_id] = _money(entitlements.get(operator_id, _ZERO) + residue)

    return entitlements


def _remaining_inventory_capital_entitlements(procurement: Procurement) -> dict[int, Decimal]:
    """Historical capital still tied to physically unsold stock."""

    from apps.inventory.models import LotStock

    entitlements: dict[int, Decimal] = {}
    stocks = (
        LotStock.objects
        .filter(
            tenant_id=procurement.tenant_id,
            quantity_remaining__gt=0,
            lot__procurement_item__procurement=procurement,
            lot__reversed=False,
        )
        .select_related('lot')
    )
    for stock in stocks:
        lot = stock.lot
        meta = _partner_meta_by_id(getattr(lot, 'contract_snapshot', None))
        if not meta:
            continue
        stock_capital = _money(Decimal(str(lot.landed_cost_per_unit)) * Decimal(str(stock.quantity_remaining)))
        distributed = _ZERO
        operator_id = None
        for partner_id, values in meta.items():
            if values.get('role') == 'OPERATOR':
                operator_id = partner_id
            share_amount = _money(stock_capital * Decimal(str(values.get('capital_share', _ZERO))))
            entitlements[partner_id] = _money(entitlements.get(partner_id, _ZERO) + share_amount)
            distributed += share_amount

        if operator_id is not None:
            residue = _money(stock_capital - distributed)
            entitlements[operator_id] = _money(entitlements.get(operator_id, _ZERO) + residue)

    return entitlements


def record_sale_line_realization(*, sale_line) -> list[ProcurementSaleRealization]:
    """Create partner-level realization events for one partnership SaleLine.

    Idempotent by (sale_line, partner, REALIZATION). Non-partnership lots return
    an empty list.
    """

    lot = sale_line.lot
    procurement_item = getattr(lot, 'procurement_item', None)
    procurement = getattr(procurement_item, 'procurement', None)
    if procurement is None or procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        return []

    partner_meta = _partner_meta_by_id(getattr(lot, 'contract_snapshot', None))
    if not partner_meta:
        return []

    money = _sale_line_money(sale_line)
    sale_proceeds = _money(money['sale_uzs'])
    cost_basis = _money(money['cost_uzs'])
    cost_basis_at_sale = _money(money['cost_at_sale_uzs'])
    distribution = calculate_sale_realization_distribution(
        contract_snapshot=lot.contract_snapshot,
        sale_proceeds=sale_proceeds,
        cost_basis=cost_basis_at_sale,
    )
    if not distribution:
        return []

    created: list[ProcurementSaleRealization] = []
    with transaction.atomic():
        for partner_id_str, values in distribution.items():
            partner_id = int(partner_id_str)
            meta = partner_meta.get(partner_id)
            if meta is None:
                continue
            existing = ProcurementSaleRealization.objects.filter(
                sale_line=sale_line,
                partner_id=partner_id,
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
            ).first()
            if existing is not None:
                created.append(existing)
                continue
            created.append(ProcurementSaleRealization.objects.create(
                tenant_id=sale_line.tenant_id,
                procurement=procurement,
                sale_line=sale_line,
                lot=lot,
                partner_id=partner_id,
                role=meta['role'],
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
                quantity=Decimal(str(sale_line.quantity)).quantize(Decimal('0.001')),
                sale_proceeds_currency=money['sale_currency'],
                sale_proceeds_amount=money['sale_amount'],
                sale_fx_rate=money['sale_fx'],
                cost_basis_currency=money['cost_currency'],
                cost_basis_amount=money['cost_amount'],
                cost_fx_rate=money['cost_fx'],
                sale_proceeds_uzs=sale_proceeds,
                cost_basis_uzs=cost_basis,
                cost_basis_at_sale_uzs=cost_basis_at_sale,
                capital_share=meta['capital_share'],
                profit_share=meta['profit_share'],
                capital_recovered_currency=money['cost_currency'],
                capital_recovered_amount=_native_amount_from_uzs(
                    _money(values.get('capital_recovered', '0')),
                    str(money['cost_currency']),
                    money['cost_fx'],
                ),
                profit_currency=money['sale_currency'],
                profit_amount=_native_amount_from_uzs(
                    _money(values.get('provisional_profit', '0')),
                    str(money['sale_currency']),
                    money['sale_fx'],
                ),
                loss_currency=money['cost_currency'],
                loss_amount=_native_amount_from_uzs(
                    _money(values.get('loss', '0')),
                    str(money['cost_currency']),
                    money['cost_fx'],
                ),
                fx_gain_loss_uzs=_money(Decimal(str(money['fx_gain_loss_uzs'])) * meta['capital_share']),
                capital_recovered_uzs=_money(values.get('capital_recovered', '0')),
                provisional_profit_uzs=_money(values.get('provisional_profit', '0')),
                loss_uzs=_money(values.get('loss', '0')),
                source_ref=f'sale_line:{sale_line.pk}',
            ))
    return created


def record_sale_line_return_realization(
    *,
    sale_line,
    quantity: int,
    source_ref: str,
    disposed: bool = False,
) -> list[ProcurementSaleRealization]:
    """Append E16 reversal rows for returned sale quantity.

    RESTOCK reverses the sale realization proportionally. DISPOSE also records
    the damaged-return loss by capital share.
    """

    if quantity <= 0:
        return []
    lot = sale_line.lot
    procurement_item = getattr(lot, 'procurement_item', None)
    procurement = getattr(procurement_item, 'procurement', None)
    if procurement is None or procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        return []
    qty_ratio = Decimal(str(quantity)) / Decimal(str(sale_line.quantity))
    partner_meta = _partner_meta_by_id(getattr(lot, 'contract_snapshot', None))
    if not partner_meta:
        return []

    loss_distribution = {}
    if disposed:
        money = _sale_line_money(sale_line)
        loss_distribution = distribute_loss_by_capital_from_snapshot(
            contract_snapshot=lot.contract_snapshot,
            loss_amount=_money(Decimal(str(money['cost_at_sale_uzs'])) * qty_ratio),
        )

    originals = ProcurementSaleRealization.objects.filter(
        sale_line=sale_line,
        event_type=ProcurementSaleRealization.EventType.REALIZATION,
    )
    created: list[ProcurementSaleRealization] = []
    with transaction.atomic():
        for original in originals:
            meta = partner_meta.get(original.partner_id)
            if meta is None:
                continue
            existing = ProcurementSaleRealization.objects.filter(
                tenant_id=sale_line.tenant_id,
                sale_line=sale_line,
                partner_id=original.partner_id,
                event_type=ProcurementSaleRealization.EventType.REVERSAL,
                source_ref=source_ref,
                reversal_of=original,
            ).first()
            if existing is not None:
                created.append(existing)
                continue
            money = _sale_line_money(sale_line)
            created.append(ProcurementSaleRealization.objects.create(
                tenant_id=sale_line.tenant_id,
                procurement=procurement,
                sale_line=sale_line,
                lot=lot,
                partner_id=original.partner_id,
                role=meta['role'],
                event_type=ProcurementSaleRealization.EventType.REVERSAL,
                quantity=Decimal(str(quantity)).quantize(Decimal('0.001')),
                sale_proceeds_currency=money['sale_currency'],
                sale_proceeds_amount=_money(Decimal(str(money['sale_amount'])) * qty_ratio),
                sale_fx_rate=money['sale_fx'],
                cost_basis_currency=money['cost_currency'],
                cost_basis_amount=_money(Decimal(str(money['cost_amount'])) * qty_ratio),
                cost_fx_rate=money['cost_fx'],
                sale_proceeds_uzs=_money(Decimal(str(sale_line.unit_price)) * Decimal(str(quantity))),
                cost_basis_uzs=_money(Decimal(str(sale_line.unit_landed_cost)) * Decimal(str(quantity))),
                cost_basis_at_sale_uzs=_money(Decimal(str(money['cost_at_sale_uzs'])) * qty_ratio),
                capital_share=meta['capital_share'],
                profit_share=meta['profit_share'],
                capital_recovered_currency=original.capital_recovered_currency,
                capital_recovered_amount=_money(original.capital_recovered_amount * qty_ratio),
                profit_currency=original.profit_currency,
                profit_amount=_money(original.profit_amount * qty_ratio),
                loss_currency=original.loss_currency,
                loss_amount=_native_amount_from_uzs(
                    _money(loss_distribution.get(str(original.partner_id), '0')),
                    original.loss_currency,
                    original.cost_fx_rate,
                ),
                fx_gain_loss_uzs=_money(original.fx_gain_loss_uzs * qty_ratio),
                capital_recovered_uzs=_money(original.capital_recovered_uzs * qty_ratio),
                provisional_profit_uzs=_money(original.provisional_profit_uzs * qty_ratio),
                loss_uzs=_money(loss_distribution.get(str(original.partner_id), '0')),
                source_ref=source_ref,
                reversal_of=original,
            ))
    return created


def record_lot_loss_realization(
    *,
    lot,
    quantity: int | Decimal,
    loss_distribution: dict[str, str | Decimal],
    source_ref: str,
    is_partner_liability: bool = False,
) -> list[ProcurementSaleRealization]:
    """Append E16 loss rows for stock lost without a sale.

    Used by generic writeoffs/stock losses. `loss_distribution` is supplied by
    the caller because negligence/business-liability policy belongs to risk.
    """

    quantity_dec = Decimal(str(quantity)).quantize(Decimal('0.001'))
    if quantity_dec <= 0:
        return []
    procurement_item = getattr(lot, 'procurement_item', None)
    procurement = getattr(procurement_item, 'procurement', None)
    if procurement is None or procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        return []
    partner_meta = _partner_meta_by_id(getattr(lot, 'contract_snapshot', None))
    if not partner_meta:
        return []

    item = getattr(lot, 'procurement_item', None)
    cost_currency = str(getattr(item, 'currency', None) or 'UZS').upper()
    cost_fx = Decimal(str(getattr(item, 'fx_rate', Decimal('1')) or '1')) if cost_currency != 'UZS' else Decimal('1')
    cost_basis = _money(Decimal(str(lot.landed_cost_per_unit)) * quantity_dec)
    cost_amount = _native_amount_from_uzs(cost_basis, cost_currency, cost_fx)
    created: list[ProcurementSaleRealization] = []
    with transaction.atomic():
        for partner_id_str, loss_amount in loss_distribution.items():
            partner_id = int(partner_id_str)
            loss = _money(loss_amount)
            if loss <= 0:
                continue
            meta = partner_meta.get(partner_id)
            if meta is None:
                continue
            existing = ProcurementSaleRealization.objects.filter(
                tenant_id=procurement.tenant_id,
                procurement=procurement,
                partner_id=partner_id,
                event_type=ProcurementSaleRealization.EventType.LOSS,
                source_ref=source_ref,
            ).first()
            if existing is not None:
                created.append(existing)
                continue
            created.append(ProcurementSaleRealization.objects.create(
                tenant_id=procurement.tenant_id,
                procurement=procurement,
                sale_line=None,
                lot=lot,
                partner_id=partner_id,
                role=meta['role'],
                event_type=ProcurementSaleRealization.EventType.LOSS,
                quantity=quantity_dec,
                sale_proceeds_currency='UZS',
                sale_proceeds_amount=_ZERO,
                sale_fx_rate=Decimal('1'),
                cost_basis_currency=cost_currency,
                cost_basis_amount=cost_amount,
                cost_fx_rate=cost_fx,
                sale_proceeds_uzs=_ZERO,
                cost_basis_uzs=cost_basis,
                cost_basis_at_sale_uzs=cost_basis,
                capital_share=meta['capital_share'],
                profit_share=meta['profit_share'],
                capital_recovered_currency='UZS',
                capital_recovered_amount=_ZERO,
                profit_currency='UZS',
                profit_amount=_ZERO,
                loss_currency=cost_currency,
                loss_amount=_native_amount_from_uzs(loss, cost_currency, cost_fx),
                fx_gain_loss_uzs=_ZERO,
                is_partner_liability=is_partner_liability,
                capital_recovered_uzs=_ZERO,
                provisional_profit_uzs=_ZERO,
                loss_uzs=loss,
                source_ref=source_ref,
            ))
    return created


def procurement_venture_positions(
    *,
    procurement: Procurement,
    include_settlement_profit: bool = False,
) -> dict[int, dict[str, Decimal]]:
    """Aggregate current E16 venture buckets by partner in functional UZS."""

    batches = (
        ProcurementReceiveBatch.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement, is_reversal=False)
        .exclude(reversal_batches__isnull=False)
        .prefetch_related('capital_allocations')
    )
    positions: dict[int, dict[str, Decimal]] = {}

    def row(partner_id: int) -> dict[str, Decimal]:
        return positions.setdefault(partner_id, {
            'deployed_uzs': _ZERO,
            'capital_recovered_uzs': _ZERO,
            'provisional_profit_uzs': _ZERO,
            'loss_uzs': _ZERO,
            'partner_liability_loss_uzs': _ZERO,
            'capital_returned_uzs': _ZERO,
            'dividends_paid_uzs': _ZERO,
            'remaining_inventory_capital_uzs': _ZERO,
            'liability_capital_recovered_uzs': _ZERO,
            'capital_return_available_uzs': _ZERO,
            'provisional_profit_available_uzs': _ZERO,
            'negative_position_uzs': _ZERO,
        })

    for batch in batches:
        required_uzs = _money(batch.total_inventory_uzs)
        for allocation in batch.capital_allocations.all():
            row(allocation.partner_id)['deployed_uzs'] += _money(
                required_uzs * Decimal(str(allocation.capital_share)),
            )

    realization_rows = (
        ProcurementSaleRealization.objects
        .filter(
            tenant_id=procurement.tenant_id,
            procurement=procurement,
        )
        .values('partner_id', 'event_type')
        .annotate(
            capital_recovered=Sum('capital_recovered_uzs'),
            provisional_profit=Sum('provisional_profit_uzs'),
            loss=Sum('loss_uzs'),
            liability_loss=Sum('loss_uzs', filter=models.Q(is_partner_liability=True)),
        )
    )
    for item in realization_rows:
        r = row(item['partner_id'])
        if item['event_type'] == ProcurementSaleRealization.EventType.REVERSAL:
            r['capital_recovered_uzs'] -= _money(item['capital_recovered'])
            r['provisional_profit_uzs'] -= _money(item['provisional_profit'])
            r['loss_uzs'] += _money(item['loss'])
        elif item['event_type'] == ProcurementSaleRealization.EventType.LOSS:
            liability_loss = _money(item.get('liability_loss'))
            r['partner_liability_loss_uzs'] += liability_loss
            r['negative_position_uzs'] += liability_loss
            r['loss_uzs'] += _money(item['loss'])
        else:
            r['capital_recovered_uzs'] += _money(item['capital_recovered'])
            r['provisional_profit_uzs'] += _money(item['provisional_profit'])
            r['loss_uzs'] += _money(item['loss'])

    for r in positions.values():
        r['provisional_profit_uzs'] = _ZERO
    net_profit_entitlements = _net_profit_entitlements(procurement)
    for partner_id, amount in net_profit_entitlements.items():
        row(partner_id)['provisional_profit_uzs'] = _money(amount)

    ledger_rows = (
        PartnerLedgerEntry.objects
        .filter(tenant_id=procurement.tenant_id, ledger__procurement=procurement)
        .values('ledger__partner_id', 'entry_type')
        .annotate(total=Sum('functional_amount_uzs'))
    )
    for item in ledger_rows:
        r = row(item['ledger__partner_id'])
        total = _money(item['total'])
        if item['entry_type'] == PartnerLedgerEntry.EntryType.CAPITAL_OUT:
            r['capital_returned_uzs'] += total
        elif item['entry_type'] == PartnerLedgerEntry.EntryType.DIVIDEND_PAID:
            r['dividends_paid_uzs'] += total

    withdrawals = AgreementWithdrawal.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
    )
    for withdrawal in withdrawals:
        row(withdrawal.partner_id)['capital_returned_uzs'] += _money(
            Decimal(str(withdrawal.amount)) * Decimal(str(withdrawal.fx_rate or 1)),
        )

    has_settlement = include_settlement_profit or procurement.venture_settlements.exists()
    if has_settlement:
        net_capital_loss = _net_capital_loss_entitlements(procurement)
        for r in positions.values():
            r['capital_recovered_uzs'] = _ZERO
            r['loss_uzs'] = _money(r['partner_liability_loss_uzs'])
        for partner_id, values in net_capital_loss.items():
            partner_row = row(partner_id)
            partner_row['capital_recovered_uzs'] += _money(values.get('capital_recovered_uzs'))
            partner_row['loss_uzs'] += _money(values.get('loss_uzs'))

        for partner_id, amount in _liability_capital_recovery_entitlements(procurement).items():
            partner_row = row(partner_id)
            recovered = _money(amount)
            partner_row['liability_capital_recovered_uzs'] += recovered
            partner_row['capital_recovered_uzs'] += recovered

    remaining_capital = _remaining_inventory_capital_entitlements(procurement)
    for r in positions.values():
        r['remaining_inventory_capital_uzs'] = _ZERO
    for partner_id, amount in remaining_capital.items():
        row(partner_id)['remaining_inventory_capital_uzs'] = _money(amount)

    for r in positions.values():
        capital_delta = _money(r['capital_recovered_uzs'] - r['capital_returned_uzs'])
        r['capital_return_available_uzs'] = max(_ZERO, capital_delta)
        profit_delta = _money(r['provisional_profit_uzs'] - r['dividends_paid_uzs'])
        r['provisional_profit_available_uzs'] = max(_ZERO, profit_delta) if has_settlement else _ZERO
        r['negative_position_uzs'] += max(_ZERO, -capital_delta) + max(_ZERO, -profit_delta)

    return positions


def _json_money_map(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(_money(value)) for key, value in values.items()}


def venture_blocking_reasons(*, procurement: Procurement) -> list[str]:
    """Reasons why the procurement venture should not be closed yet."""

    from apps.inventory.models import Lot

    reasons: list[str] = []
    if Lot.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement_item__procurement=procurement,
        is_active=True,
        reversed=False,
    ).exists():
        reasons.append('По этому приходу ещё есть нераспроданный товар.')
    positions = procurement_venture_positions(procurement=procurement)
    if any(_money(row.get('negative_position_uzs', _ZERO)) > _ZERO for row in positions.values()):
        reasons.append('Есть отрицательные позиции партнёров.')
    return reasons


def create_venture_settlement(
    *,
    tenant_id: int,
    procurement_id: int,
    settlement_type: str,
    settled_at=None,
    inventory_value_uzs=Decimal('0'),
    reserve_uzs=Decimal('0'),
    notes: str = '',
    client_request_id=None,
) -> ProcurementVentureSettlement:
    """Create an immutable constructive/final settlement snapshot."""

    from django.utils import timezone
    from apps.inventory.models import Lot

    settlement_type = str(settlement_type).upper()
    if settled_at is None:
        settled_at = timezone.now()
    with transaction.atomic():
        if client_request_id:
            existing = ProcurementVentureSettlement.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing

        procurement = Procurement.objects.select_for_update().get(pk=procurement_id, tenant_id=tenant_id)
        if settlement_type == ProcurementVentureSettlement.SettlementType.FINAL:
            has_active_lots = Lot.objects.filter(
                tenant_id=tenant_id,
                procurement_item__procurement=procurement,
                is_active=True,
                reversed=False,
            ).exists()
            if has_active_lots:
                raise ValueError('Final venture settlement requires all procurement stock to be sold or reversed.')
        elif settlement_type != ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE:
            raise ValueError(f'Unknown venture settlement type: {settlement_type}.')

        positions = procurement_venture_positions(procurement=procurement, include_settlement_profit=True)
        serialized_positions: dict[str, dict[str, str]] = {}
        totals: dict[str, Decimal] = {}
        for partner_id, row in positions.items():
            serialized_positions[str(partner_id)] = _json_money_map(row)
            for key, value in row.items():
                totals[key] = totals.get(key, _ZERO) + Decimal(str(value))

        totals['inventory_value_uzs'] = _money(inventory_value_uzs)
        totals['reserve_uzs'] = _money(reserve_uzs)

        return ProcurementVentureSettlement.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            settlement_type=settlement_type,
            settled_at=settled_at,
            inventory_value_uzs=_money(inventory_value_uzs),
            reserve_uzs=_money(reserve_uzs),
            totals=_json_money_map(totals),
            partner_positions=serialized_positions,
            notes=notes,
            client_request_id=client_request_id,
        )
