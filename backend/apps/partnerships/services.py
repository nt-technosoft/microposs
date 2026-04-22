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

    from apps.finance.services import get_fx_rate_for_date

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


def _procurement_spend_by_currency(balance) -> dict[str, Decimal]:
    spent: dict[str, Decimal] = {}
    for withdrawal in balance.withdrawals.filter(partner_id__isnull=True):
        _money_by_currency_add(spent, withdrawal.currency, Decimal(str(withdrawal.amount)))
    return spent


def _landed_expense_allocations(items: list, expenses: list) -> list[Decimal]:
    allocations = [_ZERO for _ in items]
    if not items:
        return allocations

    item_values = [_item_value_uzs(item) for item in items]
    item_quantities = [Decimal(str(item.quantity)) for item in items]

    for expense in expenses:
        amount_uzs = _expense_value_uzs(expense)
        method = str(expense.allocation_method)
        if method == 'BY_VALUE':
            bases = item_values
        else:
            # BY_WEIGHT falls back to quantity until item weights exist.
            bases = item_quantities

        for index, allocation in enumerate(_allocate_amount(amount_uzs, bases)):
            allocations[index] = _q(allocations[index] + allocation)
    return allocations


def _landed_cost_preview_block(items: list, expenses: list) -> dict:
    allocations = _landed_expense_allocations(items, expenses)
    lines: list[dict] = []
    total_expenses_uzs = sum((_expense_value_uzs(expense) for expense in expenses), _ZERO)
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


def build_procurement_cost_preview(procurement) -> dict:
    all_items = list(procurement.items.all())
    all_expenses = list(procurement.expenses.all())
    paid_items = [item for item in all_items if item.status == item.Status.PAID]
    paid_expenses = [expense for expense in all_expenses if expense.status == expense.Status.PAID]
    draft_items = [item for item in all_items if item.status == item.Status.DRAFT]
    draft_expenses = [expense for expense in all_expenses if expense.status == expense.Status.DRAFT]

    preview = {
        'receive_basis': _landed_cost_preview_block(paid_items, paid_expenses),
        'if_all_current_lines_paid': _landed_cost_preview_block(all_items, all_expenses),
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
    mudaraba_ratio = Decimal(str(mudaraba_ratio))
    investor_capital_total = sum(
        (
            Decimal(str(partner.get('capital_share', '0')))
            for partner in partners_meta
            if partner.get('role') == 'INVESTOR'
        ),
        _ZERO,
    )
    operator = next(
        (partner for partner in partners_meta if partner.get('role') == 'OPERATOR'),
        None,
    )

    result: dict[int, Decimal] = {}
    for partner in partners_meta:
        partner_id = int(partner['partner_id'])
        capital_share = Decimal(str(partner.get('capital_share', '0')))
        role = partner.get('role')
        if role == 'INVESTOR':
            share = capital_share * mudaraba_ratio
        elif role == 'OPERATOR':
            share = capital_share + ((Decimal('1') - mudaraba_ratio) * investor_capital_total)
        else:
            share = _ZERO
        result[partner_id] = _q_ratio(share)

    if operator is not None:
        distributed = sum(result.values(), _ZERO)
        residue = _q_ratio(Decimal('1') - distributed)
        if residue:
            operator_id = int(operator['partner_id'])
            result[operator_id] = _q_ratio(result.get(operator_id, _ZERO) + residue)
    return result


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
    from .models import ProcurementExpense, ProcurementItem

    item_queryset = procurement.items.all()
    expense_queryset = procurement.expenses.all()
    if draft_only:
        item_queryset = item_queryset.filter(status=ProcurementItem.Status.DRAFT)
        expense_queryset = expense_queryset.filter(status=ProcurementExpense.Status.DRAFT)

    item_queryset.delete()
    expense_queryset.delete()

    for item in items or []:
        ProcurementItem.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            product_variant_id=item['product_variant_id'],
            quantity=Decimal(str(item['quantity'])),
            unit_purchase_price=Decimal(str(item['unit_purchase_price'])),
            currency=str(item.get('currency', 'UZS')).upper(),
            fx_rate=Decimal(str(item.get('fx_rate', '1'))),
            status=ProcurementItem.Status.DRAFT,
        )

    for expense in expenses or []:
        ProcurementExpense.objects.create(
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


def open_procurement(
    *,
    tenant_id: int,
    procurement_type: str,
    opened_at=None,
    supplier_id: int | None = None,
    notes: str = '',
    client_request_id: str | None = None,
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
        InvestmentContract, ContractPartner, ProcurementBalance,
    )

    if opened_at is None:
        opened_at = timezone.now()
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
    notes: str = '',
    contract: dict | None = None,
    items: list[dict] | None = None,
    expenses: list[dict] | None = None,
):
    from .models import InvestmentContract, Procurement

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
        if procurement.status != Procurement.Status.OPEN:
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
            or incoming_contract != current_contract
        )
        if contract_changed and _has_balance_activity(procurement):
            raise ValueError(
                'Нельзя менять тип или договор после движения денег по балансу прихода.'
            )

        procurement.procurement_type = procurement_type
        procurement.supplier_id = supplier_id
        procurement.notes = notes
        procurement.save(update_fields=['procurement_type', 'supplier', 'notes', 'updated_at'])

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
        Procurement, ProcurementBalance, BalanceContribution,
        PartnerLedgerEntry,
    )

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
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot contribute to procurement in status {procurement.status}.'
            )

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
        if procurement.status != Procurement.Status.OPEN:
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
        if procurement.status != Procurement.Status.OPEN:
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
    reason: str = '',
):
    from .models import Procurement, ProcurementBalance, ProcurementItem

    payment_reason = reason or 'Item payment from procurement balance'

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id,
            tenant_id=tenant_id,
        )
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot pay procurement items in status {procurement.status}.'
            )

        draft_items = list(
            ProcurementItem.objects.select_for_update().filter(
                tenant_id=tenant_id,
                procurement=procurement,
                status=ProcurementItem.Status.DRAFT,
            )
        )
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
        if procurement.status != Procurement.Status.OPEN:
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


