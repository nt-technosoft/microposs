"""Procurement venture realization and position helpers.

E16 treats each partnership procurement as an economic venture. Sale lines create
realization events; final entitlement is later determined by venture settlement.
"""

from dataclasses import dataclass, field
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


def _net_profit_entitlements(procurement: Procurement, groups=None) -> dict[int, Decimal]:
    """Net realized P&L by immutable share profile, then split net.

    This is the core sharia/venture rule: profitable and losing sale slices from
    the same ownership snapshot are netted first. Only positive net P&L is split
    by profit shares. Negative net remains capital loss by capital shares.
    """

    if groups is None:
        groups = _realization_groups(procurement)
    profiles: dict[tuple, Decimal] = {}
    profile_rows: dict[tuple, list[ProcurementSaleRealization]] = {}
    for rows in groups.values():
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


def _realization_groups(procurement: Procurement, events=None) -> dict[tuple, list[ProcurementSaleRealization]]:
    if events is None:
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


def _net_capital_loss_entitlements(procurement: Procurement, groups=None) -> dict[int, dict[str, Decimal]]:
    """Settlement capital/loss true-up by share profile.

    Interim recovered capital stays conservative and per-sale. Once a
    constructive/final settlement exists, ordinary sale gains and losses are
    netted symmetrically: recovered capital = min(net proceeds, net cost), and
    only the remaining negative net becomes capital loss. Partner-liability
    losses are excluded because they are a receivable from the responsible
    partner, not venture market loss.
    """

    if groups is None:
        groups = _realization_groups(procurement)
    profile_totals: dict[tuple, dict[str, Decimal]] = {}
    profile_rows: dict[tuple, list[ProcurementSaleRealization]] = {}

    for rows in groups.values():
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


