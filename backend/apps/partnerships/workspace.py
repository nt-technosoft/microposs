from __future__ import annotations

from decimal import Decimal

from django.db import models, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import CashAccount, CashEntry, Payment, PaymentAllocation
from apps.finance.fx_rates import resolve_fx_rate_snapshot
from apps.finance.services import (
    create_cash_entry,
    create_journal_entry,
    record_capital_pool_payment,
    record_generic_cash_payment,
    record_journal_from_cash_entry,
    record_pool_journal_functional,
)
from apps.partnerships.multicurrency import get_or_create_currency_pool
from apps.partnerships.formulas import profit_shares_from_capital
from apps.suppliers.models import SupplierPayable
from apps.suppliers.services import create_payable_from_procurement, record_payable_payment

from .models import (
    AgreementActionSource,
    AgreementAllocation,
    AgreementConfirmationStatus,
    AgreementContribution,
    AgreementPartner,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementExpense,
    ProcurementExpenseTarget,
    ProcurementItem,
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
)
from .procurement_cost import (
    active_procurement_lines,
    procurement_cost_by_currency,
    procurement_cost_uzs_for_reporting,
)
from .policies import (
    ProcurementPolicyContext,
    SUPPLIER_REQUIRED_SETTLEMENTS,
    allowed_settlements_for_funding,
    evaluate_procurement_policy,
)
from .workspace_support import (
    add_agreement_contribution,
    append_ledger_entry,
    apply_terms_amendment,
    create_investment_agreement,
    generate_installment_schedule,
    get_or_create_ledger,
    record_agreement_event,
    upsert_procurement_terms_draft,
    upsert_supplier_links_for_items,
)
from .workspace_common import (
    _SUPPLIER_OPTIONAL_TYPES,
    _add_amount,
    _agreement_available_by_partner,
    _amount_uzs_to_currency,
    _coerce_datetime,
    _derive_items_currency,
    _ensure_source_editable,
    _expense_allocated_value_uzs,
    _expense_is_fully_allocated_after_receive,
    _expense_remaining_value_uzs,
    _expense_value_uzs,
    _has_capital_activity,
    _has_payment_activity,
    _item_value_uzs,
    _landed_expense_allocations,
    _normalize_currency,
    _primary_currency,
    _receive_funding_breakdown,
    _received_quantity,
    _remaining_item_quantity,
    _remaining_item_value_uzs,
    _remaining_obligation_cost_by_currency,
    _remaining_obligation_cost_uzs,
    _require_workspace_agreement,
    _resolve_procurement_row_fx_rate,
    _resolve_workspace_fx_rate,
    _with_client_request_id,
)
from .workspace_funding import (
    _auto_capital_amounts,
    _pre_allocate_at_receipt_partnership_capital,
    _procurement_capital_available_by_partner,
    _resolve_workspace_capital_snapshot,
    _spend_allocated_partnership_capital,
    allocate_workspace_capital,
    build_workspace_capital_allocation_preview,
    convert_workspace_capital_pool,
    create_and_link_workspace_agreement,
    link_workspace_agreement,
    record_workspace_capital_contribution,
)
from .workspace_payload import (
    ACTION_LABELS,
    ACTION_MAP,
    FLOW_TITLES,
    SECTION_KEY_MAP,
    SECTION_TITLES,
    _terms_status_for_paid_amount,
    build_workspace_payload,
)
from .workspace_payment import (
    _has_procurement_cost_payment,
    pay_workspace_costs,
    pay_workspace_supplier_payable,
    resolve_workspace_overpayment,
)
from .workspace_receive import (
    receive_workspace_batch,
    reverse_workspace_receive_batch,
)
from .workspace_amendments import (
    apply_expenses_amendment,
    apply_items_amendment,
    cancel_workspace_procurement,
    split_workspace_item,
    update_workspace_lines,
    update_workspace_settlement,
    update_workspace_source,
)


def create_workspace(
    *,
    tenant_id: int,
    funding_source: str = Procurement.FundingSource.OWN_FUNDS,
    primary_currency: str = 'UZS',
    supplier_id: int | None = None,
    agreement_id: int | None = None,
    notes: str = '',
    client_request_id: str | None = None,
) -> Procurement:
    if funding_source not in Procurement.FundingSource.values:
        raise ValueError('Unsupported funding source.')
    primary_currency = _normalize_currency(primary_currency)

    if client_request_id:
        existing = Procurement.objects.filter(
            tenant_id=tenant_id,
            client_request_id=client_request_id,
        ).first()
        if existing:
            return existing

    return Procurement.objects.create(
        tenant_id=tenant_id,
        funding_source=funding_source,
        primary_currency=primary_currency,
        supplier_id=supplier_id,
        agreement_id=agreement_id,
        notes=notes,
        opened_at=timezone.now(),
        client_request_id=client_request_id,
    )


