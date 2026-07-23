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
from apps.suppliers.models import SupplierPayable
from apps.suppliers.services import create_payable_from_procurement, record_payable_payment

from .models import (
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