def _liability_capital_recovery_entitlements(procurement: Procurement, groups=None) -> dict[int, Decimal]:
    """Capital restored to non-liable partners by partner-liability losses."""

    if groups is None:
        groups = _realization_groups(procurement)
    entitlements: dict[int, Decimal] = {}
    for rows in groups.values():
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
            'profit_to_capital_uzs': _ZERO,
            'remaining_inventory_capital_uzs': _ZERO,
            'liability_capital_recovered_uzs': _ZERO,
            'capital_return_available_uzs': _ZERO,
            'provisional_profit_available_uzs': _ZERO,
            'negative_position_uzs': _ZERO,
            'negative_liability_uzs': _ZERO,
            'negative_capital_uzs': _ZERO,
            'negative_dividend_uzs': _ZERO,
            'debt_repaid_uzs': _ZERO,
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
            r['loss_uzs'] += _money(item['loss'])
        else:
            r['capital_recovered_uzs'] += _money(item['capital_recovered'])
            r['provisional_profit_uzs'] += _money(item['provisional_profit'])
            r['loss_uzs'] += _money(item['loss'])

    # E17 T-4.7: compute realization groups once and thread them into every
    # netting helper below, instead of re-querying per helper.
    groups = _realization_groups(procurement)
    for r in positions.values():
        r['provisional_profit_uzs'] = _ZERO
    net_profit_entitlements = _net_profit_entitlements(procurement, groups)
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
        elif item['entry_type'] == PartnerLedgerEntry.EntryType.PROFIT_TO_CAPITAL:
            r['profit_to_capital_uzs'] += total

    withdrawals = AgreementWithdrawal.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
    )
    for withdrawal in withdrawals:
        row(withdrawal.partner_id)['capital_returned_uzs'] += _money(
            Decimal(str(withdrawal.amount)) * Decimal(str(withdrawal.fx_rate or 1)),
        )

    # E17 T-5.3: partner venture-debt repayments (append-only), per component.
    from .models import ProcurementPartnerVentureDebtRepayment
    repaid_by_partner: dict[int, dict] = {
        rec['partner_id']: rec
        for rec in (
            ProcurementPartnerVentureDebtRepayment.objects
            .filter(tenant_id=procurement.tenant_id, procurement=procurement)
            .values('partner_id')
            .annotate(
                liability=Sum('repaid_liability_uzs'),
                capital=Sum('repaid_capital_uzs'),
                dividend=Sum('repaid_dividend_uzs'),
            )
        )
    }

    has_settlement = include_settlement_profit or procurement.venture_settlements.exists()
    if has_settlement:
        net_capital_loss = _net_capital_loss_entitlements(procurement, groups)
        for r in positions.values():
            r['capital_recovered_uzs'] = _ZERO
            r['loss_uzs'] = _money(r['partner_liability_loss_uzs'])
        for partner_id, values in net_capital_loss.items():
            partner_row = row(partner_id)
            partner_row['capital_recovered_uzs'] += _money(values.get('capital_recovered_uzs'))
            partner_row['loss_uzs'] += _money(values.get('loss_uzs'))

        for partner_id, amount in _liability_capital_recovery_entitlements(procurement, groups).items():
            partner_row = row(partner_id)
            recovered = _money(amount)
            partner_row['liability_capital_recovered_uzs'] += recovered
            partner_row['capital_recovered_uzs'] += recovered

    remaining_capital = _remaining_inventory_capital_entitlements(procurement)
    for r in positions.values():
        r['remaining_inventory_capital_uzs'] = _ZERO
    for partner_id, amount in remaining_capital.items():
        row(partner_id)['remaining_inventory_capital_uzs'] = _money(amount)

    for partner_id, r in positions.items():
        repaid = repaid_by_partner.get(partner_id, {})
        repaid_liability = _money(repaid.get('liability'))
        repaid_capital = _money(repaid.get('capital'))
        repaid_dividend = _money(repaid.get('dividend'))

        capital_delta = _money(r['capital_recovered_uzs'] - r['capital_returned_uzs'] + repaid_capital)
        r['capital_return_available_uzs'] = max(_ZERO, capital_delta)
        # E18 Phase 1: subtract profit_to_capital_uzs explicitly (separate bucket).
        profit_delta = _money(
            r['provisional_profit_uzs']
            - r['dividends_paid_uzs']
            - r['profit_to_capital_uzs']
            + repaid_dividend
        )
        r['provisional_profit_available_uzs'] = max(_ZERO, profit_delta) if has_settlement else _ZERO

        # E17 T-5.3: negative position is component-aware; repayments (waterfall)
        # reduce each component. Originals are never mutated.
        r['negative_liability_uzs'] = max(_ZERO, _money(r['partner_liability_loss_uzs'] - repaid_liability))
        r['negative_capital_uzs'] = max(_ZERO, -capital_delta)
        r['negative_dividend_uzs'] = max(_ZERO, -profit_delta)
        r['debt_repaid_uzs'] = _money(repaid_liability + repaid_capital + repaid_dividend)
        r['negative_position_uzs'] = _money(
            r['negative_liability_uzs'] + r['negative_capital_uzs'] + r['negative_dividend_uzs'],
        )

    return positions


def _json_money_map(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: str(_money(value)) for key, value in values.items()}


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
        assert_procurement_open(procurement)
        if settlement_type == ProcurementVentureSettlement.SettlementType.FINAL:
            if procurement_has_active_lots(procurement):
                raise ValueError('Final venture settlement requires all procurement stock to be sold or reversed.')
            # E17 T-4.5: safety lock — a FINAL settlement (the basis for close) is
            # forbidden while the conservation invariant does not net to zero in
            # every pocket and currency. We block and surface the residual; we do
            # not adjust the numbers to make it close.
            report = venture_conservation(procurement=procurement)
            if not report.is_balanced():
                raise ValueError(
                    'Conservation invariant violated — final settlement blocked. '
                    f'Residuals: {report.breakdown()}'
                )
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


