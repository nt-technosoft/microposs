"""
Partnerships services — ledger management, dividend payout, partner aggregates.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.finance.models import CashAccount, CashEntry
from apps.finance.services import create_cash_entry, create_journal_entry, record_journal_from_cash_entry

from apps.core.services import publish_event
from apps.core.exceptions import ImmutableRecordError
from apps.partnerships.formulas import profit_shares_from_capital


_PARTNERSHIP_TYPES = ('PARTNERSHIP', 'MUSHARAKA')
_ZERO = Decimal('0')
_CENT = Decimal('0.01')
_RATIO_Q = Decimal('0.000001')


def _q(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_CENT)


def _q_ratio(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_RATIO_Q)


def _functional_uzs(
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
) -> Decimal:
    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    if currency == 'UZS':
        return _q(amount)
    return _q(amount * fx_rate)


def _balance_get(balances: dict, currency: str) -> Decimal:
    return Decimal(str(balances.get(currency, '0')))


def _balance_set(balances: dict, currency: str, value: Decimal) -> None:
    balances[currency] = str(_q(value))


def _money_by_currency_add(target: dict[str, Decimal], currency: str, amount: Decimal) -> None:
    currency = str(currency or 'UZS').upper()
    target[currency] = _q(target.get(currency, _ZERO) + Decimal(str(amount)))


def _item_native_total(item) -> Decimal:
    return _q(Decimal(str(item.quantity)) * Decimal(str(item.unit_purchase_price)))


def _item_value_uzs(item) -> Decimal:
    return _q(
        Decimal(str(item.quantity))
        * Decimal(str(item.unit_purchase_price))
        * Decimal(str(item.fx_rate))
    )


def _expense_value_uzs(expense) -> Decimal:
    return _q(Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate)))


def _functional_uzs_to_currency(
    *,
    tenant_id: int,
    functional_amount_uzs: Decimal,
    target_currency: str,
    rate_date,
) -> Decimal:
    target = str(target_currency or 'UZS').upper()
    if target == 'UZS':
        return _q(functional_amount_uzs)

    from apps.finance.fx_rates import get_fx_rate_for_date

    rate_row = get_fx_rate_for_date(
        tenant_id=tenant_id,
        base_currency=target,
        quote_currency='UZS',
        rate_date=rate_date,
    )
    if rate_row is None:
        raise ValueError(
            f'FX rate for {target}/UZS is missing on {rate_date}. '
            f'Add manual rate or official sync before receive.'
        )

    target_rate = Decimal(str(rate_row.rate))
    return _q(Decimal(str(functional_amount_uzs)) / target_rate)


def _entry_amount_in_currency(
    *,
    entry,
    tenant_id: int,
    target_currency: str,
) -> Decimal:
    target = str(target_currency or 'UZS').upper()
    entry_currency = str(entry.currency or 'UZS').upper()
    amount = Decimal(str(entry.amount))

    if target == entry_currency:
        return _q(amount)

    return _functional_uzs_to_currency(
        tenant_id=tenant_id,
        functional_amount_uzs=Decimal(str(entry.functional_amount_uzs)),
        target_currency=target,
        rate_date=entry.date.date(),
    )


def _amount_to_currency(
    *,
    tenant_id: int,
    amount: Decimal,
    currency: str,
    fx_rate: Decimal,
    target_currency: str,
    rate_date,
) -> Decimal:
    source = str(currency or 'UZS').upper()
    target = str(target_currency or 'UZS').upper()
    amount = Decimal(str(amount))
    fx_rate = Decimal(str(fx_rate or Decimal('1')))

    if source == target:
        return _q(amount)

    functional_uzs = _functional_uzs(amount, source, fx_rate)
    if target == 'UZS':
        return _q(functional_uzs)

    if source == 'UZS' and fx_rate > 1:
        return _q(amount / fx_rate)

    return _functional_uzs_to_currency(
        tenant_id=tenant_id,
        functional_amount_uzs=functional_uzs,
        target_currency=target,
        rate_date=rate_date,
    )


def _allocate_amount(amount: Decimal, bases: list[Decimal]) -> list[Decimal]:
    amount = _q(amount)
    if not bases:
        return []

    total_base = sum((Decimal(str(base)) for base in bases), _ZERO)
    if total_base <= 0:
        bases = [Decimal('1') for _ in bases]
        total_base = Decimal(len(bases))

    allocations: list[Decimal] = []
    remaining = amount
    last_index = len(bases) - 1
    for index, base in enumerate(bases):
        if index == last_index:
            allocation = _q(remaining)
        else:
            allocation = _q(amount * Decimal(str(base)) / total_base)
            remaining -= allocation
        allocations.append(allocation)
    return allocations


def _required_spend_by_currency(items: list, expenses: list) -> dict[str, Decimal]:
    required: dict[str, Decimal] = {}
    for item in items:
        _money_by_currency_add(required, item.currency, _item_native_total(item))
    for expense in expenses:
        _money_by_currency_add(required, expense.currency, Decimal(str(expense.amount)))
    return required


def _partner_amounts_by_currency(entries) -> dict[int, dict[str, Decimal]]:
    result: dict[int, dict[str, Decimal]] = {}
    for entry in entries:
        partner_id = int(entry.partner_id)
        currency = str(entry.currency or 'UZS').upper()
        bucket = result.setdefault(partner_id, {})
        bucket[currency] = _q(bucket.get(currency, _ZERO) + Decimal(str(entry.amount)))
    return result


def _agreement_partner_available(agreement) -> dict[int, dict[str, Decimal]]:
    """Native per-currency available balance by partner inside a parent agreement."""
    from .models import AgreementAllocation

    available: dict[int, dict[str, Decimal]] = {}
    for source in (agreement.contributions.all(),):
        for partner_id, amounts in _partner_amounts_by_currency(source).items():
            bucket = available.setdefault(partner_id, {})
            for currency, amount in amounts.items():
                bucket[currency] = _q(bucket.get(currency, _ZERO) + amount)

    for source in (agreement.withdrawals.all(),):
        for partner_id, amounts in _partner_amounts_by_currency(source).items():
            bucket = available.setdefault(partner_id, {})
            for currency, amount in amounts.items():
                bucket[currency] = _q(bucket.get(currency, _ZERO) - amount)

    outgoing = agreement.allocations.filter(direction=AgreementAllocation.Direction.TO_PROCUREMENT)
    for partner_id, amounts in _partner_amounts_by_currency(outgoing).items():
        bucket = available.setdefault(partner_id, {})
        for currency, amount in amounts.items():
            bucket[currency] = _q(bucket.get(currency, _ZERO) - amount)

    incoming = agreement.allocations.filter(direction=AgreementAllocation.Direction.FROM_PROCUREMENT)
    for partner_id, amounts in _partner_amounts_by_currency(incoming).items():
        bucket = available.setdefault(partner_id, {})
        for currency, amount in amounts.items():
            bucket[currency] = _q(bucket.get(currency, _ZERO) + amount)

    return available


def _agreement_contract_payload(agreement) -> dict:
    partners = [
        {
            'partner_id': member.partner_id,
            'role': member.role,
            'planned_capital_share': Decimal(str(member.planned_capital_share)),
            'profit_share': Decimal(str(member.profit_share)),
        }
        for member in agreement.partners.all()
    ]
    return {
        'mudaraba_ratio': Decimal(str(agreement.mudaraba_ratio)),
        'loss_rule': agreement.loss_rule,
        'planned_budget': Decimal(str(agreement.planned_budget)),
        'currency': str(agreement.currency or 'UZS').upper(),
        'partners': partners,
    }


def _procurement_spend_by_currency(balance) -> dict[str, Decimal]:
    spent: dict[str, Decimal] = {}
    for withdrawal in balance.withdrawals.filter(partner_id__isnull=True):
        _money_by_currency_add(spent, withdrawal.currency, Decimal(str(withdrawal.amount)))
    return spent


def _receive_batches_payload(procurement) -> list[dict]:
    from .models import ProcurementReceiveBatch

    batches = (
        ProcurementReceiveBatch.objects
        .filter(procurement=procurement)
        .select_related('warehouse')
        .prefetch_related(
            'lines__item__product_variant',
            'lines__lot',
            'expenses__expense',
            'capital_allocations__partner',
        )
        .order_by('-received_at', '-id')
    )
    payload = []
    for batch in batches:
        lines = [
            {
                'id': line.id,
                'item_id': line.item_id,
                'lot_id': line.lot_id,
                'product_variant_id': line.item.product_variant_id,
                'product_variant_name': str(line.item.product_variant),
                'quantity': str(line.quantity),
                'unit_purchase_price_uzs': str(_q(line.unit_purchase_price_uzs)),
                'allocated_expense_uzs': str(_q(line.allocated_expense_uzs)),
                'landed_cost_per_unit_uzs': str(_q(line.landed_cost_per_unit_uzs)),
            }
            for line in batch.lines.all()
        ]
        expenses = [
            {
                'id': row.id,
                'expense_id': row.expense_id,
                'expense_type': row.expense.expense_type,
                'allocated_amount_uzs': str(_q(row.allocated_amount_uzs)),
            }
            for row in batch.expenses.all()
        ]
        capital_allocations = [
            {
                'id': row.id,
                'partner': row.partner_id,
                'partner_name': row.partner.display_name,
                'role': row.role,
                'amount_contract_currency': str(_q(row.amount_contract_currency)),
                'capital_share': str(_q_ratio(row.capital_share)),
                'profit_share': str(_q_ratio(row.profit_share)),
            }
            for row in batch.capital_allocations.all()
        ]
        payload.append({
            'id': batch.id,
            'warehouse_id': batch.warehouse_id,
            'warehouse_name': batch.warehouse.name,
            'received_at': batch.received_at,
            'items_count': batch.items_count,
            'total_inventory_uzs': str(_q(batch.total_inventory_uzs)),
            'lines': lines,
            'expenses': expenses,
            'capital_allocations': capital_allocations,
        })
    return payload


def _landed_expense_allocations(items: list, expenses: list) -> list[Decimal]:
    allocations = [_ZERO for _ in items]
    if not items:
        return allocations

    item_values = [_item_value_uzs(item) for item in items]
    item_quantities = [Decimal(str(item.quantity)) for item in items]
    item_indexes = {item.id: index for index, item in enumerate(items)}

    for expense in expenses:
        target_ids = {
            target.item_id
            for target in getattr(expense, 'targets', []).all()
        }
        if target_ids:
            target_indexes = [
                item_indexes[item_id]
                for item_id in target_ids
                if item_id in item_indexes
            ]
            if not target_indexes:
                continue
        else:
            target_indexes = list(range(len(items)))

        amount_uzs = _expense_value_uzs(expense)
        method = str(expense.allocation_method)
        if method == 'BY_VALUE':
            bases = [item_values[index] for index in target_indexes]
        else:
            # BY_WEIGHT falls back to quantity until item weights exist.
            bases = [item_quantities[index] for index in target_indexes]

        for local_index, allocation in enumerate(_allocate_amount(amount_uzs, bases)):
            item_index = target_indexes[local_index]
            allocations[item_index] = _q(allocations[item_index] + allocation)
    return allocations


def _landed_cost_preview_block(items: list, expenses: list) -> dict:
    allocations = _landed_expense_allocations(items, expenses)
    lines: list[dict] = []
    total_expenses_uzs = sum(allocations, _ZERO)
    for item, allocated_expense_uzs in zip(items, allocations):
        qty = Decimal(str(item.quantity))
        if qty <= 0:
            continue
        unit_purchase_price_uzs = (
            Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
        ).quantize(Decimal('0.01'))
        landed_cost_per_unit_uzs = (
            unit_purchase_price_uzs + (allocated_expense_uzs / qty)
        ).quantize(Decimal('0.01'))
        lines.append({
            'item_id': item.id,
            'product_variant_id': item.product_variant_id,
            'product_variant_name': str(item.product_variant),
            'status': item.status,
            'quantity': str(item.quantity),
            'unit_purchase_price_uzs': str(unit_purchase_price_uzs),
            'allocated_expense_uzs': str(_q(allocated_expense_uzs)),
            'landed_cost_per_unit_uzs': str(landed_cost_per_unit_uzs),
        })
    return {
        'items_count': len(items),
        'expenses_count': len(expenses),
        'total_expenses_uzs': str(_q(total_expenses_uzs)),
        'lines': lines,
    }


def _batch_value_in_contract_currency(
    *,
    tenant_id: int,
    items: list,
    expenses: list,
    contract_currency: str,
    rate_date,
) -> Decimal:
    total = _ZERO
    target = str(contract_currency or 'UZS').upper()
    for item in items:
        total += _amount_to_currency(
            tenant_id=tenant_id,
            amount=_item_native_total(item),
            currency=item.currency,
            fx_rate=item.fx_rate,
            target_currency=target,
            rate_date=rate_date,
        )
    for expense in expenses:
        total += _amount_to_currency(
            tenant_id=tenant_id,
            amount=Decimal(str(expense.amount)),
            currency=expense.currency,
            fx_rate=expense.fx_rate,
            target_currency=target,
            rate_date=rate_date,
        )
    return _q(total)


def _allocated_batch_capital_by_partner(procurement, contract_currency: str) -> dict[int, Decimal]:
    from .models import ProcurementReceiveBatchCapitalAllocation

    allocated: dict[int, Decimal] = {}
    rows = ProcurementReceiveBatchCapitalAllocation.objects.filter(
        tenant_id=procurement.tenant_id,
        batch__procurement=procurement,
    ).values('partner_id').annotate(total=models.Sum('amount_contract_currency'))
    for row in rows:
        allocated[int(row['partner_id'])] = _q(Decimal(str(row['total'] or '0')))
    return allocated


def _batch_capital_preview(
    *,
    procurement,
    items: list,
    expenses: list,
    rate_date,
) -> dict | None:
    if procurement.procurement_type not in _PARTNERSHIP_TYPES:
        return None

    from .models import ContractPartner, InvestmentContract, PartnerLedgerEntry, ProcurementPartnerLedger

    try:
        contract = procurement.contract
    except InvestmentContract.DoesNotExist:
        return None

    contract_currency = str(contract.currency or 'UZS').upper()
    required = _batch_value_in_contract_currency(
        tenant_id=procurement.tenant_id,
        items=items,
        expenses=expenses,
        contract_currency=contract_currency,
        rate_date=rate_date,
    )
    partners = list(
        ContractPartner.objects
        .filter(contract=contract)
        .select_related('partner')
        .order_by('id')
    )
    ledgers = (
        ProcurementPartnerLedger.objects
        .filter(procurement=procurement, tenant_id=procurement.tenant_id)
        .prefetch_related('entries')
    )
    actual_capital = _capital_by_partner(
        ledgers,
        PartnerLedgerEntry,
        tenant_id=procurement.tenant_id,
        target_currency=contract_currency,
    )
    already_allocated = _allocated_batch_capital_by_partner(procurement, contract_currency)
    available = {
        partner.partner_id: _q(actual_capital.get(partner.partner_id, _ZERO) - already_allocated.get(partner.partner_id, _ZERO))
        for partner in partners
    }

    if required <= 0:
        return {
            'currency': contract_currency,
            'required_amount': '0.00',
            'status': 'NO_CAPITAL_REQUIRED',
            'message': 'Стоимость партии не рассчитана.',
            'partners': [],
        }

    planned_total = sum((Decimal(str(partner.planned_capital_share)) for partner in partners), _ZERO)
    suggested: dict[int, Decimal] = {}
    remaining = required
    for partner in partners:
        planned_share = (
            Decimal(str(partner.planned_capital_share)) / planned_total
            if planned_total > 0 else Decimal('0')
        )
        amount = _q(min(required * planned_share, max(available.get(partner.partner_id, _ZERO), _ZERO)))
        suggested[partner.partner_id] = amount
        remaining = _q(remaining - amount)

    if remaining > 0:
        for partner in partners:
            headroom = _q(max(available.get(partner.partner_id, _ZERO), _ZERO) - suggested.get(partner.partner_id, _ZERO))
            if headroom <= 0:
                continue
            top_up = min(headroom, remaining)
            suggested[partner.partner_id] = _q(suggested.get(partner.partner_id, _ZERO) + top_up)
            remaining = _q(remaining - top_up)
            if remaining <= 0:
                break

    suggested_total = sum(suggested.values(), _ZERO)
    if abs(suggested_total - required) <= Decimal('0.01') and partners:
        last_partner = partners[-1]
        suggested[last_partner.partner_id] = _q(
            suggested.get(last_partner.partner_id, _ZERO) + (required - suggested_total),
        )
        suggested_total = required

    partners_meta = []
    for partner in partners:
        amount = _q(suggested.get(partner.partner_id, _ZERO))
        capital_share = _q_ratio(amount / required) if required > 0 else _ZERO
        partners_meta.append({
            'partner_id': partner.partner_id,
            'partner_name': partner.partner.display_name,
            'role': partner.role,
            'amount': amount,
            'available_amount': available.get(partner.partner_id, _ZERO),
            'capital_share': capital_share,
        })
    profit_shares = _profit_shares_from_capital(partners_meta, contract.mudaraba_ratio)

    rows = []
    for meta in partners_meta:
        partner_id = int(meta['partner_id'])
        rows.append({
            'partner_id': partner_id,
            'partner_name': meta['partner_name'],
            'role': meta['role'],
            'available_amount': str(_q(meta['available_amount'])),
            'amount': str(_q(meta['amount'])),
            'capital_share': str(_q_ratio(meta['capital_share'])),
            'profit_share': str(profit_shares.get(partner_id, _ZERO)),
        })

    return {
        'currency': contract_currency,
        'required_amount': str(_q(required)),
        'status': 'READY' if remaining <= Decimal('0.01') else 'CAPITAL_SHORTAGE',
        'message': (
            'Распределение партии рассчитано.'
            if remaining <= Decimal('0.01')
            else 'Недостаточно доступного капитала для выбранной партии.'
        ),
        'partners': rows,
    }


def _resolve_batch_capital_snapshot(
    *,
    procurement,
    items: list,
    expenses: list,
    raw_allocations: list[dict] | None,
    is_partial_receive: bool,
    received_at,
) -> tuple[dict, list[dict]]:
    from .models import ContractPartner, InvestmentContract, PartnerLedgerEntry, ProcurementPartnerLedger

    contract = InvestmentContract.objects.get(procurement=procurement)
    partners = list(
        ContractPartner.objects
        .filter(contract=contract)
        .select_related('partner')
        .order_by('id')
    )
    contract_currency = str(contract.currency or 'UZS').upper()
    required = _batch_value_in_contract_currency(
        tenant_id=procurement.tenant_id,
        items=items,
        expenses=expenses,
        contract_currency=contract_currency,
        rate_date=received_at.date(),
    )

    ledgers = (
        ProcurementPartnerLedger.objects
        .filter(procurement=procurement, tenant_id=procurement.tenant_id)
        .prefetch_related('entries')
    )
    actual_capital = _capital_by_partner(
        ledgers,
        PartnerLedgerEntry,
        tenant_id=procurement.tenant_id,
        target_currency=contract_currency,
    )
    already_allocated = _allocated_batch_capital_by_partner(procurement, contract_currency)
    available = {
        partner.partner_id: _q(actual_capital.get(partner.partner_id, _ZERO) - already_allocated.get(partner.partner_id, _ZERO))
        for partner in partners
    }
    partner_by_id = {partner.partner_id: partner for partner in partners}

    if raw_allocations:
        amounts: dict[int, Decimal] = {}
        for item in raw_allocations:
            partner_id = int(item.get('partner_id') or item.get('partner') or 0)
            if partner_id not in partner_by_id:
                raise ValueError('Capital allocation contains an unknown partner.')
            amount = _q(Decimal(str(item.get('amount', '0'))))
            if amount < 0:
                raise ValueError('Capital allocation amount cannot be negative.')
            amounts[partner_id] = _q(amounts.get(partner_id, _ZERO) + amount)
    else:
        if is_partial_receive:
            raise ValueError('Для частичного оприходования укажите доли капитала партии.')
        preview = _batch_capital_preview(
            procurement=procurement,
            items=items,
            expenses=expenses,
            rate_date=received_at.date(),
        )
        if not preview or preview.get('status') != 'READY':
            raise ValueError('Не удалось автоматически рассчитать доли капитала партии.')
        amounts = {
            int(row['partner_id']): _q(Decimal(str(row['amount'])))
            for row in preview.get('partners', [])
        }

    total = _q(sum(amounts.values(), _ZERO))
    if abs(total - required) > Decimal('0.01'):
        raise ValueError(
            f'Сумма долей партии должна быть {required} {contract_currency}.'
        )
    for partner_id, amount in amounts.items():
        if amount - available.get(partner_id, _ZERO) > Decimal('0.01'):
            partner = partner_by_id[partner_id]
            raise ValueError(
                f'Недостаточно капитала у {partner.partner.display_name}: '
                f'доступно {available.get(partner_id, _ZERO)} {contract_currency}.'
            )

    partners_meta = []
    for partner in partners:
        amount = _q(amounts.get(partner.partner_id, _ZERO))
        capital_share = _q_ratio(amount / required) if required > 0 else _ZERO
        partners_meta.append({
            'partner_id': partner.partner_id,
            'role': partner.role,
            'capital_amount_contract_currency': str(amount),
            'capital_share': str(capital_share),
        })
    profit_shares = _profit_shares_from_capital(partners_meta, contract.mudaraba_ratio)
    allocation_rows: list[dict] = []
    for meta in partners_meta:
        partner_id = int(meta['partner_id'])
        profit_share = profit_shares.get(partner_id, _ZERO)
        meta['profit_share'] = str(profit_share)
        allocation_rows.append({
            'partner_id': partner_id,
            'role': meta['role'],
            'amount_contract_currency': Decimal(str(meta['capital_amount_contract_currency'])),
            'capital_share': Decimal(str(meta['capital_share'])),
            'profit_share': profit_share,
        })

    return {
        'contract_currency': contract_currency,
        'mudaraba_ratio': str(_q_ratio(contract.mudaraba_ratio)),
        'loss_rule': contract.loss_rule,
        'partners': partners_meta,
    }, allocation_rows


def build_procurement_cost_preview(procurement) -> dict:
    all_items = list(procurement.items.all())
    all_expenses = list(procurement.expenses.all())
    open_items = [item for item in all_items if item.status != item.Status.RECEIVED]
    open_expenses = [expense for expense in all_expenses if expense.status != expense.Status.RECEIVED]
    paid_items = [item for item in open_items if item.status == item.Status.PAID]
    paid_expenses = [expense for expense in open_expenses if expense.status == expense.Status.PAID]
    draft_items = [item for item in open_items if item.status == item.Status.DRAFT]
    draft_expenses = [expense for expense in open_expenses if expense.status == expense.Status.DRAFT]

    preview = {
        'receive_basis': _landed_cost_preview_block(paid_items, paid_expenses),
        'if_all_current_lines_paid': _landed_cost_preview_block(open_items, open_expenses),
        'reallocation_pending': bool(paid_expenses and draft_items),
        'message': '',
    }
    if not paid_items:
        preview['message'] = 'Себестоимость для receive появится после оплаты товаров.'
    elif paid_expenses and draft_items:
        preview['message'] = 'Если оплатить новые товары, текущие расходы прихода перераспределятся заново по всем оплаченным товарам.'
    elif draft_expenses:
        preview['message'] = 'Есть черновики расходов. После их оплаты landed cost будет пересчитан.'
    else:
        preview['message'] = 'Текущая себестоимость рассчитана по оплаченным строкам. Финальная фиксация произойдёт при receive.'
    return preview


def _profit_shares_from_capital(partners_meta: list[dict], mudaraba_ratio: Decimal) -> dict[int, Decimal]:
    return profit_shares_from_capital(partners_meta, mudaraba_ratio)


def _validate_contract_formula(partners: list[dict], mudaraba_ratio: Decimal) -> None:
    operator_count = sum(1 for partner in partners if partner.get('role') == 'OPERATOR')
    if operator_count != 1:
        raise ValueError('Contract must include exactly one OPERATOR partner.')

    total_planned = sum(
        (Decimal(str(partner.get('planned_capital_share', '0'))) for partner in partners),
        _ZERO,
    )
    if total_planned <= 0:
        raise ValueError('Total planned capital must be positive.')

    partners_meta = []
    for partner in partners:
        capital_share = Decimal(str(partner.get('planned_capital_share', '0'))) / total_planned
        partners_meta.append({
            'partner_id': partner['partner_id'],
            'role': partner['role'],
            'capital_share': _q_ratio(capital_share),
        })

    expected = _profit_shares_from_capital(partners_meta, mudaraba_ratio)
    for partner in partners:
        partner_id = int(partner['partner_id'])
        provided = _q_ratio(Decimal(str(partner.get('profit_share', '0'))))
        if abs(expected[partner_id] - provided) > Decimal('0.0001'):
            raise ValueError(
                'Partner profit_share does not match planned capital shares '
                'and mudaraba_ratio.'
            )


def _validate_contract_partner_access(*, tenant_id: int, partners: list[dict]) -> None:
    from apps.core.models import BusinessInvestorRelation, Partner

    partner_ids = [partner['partner_id'] for partner in partners]
    db_partners = {
        partner.id: partner
        for partner in Partner.objects.filter(
            tenant_id=tenant_id,
            id__in=partner_ids,
            is_active=True,
        )
    }
    for partner in partners:
        partner_id = int(partner['partner_id'])
        expected_role = partner.get('role')
        db_partner = db_partners.get(partner_id)
        if db_partner is None:
            raise ValueError('Contract partner is not available for this business.')
        if db_partner.role != expected_role:
            raise ValueError('Contract partner role does not match partner profile.')
        if expected_role == Partner.Role.INVESTOR and not BusinessInvestorRelation.objects.filter(
            tenant_id=tenant_id,
            partner_id=partner_id,
            status=BusinessInvestorRelation.Status.ACTIVE,
        ).exists():
            raise ValueError('Investor is not related to this business.')


def _validate_contract_payload(
    *,
    tenant_id: int,
    procurement_type: str,
    contract: dict | None,
) -> None:
    is_partnership = procurement_type in _PARTNERSHIP_TYPES
    if is_partnership and not contract:
        raise ValueError(
            f'contract payload required for procurement_type={procurement_type}'
        )
    if not is_partnership:
        return

    partners = contract.get('partners') or []
    if not partners:
        raise ValueError('At least one contract partner is required.')
    roles = {partner.get('role') for partner in partners}
    if 'OPERATOR' not in roles:
        raise ValueError('Contract must include an OPERATOR partner.')
    mudaraba_ratio = Decimal(str(contract.get('mudaraba_ratio', '0')))
    if mudaraba_ratio < 0 or mudaraba_ratio > 1:
        raise ValueError('mudaraba_ratio must be in [0, 1].')
    planned_budget = Decimal(str(contract.get('planned_budget', '0')))
    if planned_budget <= 0:
        raise ValueError('planned_budget must be positive.')
    profit_share_sum = sum(
        (Decimal(str(partner.get('profit_share', '0'))) for partner in partners),
        _ZERO,
    )
    if abs(profit_share_sum - Decimal('1')) > Decimal('0.000001'):
        raise ValueError('Sum of partner profit_share must equal 1.0.')
    _validate_contract_partner_access(tenant_id=tenant_id, partners=partners)
    _validate_contract_formula(partners, mudaraba_ratio)


def _replace_procurement_items_and_expenses(
    *,
    tenant_id: int,
    procurement,
    items: list[dict] | None,
    expenses: list[dict] | None,
    draft_only: bool = False,
) -> None:
    from .models import ProcurementExpense, ProcurementExpenseTarget, ProcurementItem

    item_queryset = procurement.items.all()
    expense_queryset = procurement.expenses.all()
    if draft_only:
        item_queryset = item_queryset.filter(status=ProcurementItem.Status.DRAFT)
        expense_queryset = expense_queryset.filter(status=ProcurementExpense.Status.DRAFT)

    existing_items = {item.pk: item for item in item_queryset.select_for_update()}
    seen_item_ids: set[int] = set()

    for item in items or []:
        item_id = item.get('id')
        if item_id is not None:
            item_id = int(item_id)
            item_obj = existing_items.get(item_id)
            if item_obj is None:
                raise ValueError('Only draft procurement items can be edited here.')
            item_obj.product_variant_id = item['product_variant_id']
            item_obj.quantity = Decimal(str(item['quantity']))
            item_obj.unit_purchase_price = Decimal(str(item['unit_purchase_price']))
            item_obj.currency = str(item.get('currency', 'UZS')).upper()
            item_obj.fx_rate = Decimal(str(item.get('fx_rate', '1')))
            item_obj.save(update_fields=[
                'product_variant', 'quantity', 'unit_purchase_price',
                'currency', 'fx_rate', 'updated_at',
            ])
            seen_item_ids.add(item_id)
            continue

        item_obj = ProcurementItem.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            product_variant_id=item['product_variant_id'],
            quantity=Decimal(str(item['quantity'])),
            unit_purchase_price=Decimal(str(item['unit_purchase_price'])),
            currency=str(item.get('currency', 'UZS')).upper(),
            fx_rate=Decimal(str(item.get('fx_rate', '1'))),
            status=ProcurementItem.Status.DRAFT,
        )
        seen_item_ids.add(item_obj.pk)

    stale_item_ids = set(existing_items) - seen_item_ids
    if stale_item_ids:
        ProcurementItem.objects.filter(pk__in=stale_item_ids).delete()

    existing_expenses = {expense.pk: expense for expense in expense_queryset.select_for_update()}
    seen_expense_ids: set[int] = set()
    valid_item_ids = set(
        procurement.items
        .exclude(status=ProcurementItem.Status.RECEIVED)
        .values_list('id', flat=True)
    )
    for expense in expenses or []:
        requested_target_ids = {
            int(item_id)
            for item_id in expense.get('target_item_ids', []) or []
        }
        invalid_target_ids = requested_target_ids - valid_item_ids
        if invalid_target_ids:
            raise ValueError('Expense targets must belong to pending items in this procurement.')
        target_ids = {
            int(item_id)
            for item_id in requested_target_ids
        }
        expense_id = expense.get('id')
        if expense_id is not None:
            expense_id = int(expense_id)
            expense_obj = existing_expenses.get(expense_id)
            if expense_obj is None:
                raise ValueError('Only draft procurement expenses can be edited here.')
            expense_obj.expense_type = expense['expense_type']
            expense_obj.amount = Decimal(str(expense['amount']))
            expense_obj.currency = str(expense.get('currency', 'UZS')).upper()
            expense_obj.fx_rate = Decimal(str(expense.get('fx_rate', '1')))
            expense_obj.allocation_method = expense.get(
                'allocation_method',
                ProcurementExpense.AllocationMethod.BY_VALUE,
            )
            expense_obj.notes = expense.get('notes', '')
            expense_obj.save(update_fields=[
                'expense_type', 'amount', 'currency', 'fx_rate',
                'allocation_method', 'notes', 'updated_at',
            ])
            seen_expense_ids.add(expense_id)
        else:
            expense_obj = ProcurementExpense.objects.create(
                tenant_id=tenant_id,
                procurement=procurement,
                expense_type=expense['expense_type'],
                amount=Decimal(str(expense['amount'])),
                currency=str(expense.get('currency', 'UZS')).upper(),
                fx_rate=Decimal(str(expense.get('fx_rate', '1'))),
                allocation_method=expense.get(
                    'allocation_method',
                    ProcurementExpense.AllocationMethod.BY_VALUE,
                ),
                notes=expense.get('notes', ''),
                status=ProcurementExpense.Status.DRAFT,
            )
            seen_expense_ids.add(expense_obj.pk)

        ProcurementExpenseTarget.objects.filter(expense=expense_obj).delete()
        for item_id in target_ids:
            ProcurementExpenseTarget.objects.create(
                tenant_id=tenant_id,
                expense=expense_obj,
                item_id=item_id,
            )

    stale_expense_ids = set(existing_expenses) - seen_expense_ids
    if stale_expense_ids:
        ProcurementExpense.objects.filter(pk__in=stale_expense_ids).delete()


def _replace_procurement_contract(
    *,
    tenant_id: int,
    procurement,
    procurement_type: str,
    contract: dict | None,
) -> None:
    from .models import ContractPartner, InvestmentContract

    existing_contract = InvestmentContract.objects.filter(procurement=procurement).first()
    if existing_contract is not None:
        existing_contract.delete()

    if procurement_type not in _PARTNERSHIP_TYPES:
        return

    inv_contract = InvestmentContract.objects.create(
        tenant_id=tenant_id,
        procurement=procurement,
        mudaraba_ratio=Decimal(str(contract['mudaraba_ratio'])),
        loss_rule=contract.get(
            'loss_rule', InvestmentContract.LossRule.BY_CAPITAL,
        ),
        planned_budget=Decimal(str(contract['planned_budget'])),
        currency=str(contract.get('currency', 'UZS')).upper(),
    )
    for partner in contract['partners']:
        ContractPartner.objects.create(
            tenant_id=tenant_id,
            contract=inv_contract,
            partner_id=partner['partner_id'],
            role=partner['role'],
            planned_capital_share=Decimal(str(partner['planned_capital_share'])),
            profit_share=Decimal(str(partner.get('profit_share', '0'))),
        )


def _contract_snapshot(contract) -> dict | None:
    if contract is None:
        return None
    partners = sorted(
        [
            {
                'partner_id': int(member.partner_id),
                'role': member.role,
                'planned_capital_share': str(Decimal(str(member.planned_capital_share))),
                'profit_share': str(_q_ratio(Decimal(str(member.profit_share)))),
            }
            for member in contract.contract_partners.all()
        ],
        key=lambda item: (item['role'], item['partner_id']),
    )
    return {
        'mudaraba_ratio': str(_q_ratio(Decimal(str(contract.mudaraba_ratio)))),
        'planned_budget': str(_q(Decimal(str(contract.planned_budget)))),
        'currency': str(contract.currency or 'UZS').upper(),
        'partners': partners,
    }


def _contract_payload_snapshot(contract: dict | None) -> dict | None:
    if not contract:
        return None
    partners = sorted(
        [
            {
                'partner_id': int(partner['partner_id']),
                'role': partner['role'],
                'planned_capital_share': str(_q(Decimal(str(partner['planned_capital_share'])))),
                'profit_share': str(_q_ratio(Decimal(str(partner.get('profit_share', '0'))))),
            }
            for partner in contract.get('partners', [])
        ],
        key=lambda item: (item['role'], item['partner_id']),
    )
    return {
        'mudaraba_ratio': str(_q_ratio(Decimal(str(contract.get('mudaraba_ratio', '0'))))),
        'planned_budget': str(_q(Decimal(str(contract.get('planned_budget', '0'))))),
        'currency': str(contract.get('currency', 'UZS')).upper(),
        'partners': partners,
    }


def _has_balance_activity(procurement) -> bool:
    balance = getattr(procurement, 'balance', None)
    if balance is None:
        return False
    return (
        balance.contributions.exists()
        or balance.withdrawals.exists()
    )


def _mutate_agreement_balance(agreement, currency: str, delta: Decimal) -> None:
    currency = str(currency or 'UZS').upper()
    balances = dict(agreement.balances or {})
    next_value = _balance_get(balances, currency) + Decimal(str(delta))
    if next_value < 0:
        raise ValueError(
            f'Insufficient agreement balance for {currency}: have {_balance_get(balances, currency)}, need {abs(delta)}.'
        )
    _balance_set(balances, currency, next_value)
    agreement.balances = balances
    agreement.save(update_fields=['balances', 'updated_at'])


def create_investment_agreement(
    *,
    tenant_id: int,
    opened_at=None,
    supplier_id: int | None = None,
    mudaraba_ratio: Decimal,
    planned_budget: Decimal,
    currency: str = 'UZS',
    notes: str = '',
    client_request_id: str | None = None,
    partners: list[dict],
):
    from .models import AgreementPartner, InvestmentAgreement

    if opened_at is None:
        opened_at = timezone.now()
    currency = str(currency or 'UZS').upper()
    payload = {
        'mudaraba_ratio': Decimal(str(mudaraba_ratio)),
        'planned_budget': Decimal(str(planned_budget)),
        'currency': currency,
        'partners': partners,
    }
    _validate_contract_payload(
        tenant_id=tenant_id,
        procurement_type='PARTNERSHIP',
        contract=payload,
    )

    with transaction.atomic():
        if client_request_id:
            existing = InvestmentAgreement.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        agreement = InvestmentAgreement.objects.create(
            tenant_id=tenant_id,
            status=InvestmentAgreement.Status.OPEN,
            opened_at=opened_at,
            supplier_id=supplier_id,
            mudaraba_ratio=Decimal(str(mudaraba_ratio)),
            planned_budget=Decimal(str(planned_budget)),
            currency=currency,
            notes=notes,
            client_request_id=client_request_id,
            balances={},
        )
        for partner in partners:
            AgreementPartner.objects.create(
                tenant_id=tenant_id,
                agreement=agreement,
                partner_id=partner['partner_id'],
                role=partner['role'],
                planned_capital_share=Decimal(str(partner['planned_capital_share'])),
                profit_share=Decimal(str(partner.get('profit_share', '0'))),
            )
        publish_event(
            event_type='investment_agreement.opened',
            payload={'agreement_id': agreement.pk},
            tenant_id=tenant_id,
        )
    return agreement


def add_agreement_contribution(
    *,
    tenant_id: int,
    agreement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    date=None,
    notes: str = '',
):
    from .models import AgreementContribution, AgreementPartner, InvestmentAgreement

    amount = _q(Decimal(str(amount)))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Contribution amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id,
            tenant_id=tenant_id,
        )
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Cannot contribute to closed agreement.')
        if not AgreementPartner.objects.filter(agreement=agreement, partner_id=partner_id).exists():
            raise ValueError('Selected partner is not part of this agreement.')
        contribution = AgreementContribution.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            notes=notes,
        )
        _mutate_agreement_balance(agreement, currency, amount)
        if agreement.status == InvestmentAgreement.Status.OPEN:
            agreement.status = InvestmentAgreement.Status.ACTIVE
            agreement.save(update_fields=['status', 'updated_at'])
        publish_event(
            event_type='investment_agreement.contribution_added',
            payload={
                'agreement_id': agreement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
    return contribution


def add_agreement_withdrawal(
    *,
    tenant_id: int,
    agreement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    date=None,
    reason: str = '',
):
    from .models import AgreementPartner, AgreementWithdrawal, InvestmentAgreement

    amount = _q(Decimal(str(amount)))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Withdrawal amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id,
            tenant_id=tenant_id,
        )
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Cannot withdraw from closed agreement.')
        if not AgreementPartner.objects.filter(agreement=agreement, partner_id=partner_id).exists():
            raise ValueError('Selected partner is not part of this agreement.')
        _mutate_agreement_balance(agreement, currency, -amount)
        withdrawal = AgreementWithdrawal.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            reason=reason,
        )
        publish_event(
            event_type='investment_agreement.withdrawal_added',
            payload={
                'agreement_id': agreement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
    return withdrawal


def open_procurement(
    *,
    tenant_id: int,
    procurement_type: str,
    opened_at=None,
    supplier_id: int | None = None,
    notes: str = '',
    client_request_id: str | None = None,
    agreement_id: int | None = None,
    contract: dict | None = None,
    items: list[dict] | None = None,
    expenses: list[dict] | None = None,
):
    """
    Create a Procurement (and, for partnership types, InvestmentContract + ContractPartner[]).

    contract (required for PARTNERSHIP/MUSHARAKA):
        {mudaraba_ratio, planned_budget, currency,
         partners: [{partner_id, role, planned_capital_share, profit_share?}]}
    items: [{product_variant_id, quantity, unit_purchase_price, currency, fx_rate}]
    expenses: [{expense_type, amount, currency, fx_rate, allocation_method, notes}]
    """
    from .models import (
        Procurement, ProcurementItem, ProcurementExpense,
        InvestmentAgreement, InvestmentContract, ContractPartner, ProcurementBalance,
    )

    if opened_at is None:
        opened_at = timezone.now()
    agreement = None
    if agreement_id is not None:
        agreement = (
            InvestmentAgreement.objects
            .prefetch_related('partners')
            .filter(tenant_id=tenant_id, pk=agreement_id)
            .first()
        )
        if agreement is None:
            raise ValueError('Investment agreement not found.')
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Investment agreement is not open.')
        if contract is None:
            contract = _agreement_contract_payload(agreement)
    is_partnership = procurement_type in _PARTNERSHIP_TYPES
    _validate_contract_payload(
        tenant_id=tenant_id,
        procurement_type=procurement_type,
        contract=contract,
    )

    with transaction.atomic():
        if client_request_id:
            existing = Procurement.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return existing

        procurement = Procurement.objects.create(
            tenant_id=tenant_id,
            procurement_type=procurement_type,
            status=Procurement.Status.OPEN,
            opened_at=opened_at,
            supplier_id=supplier_id,
            agreement=agreement,
            notes=notes,
            client_request_id=client_request_id,
        )

        _replace_procurement_items_and_expenses(
            tenant_id=tenant_id,
            procurement=procurement,
            items=items,
            expenses=expenses,
            draft_only=True,
        )

        if is_partnership:
            _replace_procurement_contract(
                tenant_id=tenant_id,
                procurement=procurement,
                procurement_type=procurement_type,
                contract=contract,
            )

        ProcurementBalance.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            balances={},
        )

        publish_event(
            event_type='procurement.opened',
            payload={
                'procurement_id': procurement.pk,
                'procurement_type': procurement_type,
                'is_partnership': is_partnership,
            },
            tenant_id=tenant_id,
        )

    return procurement


def update_open_procurement(
    *,
    tenant_id: int,
    procurement_id: int,
    procurement_type: str,
    supplier_id: int | None = None,
    agreement_id: int | None = None,
    notes: str = '',
    contract: dict | None = None,
    items: list[dict] | None = None,
    expenses: list[dict] | None = None,
):
    from .models import InvestmentAgreement, InvestmentContract, Procurement

    agreement = None
    if agreement_id is not None:
        agreement = (
            InvestmentAgreement.objects
            .prefetch_related('partners')
            .filter(tenant_id=tenant_id, pk=agreement_id)
            .first()
        )
        if agreement is None:
            raise ValueError('Investment agreement not found.')
        if contract is None:
            contract = _agreement_contract_payload(agreement)

    _validate_contract_payload(
        tenant_id=tenant_id,
        procurement_type=procurement_type,
        contract=contract,
    )

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot edit procurement in status {procurement.status}.'
            )

        current_contract_obj = (
            InvestmentContract.objects.filter(procurement=procurement)
            .prefetch_related('contract_partners')
            .first()
        )
        incoming_contract = _contract_payload_snapshot(contract)
        current_contract = _contract_snapshot(current_contract_obj)
        contract_changed = (
            procurement.procurement_type != procurement_type
            or procurement.agreement_id != agreement_id
            or incoming_contract != current_contract
        )
        if contract_changed and _has_balance_activity(procurement):
            raise ValueError(
                'Нельзя менять тип или договор после движения денег по балансу прихода.'
            )

        procurement.procurement_type = procurement_type
        procurement.agreement = agreement
        procurement.supplier_id = supplier_id
        procurement.notes = notes
        procurement.save(update_fields=['procurement_type', 'agreement', 'supplier', 'notes', 'updated_at'])

        _replace_procurement_items_and_expenses(
            tenant_id=tenant_id,
            procurement=procurement,
            items=items,
            expenses=expenses,
            draft_only=True,
        )

        if contract_changed:
            _replace_procurement_contract(
                tenant_id=tenant_id,
                procurement=procurement,
                procurement_type=procurement_type,
                contract=contract,
            )

        publish_event(
            event_type='procurement.updated',
            payload={
                'procurement_id': procurement.pk,
                'procurement_type': procurement.procurement_type,
            },
            tenant_id=tenant_id,
        )

    return procurement


def add_contribution(
    *,
    tenant_id: int,
    procurement_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    date=None,
    notes: str = '',
):
    """
    Partner deposits capital into ProcurementBalance.
    → BalanceContribution + balances[currency] += amount + Ledger(CAPITAL_IN).
    """
    from .models import (
        BalanceContribution,
        ContractPartner,
        InvestmentContract,
        PartnerLedgerEntry,
        Procurement,
        ProcurementBalance,
    )
    from apps.core.models import Partner

    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Contribution amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot contribute to procurement in status {procurement.status}.'
            )
        partner = Partner.objects.filter(pk=partner_id, tenant_id=tenant_id).first()
        if partner is None:
            raise ValueError('Partner does not belong to this tenant.')

        if procurement.procurement_type in _PARTNERSHIP_TYPES:
            contract = InvestmentContract.objects.filter(procurement=procurement).first()
            if contract is None:
                raise ValueError('Partnership procurement contract is missing.')
            if not ContractPartner.objects.filter(contract=contract, partner_id=partner_id).exists():
                raise ValueError('Selected partner is not part of this procurement contract.')

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement, tenant_id=tenant_id,
        )

        contribution = BalanceContribution.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            notes=notes,
        )

        balances = dict(balance.balances or {})
        _balance_set(balances, currency, _balance_get(balances, currency) + amount)
        balance.balances = balances
        balance.save(update_fields=['balances', 'updated_at'])

        ledger = get_or_create_ledger(
            procurement_id=procurement.pk,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )
        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.CAPITAL_IN,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            source_ref=f'contribution:{contribution.pk}',
            date=date,
        )

        publish_event(
            event_type='procurement.contribution_added',
            payload={
                'procurement_id': procurement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'contribution_id': contribution.pk,
            },
            tenant_id=tenant_id,
        )

    return contribution


def add_withdrawal(
    *,
    tenant_id: int,
    procurement_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    partner_id: int | None = None,
    date=None,
    reason: str = '',
):
    """
    Spend from the common pot. If partner_id given → CAPITAL_OUT ledger entry.
    """
    from .models import (
        Procurement, ProcurementBalance, BalanceWithdrawal,
        PartnerLedgerEntry,
    )

    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    if amount <= 0:
        raise ValueError('Withdrawal amount must be > 0.')
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot withdraw from procurement in status {procurement.status}.'
            )

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement, tenant_id=tenant_id,
        )
        balances = dict(balance.balances or {})
        current = _balance_get(balances, currency)
        if current < amount:
            raise ValueError(
                f'Insufficient balance for {currency}: have {current}, need {amount}.'
            )
        _balance_set(balances, currency, current - amount)
        balance.balances = balances
        balance.save(update_fields=['balances', 'updated_at'])

        withdrawal = BalanceWithdrawal.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            partner_id=partner_id,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate)),
            date=date,
            reason=reason,
        )

        if partner_id is not None:
            ledger = get_or_create_ledger(
                procurement_id=procurement.pk,
                partner_id=partner_id,
                tenant_id=tenant_id,
            )
            append_ledger_entry(
                ledger=ledger,
                entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                source_ref=f'withdrawal:{withdrawal.pk}',
                date=date,
            )

        publish_event(
            event_type='procurement.withdrawal_added',
            payload={
                'procurement_id': procurement.pk,
                'partner_id': partner_id,
                'amount': str(amount),
                'currency': currency,
                'withdrawal_id': withdrawal.pk,
            },
            tenant_id=tenant_id,
        )

    return withdrawal


def exchange_procurement_balance(
    *,
    tenant_id: int,
    procurement_id: int,
    from_currency: str,
    from_amount: Decimal,
    to_currency: str,
    rate: Decimal,
    date=None,
    notes: str = '',
):
    from .models import Procurement, ProcurementBalance, ProcurementBalanceExchange

    source_currency = str(from_currency or 'UZS').upper()
    target_currency = str(to_currency or 'UZS').upper()
    source_amount = _q(Decimal(str(from_amount)))
    exchange_rate = Decimal(str(rate)).quantize(_RATIO_Q)
    if source_currency == target_currency:
        raise ValueError('Exchange currencies must be different.')
    if source_amount <= 0:
        raise ValueError('Exchange amount must be > 0.')
    if exchange_rate <= 0:
        raise ValueError('Exchange rate must be > 0.')
    if date is None:
        date = timezone.now()

    target_amount = _q(source_amount * exchange_rate)
    if target_amount <= 0:
        raise ValueError('Exchange result must be > 0.')

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot exchange procurement balance in status {procurement.status}.'
            )

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement,
            tenant_id=tenant_id,
        )
        balances = dict(balance.balances or {})
        available = _balance_get(balances, source_currency)
        if available < source_amount:
            raise ValueError(
                f'Insufficient balance for {source_currency}: have {available}, need {source_amount}.'
            )

        _balance_set(balances, source_currency, available - source_amount)
        _balance_set(
            balances,
            target_currency,
            _balance_get(balances, target_currency) + target_amount,
        )
        balance.balances = balances
        balance.save(update_fields=['balances', 'updated_at'])

        exchange = ProcurementBalanceExchange.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            from_currency=source_currency,
            from_amount=source_amount,
            to_currency=target_currency,
            to_amount=target_amount,
            rate=exchange_rate,
            date=date,
            notes=notes,
        )

        publish_event(
            event_type='procurement.balance_exchanged',
            payload={
                'procurement_id': procurement.pk,
                'exchange_id': exchange.pk,
                'from_currency': source_currency,
                'from_amount': str(source_amount),
                'to_currency': target_currency,
                'to_amount': str(target_amount),
                'rate': str(exchange_rate),
            },
            tenant_id=tenant_id,
        )

    return exchange


def _withdraw_procurement_amounts(
    *,
    tenant_id: int,
    procurement,
    balance,
    amounts_by_currency: dict[str, Decimal],
    fx_rate_map: dict[str, Decimal],
    date,
    reason: str,
) -> None:
    from .models import BalanceWithdrawal

    balances = dict(balance.balances or {})
    for currency, amount in amounts_by_currency.items():
        amount = _q(amount)
        if amount <= 0:
            continue
        current = _balance_get(balances, currency)
        if current < amount:
            raise ValueError(
                f'Insufficient balance for {currency}: have {current}, need {amount}.'
            )
        _balance_set(balances, currency, current - amount)
        BalanceWithdrawal.objects.create(
            tenant_id=tenant_id,
            balance=balance,
            partner_id=None,
            amount=amount,
            currency=currency,
            fx_rate=Decimal(str(fx_rate_map.get(currency, Decimal('1')))),
            date=date,
            reason=reason,
        )
        publish_event(
            event_type='procurement.withdrawal_added',
            payload={
                'procurement_id': procurement.pk,
                'partner_id': None,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )

    balance.balances = balances
    balance.save(update_fields=['balances', 'updated_at'])


def pay_procurement_items(
    *,
    tenant_id: int,
    procurement_id: int,
    item_ids: list[int] | None = None,
    reason: str = '',
):
    from .models import Procurement, ProcurementBalance, ProcurementItem

    payment_reason = reason or 'Item payment from procurement balance'

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot pay procurement items in status {procurement.status}.'
            )

        queryset = ProcurementItem.objects.select_for_update().filter(
            tenant_id=tenant_id,
            procurement=procurement,
            status=ProcurementItem.Status.DRAFT,
        )
        requested_item_ids = {int(item_id) for item_id in item_ids or []}
        if requested_item_ids:
            queryset = queryset.filter(pk__in=requested_item_ids)
        draft_items = list(queryset)
        if requested_item_ids:
            found_item_ids = {item.pk for item in draft_items}
            missing_item_ids = requested_item_ids - found_item_ids
            if missing_item_ids:
                raise ValueError('Some selected items are not draft or do not belong to this procurement.')
        if not draft_items:
            raise ValueError('No draft items to pay.')

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement,
            tenant_id=tenant_id,
        )

        amounts_by_currency: dict[str, Decimal] = {}
        fx_rate_map: dict[str, Decimal] = {}
        for item in draft_items:
            amount = _item_native_total(item)
            _money_by_currency_add(amounts_by_currency, item.currency, amount)
            fx_rate_map[str(item.currency).upper()] = Decimal(str(item.fx_rate))

        paid_at = timezone.now()
        _withdraw_procurement_amounts(
            tenant_id=tenant_id,
            procurement=procurement,
            balance=balance,
            amounts_by_currency=amounts_by_currency,
            fx_rate_map=fx_rate_map,
            date=paid_at,
            reason=payment_reason,
        )

        ProcurementItem.objects.filter(
            pk__in=[item.pk for item in draft_items],
        ).update(status=ProcurementItem.Status.PAID, updated_at=paid_at)

        publish_event(
            event_type='procurement.items_paid',
            payload={
                'procurement_id': procurement.pk,
                'items_count': len(draft_items),
                'currencies': {key: str(value) for key, value in amounts_by_currency.items()},
            },
            tenant_id=tenant_id,
        )

    return draft_items


def update_procurement_expense_targets(
    *,
    tenant_id: int,
    procurement_id: int,
    expense_id: int,
    target_item_ids: list[int] | None = None,
):
    from .models import Procurement, ProcurementExpense, ProcurementExpenseTarget, ProcurementItem

    requested_target_ids = {int(item_id) for item_id in target_item_ids or []}

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot edit expense targets in status {procurement.status}.'
            )
        expense = ProcurementExpense.objects.select_for_update().get(
            pk=expense_id,
            tenant_id=tenant_id,
            procurement=procurement,
        )
        if expense.status == ProcurementExpense.Status.RECEIVED:
            raise ValueError('Cannot edit targets for an already received expense.')

        valid_item_ids = set(
            ProcurementItem.objects
            .filter(
                tenant_id=tenant_id,
                procurement=procurement,
            )
            .exclude(status=ProcurementItem.Status.RECEIVED)
            .values_list('id', flat=True)
        )
        invalid_target_ids = requested_target_ids - valid_item_ids
        if invalid_target_ids:
            raise ValueError('Expense targets must belong to pending items in this procurement.')

        ProcurementExpenseTarget.objects.filter(expense=expense).delete()
        for item_id in sorted(requested_target_ids):
            ProcurementExpenseTarget.objects.create(
                tenant_id=tenant_id,
                expense=expense,
                item_id=item_id,
            )

        publish_event(
            event_type='procurement.expense_targets_updated',
            payload={
                'procurement_id': procurement.pk,
                'expense_id': expense.pk,
                'target_item_ids': sorted(requested_target_ids),
            },
            tenant_id=tenant_id,
        )

    return expense


def pay_procurement_expenses(
    *,
    tenant_id: int,
    procurement_id: int,
    expense_ids: list[int] | None = None,
    reason: str = '',
):
    from .models import Procurement, ProcurementBalance, ProcurementExpense

    payment_reason = reason or 'Expense payment from procurement balance'

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot pay procurement expenses in status {procurement.status}.'
            )

        queryset = ProcurementExpense.objects.select_for_update().filter(
            tenant_id=tenant_id,
            procurement=procurement,
            status=ProcurementExpense.Status.DRAFT,
        )
        if expense_ids:
            queryset = queryset.filter(pk__in=expense_ids)
        draft_expenses = list(queryset)
        if not draft_expenses:
            raise ValueError('No draft expenses to pay.')

        balance = ProcurementBalance.objects.select_for_update().get(
            procurement=procurement,
            tenant_id=tenant_id,
        )

        amounts_by_currency: dict[str, Decimal] = {}
        fx_rate_map: dict[str, Decimal] = {}
        for expense in draft_expenses:
            amount = Decimal(str(expense.amount))
            _money_by_currency_add(amounts_by_currency, expense.currency, amount)
            fx_rate_map[str(expense.currency).upper()] = Decimal(str(expense.fx_rate))

        paid_at = timezone.now()
        _withdraw_procurement_amounts(
            tenant_id=tenant_id,
            procurement=procurement,
            balance=balance,
            amounts_by_currency=amounts_by_currency,
            fx_rate_map=fx_rate_map,
            date=paid_at,
            reason=payment_reason,
        )

        ProcurementExpense.objects.filter(
            pk__in=[expense.pk for expense in draft_expenses],
        ).update(status=ProcurementExpense.Status.PAID, updated_at=paid_at)

        publish_event(
            event_type='procurement.expenses_paid',
            payload={
                'procurement_id': procurement.pk,
                'expenses_count': len(draft_expenses),
                'currencies': {key: str(value) for key, value in amounts_by_currency.items()},
            },
            tenant_id=tenant_id,
        )

    return draft_expenses


def split_procurement_item(
    *,
    tenant_id: int,
    procurement_id: int,
    item_id: int,
    quantity: Decimal,
):
    from .models import Procurement, ProcurementExpenseTarget, ProcurementItem

    split_quantity = Decimal(str(quantity))
    if split_quantity <= 0:
        raise ValueError('Split quantity must be > 0.')

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot split item in status {procurement.status}.'
            )
        item = ProcurementItem.objects.select_for_update().get(
            pk=item_id,
            tenant_id=tenant_id,
            procurement=procurement,
        )
        if item.status == ProcurementItem.Status.RECEIVED:
            raise ValueError('Cannot split an already received item.')
        current_quantity = Decimal(str(item.quantity))
        if split_quantity >= current_quantity:
            raise ValueError('Split quantity must be less than current item quantity.')

        remaining_quantity = current_quantity - split_quantity
        item.quantity = split_quantity
        item.save(update_fields=['quantity', 'updated_at'])
        new_item = ProcurementItem.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            product_variant_id=item.product_variant_id,
            quantity=remaining_quantity,
            unit_purchase_price=item.unit_purchase_price,
            currency=item.currency,
            fx_rate=item.fx_rate,
            status=item.status,
        )
        for target in ProcurementExpenseTarget.objects.filter(item=item):
            ProcurementExpenseTarget.objects.get_or_create(
                tenant_id=tenant_id,
                expense_id=target.expense_id,
                item=new_item,
            )

        publish_event(
            event_type='procurement.item_split',
            payload={
                'procurement_id': procurement.pk,
                'source_item_id': item.pk,
                'new_item_id': new_item.pk,
                'source_quantity': str(split_quantity),
                'new_quantity': str(remaining_quantity),
            },
            tenant_id=tenant_id,
        )

    return item, new_item


def _draft_requirement_by_currency(procurement) -> dict[str, Decimal]:
    required: dict[str, Decimal] = {}
    for item in procurement.items.filter(status='DRAFT'):
        _money_by_currency_add(required, item.currency, _item_native_total(item))
    for expense in procurement.expenses.filter(status='DRAFT'):
        _money_by_currency_add(required, expense.currency, Decimal(str(expense.amount)))
    return required


def get_agreement_allocation_preview(
    *,
    tenant_id: int,
    agreement_id: int,
    procurement_id: int,
) -> dict:
    from .models import InvestmentAgreement, Procurement

    agreement = (
        InvestmentAgreement.objects
        .filter(pk=agreement_id, tenant_id=tenant_id)
        .prefetch_related('partners__partner', 'contributions', 'withdrawals', 'allocations')
        .get()
    )
    procurement = (
        Procurement.objects
        .filter(pk=procurement_id, tenant_id=tenant_id)
        .prefetch_related('items', 'expenses')
        .get()
    )
    if procurement.agreement_id != agreement.id:
        raise ValueError('Procurement is not linked to this agreement.')

    required = _draft_requirement_by_currency(procurement)
    available_by_partner = _agreement_partner_available(agreement)
    partners = list(agreement.partners.select_related('partner').all())
    planned_total = sum((Decimal(str(partner.planned_capital_share)) for partner in partners), _ZERO)

    suggestions: list[dict] = []
    for currency, required_amount in required.items():
        remaining = _q(required_amount)
        raw_rows: list[dict] = []
        for member in partners:
            planned_ratio = (
                Decimal(str(member.planned_capital_share)) / planned_total
                if planned_total > 0 else Decimal('0')
            )
            available = _q(available_by_partner.get(member.partner_id, {}).get(currency, _ZERO))
            target = _q(required_amount * planned_ratio)
            amount = min(target, available)
            raw_rows.append({
                'partner_id': member.partner_id,
                'partner_name': member.partner.display_name,
                'role': member.role,
                'currency': currency,
                'available': available,
                'target_amount': target,
                'amount': amount,
            })
            remaining = _q(remaining - amount)

        if remaining > 0:
            for row in raw_rows:
                spare = _q(row['available'] - row['amount'])
                if spare <= 0:
                    continue
                top_up = min(spare, remaining)
                row['amount'] = _q(row['amount'] + top_up)
                remaining = _q(remaining - top_up)
                if remaining <= 0:
                    break

        for row in raw_rows:
            suggestions.append({
                **row,
                'available': str(row['available']),
                'target_amount': str(row['target_amount']),
                'amount': str(row['amount']),
            })

    return {
        'agreement_id': agreement.id,
        'procurement_id': procurement.id,
        'required': {key: str(value) for key, value in required.items()},
        'agreement_balances': agreement.balances or {},
        'suggestions': suggestions,
    }


def allocate_agreement_to_procurement(
    *,
    tenant_id: int,
    agreement_id: int,
    procurement_id: int,
    allocations: list[dict],
    date=None,
):
    from .models import AgreementAllocation, AgreementPartner, InvestmentAgreement, Procurement

    if date is None:
        date = timezone.now()
    if not allocations:
        raise ValueError('At least one allocation row is required.')

    with transaction.atomic():
        agreement = (
            InvestmentAgreement.objects
            .select_for_update()
            .filter(pk=agreement_id, tenant_id=tenant_id)
            .prefetch_related('partners', 'contributions', 'withdrawals', 'allocations')
            .get()
        )
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.agreement_id != agreement.id:
            raise ValueError('Procurement is not linked to this agreement.')
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError('Cannot allocate to non-open procurement.')
        if agreement.status not in (InvestmentAgreement.Status.OPEN, InvestmentAgreement.Status.ACTIVE):
            raise ValueError('Cannot allocate from closed agreement.')

        agreement_partner_ids = set(
            AgreementPartner.objects.filter(agreement=agreement).values_list('partner_id', flat=True)
        )
        available_by_partner = _agreement_partner_available(agreement)
        created = []
        for row in allocations:
            partner_id = int(row['partner_id'])
            if partner_id not in agreement_partner_ids:
                raise ValueError('Selected partner is not part of this agreement.')
            amount = _q(Decimal(str(row['amount'])))
            currency = str(row.get('currency') or agreement.currency or 'UZS').upper()
            fx_rate = Decimal(str(row.get('fx_rate') or Decimal('1')))
            if amount <= 0:
                continue
            available = _q(available_by_partner.get(partner_id, {}).get(currency, _ZERO))
            if available < amount:
                raise ValueError(
                    f'Partner balance is insufficient for {currency}: have {available}, need {amount}.'
                )

            _mutate_agreement_balance(agreement, currency, -amount)
            allocation = AgreementAllocation.objects.create(
                tenant_id=tenant_id,
                agreement=agreement,
                procurement=procurement,
                partner_id=partner_id,
                direction=AgreementAllocation.Direction.TO_PROCUREMENT,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                date=date,
                notes=row.get('notes', ''),
            )
            add_contribution(
                tenant_id=tenant_id,
                procurement_id=procurement.id,
                partner_id=partner_id,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                date=date,
                notes=f'agreement_allocation:{allocation.pk}',
            )
            available_by_partner.setdefault(partner_id, {})[currency] = _q(available - amount)
            created.append(allocation)

        publish_event(
            event_type='investment_agreement.allocated_to_procurement',
            payload={
                'agreement_id': agreement.pk,
                'procurement_id': procurement.pk,
                'allocations_count': len(created),
            },
            tenant_id=tenant_id,
        )
    return created


def _capital_by_partner(
    ledgers,
    entry_type_model,
    *,
    tenant_id: int,
    target_currency: str,
) -> dict[int, Decimal]:
    actual_capital: dict[int, Decimal] = {}
    for ledger in ledgers:
        entries = ledger.entries.all()
        capital_in = sum(
            (
                _entry_amount_in_currency(
                    entry=entry,
                    tenant_id=tenant_id,
                    target_currency=target_currency,
                )
                for entry in entries
                if entry.entry_type == entry_type_model.EntryType.CAPITAL_IN
            ),
            _ZERO,
        )
        capital_out = sum(
            (
                _entry_amount_in_currency(
                    entry=entry,
                    tenant_id=tenant_id,
                    target_currency=target_currency,
                )
                for entry in entries
                if entry.entry_type == entry_type_model.EntryType.CAPITAL_OUT
            ),
            _ZERO,
        )
        actual_capital[ledger.partner_id] = _q(capital_in - capital_out)
    return actual_capital


def _surplus_withdrawal_plan(
    *,
    procurement,
    balance,
    items: list,
    expenses: list,
    balances: dict[str, Decimal],
) -> dict:
    from .models import (
        ContractPartner, InvestmentContract,
        PartnerLedgerEntry, ProcurementPartnerLedger,
    )

    if procurement.procurement_type not in _PARTNERSHIP_TYPES:
        return {
            'status': 'BLOCKED',
            'message': 'Cannot auto-adjust non-partnership procurement balance.',
            'suggested_withdrawals': [],
        }

    contract = InvestmentContract.objects.get(procurement=procurement)
    currency = str(contract.currency or 'UZS').upper()
    non_zero_currencies = [cur for cur, amount in balances.items() if amount != 0]
    if any(cur != currency for cur in non_zero_currencies):
        return {
            'status': 'BLOCKED',
            'message': 'Manual adjustment required for balances outside contract currency.',
            'suggested_withdrawals': [],
        }

    partners = list(ContractPartner.objects.filter(contract=contract))
    planned_total = sum(
        (Decimal(str(partner.planned_capital_share)) for partner in partners),
        _ZERO,
    )
    if planned_total <= 0:
        return {
            'status': 'BLOCKED',
            'message': 'Contract planned capital is empty.',
            'suggested_withdrawals': [],
        }

    required = _required_spend_by_currency(items, expenses)
    required_amount = _q(required.get(currency, _ZERO))
    ledgers = (
        ProcurementPartnerLedger.objects
        .filter(procurement=procurement, tenant_id=procurement.tenant_id)
        .prefetch_related('entries')
    )
    actual_capital = _capital_by_partner(
        ledgers,
        PartnerLedgerEntry,
        tenant_id=procurement.tenant_id,
        target_currency=currency,
    )

    suggestions: list[dict] = []
    for partner in partners:
        planned_ratio = Decimal(str(partner.planned_capital_share)) / planned_total
        target_net = _q(required_amount * planned_ratio)
        actual_net = actual_capital.get(partner.partner_id, _ZERO)
        withdrawal = _q(actual_net - target_net)
        suggestions.append({
            'partner_id': partner.partner_id,
            'partner_name': partner.partner.display_name,
            'currency': currency,
            'amount': withdrawal,
            'target_net_capital': target_net,
            'actual_net_capital': actual_net,
        })

    negative = [item for item in suggestions if item['amount'] < 0]
    if negative:
        return {
            'status': 'RECALCULATE_OR_CONTRIBUTE',
            'message': 'Some partners are below planned capital share.',
            'suggested_withdrawals': suggestions,
        }

    positive_suggestions = [item for item in suggestions if item['amount'] > 0]
    suggested_total = _q(sum((item['amount'] for item in positive_suggestions), _ZERO))
    balance_amount = _q(balances.get(currency, _ZERO))
    residue = _q(balance_amount - suggested_total)
    if residue:
        operator_item = next(
            (item for item in positive_suggestions if any(
                partner.partner_id == item['partner_id'] and partner.role == 'OPERATOR'
                for partner in partners
            )),
            positive_suggestions[-1] if positive_suggestions else None,
        )
        if operator_item is not None:
            operator_item['amount'] = _q(operator_item['amount'] + residue)
            suggested_total = _q(suggested_total + residue)

    if suggested_total != balance_amount:
        return {
            'status': 'BLOCKED',
            'message': 'Surplus balance cannot be matched to partner capital.',
            'suggested_withdrawals': suggestions,
        }

    return {
        'status': 'AUTO_SURPLUS',
        'message': 'Surplus can be returned to partners before receive.',
        'suggested_withdrawals': positive_suggestions,
    }


def _agreement_surplus_return_plan(*, procurement, balances: dict[str, Decimal]) -> dict:
    from .models import InvestmentContract, PartnerLedgerEntry, ProcurementPartnerLedger

    contract = InvestmentContract.objects.get(procurement=procurement)
    partners = list(contract.contract_partners.select_related('partner').all())
    ledgers = (
        ProcurementPartnerLedger.objects
        .filter(procurement=procurement, tenant_id=procurement.tenant_id)
        .prefetch_related('entries')
    )

    suggestions: list[dict] = []
    for currency, balance_amount in balances.items():
        actual_capital = _capital_by_partner(
            ledgers,
            PartnerLedgerEntry,
            tenant_id=procurement.tenant_id,
            target_currency=currency,
        )
        total_capital = sum((amount for amount in actual_capital.values() if amount > 0), _ZERO)
        if total_capital <= 0:
            continue
        remaining = _q(balance_amount)
        positive_partners = [member for member in partners if actual_capital.get(member.partner_id, _ZERO) > 0]
        for index, member in enumerate(positive_partners):
            if index == len(positive_partners) - 1:
                amount = remaining
            else:
                amount = _q(balance_amount * actual_capital[member.partner_id] / total_capital)
                remaining = _q(remaining - amount)
            if amount <= 0:
                continue
            suggestions.append({
                'partner_id': member.partner_id,
                'partner_name': member.partner.display_name,
                'currency': currency,
                'amount': amount,
                'target_net_capital': Decimal('0'),
                'actual_net_capital': actual_capital[member.partner_id],
            })

    return {
        'status': 'AGREEMENT_SURPLUS',
        'message': 'Surplus can be returned to the parent investment agreement before receive.',
        'suggested_withdrawals': suggestions,
    }


def build_receive_plan(procurement, item_ids: list[int] | None = None) -> dict:
    """
    Explain whether a procurement can be received and which balancing action is needed.
    """
    from .models import ProcurementBalance

    def blocked_batch_capital_preview(message: str) -> dict:
        contract_currency = getattr(procurement.contract, 'currency', '') if getattr(procurement, 'contract', None) else ''
        return {
            'currency': str(contract_currency or '').upper(),
            'required_amount': '0.00',
            'status': 'BLOCKED',
            'message': message,
            'partners': [],
        }

    all_items = list(procurement.items.all())
    all_expenses = list(procurement.expenses.all())
    paid_items = [item for item in all_items if item.status == item.Status.PAID]
    paid_expenses = [expense for expense in all_expenses if expense.status == expense.Status.PAID]
    received_items_count = sum(1 for item in all_items if item.status == item.Status.RECEIVED)
    received_expenses_count = sum(1 for expense in all_expenses if expense.status == expense.Status.RECEIVED)
    draft_items_count = sum(1 for item in all_items if item.status == item.Status.DRAFT)
    draft_expenses_count = sum(1 for expense in all_expenses if expense.status == expense.Status.DRAFT)
    requested_item_ids = {int(item_id) for item_id in item_ids or []}
    selected_paid_items = [
        item for item in paid_items
        if not requested_item_ids or item.id in requested_item_ids
    ]
    selected_item_ids = {item.id for item in selected_paid_items}
    delayed_item_ids_for_preview = (
        ({item.id for item in paid_items} | {item.id for item in all_items if item.status == item.Status.DRAFT})
        - selected_item_ids
    )
    selected_paid_expenses = paid_expenses
    if requested_item_ids and delayed_item_ids_for_preview:
        selected_paid_expenses = []
        for expense in paid_expenses:
            target_ids = {target.item_id for target in expense.targets.all()}
            if target_ids and target_ids & selected_item_ids and not (target_ids & delayed_item_ids_for_preview):
                selected_paid_expenses.append(expense)
    try:
        batch_capital_preview = _batch_capital_preview(
            procurement=procurement,
            items=selected_paid_items,
            expenses=selected_paid_expenses,
            rate_date=timezone.now().date(),
        )
    except ValueError as error:
        batch_capital_preview = blocked_batch_capital_preview(str(error))
    if (
        procurement.procurement_type in _PARTNERSHIP_TYPES
        and selected_paid_items
        and batch_capital_preview is None
    ):
        batch_capital_preview = blocked_batch_capital_preview(
            'Не удалось сформировать доли партии. Повторите расчёт перед оприходованием.'
        )

    def pending_item_payload(item) -> dict:
        return {
            'id': item.id,
            'product_variant_id': item.product_variant_id,
            'product_variant_name': str(item.product_variant),
            'quantity': str(item.quantity),
            'unit_purchase_price': str(item.unit_purchase_price),
            'currency': str(item.currency).upper(),
            'fx_rate': str(item.fx_rate),
            'status': item.status,
        }

    def with_receive_context(payload: dict, *, will_finish: bool = False) -> dict:
        payload.setdefault('balances', {})
        payload.setdefault('missing_spend', {})
        payload.setdefault('suggested_withdrawals', [])
        payload['received_items_count'] = received_items_count
        payload['received_expenses_count'] = received_expenses_count
        payload['pending_paid_items_count'] = len(paid_items)
        payload['pending_paid_expenses_count'] = len(paid_expenses)
        payload['draft_items_count'] = draft_items_count
        payload['draft_expenses_count'] = draft_expenses_count
        payload['pending_paid_items'] = [pending_item_payload(item) for item in paid_items]
        payload['receive_batches'] = _receive_batches_payload(procurement)
        payload['will_finish_procurement'] = bool(will_finish)
        payload['batch_capital_preview'] = batch_capital_preview
        if (
            procurement.procurement_type in _PARTNERSHIP_TYPES
            and selected_paid_items
            and payload.get('status') == 'READY'
            and batch_capital_preview
            and batch_capital_preview.get('status') != 'READY'
        ):
            payload['status'] = 'BLOCKED'
            payload['message'] = batch_capital_preview.get('message') or payload.get('message') or ''
        return payload

    if procurement.status == procurement.Status.RECEIVED:
        return with_receive_context({
            'status': 'COMPLETE',
            'message': 'Приход полностью оприходован.',
        }, will_finish=True)

    if procurement.status not in (procurement.Status.OPEN, procurement.Status.PARTIALLY_RECEIVED):
        return with_receive_context({
            'status': 'NOT_OPEN',
            'message': f'Procurement is already {procurement.status}.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        })

    if not paid_items and not draft_items_count:
        return with_receive_context({
            'status': 'NO_ITEMS',
            'message': 'Procurement has no items.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        })

    if not paid_items:
        return with_receive_context({
            'status': 'DRAFT_PENDING',
            'message': 'Есть строки, но ещё нет оплаченных товаров для оприходования.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        })

    try:
        balance = procurement.balance
    except ProcurementBalance.DoesNotExist:
        return with_receive_context({
            'status': 'NO_BALANCE',
            'message': 'Procurement balance is missing.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        })

    required = _required_spend_by_currency(paid_items, paid_expenses)
    spent = _procurement_spend_by_currency(balance)
    missing = {
        currency: _q(amount - spent.get(currency, _ZERO))
        for currency, amount in required.items()
        if _q(amount - spent.get(currency, _ZERO)) > 0
    }
    balances = {
        str(currency).upper(): _q(Decimal(str(amount)))
        for currency, amount in (balance.balances or {}).items()
    }

    if missing:
        return with_receive_context({
            'status': 'COSTS_UNPAID',
            'message': 'Оплаченные позиции ещё не полностью списаны с баланса.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {key: str(value) for key, value in missing.items()},
            'suggested_withdrawals': [],
        })

    non_zero = {
        currency: amount for currency, amount in balances.items()
        if amount != 0
    }
    if not non_zero:
        return with_receive_context({
            'status': 'READY',
            'message': 'Ready to receive.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
        }, will_finish=bool(paid_items and not draft_items_count and not draft_expenses_count))

    if any(amount < 0 for amount in non_zero.values()):
        return with_receive_context({
            'status': 'CONTRIBUTION_REQUIRED',
            'message': 'Balance is negative; add contribution before receive.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
        })

    if draft_items_count or draft_expenses_count:
        return with_receive_context({
            'status': 'READY',
            'message': 'Можно оприходовать оплаченную партию. Остаток баланса останется в приходе для следующих строк.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
        }, will_finish=False)

    if procurement.agreement_id:
        plan = _agreement_surplus_return_plan(procurement=procurement, balances=non_zero)
        plan['balances'] = {key: str(value) for key, value in balances.items()}
        plan['missing_spend'] = {}
        plan['suggested_withdrawals'] = [
            {
                **item,
                'amount': str(_q(item['amount'])),
                'target_net_capital': str(_q(item['target_net_capital'])),
                'actual_net_capital': str(_q(item['actual_net_capital'])),
            }
            for item in plan.get('suggested_withdrawals', [])
        ]
        return with_receive_context(
            plan,
            will_finish=bool(paid_items and not draft_items_count and not draft_expenses_count),
        )

    plan = _surplus_withdrawal_plan(
        procurement=procurement,
        balance=balance,
        items=paid_items,
        expenses=paid_expenses,
        balances=non_zero,
    )
    plan['balances'] = {key: str(value) for key, value in balances.items()}
    plan['missing_spend'] = {}
    plan['suggested_withdrawals'] = [
        {
            **item,
            'amount': str(_q(item['amount'])),
            'target_net_capital': str(_q(item['target_net_capital'])),
            'actual_net_capital': str(_q(item['actual_net_capital'])),
        }
        for item in plan.get('suggested_withdrawals', [])
    ]
    return with_receive_context(
        plan,
        will_finish=bool(paid_items and not draft_items_count and not draft_expenses_count),
    )


def get_procurement_receive_plan(*, tenant_id: int, procurement_id: int, item_ids: list[int] | None = None) -> dict:
    from .models import Procurement

    procurement = (
        Procurement.objects
        .filter(tenant_id=tenant_id, pk=procurement_id)
        .select_related('balance', 'contract')
        .prefetch_related('items', 'expenses__targets', 'balance__withdrawals')
        .get()
    )
    return build_receive_plan(procurement, item_ids=item_ids)


def receive_procurement(
    *,
    tenant_id: int,
    procurement_id: int,
    destination_warehouse_id: int,
    item_ids: list[int] | None = None,
    capital_allocations: list[dict] | None = None,
    received_at=None,
):
    """
    Finalize a procurement: validate balance == 0, allocate landed cost,
    create Lot + LotStock for every item with an immutable contract_snapshot.
    """
    from apps.inventory.models import Lot, LotStock, StockMovement
    from .models import (
        Procurement, ProcurementExpense, ProcurementItem, ProcurementBalance, BalanceWithdrawal,
        InvestmentContract, ContractPartner, PartnerLedgerEntry,
        ProcurementPartnerLedger, ProcurementReceiveBatch, ProcurementReceiveBatchLine,
        ProcurementReceiveBatchExpense, ProcurementReceiveBatchCapitalAllocation,
    )

    if received_at is None:
        received_at = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(
                f'Cannot receive procurement in status {procurement.status}.'
            )

        is_partnership = procurement.procurement_type in _PARTNERSHIP_TYPES

        if is_partnership:
            balance = ProcurementBalance.objects.select_for_update().get(procurement=procurement)
            receive_plan = build_receive_plan(procurement)
            if receive_plan['status'] == 'AUTO_SURPLUS':
                from apps.finance.fx_rates import resolve_fx_rate_snapshot

                balances = dict(balance.balances or {})
                for suggestion in receive_plan['suggested_withdrawals']:
                    amount = _q(Decimal(str(suggestion['amount'])))
                    if amount <= 0:
                        continue
                    currency = str(suggestion['currency']).upper()
                    current = _balance_get(balances, currency)
                    if current < amount:
                        raise ValueError(
                            f'Cannot auto-adjust {currency}: have {current}, need {amount}.'
                        )
                    fx_rate = resolve_fx_rate_snapshot(
                        tenant_id=tenant_id,
                        operation_currency=currency,
                        operation_at=received_at,
                    )
                    _balance_set(balances, currency, current - amount)
                    withdrawal = BalanceWithdrawal.objects.create(
                        tenant_id=tenant_id,
                        balance=balance,
                        partner_id=suggestion['partner_id'],
                        amount=amount,
                        currency=currency,
                        fx_rate=fx_rate,
                        date=received_at,
                        reason='Auto surplus return before receive',
                    )
                    ledger = get_or_create_ledger(
                        procurement_id=procurement.pk,
                        partner_id=suggestion['partner_id'],
                        tenant_id=tenant_id,
                    )
                    append_ledger_entry(
                        ledger=ledger,
                        entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
                        amount=amount,
                        currency=currency,
                        fx_rate=fx_rate,
                        source_ref=f'withdrawal:{withdrawal.pk}',
                        date=received_at,
                    )
                balance.balances = balances
                balance.save(update_fields=['balances', 'updated_at'])
                procurement._state.fields_cache.pop('balance', None)
                receive_plan = build_receive_plan(procurement)
            elif receive_plan['status'] == 'AGREEMENT_SURPLUS':
                from apps.finance.fx_rates import resolve_fx_rate_snapshot
                from .models import AgreementAllocation, InvestmentAgreement

                if not procurement.agreement_id:
                    raise ValueError('Linked agreement is missing for surplus return.')
                agreement = InvestmentAgreement.objects.select_for_update().get(
                    pk=procurement.agreement_id,
                    tenant_id=tenant_id,
                )
                balances = dict(balance.balances or {})
                for suggestion in receive_plan['suggested_withdrawals']:
                    amount = _q(Decimal(str(suggestion['amount'])))
                    if amount <= 0:
                        continue
                    currency = str(suggestion['currency']).upper()
                    current = _balance_get(balances, currency)
                    if current < amount:
                        raise ValueError(
                            f'Cannot return {currency}: have {current}, need {amount}.'
                        )
                    fx_rate = resolve_fx_rate_snapshot(
                        tenant_id=tenant_id,
                        operation_currency=currency,
                        operation_at=received_at,
                    )
                    _balance_set(balances, currency, current - amount)
                    withdrawal = BalanceWithdrawal.objects.create(
                        tenant_id=tenant_id,
                        balance=balance,
                        partner_id=suggestion['partner_id'],
                        amount=amount,
                        currency=currency,
                        fx_rate=fx_rate,
                        date=received_at,
                        reason='Return surplus to parent investment agreement before receive',
                    )
                    AgreementAllocation.objects.create(
                        tenant_id=tenant_id,
                        agreement=agreement,
                        procurement=procurement,
                        partner_id=suggestion['partner_id'],
                        direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
                        amount=amount,
                        currency=currency,
                        fx_rate=fx_rate,
                        date=received_at,
                        notes=f'withdrawal:{withdrawal.pk}',
                    )
                    _mutate_agreement_balance(agreement, currency, amount)
                    ledger = get_or_create_ledger(
                        procurement_id=procurement.pk,
                        partner_id=suggestion['partner_id'],
                        tenant_id=tenant_id,
                    )
                    append_ledger_entry(
                        ledger=ledger,
                        entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
                        amount=amount,
                        currency=currency,
                        fx_rate=fx_rate,
                        source_ref=f'withdrawal:{withdrawal.pk}',
                        date=received_at,
                    )
                balance.balances = balances
                balance.save(update_fields=['balances', 'updated_at'])
                procurement._state.fields_cache.pop('balance', None)
                receive_plan = build_receive_plan(procurement)

            if receive_plan['status'] != 'READY':
                raise ValueError(
                    f"Cannot receive: {receive_plan['message']}"
                )

        paid_items = list(
            ProcurementItem.objects
            .filter(
                tenant_id=tenant_id,
                procurement=procurement,
                status=ProcurementItem.Status.PAID,
            )
            .select_for_update()
        )
        requested_item_ids = {int(item_id) for item_id in item_ids or []}
        if requested_item_ids:
            items = [item for item in paid_items if item.pk in requested_item_ids]
            found_item_ids = {item.pk for item in items}
            missing_item_ids = requested_item_ids - found_item_ids
            if missing_item_ids:
                raise ValueError(
                    'Some selected items are not paid or do not belong to this procurement.'
                )
        else:
            items = paid_items

        if not items:
            raise ValueError('Procurement has no paid items.')

        selected_item_ids = {item.pk for item in items}
        draft_item_ids = set(
            ProcurementItem.objects
            .filter(
                tenant_id=tenant_id,
                procurement=procurement,
                status=ProcurementItem.Status.DRAFT,
            )
            .values_list('pk', flat=True)
        )
        delayed_item_ids = ({item.pk for item in paid_items} | draft_item_ids) - selected_item_ids
        is_partial_receive = bool(delayed_item_ids)
        paid_expenses = list(
            procurement.expenses
            .filter(status=ProcurementExpense.Status.PAID)
            .prefetch_related('targets')
        )
        expenses_for_receive = paid_expenses
        if is_partial_receive:
            expenses_for_receive = []
            for expense in paid_expenses:
                target_ids = {target.item_id for target in expense.targets.all()}
                if not target_ids:
                    raise ValueError(
                        'Для частичного оприходования у каждого оплаченного расхода должны быть выбраны товары.'
                    )
                touches_selected = bool(target_ids & selected_item_ids)
                touches_delayed = bool(target_ids & delayed_item_ids)
                if touches_selected and touches_delayed:
                    raise ValueError(
                        'Расход привязан и к выбранным, и к отложенным товарам. Разделите расход или уточните позиции расхода.'
                    )
                if touches_selected:
                    expenses_for_receive.append(expense)
            draft_expenses = list(
                procurement.expenses
                .filter(status=ProcurementExpense.Status.DRAFT)
                .prefetch_related('targets')
            )
            for expense in draft_expenses:
                target_ids = {target.item_id for target in expense.targets.all()}
                if not target_ids:
                    raise ValueError(
                        'Для частичного оприходования у каждого неоплаченного расхода тоже должны быть выбраны товары.'
                    )
                if target_ids & selected_item_ids:
                    raise ValueError(
                        'Есть неоплаченный расход для выбранных товаров. Сначала оплатите расход или перенесите его на отложенные позиции.'
                    )
        else:
            has_draft_expenses = ProcurementExpense.objects.filter(
                tenant_id=tenant_id,
                procurement=procurement,
                status=ProcurementExpense.Status.DRAFT,
            ).exists()
            if has_draft_expenses:
                raise ValueError(
                    'Перед завершением прихода оплатите или удалите черновики расходов.'
                )

        items_value_uzs = [
            _item_value_uzs(item)
            for item in items
        ]
        expense_allocations_uzs = _landed_expense_allocations(
            items,
            expenses_for_receive,
        )
        expenses_total_uzs = sum(expense_allocations_uzs, _ZERO)
        total_inventory_uzs = sum(items_value_uzs) + expenses_total_uzs

        contract_snapshot = {}
        batch_allocation_rows: list[dict] = []
        if is_partnership:
            contract_snapshot, batch_allocation_rows = _resolve_batch_capital_snapshot(
                procurement=procurement,
                items=items,
                expenses=expenses_for_receive,
                raw_allocations=capital_allocations,
                is_partial_receive=is_partial_receive,
                received_at=received_at,
            )

        receive_batch = ProcurementReceiveBatch.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            warehouse_id=destination_warehouse_id,
            received_at=received_at,
            items_count=len(items),
            total_inventory_uzs=total_inventory_uzs,
        )
        for row in batch_allocation_rows:
            ProcurementReceiveBatchCapitalAllocation.objects.create(
                tenant_id=tenant_id,
                batch=receive_batch,
                partner_id=row['partner_id'],
                role=row['role'],
                amount_contract_currency=row['amount_contract_currency'],
                capital_share=row['capital_share'],
                profit_share=row['profit_share'],
            )

        # Create Lot + LotStock per item.
        for item, allocated_expense_uzs in zip(items, expense_allocations_uzs):
            item_unit_price_uzs = (
                Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
            ).quantize(Decimal('0.01'))
            qty = int(Decimal(str(item.quantity)))
            if qty <= 0:
                continue
            landed_per_unit = (
                item_unit_price_uzs + (allocated_expense_uzs / qty)
            ).quantize(Decimal('0.01'))

            lot = Lot.objects.create(
                tenant_id=tenant_id,
                procurement_item=item,
                product_variant_id=item.product_variant_id,
                quantity_initial=qty,
                unit_purchase_price=item_unit_price_uzs,
                landed_cost_per_unit=landed_per_unit,
                contract_snapshot=contract_snapshot,
                received_at=received_at,
                is_active=True,
            )
            LotStock.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                warehouse_id=destination_warehouse_id,
                quantity_remaining=qty,
            )
            StockMovement.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity=qty,
                to_location_id=destination_warehouse_id,
                reference_type='procurement',
                reference_id=procurement.pk,
            )
            ProcurementReceiveBatchLine.objects.create(
                tenant_id=tenant_id,
                batch=receive_batch,
                item=item,
                lot=lot,
                quantity=item.quantity,
                unit_purchase_price_uzs=item_unit_price_uzs,
                allocated_expense_uzs=_q(allocated_expense_uzs),
                landed_cost_per_unit_uzs=landed_per_unit,
            )

        for expense in expenses_for_receive:
            amount_uzs = _expense_value_uzs(expense)
            ProcurementReceiveBatchExpense.objects.create(
                tenant_id=tenant_id,
                batch=receive_batch,
                expense=expense,
                allocated_amount_uzs=amount_uzs,
            )

        ProcurementItem.objects.filter(pk__in=[item.pk for item in items]).update(
            status=ProcurementItem.Status.RECEIVED,
            updated_at=received_at,
        )
        if expenses_for_receive:
            ProcurementExpense.objects.filter(
                pk__in=[expense.pk for expense in expenses_for_receive],
            ).update(status=ProcurementExpense.Status.RECEIVED, updated_at=received_at)

        has_pending_items = ProcurementItem.objects.filter(
            tenant_id=tenant_id,
            procurement=procurement,
            status__in=[ProcurementItem.Status.DRAFT, ProcurementItem.Status.PAID],
        ).exists()
        has_pending_expenses = ProcurementExpense.objects.filter(
            tenant_id=tenant_id,
            procurement=procurement,
            status__in=[ProcurementExpense.Status.DRAFT, ProcurementExpense.Status.PAID],
        ).exists()
        if has_pending_items or has_pending_expenses:
            procurement.status = Procurement.Status.PARTIALLY_RECEIVED
            procurement.save(update_fields=['status', 'updated_at'])
        else:
            procurement.status = Procurement.Status.RECEIVED
            procurement.received_at = received_at
            procurement.save(update_fields=['status', 'received_at', 'updated_at'])

        if total_inventory_uzs > 0:
            create_journal_entry(
                tenant_id=tenant_id,
                operation_type='receipt',
                operation_id=procurement.pk,
                lines=[
                    {
                        'account_code': '1100',
                        'debit': total_inventory_uzs,
                        'credit': Decimal('0'),
                        'description': f'Procurement #{procurement.pk} inventory receipt',
                    },
                    {
                        'account_code': _resolve_procurement_credit_account(procurement.procurement_type),
                        'debit': Decimal('0'),
                        'credit': total_inventory_uzs,
                        'description': f'Procurement #{procurement.pk} funding source',
                    },
                ],
                description=f'Procurement #{procurement.pk} batch #{receive_batch.pk} received',
                date=received_at,
            )

        publish_event(
            event_type='procurement.received',
            payload={
                'procurement_id': procurement.pk,
                'receive_batch_id': receive_batch.pk,
                'destination_warehouse_id': destination_warehouse_id,
                'items_count': len(items),
            },
            tenant_id=tenant_id,
        )

    return procurement


# ─── Ledger ────────────────────────────────────────────────────────────────────

def get_or_create_ledger(
    *,
    procurement_id: int,
    partner_id: int,
    tenant_id: int,
):
    """Get (or lazily create) a ProcurementPartnerLedger."""
    from .models import ProcurementPartnerLedger
    ledger, _ = ProcurementPartnerLedger.objects.get_or_create(
        tenant_id=tenant_id,
        procurement_id=procurement_id,
        partner_id=partner_id,
    )
    return ledger


def append_ledger_entry(
    *,
    ledger,
    entry_type: str,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    source_ref: str = '',
    date=None,
):
    """
    Append an immutable entry to a ProcurementPartnerLedger.
    Always call inside a transaction.atomic().
    """
    from .models import PartnerLedgerEntry
    if date is None:
        date = timezone.now()
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    return PartnerLedgerEntry.objects.create(
        tenant_id=ledger.tenant_id,
        ledger=ledger,
        date=date,
        amount=amount,
        currency=currency,
        fx_rate=fx_rate,
        functional_amount_uzs=_functional_uzs(amount, currency, fx_rate),
        entry_type=entry_type,
        source_ref=source_ref,
    )


def _resolve_procurement_credit_account(procurement_type: str) -> str:
    if procurement_type == 'MUSHARAKA':
        return '3110'
    if procurement_type == 'PARTNERSHIP':
        return '3100'
    if procurement_type == 'DISTRIBUTOR':
        return '2200'
    return '1000'


def _empty_ledger_totals() -> dict:
    return {
        'capital_in': Decimal('0'),
        'capital_out': Decimal('0'),
        'capital_net': Decimal('0'),
        'profit_accrued': Decimal('0'),
        'profit_reversed': Decimal('0'),
        'losses_incurred': Decimal('0'),
        'dividends_paid': Decimal('0'),
        'profit_pending_payout': Decimal('0'),
    }


def _entry_key(entry_type: str) -> str | None:
    return {
        'CAPITAL_IN': 'capital_in',
        'CAPITAL_OUT': 'capital_out',
        'PROFIT_ACCRUED': 'profit_accrued',
        'PROFIT_REVERSED': 'profit_reversed',
        'LOSS_INCURRED': 'losses_incurred',
        'DIVIDEND_PAID': 'dividends_paid',
    }.get(entry_type)


def _finalize_ledger_totals(totals: dict) -> dict:
    totals['capital_net'] = _q(totals['capital_in'] - totals['capital_out'])
    profit_net = (
        totals['profit_accrued']
        - totals['profit_reversed']
        - totals['losses_incurred']
    )
    totals['profit_pending_payout'] = _q(
        max(Decimal('0'), profit_net - totals['dividends_paid'])
    )
    return totals


def get_partner_aggregate(
    partner_id: int,
    tenant_id: int,
    procurement_id: int | None = None,
) -> dict:
    """
    Compute partner summary across all procurements — replaces InvestorSummary.
    Returns:
    {
        capital_in, capital_out, profit_accrued, profit_reversed,
        dividends_paid, losses_incurred, profit_pending_payout
    }
    Flat legacy totals are functional UZS. Native amounts are returned in
    by_currency to avoid mixing USD and UZS in investor-facing reporting.
    """
    from .models import PartnerLedgerEntry, ProcurementPartnerLedger

    ledger_qs = ProcurementPartnerLedger.objects.filter(
        partner_id=partner_id,
        tenant_id=tenant_id,
    )
    if procurement_id is not None:
        ledger_qs = ledger_qs.filter(procurement_id=procurement_id)
    ledger_ids = ledger_qs.values_list('id', flat=True)

    functional_rows = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type')
        .annotate(total=models.Sum('functional_amount_uzs'))
    )
    functional_uzs = _empty_ledger_totals()
    for row in functional_rows:
        key = _entry_key(row['entry_type'])
        if key:
            functional_uzs[key] = _q(row['total'] or Decimal('0'))
    functional_uzs = _finalize_ledger_totals(functional_uzs)

    currency_rows = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type', 'currency')
        .annotate(total=models.Sum('amount'))
    )
    by_currency: dict[str, dict] = {}
    for row in currency_rows:
        currency = str(row['currency'] or 'UZS').upper()
        key = _entry_key(row['entry_type'])
        if not key:
            continue
        totals = by_currency.setdefault(currency, _empty_ledger_totals())
        totals[key] = _q(row['total'] or Decimal('0'))

    for currency, totals in list(by_currency.items()):
        by_currency[currency] = _finalize_ledger_totals(totals)

    return {
        **functional_uzs,
        'summary_currency': 'UZS',
        'functional_uzs': functional_uzs,
        'by_currency': by_currency,
    }


def pay_dividend(
    *,
    partner_id: int,
    procurement_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    from_account_id: int | None = None,
    tenant_id: int,
    date=None,
):
    """
    Record a dividend payout to a partner.
    Invariant: amount <= profit_pending_payout for this procurement.
    Raises ValueError if invariant violated.
    """
    from .models import DividendPayment, ProcurementPartnerLedger, PartnerLedgerEntry

    if date is None:
        date = timezone.now()

    with transaction.atomic():
        ledger = get_or_create_ledger(
            procurement_id=procurement_id,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )

        # Compute pending payout for this specific procurement
        agg = (
            PartnerLedgerEntry.objects
            .filter(ledger=ledger)
            .values('entry_type')
            .annotate(total=models.Sum('functional_amount_uzs'))
        )
        totals = {row['entry_type']: row['total'] or Decimal('0') for row in agg}

        profit_net = (
            totals.get('PROFIT_ACCRUED', Decimal('0'))
            - totals.get('PROFIT_REVERSED', Decimal('0'))
            - totals.get('LOSS_INCURRED', Decimal('0'))
        )
        already_paid = totals.get('DIVIDEND_PAID', Decimal('0'))
        pending = max(Decimal('0'), profit_net - already_paid)

        payment_functional_uzs = _functional_uzs(amount, currency, fx_rate)
        if payment_functional_uzs > pending:
            raise ValueError(
                f'Dividend amount {payment_functional_uzs} UZS exceeds pending payout {pending} UZS '
                f'for partner {partner_id}, procurement {procurement_id}.'
            )

        payment = DividendPayment.objects.create(
            tenant_id=tenant_id,
            partner_id=partner_id,
            procurement_id=procurement_id,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            paid_from_account_id=from_account_id,
            date=date,
        )

        cash_entry = None
        if from_account_id is not None:
            account = CashAccount.objects.select_for_update().get(
                pk=from_account_id,
                tenant_id=tenant_id,
            )
            if account.currency != currency:
                raise ValueError(
                    f'Dividend currency {currency} does not match cash account '
                    f'{account.name} currency {account.currency}.'
                )
            if account.balance < amount:
                raise ValueError(
                    f'Insufficient cash in {account.name}: have {account.balance}, need {amount}.'
                )
            cash_entry = create_cash_entry(
                tenant_id=tenant_id,
                account=account,
                direction=CashEntry.Direction.OUT,
                amount=amount,
                date=date,
                source_ref_type='dividend_payment',
                source_ref_id=payment.pk,
            )

        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            source_ref=f'dividend_payment:{payment.pk}',
            date=date,
        )

        if cash_entry is not None and cash_entry.account.linked_account_id:
            record_journal_from_cash_entry(
                tenant_id=tenant_id,
                cash_entry=cash_entry,
                operation_type='payment',
                operation_id=payment.pk,
                counterpart_account_code='2100',
                description=f'Dividend payment #{payment.pk}',
                date=date,
            )

        publish_event(
            event_type='partnership.dividend_paid',
            payload={
                'payment_id': payment.pk,
                'partner_id': partner_id,
                'procurement_id': procurement_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )

    return payment
