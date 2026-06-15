"""workspace_funding.py — cluster B: agreement + capital funding layer.

create_and_link_workspace_agreement, link_workspace_agreement,
record_workspace_capital_contribution, convert_workspace_capital_pool,
allocate_workspace_capital, build_workspace_capital_allocation_preview,
and the private helpers they need exclusively (_resolve_workspace_capital_snapshot,
_pre_allocate_at_receipt_partnership_capital, _procurement_capital_available_by_partner,
_auto_capital_amounts, _spend_allocated_partnership_capital).

No cross-import from workspace.py (shell). Imports only from workspace_common,
apps.finance, apps.partnerships.*, and workspace_support.

Audit reference: E18 Фаза 2 / T-2.4 (step c).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import CashAccount, Payment
from apps.finance.services import record_capital_pool_payment
from apps.partnerships.formulas import profit_shares_from_capital

from .models import (
    AgreementActionSource,
    AgreementAllocation,
    AgreementConfirmationStatus,
    AgreementContribution,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementExpense,
    ProcurementItem,
    ProcurementReceiveBatchCapitalAllocation,
)
from .procurement_cost import (
    active_procurement_lines,
    procurement_cost_by_currency,
)
from .workspace_common import (
    _agreement_available_by_partner,
    _amount_uzs_to_currency,
    _ensure_source_editable,
    _item_value_uzs,
    _receive_funding_breakdown,
    _remaining_obligation_cost_uzs,
    _require_workspace_agreement,
    _with_client_request_id,
)
from .workspace_support import (
    add_agreement_contribution,
    append_ledger_entry,
    create_investment_agreement,
    get_or_create_ledger,
    record_agreement_event,
)


def create_and_link_workspace_agreement(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
    user_id: int | None = None,
) -> InvestmentAgreement:
    if procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        _ensure_source_editable(procurement)

    agreement = create_investment_agreement(
        tenant_id=tenant_id,
        supplier_id=payload.get('supplier_id') or procurement.supplier_id,
        mudaraba_ratio=Decimal(str(payload.get('mudaraba_ratio', '0'))),
        planned_budget=Decimal(str(payload.get('planned_budget', '0'))),
        currency=payload.get('currency', 'UZS'),
        notes=payload.get('notes', ''),
        reconciliation_mode=payload.get('reconciliation_mode') or 'FACTUAL',
        client_request_id=client_request_id,
        created_by_id=user_id,
        partners=payload.get('partners') or [],
    )
    if payload.get('legal_mode'):
        agreement.legal_mode = payload['legal_mode']
        agreement.save(update_fields=['legal_mode', 'updated_at'])
    link_workspace_agreement(
        tenant_id=tenant_id,
        procurement=procurement,
        agreement_id=agreement.id,
    )
    return agreement


def link_workspace_agreement(
    *,
    tenant_id: int,
    procurement: Procurement,
    agreement_id: int | None,
) -> None:
    if not agreement_id:
        raise ValueError('agreement_id is required.')
    _ensure_source_editable(procurement)
    InvestmentAgreement.objects.get(pk=agreement_id, tenant_id=tenant_id)
    Procurement.objects.filter(pk=procurement.pk, tenant_id=tenant_id).update(
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        agreement_id=agreement_id,
        updated_at=timezone.now(),
    )


def record_workspace_capital_contribution(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
    user_id: int | None = None,
) -> AgreementContribution:
    """E11: record a contribution that moves real cash into the capital pool.

    Modes (the money always lands in the agreement pool):
      - external (default): investor or business brings new money from outside;
        no operating account is touched.
      - turnover (mode=BUSINESS_FROM_TURNOVER): the business commits money it
        already holds — `from_cash_account_id` (operating account) → pool.
    """
    agreement = _require_workspace_agreement(procurement)
    mode = str(payload.get('mode') or '').upper()
    from_cash_account_id = payload.get('from_cash_account_id')
    if mode in ('BUSINESS_FROM_TURNOVER', 'TURNOVER'):
        from_cash_account_id = from_cash_account_id or payload.get('cash_account_id')
        if not from_cash_account_id:
            raise ValueError('from_cash_account_id is required for a turnover contribution.')
    from_cash_account_id = int(from_cash_account_id) if from_cash_account_id else None
    notes = payload.get('notes', '')
    raw_fx = payload.get('fx_rate')
    fx_rate = Decimal(str(raw_fx)) if raw_fx not in (None, '', '0', 0) else None
    return add_agreement_contribution(
        tenant_id=tenant_id,
        agreement_id=agreement.id,
        partner_id=int(payload['partner_id']),
        amount=Decimal(str(payload['amount'])),
        currency=payload.get('currency', agreement.currency),
        fx_rate=fx_rate,
        date=payload.get('date') or payload.get('paid_at'),
        notes=notes,
        client_request_id=client_request_id,
        created_by_id=user_id,
        from_cash_account_id=from_cash_account_id,
        source=AgreementActionSource.BUSINESS_RECORDED,
        confirmation_status=AgreementConfirmationStatus.CONFIRMED,
    )


def convert_workspace_capital_pool(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
):
    """E12: real spot conversion of agreement base-currency pool into another
    currency, so the pool can pay costs in that currency. Records a FIFO
    cost-basis lot. `rate` is held-currency per 1 base currency.
    """
    from apps.partnerships.multicurrency import convert_agreement_pool

    agreement = _require_workspace_agreement(procurement)
    to_currency = payload.get('to_currency') or payload.get('currency')
    if not to_currency:
        raise ValueError('to_currency is required for capital pool conversion.')
    if payload.get('from_amount') is None:
        raise ValueError('from_amount is required for capital pool conversion.')
    if payload.get('rate') is None:
        raise ValueError('rate is required for capital pool conversion.')
    return convert_agreement_pool(
        tenant_id=tenant_id,
        agreement_id=agreement.id,
        to_currency=str(to_currency),
        from_amount=Decimal(str(payload['from_amount'])),
        rate=Decimal(str(payload['rate'])),
        converted_at=payload.get('date') or payload.get('converted_at'),
    )


def allocate_workspace_capital(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
    user_id: int | None = None,
) -> list[AgreementAllocation]:
    agreement = _require_workspace_agreement(procurement)
    rows = payload.get('allocations') or [payload]
    if not rows:
        raise ValueError('At least one allocation is required.')

    item_ids = {int(value) for value in payload.get('item_ids') or payload.get('target_item_ids') or []}
    expense_ids = {int(value) for value in payload.get('expense_ids') or payload.get('target_expense_ids') or []}
    date = payload.get('date') or timezone.now()
    created: list[AgreementAllocation] = []
    with transaction.atomic():
        if client_request_id:
            existing_allocations = list(AgreementAllocation.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ))
            if existing_allocations:
                return existing_allocations

        locked_agreement = (
            InvestmentAgreement.objects
            .select_for_update()
            .prefetch_related('partners', 'contributions', 'withdrawals', 'allocations')
            .get(pk=agreement.id, tenant_id=tenant_id)
        )
        locked_procurement = Procurement.objects.select_for_update().get(
            pk=procurement.pk,
            tenant_id=tenant_id,
        )
        if locked_procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError('Cannot allocate capital to non-open procurement.')

        selected_items: list[ProcurementItem] = []
        selected_expenses: list[ProcurementExpense] = []
        if item_ids:
            selected_items = list(ProcurementItem.objects.select_for_update().filter(
                tenant_id=tenant_id,
                procurement=locked_procurement,
                pk__in=item_ids,
            ))
            if {item.pk for item in selected_items} != item_ids:
                raise ValueError('Selected procurement items were not found.')
            if any(item.lifecycle_state != ProcurementItem.LifecycleState.DRAFT for item in selected_items):
                raise ValueError('Selected procurement items are already paid, received, or cancelled.')
        if expense_ids:
            selected_expenses = list(ProcurementExpense.objects.select_for_update().filter(
                tenant_id=tenant_id,
                procurement=locked_procurement,
                pk__in=expense_ids,
            ))
            if {expense.pk for expense in selected_expenses} != expense_ids:
                raise ValueError('Selected procurement expenses were not found.')
            if any(expense.lifecycle_state != ProcurementExpense.LifecycleState.DRAFT for expense in selected_expenses):
                raise ValueError('Selected procurement expenses are already paid, received, or cancelled.')

        member_ids = set(locked_agreement.partners.values_list('partner_id', flat=True))
        available_by_partner = _agreement_available_by_partner(locked_agreement)

        for row in rows:
            partner_id = int(row['partner_id'])
            if partner_id not in member_ids:
                raise ValueError('Selected partner is not part of this agreement.')
            amount = Decimal(str(row['amount'])).quantize(Decimal('0.01'))
            currency = str(row.get('currency') or locked_agreement.currency or 'UZS').upper()
            fx_rate = Decimal(str(row.get('fx_rate', '1')))
            if amount <= 0:
                raise ValueError('Allocation amount must be > 0.')
            available = available_by_partner.get(partner_id, {}).get(currency, Decimal('0'))
            if available < amount:
                raise ValueError(
                    f'Partner balance is insufficient for {currency}: have {available}, need {amount}.'
                )

            # Single event records the capital movement; agreement.balances
            # is derived from this allocation (and contributions/withdrawals).
            allocation = AgreementAllocation.objects.create(
                tenant_id=tenant_id,
                agreement=locked_agreement,
                procurement=locked_procurement,
                partner_id=partner_id,
                direction=AgreementAllocation.Direction.TO_PROCUREMENT,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                date=date,
                notes=_with_client_request_id(row.get('notes', ''), client_request_id),
                source=AgreementActionSource.BUSINESS_RECORDED,
                confirmation_status=AgreementConfirmationStatus.CONFIRMED,
                created_by_id=user_id,
                actor_partner_id=partner_id,
                client_request_id=client_request_id,
            )
            # Update in-memory snapshot so subsequent rows see the deduction.
            available_by_partner.setdefault(partner_id, {})[currency] = available - amount
            ledger = get_or_create_ledger(
                procurement_id=locked_procurement.pk,
                partner_id=partner_id,
                tenant_id=tenant_id,
            )
            append_ledger_entry(
                ledger=ledger,
                entry_type=PartnerLedgerEntry.EntryType.CAPITAL_IN,
                amount=amount,
                currency=currency,
                fx_rate=fx_rate,
                source_ref=f'allocation:{allocation.pk}',
                date=date,
            )
            created.append(allocation)
        for allocation in created:
            record_agreement_event(
                tenant_id=tenant_id,
                agreement=locked_agreement,
                event_type='allocation.to_procurement',
                source=AgreementActionSource.BUSINESS_RECORDED,
                actor_user_id=user_id,
                actor_partner_id=allocation.partner_id,
                related_model='AgreementAllocation',
                related_id=allocation.pk,
                payload={
                    'procurement_id': locked_procurement.pk,
                    'partner_id': allocation.partner_id,
                    'amount': str(allocation.amount),
                    'currency': allocation.currency,
                    'confirmation_status': allocation.confirmation_status,
                    'item_ids': sorted(item_ids),
                    'expense_ids': sorted(expense_ids),
                },
            )
        _spend_allocated_partnership_capital(
            tenant_id=tenant_id,
            procurement=locked_procurement,
            items=selected_items,
            expenses=selected_expenses,
            paid_at=date,
        )
        publish_event(
            event_type='investment_agreement.allocated_to_procurement',
            payload={
                'agreement_id': locked_agreement.pk,
                'procurement_id': locked_procurement.pk,
                'allocations_count': len(created),
            },
            tenant_id=tenant_id,
        )

        if item_ids:
            ProcurementItem.objects.filter(
                tenant_id=tenant_id,
                procurement=locked_procurement,
                pk__in=[item.pk for item in selected_items],
            ).update(
                lifecycle_state=ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
                updated_at=timezone.now(),
            )
        if expense_ids:
            ProcurementExpense.objects.filter(
                tenant_id=tenant_id,
                procurement=locked_procurement,
                pk__in=[expense.pk for expense in selected_expenses],
            ).update(
                lifecycle_state=ProcurementExpense.LifecycleState.READY_FOR_RECEIVE,
                updated_at=timezone.now(),
            )
    return created


def build_workspace_capital_allocation_preview(
    *,
    tenant_id: int,
    agreement_id: int,
    procurement_id: int,
) -> dict:
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
    if procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        raise ValueError('Capital allocation preview is available only for PARTNERSHIP procurement.')
    if procurement.agreement_id != agreement.id:
        raise ValueError('Procurement is not linked to this agreement.')

    active_items, active_expenses = active_procurement_lines(procurement)
    cost_map = procurement_cost_by_currency(active_items, active_expenses)
    if len(cost_map) > 1:
        raise ValueError(
            'Mixed currencies in obligation cost. '
            f'Found: {", ".join(sorted(cost_map))}.'
        )
    if cost_map:
        currency, required = next(iter(cost_map.items()))
    else:
        currency = str(agreement.currency or 'UZS').upper()
        required = Decimal('0.00')
    required_uzs = _remaining_obligation_cost_uzs(active_items, active_expenses)
    members = list(agreement.partners.select_related('partner').all())
    available = _agreement_available_by_partner(agreement)
    suggestions = _auto_capital_amounts(required, members, {
        member.partner_id: available.get(member.partner_id, {}).get(currency, Decimal('0'))
        for member in members
    }) if required > 0 else {}

    return {
        'agreement_id': agreement.id,
        'procurement_id': procurement.id,
        'required': {currency: str(required)},
        'required_uzs': str(required_uzs),
        'agreement_balances': agreement.balances or {},
        'suggestions': [
            {
                'partner_id': member.partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(member.partner_id)),
                'role': member.role,
                'currency': currency,
                'available': str(available.get(member.partner_id, {}).get(currency, Decimal('0')).quantize(Decimal('0.01'))),
                'target_amount': str(suggestions.get(member.partner_id, Decimal('0')).quantize(Decimal('0.01'))),
                'amount': str(suggestions.get(member.partner_id, Decimal('0')).quantize(Decimal('0.01'))),
            }
            for member in members
        ],
    }


def _pre_allocate_at_receipt_partnership_capital(
    *,
    tenant_id: int,
    procurement: Procurement,
    required_uzs: Decimal,
    raw_allocations: list[dict] | None,
    received_at,
    required_base: Decimal | None = None,
) -> None:
    """
    PARTNERSHIP × AT_RECEIPT: atomically draw from the agreement's capital pool
    by creating AgreementAllocation(TO_PROCUREMENT) records so that
    _resolve_workspace_capital_snapshot can proceed normally.
    Derives amounts from planned shares when raw_allocations is absent.
    """
    agreement = _require_workspace_agreement(procurement)
    currency = str(agreement.currency or 'UZS').upper()
    if required_base is not None:
        required = Decimal(str(required_base)).quantize(Decimal('0.01'))
    else:
        required = _amount_uzs_to_currency(
            tenant_id=tenant_id, amount_uzs=required_uzs, currency=currency, received_at=received_at,
        )
    if required <= 0:
        raise ValueError('AT_RECEIPT receive batch capital requirement must be positive.')

    members = list(agreement.partners.select_related('partner').all())
    if not members:
        raise ValueError('Investment agreement has no partners.')
    member_by_id = {m.partner_id: m for m in members}
    available_by_partner = _agreement_available_by_partner(agreement)
    available_flat = {
        pid: avail.get(currency, Decimal('0'))
        for pid, avail in available_by_partner.items()
    }

    if raw_allocations:
        amounts: dict[int, Decimal] = {}
        for row in raw_allocations:
            pid = int(row['partner_id'])
            if pid not in member_by_id:
                raise ValueError(f'AT_RECEIPT capital allocation: partner {pid} not in agreement.')
            amt = Decimal(str(row['amount'])).quantize(Decimal('0.01'))
            amounts[pid] = (amounts.get(pid, Decimal('0')) + amt).quantize(Decimal('0.01'))
    else:
        amounts = _auto_capital_amounts(required, members, available_flat)

    for pid, amount in amounts.items():
        avail = available_flat.get(pid, Decimal('0'))
        if amount - avail > Decimal('0.01'):
            member = member_by_id[pid]
            name = getattr(member.partner, 'display_name', str(pid))
            raise ValueError(
                f'AT_RECEIPT: Insufficient capital for {name}: have {avail} {currency}, need {amount}.'
            )

    for pid, amount in amounts.items():
        if amount <= Decimal('0'):
            continue
        AgreementAllocation.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            procurement=procurement,
            partner_id=pid,
            direction=AgreementAllocation.Direction.TO_PROCUREMENT,
            amount=amount,
            currency=currency,
            fx_rate=Decimal('1'),
            date=received_at,
            notes='AT_RECEIPT auto-allocation',
            source=AgreementActionSource.BUSINESS_RECORDED,
            confirmation_status=AgreementConfirmationStatus.CONFIRMED,
        )


def _resolve_workspace_capital_snapshot(
    *,
    tenant_id: int,
    procurement: Procurement,
    required_uzs: Decimal,
    raw_allocations: list[dict] | None,
    received_at,
    required_base: Decimal | None = None,
    share_basis: str = 'FACTUAL',
) -> tuple[dict, list[dict]]:
    """E14/E17: `share_basis` selects how lot ownership is fixed.

    - 'FACTUAL' (Path 1, default): capital_share derived from the actual cash
      each partner allocated; profit via profit_shares_from_capital.
    - 'AGREED' (Path 2): capital_share/profit_share pinned to the agreed
      AgreementPartner shares regardless of actual cash. `amount_contract_currency`
      still records the ACTUAL cash (keeps pool / availability accounting honest);
      the per-partner gap (agreed − actual) is read as a net capital position
      (partner_capital_positions: owed / withdrawable), not a CapitalAdvance.

    Returns (contract_snapshot, capital_rows)."""
    agreement = _require_workspace_agreement(procurement)
    currency = str(agreement.currency or 'UZS').upper()
    # E12: when the receive was funded from currency sub-pools, the base-currency
    # cost comes from FIFO cost-basis (real conversion rate), not the receive-day
    # market rate. Fall back to market conversion only when no funded base cost
    # is provided (e.g. CONSIGNED).
    if required_base is not None:
        required = Decimal(str(required_base)).quantize(Decimal('0.01'))
    else:
        required = _amount_uzs_to_currency(
            tenant_id=tenant_id,
            amount_uzs=required_uzs,
            currency=currency,
            received_at=received_at,
        )
    if required <= 0:
        raise ValueError('Receive batch capital requirement must be positive.')

    members = list(agreement.partners.select_related('partner').all())
    if not members:
        raise ValueError('Investment agreement has no partners.')
    member_by_id = {member.partner_id: member for member in members}
    available = _procurement_capital_available_by_partner(procurement, currency)

    if raw_allocations:
        amounts: dict[int, Decimal] = {}
        for row in raw_allocations:
            partner_id = int(row['partner_id'])
            if partner_id not in member_by_id:
                raise ValueError('Capital allocation contains an unknown partner.')
            amount = Decimal(str(row['amount'])).quantize(Decimal('0.01'))
            if amount < 0:
                raise ValueError('Capital allocation amount cannot be negative.')
            amounts[partner_id] = (amounts.get(partner_id, Decimal('0')) + amount).quantize(Decimal('0.01'))
    else:
        amounts = _auto_capital_amounts(required, members, available)

    total = sum(amounts.values(), Decimal('0')).quantize(Decimal('0.01'))
    if abs(total - required) > Decimal('0.01'):
        raise ValueError(f'Capital allocation total must be {required} {currency}.')
    for partner_id, amount in amounts.items():
        if amount - available.get(partner_id, Decimal('0')) > Decimal('0.01'):
            member = member_by_id[partner_id]
            name = getattr(member.partner, 'display_name', str(partner_id))
            raise ValueError(f'Insufficient capital for {name}: have {available.get(partner_id, Decimal("0"))}, need {amount}.')

    # Capital consumption is recorded by ProcurementReceiveBatchCapitalAllocation
    # rows produced below — _procurement_capital_available_by_partner subtracts
    # those, and the aggregate check is implicit in the per-partner availability
    # validation above.

    basis = str(share_basis or 'FACTUAL').upper()

    # Agreed capital ratio per partner (used by AGREED basis).
    planned_total = sum((Decimal(str(m.planned_capital_share)) for m in members), Decimal('0'))

    partners_meta = []
    for member in members:
        amount = amounts.get(member.partner_id, Decimal('0')).quantize(Decimal('0.01'))
        actual_share = (amount / required).quantize(Decimal('0.000001')) if required > 0 else Decimal('0')
        if basis == 'AGREED':
            agreed_ratio = (
                (Decimal(str(member.planned_capital_share)) / planned_total).quantize(Decimal('0.000001'))
                if planned_total > 0 else Decimal('0')
            )
            capital_share = agreed_ratio
        else:
            capital_share = actual_share
        partners_meta.append({
            'partner_id': member.partner_id,
            'role': member.role,
            'capital_amount_contract_currency': str(amount),  # actual cash (honest pool accounting)
            'capital_share': str(capital_share),
        })

    if basis == 'AGREED':
        # Profit by agreement (negotiated AgreementPartner.profit_share), not derived.
        profit_shares = {m.partner_id: Decimal(str(m.profit_share)) for m in members}
    else:
        profit_shares = profit_shares_from_capital(partners_meta, agreement.mudaraba_ratio)

    rows = []
    snapshot_partners = []
    for meta in partners_meta:
        partner_id = int(meta['partner_id'])
        member = member_by_id[partner_id]
        profit_share = profit_shares.get(partner_id, Decimal('0'))
        snapshot_partners.append({
            **meta,
            'partner_name': getattr(member.partner, 'display_name', str(partner_id)),
            'profit_share': str(profit_share),
        })
        rows.append({
            'partner_id': partner_id,
            'role': meta['role'],
            'amount_contract_currency': Decimal(str(meta['capital_amount_contract_currency'])),
            'capital_share': Decimal(str(meta['capital_share'])),
            'profit_share': profit_share,
        })

    return {
        'agreement_id': agreement.id,
        'contract_currency': currency,
        'mudaraba_ratio': str(agreement.mudaraba_ratio),
        'loss_rule': agreement.loss_rule,
        'partners': snapshot_partners,
    }, rows


def _procurement_capital_available_by_partner(procurement: Procurement, currency: str) -> dict[int, Decimal]:
    """
    Capital allocated to this procurement and not yet consumed by a receive
    batch, broken down by partner. Sources:
      + AgreementAllocation(direction=TO_PROCUREMENT, currency)
      - AgreementAllocation(direction=FROM_PROCUREMENT, currency)
      - ProcurementReceiveBatchCapitalAllocation already snapshotted into a batch.
    """
    contributions: dict[int, Decimal] = {}
    for allocation in AgreementAllocation.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
        currency=currency,
    ):
        delta = Decimal(str(allocation.amount))
        if allocation.direction != AgreementAllocation.Direction.TO_PROCUREMENT:
            delta = -delta
        contributions[allocation.partner_id] = (
            contributions.get(allocation.partner_id, Decimal('0')) + delta
        ).quantize(Decimal('0.01'))
    for allocation in ProcurementReceiveBatchCapitalAllocation.objects.filter(
        batch__procurement=procurement,
        batch__tenant_id=procurement.tenant_id,
    ):
        contributions[allocation.partner_id] = (
            contributions.get(allocation.partner_id, Decimal('0'))
            - Decimal(str(allocation.amount_contract_currency))
        ).quantize(Decimal('0.01'))
    return contributions


def _auto_capital_amounts(required: Decimal, members: list, available: dict[int, Decimal]) -> dict[int, Decimal]:
    planned_total = sum((Decimal(str(member.planned_capital_share)) for member in members), Decimal('0'))
    amounts: dict[int, Decimal] = {}
    remaining = required
    for member in members:
        if planned_total > 0:
            target = (required * Decimal(str(member.planned_capital_share)) / planned_total).quantize(Decimal('0.01'))
        else:
            target = (required / Decimal(str(len(members)))).quantize(Decimal('0.01'))
        amount = min(target, max(available.get(member.partner_id, Decimal('0')), Decimal('0')))
        amounts[member.partner_id] = amount
        remaining = (remaining - amount).quantize(Decimal('0.01'))
    if remaining > 0:
        for member in members:
            headroom = (
                max(available.get(member.partner_id, Decimal('0')), Decimal('0'))
                - amounts.get(member.partner_id, Decimal('0'))
            ).quantize(Decimal('0.01'))
            if headroom <= 0:
                continue
            top_up = min(headroom, remaining)
            amounts[member.partner_id] = (amounts.get(member.partner_id, Decimal('0')) + top_up).quantize(Decimal('0.01'))
            remaining = (remaining - top_up).quantize(Decimal('0.01'))
            if remaining <= 0:
                break
    if abs(sum(amounts.values(), Decimal('0')) - required) <= Decimal('0.01') and members:
        residue = (required - sum(amounts.values(), Decimal('0'))).quantize(Decimal('0.01'))
        amounts[members[-1].partner_id] = (amounts.get(members[-1].partner_id, Decimal('0')) + residue).quantize(Decimal('0.01'))
    return amounts


def _spend_allocated_partnership_capital(
    *,
    tenant_id: int,
    procurement: Procurement,
    items: list[ProcurementItem],
    expenses: list[ProcurementExpense],
    paid_at,
) -> None:
    if not items and not expenses:
        return
    agreement = _require_workspace_agreement(procurement)
    if not agreement.capital_account_id:
        raise ValueError('Partnership agreement has no capital pool.')

    item_values_uzs = [_item_value_uzs(item) for item in items]
    native_by_ccy, func_by_ccy = _receive_funding_breakdown(
        items,
        item_values_uzs,
        expenses,
        [Decimal('0.00') for _ in items],
    )
    for ccy in sorted(func_by_ccy.keys()):
        native_amt = Decimal(str(native_by_ccy[ccy])).quantize(Decimal('0.01'))
        func_uzs = Decimal(str(func_by_ccy[ccy])).quantize(Decimal('0.01'))
        if native_amt <= 0 or func_uzs <= 0:
            continue
        pool = CashAccount.objects.select_for_update().get(
            pk=agreement.capital_account_id,
            tenant_id=tenant_id,
            is_active=True,
        )
        if str(pool.currency or '').upper() != ccy:
            raise ValueError(
                f'Agreement capital pool is in {pool.currency}, but selected prepaid lines are in {ccy}.'
            )
        record_capital_pool_payment(
            tenant_id=tenant_id,
            pool_account_id=pool.pk,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.pk,
            amount=native_amt,
            functional_amount_uzs=func_uzs,
            counterpart_account_code='1100',
            currency=ccy,
            paid_at=paid_at,
            operation_type='procurement_payment',
            description=f'Procurement #{procurement.pk} prepaid from capital pool ({ccy})',
        )