# ---------------------------------------------------------------------------
# E17 Phase 4 — Conservation invariant (safety-critical close/settlement gate)
# ---------------------------------------------------------------------------
#
# "Money is neither created nor destroyed." The venture's value lives in three
# pockets and EACH must net to ~0 INDEPENDENTLY, per currency — a single master
# sum is forbidden because pocket +X / pocket -X would falsely cancel and hide a
# real leak. Derived from first principles (per-slice realization fields), the
# matrix only CONFIRMS it:
#
#   per realization slice:  cost_at_sale = recovered + loss ; proceeds = recovered + profit ;
#                           cost_at_sale = cost_hist + fx_gain
#
#   Pocket CAPITAL    (UZS): deployed + Σfx = Σrecovered + Σloss + remaining + PLR
#   Pocket PROCEEDS   (UZS): Σproceeds      = Σrecovered + Σprofit
#   Pocket DISTRIBUTION(UZS): Σ_partner(positions) = venture aggregate (no money lost in the split)
#
# Functional UZS residuals are expected to be EXACTLY 0 (Decimal); native-currency
# residuals may carry sub-cent rounding ONLY from FX division (native = uzs / fx).
# A softer ε is a leak to fix, not to tolerate.

_EPS = Decimal('0.01')


@dataclass
class ConservationReport:
    """Per-pocket × per-currency conservation residuals for a venture (or an
    aggregate of ventures — reports compose via ``merge``)."""

    pockets: dict[str, dict[str, dict[str, Decimal]]] = field(default_factory=dict)

    POCKETS = ('capital', 'proceeds', 'distribution')

    def _bucket(self, pocket: str, currency: str) -> dict[str, Decimal]:
        return self.pockets.setdefault(pocket, {}).setdefault(currency, {})

    def add(self, pocket: str, currency: str, component: str, amount) -> None:
        bucket = self._bucket(pocket, currency)
        bucket[component] = _money(bucket.get(component, _ZERO) + Decimal(str(amount)))

    def residual(self, pocket: str, currency: str) -> Decimal:
        """sources − sinks for one pocket/currency. Component names prefixed with
        '-' are sinks; everything else is a source."""
        total = _ZERO
        for component, amount in self._bucket(pocket, currency).items():
            if component == 'residual':
                continue
            total += -amount if component.startswith('-') else amount
        return _money(total)

    def residuals(self) -> dict[tuple[str, str], Decimal]:
        out: dict[tuple[str, str], Decimal] = {}
        for pocket, by_ccy in self.pockets.items():
            for currency in by_ccy:
                out[(pocket, currency)] = self.residual(pocket, currency)
        return out

    def imbalances(self, eps: Decimal = _EPS) -> list[tuple[str, str, Decimal]]:
        return [
            (pocket, currency, residual)
            for (pocket, currency), residual in self.residuals().items()
            if abs(residual) > eps
        ]

    def is_balanced(self, eps: Decimal = _EPS) -> bool:
        return not self.imbalances(eps)

    def breakdown(self, eps: Decimal = _EPS) -> str:
        lines = []
        for pocket, currency, residual in self.imbalances(eps):
            comps = ', '.join(
                f'{name}={value}' for name, value in sorted(self._bucket(pocket, currency).items())
            )
            lines.append(f'{pocket}/{currency}: residual={residual} ({comps})')
        return '; '.join(lines)

    def merge(self, other: 'ConservationReport') -> None:
        for pocket, by_ccy in other.pockets.items():
            for currency, comps in by_ccy.items():
                for component, amount in comps.items():
                    if component == 'residual':
                        continue
                    self.add(pocket, currency, component, amount)


def _sign(event) -> Decimal:
    return Decimal('-1') if event.event_type == ProcurementSaleRealization.EventType.REVERSAL else Decimal('1')