def build_receive_plan(procurement) -> dict:
    """
    Explain whether a procurement can be received and which balancing action is needed.
    """
    from .models import ProcurementBalance

    if procurement.status != procurement.Status.OPEN:
        return {
            'status': 'NOT_OPEN',
            'message': f'Procurement is already {procurement.status}.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        }

    all_items = list(procurement.items.all())
    all_expenses = list(procurement.expenses.all())
    paid_items = [item for item in all_items if item.status == item.Status.PAID]
    paid_expenses = [expense for expense in all_expenses if expense.status == expense.Status.PAID]
    draft_items_count = sum(1 for item in all_items if item.status == item.Status.DRAFT)
    draft_expenses_count = sum(1 for expense in all_expenses if expense.status == expense.Status.DRAFT)

    if not paid_items and not draft_items_count:
        return {
            'status': 'NO_ITEMS',
            'message': 'Procurement has no items.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
            'draft_items_count': 0,
            'draft_expenses_count': draft_expenses_count,
        }

    try:
        balance = procurement.balance
    except ProcurementBalance.DoesNotExist:
        return {
            'status': 'NO_BALANCE',
            'message': 'Procurement balance is missing.',
            'balances': {},
            'missing_spend': {},
            'suggested_withdrawals': [],
        }

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
        return {
            'status': 'COSTS_UNPAID',
            'message': 'Оплаченные позиции ещё не полностью списаны с баланса.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {key: str(value) for key, value in missing.items()},
            'suggested_withdrawals': [],
            'draft_items_count': draft_items_count,
            'draft_expenses_count': draft_expenses_count,
        }

    if draft_items_count or draft_expenses_count:
        return {
            'status': 'DRAFT_PENDING',
            'message': 'Есть неоплаченные черновики товаров или расходов.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
            'draft_items_count': draft_items_count,
            'draft_expenses_count': draft_expenses_count,
        }

    non_zero = {
        currency: amount for currency, amount in balances.items()
        if amount != 0
    }
    if not non_zero:
        return {
            'status': 'READY',
            'message': 'Ready to receive.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
            'draft_items_count': 0,
            'draft_expenses_count': 0,
        }

    if any(amount < 0 for amount in non_zero.values()):
        return {
            'status': 'CONTRIBUTION_REQUIRED',
            'message': 'Balance is negative; add contribution before receive.',
            'balances': {key: str(value) for key, value in balances.items()},
            'missing_spend': {},
            'suggested_withdrawals': [],
            'draft_items_count': 0,
            'draft_expenses_count': 0,
        }

    plan = _surplus_withdrawal_plan(
        procurement=procurement,
        balance=balance,
        items=paid_items,
        expenses=paid_expenses,
        balances=non_zero,
    )
    plan['balances'] = {key: str(value) for key, value in balances.items()}
    plan['missing_spend'] = {}
    plan['draft_items_count'] = 0
    plan['draft_expenses_count'] = 0
    plan['suggested_withdrawals'] = [
        {
            **item,
            'amount': str(_q(item['amount'])),
            'target_net_capital': str(_q(item['target_net_capital'])),
            'actual_net_capital': str(_q(item['actual_net_capital'])),
        }
        for item in plan.get('suggested_withdrawals', [])
    ]
    return plan


def get_procurement_receive_plan(*, tenant_id: int, procurement_id: int) -> dict:
    from .models import Procurement

    procurement = (
        Procurement.objects
        .filter(tenant_id=tenant_id, pk=procurement_id)
        .select_related('balance', 'contract')
        .prefetch_related('items', 'expenses', 'balance__withdrawals')
        .get()
    )
    return build_receive_plan(procurement)


def receive_procurement(
    *,
    tenant_id: int,
    procurement_id: int,
    destination_warehouse_id: int,
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
        ProcurementPartnerLedger,
    )

    if received_at is None:
        received_at = timezone.now()

    with transaction.atomic():
        procurement = Procurement.objects.select_for_update().get(
            pk=procurement_id, tenant_id=tenant_id,
        )
        if procurement.status != Procurement.Status.OPEN:
            raise ValueError(
                f'Cannot receive procurement in status {procurement.status}.'
            )

        is_partnership = procurement.procurement_type in _PARTNERSHIP_TYPES

        if is_partnership:
            balance = ProcurementBalance.objects.select_for_update().get(procurement=procurement)
            receive_plan = build_receive_plan(procurement)
            if receive_plan['status'] == 'AUTO_SURPLUS':
                from apps.finance.services import resolve_fx_rate_snapshot

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

            if receive_plan['status'] != 'READY':
                raise ValueError(
                    f"Cannot receive: {receive_plan['message']}"
                )

        items = list(
            ProcurementItem.objects
            .filter(
                tenant_id=tenant_id,
                procurement=procurement,
                status=ProcurementItem.Status.PAID,
            )
            .select_for_update()
        )
        if not items:
            raise ValueError('Procurement has no paid items.')

        items_value_uzs = [
            _item_value_uzs(item)
            for item in items
        ]
        expense_allocations_uzs = _landed_expense_allocations(
            items,
            list(procurement.expenses.filter(status=ProcurementExpense.Status.PAID)),
        )
        expenses_total_uzs = sum(expense_allocations_uzs, _ZERO)

        # Build contract snapshot from actual CAPITAL_IN (not planned).
        contract_snapshot = {}
        if is_partnership:
            contract = InvestmentContract.objects.get(procurement=procurement)
            mudaraba_ratio = Decimal(str(contract.mudaraba_ratio))
            partners = list(ContractPartner.objects.filter(contract=contract))

            ledgers = (
                ProcurementPartnerLedger.objects
                .filter(procurement=procurement, tenant_id=tenant_id)
                .prefetch_related('entries')
            )
            contract_currency = str(contract.currency or 'UZS').upper()
            actual_capital = _capital_by_partner(
                ledgers,
                PartnerLedgerEntry,
                tenant_id=tenant_id,
                target_currency=contract_currency,
            )

            total_capital = sum(actual_capital.values()) or Decimal('1')

            partners_meta = []
            for cp in partners:
                cap = actual_capital.get(cp.partner_id, Decimal('0'))
                capital_share = _q_ratio(cap / total_capital)
                partners_meta.append({
                    'partner_id': cp.partner_id,
                    'role': cp.role,
                    'capital_amount_contract_currency': str(_q(cap)),
                    'capital_share': str(capital_share),
                })
            profit_shares = _profit_shares_from_capital(partners_meta, mudaraba_ratio)
            for item in partners_meta:
                item['profit_share'] = str(profit_shares[int(item['partner_id'])])

            contract_snapshot = {
                'contract_currency': contract_currency,
                'mudaraba_ratio': str(_q_ratio(mudaraba_ratio)),
                'loss_rule': contract.loss_rule,
                'partners': partners_meta,
            }

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

        procurement.status = Procurement.Status.RECEIVED
        procurement.received_at = received_at
        procurement.save(update_fields=['status', 'received_at', 'updated_at'])

        total_inventory_uzs = sum(items_value_uzs) + expenses_total_uzs
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
                description=f'Procurement #{procurement.pk} received',
                date=received_at,
            )

        publish_event(
            event_type='procurement.received',
            payload={
                'procurement_id': procurement.pk,
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