def workspace_queryset(tenant_id: int):
    return (
        Procurement.objects
        .filter(tenant_id=tenant_id)
        .select_related('supplier', 'agreement')
        .prefetch_related(
            'items__product_variant',
            'expenses__targets',
            'receive_batches__lines__item__product_variant',
            'receive_batches__expenses__expense',
            'receive_batches__capital_allocations__partner',
            'agreement__partners__partner',
            'agreement__commitments__partner',
            'agreement__contributions__partner',
            'agreement__allocations__partner',
            'agreement__events__actor_user',
            'agreement__events__actor_partner',
        )
        .order_by('-opened_at', '-id')
    )


def dispatch_workspace_action(
    *,
    tenant_id: int,
    procurement: Procurement,
    action: str,
    payload: dict,
    user_id: int | None = None,
) -> Procurement:
    normalized = action.upper()
    mutation_payload = payload.get('payload') if isinstance(payload.get('payload'), dict) else payload
    client_request_id = payload.get('client_request_id') or mutation_payload.get('client_request_id')
    if normalized == 'UPDATE_SOURCE':
        return update_workspace_source(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
    if normalized in {'UPDATE_SETTLEMENT', 'AMEND_SETTLEMENT'}:
        update_workspace_settlement(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'GENERATE_INSTALLMENT_SCHEDULE':
        generate_installment_schedule(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized in {'UPDATE_ITEMS', 'UPDATE_EXPENSES'}:
        update_workspace_lines(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'SPLIT_ITEM':
        split_workspace_item(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'PAY_COSTS':
        pay_workspace_costs(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'RESOLVE_OVERPAYMENT':
        resolve_workspace_overpayment(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'PAY_SUPPLIER_PAYABLE':
        pay_workspace_supplier_payable(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'CREATE_INVESTMENT_AGREEMENT':
        create_and_link_workspace_agreement(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'LINK_INVESTMENT_AGREEMENT':
        link_workspace_agreement(
            tenant_id=tenant_id,
            procurement=procurement,
            agreement_id=mutation_payload.get('agreement_id') or mutation_payload.get('investment_agreement_id'),
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'RECORD_CAPITAL_CONTRIBUTION':
        record_workspace_capital_contribution(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'ALLOCATE_CAPITAL':
        allocate_workspace_capital(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
            client_request_id=client_request_id,
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'CONVERT_CAPITAL_POOL':
        convert_workspace_capital_pool(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'RECEIVE_BATCH':
        receive_workspace_batch(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'CANCEL_PROCUREMENT':
        return cancel_workspace_procurement(
            tenant_id=tenant_id,
            procurement=procurement,
            payload=mutation_payload,
        )
    if normalized == 'REVERSE_BATCH':
        batch_id = mutation_payload.get('batch_id')
        if not batch_id:
            raise ValueError('REVERSE_BATCH action requires batch_id in payload.')
        reverse_workspace_receive_batch(
            tenant_id=tenant_id,
            batch_id=int(batch_id),
            reason=mutation_payload.get('reason', ''),
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'AMEND_ITEMS':
        apply_items_amendment(
            tenant_id=tenant_id,
            procurement=procurement,
            new_items_payload=mutation_payload.get('items', []),
            reason=mutation_payload.get('reason', ''),
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    if normalized == 'AMEND_EXPENSES':
        apply_expenses_amendment(
            tenant_id=tenant_id,
            procurement=procurement,
            new_expenses_payload=mutation_payload.get('expenses', []),
            reason=mutation_payload.get('reason', ''),
            user_id=user_id,
        )
        return Procurement.objects.get(pk=procurement.pk, tenant_id=tenant_id)
    raise ValueError(f'Workspace action {action} is not implemented yet.')


def _draft_cost_total_uzs(items, expenses) -> Decimal:
    """Thin alias for reporting — use procurement_cost_uzs_for_reporting directly."""
    return procurement_cost_uzs_for_reporting(items, expenses)


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