def venture_conservation(*, procurement: Procurement) -> ConservationReport:
    """Conservation report for one procurement venture, built ONLY from append-only
    events (realizations, batches, stock, ledger, withdrawals). No manual inputs."""

    report = ConservationReport()

    # Per-partner fields (recovered/profit/loss/fx) are split by share and SUM to
    # the slice total; per-slice fields (proceeds/cost_basis) are stored FULL on
    # every partner row, so they are counted ONCE per slice via _realization_groups.
    deployed_uzs = _ZERO
    batches = (
        ProcurementReceiveBatch.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement, is_reversal=False)
        .exclude(reversal_batches__isnull=False)
    )
    for batch in batches:
        deployed_uzs += _money(batch.total_inventory_uzs)
    remaining_uzs = _money(sum(_remaining_inventory_capital_entitlements(procurement).values(), _ZERO))

    report.add('capital', 'UZS', 'deployed', deployed_uzs)
    report.add('capital', 'UZS', '-remaining_inventory', remaining_uzs)

    # Native capital pocket uses deployed/remaining in the cost currency (via the
    # immutable buy FX — no FX drift natively): deployed = recovered + loss +
    # remaining + PLR. cost_basis is NOT used because a DISPOSE reverses the sold
    # cost while booking the same unit as loss (the deployed view avoids that).
    cost_buy_fx: dict[str, Decimal] = {}

    groups = _realization_groups(procurement)  # E17 T-4.7: query once, reuse below
    for rows in groups.values():
        first = rows[0]
        sgn = _sign(first)
        is_liability_loss = (
            first.event_type == ProcurementSaleRealization.EventType.LOSS and first.is_partner_liability
        )
        # per-partner sums for this slice
        recovered_uzs = _money(sum((r.capital_recovered_uzs for r in rows), _ZERO))
        profit_uzs = _money(sum((r.provisional_profit_uzs for r in rows), _ZERO))
        loss_uzs = _money(sum((r.loss_uzs for r in rows), _ZERO))
        fx_uzs = _money(sum((r.fx_gain_loss_uzs for r in rows), _ZERO))
        recovered_native = _money(sum((r.capital_recovered_amount for r in rows), _ZERO))
        profit_native = _money(sum((r.profit_amount for r in rows), _ZERO))
        loss_native = _money(sum((r.loss_amount for r in rows), _ZERO))

        # ---- Pocket CAPITAL (UZS): deployed + Σfx = Σrecovered + Σloss + remaining + PLR
        report.add('capital', 'UZS', '-recovered', sgn * recovered_uzs)
        report.add('capital', 'UZS', 'fx_gain', sgn * fx_uzs)
        report.add('capital', 'UZS', '-partner_liability' if is_liability_loss else '-loss', loss_uzs)

        # ---- Pocket PROCEEDS (UZS): Σproceeds = Σrecovered + Σprofit (proceeds once per slice)
        report.add('proceeds', 'UZS', 'proceeds', sgn * _money(first.sale_proceeds_uzs))
        report.add('proceeds', 'UZS', '-recovered', sgn * recovered_uzs)
        report.add('proceeds', 'UZS', '-profit', sgn * profit_uzs)

        # ---- Native legs (sub-cent FX-division ε tolerated) ----
        cost_ccy = str(first.cost_basis_currency or 'UZS').upper()
        sale_ccy = str(first.sale_proceeds_currency or 'UZS').upper()
        if cost_ccy != 'UZS':
            # capital in cost currency: deployed = recovered + loss + remaining + PLR
            report.add('capital', cost_ccy, '-recovered', sgn * recovered_native)
            report.add('capital', cost_ccy, '-partner_liability' if is_liability_loss else '-loss', loss_native)
            if cost_ccy not in cost_buy_fx and _money(first.cost_basis_amount) > 0:
                cost_buy_fx[cost_ccy] = _money(first.cost_basis_uzs) / _money(first.cost_basis_amount)
        if sale_ccy != 'UZS' and sale_ccy == cost_ccy:
            # proceeds close natively only when sale and cost share a currency;
            # cross-currency proceeds are bridged by FX and covered by the UZS pocket.
            report.add('proceeds', sale_ccy, 'proceeds', sgn * _money(first.sale_proceeds_amount))
            report.add('proceeds', sale_ccy, '-recovered', sgn * recovered_native)
            report.add('proceeds', sale_ccy, '-profit', sgn * profit_native)

    # Deployed/remaining in the cost currency. Supported for a single non-UZS
    # cost currency (mixed-currency procurement is E13, blocked); with one cost
    # currency the whole deployed/remaining maps to it via the buy FX.
    if len(cost_buy_fx) == 1:
        ((cost_ccy, buy_fx),) = cost_buy_fx.items()
        if buy_fx > 0:
            report.add('capital', cost_ccy, 'deployed', _money(deployed_uzs / buy_fx))
            report.add('capital', cost_ccy, '-remaining_inventory', _money(remaining_uzs / buy_fx))

    # ---- Pocket DISTRIBUTION (functional UZS): per-partner positions sum to venture aggregate
    positions = procurement_venture_positions(procurement=procurement)
    sum_recovered = _money(sum((row['capital_recovered_uzs'] for row in positions.values()), _ZERO))
    sum_profit = _money(sum((row['provisional_profit_uzs'] for row in positions.values()), _ZERO))
    sum_deployed = _money(sum((row['deployed_uzs'] for row in positions.values()), _ZERO))
    report.add('distribution', 'UZS', 'deployed_total', deployed_uzs)
    report.add('distribution', 'UZS', '-deployed_partners', sum_deployed)

    has_settlement = procurement.venture_settlements.exists()
    if has_settlement:
        net_cap = _net_capital_loss_entitlements(procurement, groups)
        venture_recovered = _money(sum((v['capital_recovered_uzs'] for v in net_cap.values()), _ZERO))
        venture_recovered += _money(sum(_liability_capital_recovery_entitlements(procurement, groups).values(), _ZERO))
    else:
        venture_recovered = _money(sum(
            (_sign(rows[0]) * _money(sum((r.capital_recovered_uzs for r in rows), _ZERO))
             for rows in groups.values()),
            _ZERO,
        ))
    venture_profit = _money(sum(_net_profit_entitlements(procurement, groups).values(), _ZERO))
    report.add('distribution', 'UZS', 'recovered_venture', venture_recovered)
    report.add('distribution', 'UZS', '-recovered_partners', sum_recovered)
    report.add('distribution', 'UZS', 'profit_venture', venture_profit)
    report.add('distribution', 'UZS', '-profit_partners', sum_profit)

    return report


# ---------------------------------------------------------------------------
# E17 Phase 3 — procurement venture close lifecycle & read-only lock
# ---------------------------------------------------------------------------


def procurement_has_active_lots(procurement: Procurement) -> bool:
    """Authoritative "stock still on hand" signal — the single source used by the
    FINAL-settlement precondition, the close gate, and the UI (so the UI button
    and the backend never diverge)."""
    from apps.inventory.models import Lot

    return Lot.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement_item__procurement=procurement,
        is_active=True,
        reversed=False,
    ).exists()


def procurement_close_blocking_reasons(*, procurement: Procurement) -> list[str]:
    """Reasons a procurement venture cannot be closed yet (empty = closeable).

    Gates: FINAL settlement exists; no active lots; no negative positions; the
    conservation invariant nets to zero in every pocket/currency (T-4.5); and no
    entitlement is left hanging — available capital/profit must be paid out, FX-
    converted (sarf), or fixed as an explicit final debt, never silently dropped
    (T-4.6).
    """
    reasons: list[str] = []

    has_final = procurement.venture_settlements.filter(
        settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
    ).exists()
    if not has_final:
        reasons.append('Нет финальной сверки (FINAL settlement) по этому приходу.')

    if procurement_has_active_lots(procurement):
        reasons.append('По этому приходу ещё есть нераспроданный товар.')

    positions = procurement_venture_positions(procurement=procurement)
    if any(_money(row.get('negative_position_uzs', _ZERO)) > _ZERO for row in positions.values()):
        reasons.append('Есть отрицательные позиции партнёров; сначала погасите их.')

    # Claim ≠ liquidity (T-4.6): nothing may be left available-but-unpaid.
    for partner_id, row in positions.items():
        cap = _money(row.get('capital_return_available_uzs', _ZERO))
        profit = _money(row.get('provisional_profit_available_uzs', _ZERO))
        if cap > _ZERO or profit > _ZERO:
            reasons.append(
                f'У партнёра {partner_id} есть невыплаченный капитал/прибыль '
                f'(капитал {cap} UZS, прибыль {profit} UZS): выплатите, при несовпадении '
                f'валюты конвертируйте (sarf), либо зафиксируйте как явный финальный долг.'
            )

    report = venture_conservation(procurement=procurement)
    if not report.is_balanced():
        reasons.append(f'Нарушен инвариант сохранения денег (residual): {report.breakdown()}.')

    return reasons


def procurement_close_state(*, procurement: Procurement) -> dict:
    """Derived close read-model for the UI (single source — gates stay on the
    backend, the frontend only displays).

      show_close — the venture has entered wind-down, so "close" is now the
        relevant next action. Anchored on END-OF-LIFE facts: a fully received
        partnership procurement with NO active lots, or a FINAL settlement.
        A CONSTRUCTIVE settlement does NOT trigger it (it can be a mid-life
        checkpoint), so the close affordance never surfaces prematurely.
      closeable — every gate passes (blocking_reasons empty).
      blocking_reasons — the remaining steps to close (human-readable)."""
    reasons = procurement_close_blocking_reasons(procurement=procurement)
    is_partnership = procurement.funding_source == Procurement.FundingSource.PARTNERSHIP
    has_active_lots = procurement_has_active_lots(procurement)
    has_final = procurement.venture_settlements.filter(
        settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
    ).exists()
    show_close = (
        is_partnership
        and procurement.status == Procurement.Status.RECEIVED
        and (not has_active_lots or has_final)
    )
    return {
        'show_close': show_close,
        'closeable': not reasons,
        'blocking_reasons': reasons,
    }


def close_procurement_venture(*, tenant_id: int, procurement_id: int, client_request_id=None) -> Procurement:
    """Close a partnership procurement venture once every gate passes. Idempotent:
    an already-closed venture is returned unchanged. Uses an explicit lifecycle
    transition (queryset update) because a RECEIVED procurement is immutable to
    save(); the close is append-only at the event level."""
    from django.utils import timezone
    from apps.core.services import publish_event

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(pk=procurement_id, tenant_id=tenant_id)
        if procurement.status == Procurement.Status.CLOSED:
            return procurement
        if procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
            raise ValueError('Закрытие венчура применимо только к партнёрским приходам.')

        reasons = procurement_close_blocking_reasons(procurement=procurement)
        if reasons:
            raise ValueError('Нельзя закрыть приход: ' + ' '.join(reasons))

        Procurement.objects.filter(pk=procurement_id, tenant_id=tenant_id).update(
            status=Procurement.Status.CLOSED,
            closed_at=timezone.now(),
        )
        procurement.refresh_from_db()
        publish_event(
            event_type='procurement.venture_closed',
            payload={'procurement_id': procurement_id},
            tenant_id=tenant_id,
        )
        return procurement


def assert_procurement_open(procurement: Procurement) -> None:
    """Read-only lock: after CLOSED, any operation that would change the
    procurement venture economics is forbidden (T-3.3)."""
    if getattr(procurement, 'status', None) == Procurement.Status.CLOSED:
        raise ValueError(
            'Приход закрыт (CLOSED): операции, меняющие экономику прихода '
            '(продажи/возвраты/списания/выплаты/сверка), запрещены.'
        )


def repay_partner_venture_debt(
    *,
    tenant_id: int,
    procurement_id: int,
    partner_id: int,
    amount,
    currency: str = 'UZS',
    paid_to_account_id: int,
    fx_rate=None,
    client_request_id=None,
    date=None,
) -> 'ProcurementPartnerVentureDebtRepayment':
    """E17 T-5.3: repay a partner's negative venture position with real cash.

    The debtor brings cash into operating cash (CashEntry IN). The amount is
    allocated by waterfall — liability → over-returned capital → over-paid
    dividend — and credited component-correct: liability → 5100 (loss restored),
    over-capital → role equity (3100/3110/3000), over-dividend → 3200. Append-only;
    originals are never touched; the position folds `repaid_*` to cut
    negative_position; the cash now funds the counterparty's claim. Idempotent on
    client_request_id; blocked after close."""
    from django.utils import timezone
    from apps.finance.models import CashAccount, CashEntry
    from apps.finance.fx_rates import resolve_fx_rate_snapshot_details
    from apps.finance.services import create_cash_entry, create_journal_entry
    from .advances import _equity_account_code
    from .models import (
        AgreementPartner,
        ProcurementPartnerVentureDebtRepayment,
    )

    amount = _money(amount)
    currency = str(currency or 'UZS').upper()
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        if client_request_id:
            existing = ProcurementPartnerVentureDebtRepayment.objects.filter(
                tenant_id=tenant_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing

        if amount <= _ZERO:
            raise ValueError('Сумма погашения должна быть положительной.')

        procurement = Procurement.objects.select_for_update().get(pk=procurement_id, tenant_id=tenant_id)
        assert_procurement_open(procurement)
        agreement = procurement.agreement
        if agreement is None:
            raise ValueError('Погашение долга применимо только к партнёрскому приходу.')

        fx = resolve_fx_rate_snapshot_details(
            tenant_id=tenant_id, operation_currency=currency, operation_at=date, fx_rate_snapshot=fx_rate,
        )
        functional = _money(amount * Decimal(str(fx.rate)))

        pos = procurement_venture_positions(procurement=procurement).get(partner_id)
        if not pos:
            raise ValueError('У партнёра нет позиции по этому приходу.')
        out_liability = _money(pos['negative_liability_uzs'])
        out_capital = _money(pos['negative_capital_uzs'])
        out_dividend = _money(pos['negative_dividend_uzs'])
        total_out = _money(out_liability + out_capital + out_dividend)
        if total_out <= _ZERO:
            raise ValueError('У партнёра нет непогашенного долга перед венчуром.')
        if functional - total_out > _CENTS:
            raise ValueError(f'Погашение {functional} превышает долг {total_out} UZS.')

        # Waterfall: liability → over-capital → over-dividend.
        remaining = functional
        repaid_liability = min(remaining, out_liability)
        remaining = _money(remaining - repaid_liability)
        repaid_capital = min(remaining, out_capital)
        remaining = _money(remaining - repaid_capital)
        repaid_dividend = min(remaining, out_dividend)

        account = CashAccount.objects.select_for_update().get(pk=paid_to_account_id, tenant_id=tenant_id)
        if str(account.currency).upper() != currency:
            raise ValueError(
                f'Погашение в {currency} должно поступать на кассу {currency}; '
                f'сделайте явную конвертацию (sarf), если деньги в {account.currency}.'
            )
        if not account.linked_account_id:
            raise ValueError('У кассы нет привязанного GL-счёта.')

        role = AgreementPartner.objects.get(agreement=agreement, partner_id=partner_id).role
        equity_code = _equity_account_code(role=role, legal_mode=agreement.legal_mode)

        repayment = ProcurementPartnerVentureDebtRepayment.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=fx.rate,
            fx_rate_source=fx.source,
            fx_rate_date=fx.rate_date,
            paid_to_account=account,
            amount_uzs=functional,
            repaid_liability_uzs=_money(repaid_liability),
            repaid_capital_uzs=_money(repaid_capital),
            repaid_dividend_uzs=_money(repaid_dividend),
            date=date,
            client_request_id=str(client_request_id) if client_request_id else None,
        )

        create_cash_entry(
            tenant_id=tenant_id, account=account, direction=CashEntry.Direction.IN,
            amount=amount, date=date,
            source_ref_type='venture_debt_repay', source_ref_id=repayment.pk,
        )

        lines = [{
            'account_code': account.linked_account.code,
            'debit': functional, 'credit': _ZERO,
            'description': 'Погашение долга партнёра — приход кэша',
        }]
        if repaid_liability > _ZERO:
            lines.append({'account_code': '5100', 'debit': _ZERO, 'credit': _money(repaid_liability),
                          'description': 'Погашение долга: восстановление списания (вина)'})
        if repaid_capital > _ZERO:
            lines.append({'account_code': equity_code, 'debit': _ZERO, 'credit': _money(repaid_capital),
                          'description': 'Погашение долга: возврат излишне выведенного капитала'})
        if repaid_dividend > _ZERO:
            lines.append({'account_code': '3200', 'debit': _ZERO, 'credit': _money(repaid_dividend),
                          'description': 'Погашение долга: возврат излишне выплаченной прибыли'})
        create_journal_entry(
            tenant_id=tenant_id, operation_type='venture_debt_repay', operation_id=repayment.pk,
            lines=lines, description=f'Погашение долга партнёра по приходу #{procurement_id}', date=date,
        )

        return repayment
