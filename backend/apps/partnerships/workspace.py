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


def update_workspace_source(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
) -> Procurement:
    """Update source facts while the workspace still has no irreversible facts."""

    _ensure_source_editable(procurement)

    funding_source = payload.get('funding_source')
    primary_currency = payload.get('primary_currency')
    supplier_id = payload.get('supplier_id', procurement.supplier_id)
    agreement_id = (
        payload.get('investment_agreement_id')
        or payload.get('agreement_id')
        or procurement.agreement_id
    )

    if funding_source is not None and funding_source not in Procurement.FundingSource.values:
        raise ValueError('Unsupported funding source.')

    next_funding_source = funding_source or procurement.funding_source
    if next_funding_source == Procurement.FundingSource.OWN_FUNDS:
        agreement_id = None
    elif not agreement_id:
        raise ValueError('PARTNERSHIP source requires investment_agreement_id.')

    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(pk=procurement.pk, tenant_id=tenant_id)
        _ensure_source_editable(locked)
        locked.funding_source = next_funding_source
        if primary_currency is not None:
            locked.primary_currency = _normalize_currency(primary_currency)
        locked.supplier_id = supplier_id
        locked.agreement_id = agreement_id
        if 'notes' in payload:
            locked.notes = payload.get('notes') or ''
        _validate_source_transition(locked)
        locked.save(update_fields=[
            'funding_source',
            'primary_currency',
            'supplier',
            'agreement',
            'notes',
            'updated_at',
        ])
        return locked


def update_workspace_settlement(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    user_id: int | None = None,
) -> ProcurementTerms:
    """Create/update draft settlement or amend it after receive batches exist."""

    terms_payload = dict(payload.get('settlement') or payload.get('terms') or payload)
    schedule_payload = terms_payload.pop('schedule', payload.get('schedule', []))

    if procurement.receive_batches.exists():
        terms = getattr(procurement, 'terms', None)
        if not terms:
            raise ValueError('Cannot amend settlement before it exists.')
        reason = terms_payload.pop('reason', payload.get('reason', ''))
        return apply_terms_amendment(
            tenant_id=tenant_id,
            terms_id=terms.id,
            new_fields=terms_payload,
            reason=reason,
            user_id=user_id,
        ).terms

    return upsert_procurement_terms_draft(
        tenant_id,
        procurement,
        terms_payload,
        schedule_payload,
    )


def update_workspace_lines(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
) -> None:
    """Create/update only draft item and expense documents."""

    if procurement.status != Procurement.Status.OPEN:
        raise ValueError('Items and expenses can be edited only while procurement is OPEN.')

    items_payload = payload.get('items')
    expenses_payload = payload.get('expenses')
    if items_payload is None and 'product_variant_id' in payload:
        items_payload = [payload]
    if expenses_payload is None and 'expense_type' in payload:
        expenses_payload = [payload]

    cancel_item_ids = {int(value) for value in payload.get('cancel_item_ids') or []}
    cancel_expense_ids = {int(value) for value in payload.get('cancel_expense_ids') or []}

    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(
            pk=procurement.pk,
            tenant_id=tenant_id,
        )
        if locked.status != Procurement.Status.OPEN:
            raise ValueError('Items and expenses can be edited only while procurement is OPEN.')

        for item_id in cancel_item_ids:
            item = _draft_item_for_update(tenant_id, locked, item_id)
            item.lifecycle_state = ProcurementItem.LifecycleState.CANCELLED
            item.save(update_fields=['lifecycle_state', 'updated_at'])

        for expense_id in cancel_expense_ids:
            expense = _draft_expense_for_update(tenant_id, locked, expense_id)
            expense.lifecycle_state = ProcurementExpense.LifecycleState.CANCELLED
            expense.save(update_fields=['lifecycle_state', 'updated_at'])

        for row in items_payload or []:
            _upsert_workspace_item(tenant_id, locked, row)

        if expenses_payload and locked.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
            raise ValueError(
                'CONSIGNED procurement не поддерживает landed expenses. '
                'Расходы на логистику/доставку для консигнации фиксируйте '
                'как отдельные операционные расходы, не как cost basis товара.'
            )

        for row in expenses_payload or []:
            _upsert_workspace_expense(tenant_id, locked, row)

        _resync_draft_terms_total(tenant_id, locked)


def _resync_draft_terms_total(tenant_id: int, procurement: Procurement) -> None:
    """Keep terms.total_amount_due and currency_of_obligation in sync with items while in DRAFT.

    Obligation amount = Σ(qty × unit_purchase_price) in items' currency.
    fx_rate is for UZS reporting only — not used here.
    Mixed-currency items raise so UI catches the configuration error early.
    ACTIVE terms are immutable and skipped.
    """
    terms = ProcurementTerms.objects.filter(
        tenant_id=tenant_id, procurement=procurement,
        lifecycle_state=ProcurementTerms.LifecycleState.DRAFT,
    ).first()
    if terms is None:
        return
    active_items, active_expenses = active_procurement_lines(procurement)
    cost_map = _remaining_obligation_cost_by_currency(active_items, active_expenses)
    if len(cost_map) > 1:
        raise ValueError(
            'Все товары прихода должны быть в одной валюте. '
            f'Найдено: {", ".join(sorted(cost_map))}.'
        )
    if cost_map:
        new_currency, new_total = next(iter(cost_map.items()))
    else:
        new_currency = str(terms.currency_of_obligation or 'UZS').upper()
        new_total = Decimal('0.00')

    update_fields = ['updated_at']
    if terms.total_amount_due != new_total:
        terms.total_amount_due = new_total
        update_fields.append('total_amount_due')
    if str(terms.currency_of_obligation or 'UZS').upper() != new_currency:
        terms.currency_of_obligation = new_currency
        update_fields.append('currency_of_obligation')
    if len(update_fields) > 1:
        terms.save(update_fields=update_fields)


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


def cancel_workspace_procurement(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
) -> Procurement:
    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(pk=procurement.pk, tenant_id=tenant_id)

        if locked.status in (
            Procurement.Status.PARTIALLY_RECEIVED,
            Procurement.Status.RECEIVED,
            Procurement.Status.CLOSED,
        ):
            raise ValueError(
                f'Cannot cancel procurement in status {locked.status}. '
                f'Only OPEN procurements with no payments or receive batches can be cancelled.'
            )
        if locked.status == Procurement.Status.CANCELLED:
            return locked

        if locked.status == Procurement.Status.OPEN:
            has_payment = Payment.objects.filter(
                tenant_id=tenant_id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=locked.pk,
            ).exists()
            if has_payment:
                raise ValueError('Cannot cancel OPEN procurement with existing payments.')
            has_batch = locked.receive_batches.exists()
            if has_batch:
                raise ValueError('Cannot cancel OPEN procurement with existing receive batches.')

        locked.status = Procurement.Status.CANCELLED
        locked.save(update_fields=['status', 'updated_at'])

        terms = getattr(locked, 'terms', None)
        if terms is not None:
            terms.lifecycle_state = ProcurementTerms.LifecycleState.DRAFT
            terms.save(update_fields=['lifecycle_state', 'updated_at'])

        publish_event(
            event_type='procurement.cancelled',
            payload={'procurement_id': locked.pk, 'reason': payload.get('reason', '')},
            tenant_id=tenant_id,
        )
        return locked


def apply_items_amendment(
    *,
    tenant_id: int,
    procurement: Procurement,
    new_items_payload: list[dict],
    reason: str = '',
    user_id: int | None = None,
) -> 'ProcurementAmendment':
    from apps.partnerships.models import ProcurementAmendment

    ALLOWED = (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED)
    if procurement.status not in ALLOWED:
        raise ValueError(
            f'Items amendment only allowed in OPEN or PARTIALLY_RECEIVED status, '
            f'got {procurement.status}.'
        )

    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(pk=procurement.pk, tenant_id=tenant_id)
        if locked.status not in ALLOWED:
            raise ValueError(
                f'Items amendment only allowed in OPEN or PARTIALLY_RECEIVED status, '
                f'got {locked.status}.'
            )

        before_snapshot = _items_snapshot(locked)

        # Validate: cannot remove or zero-out items with qty already received
        received_item_ids = set(
            ProcurementReceiveBatchLine.objects
            .filter(tenant_id=tenant_id, batch__procurement=locked)
            .values_list('item_id', flat=True)
            .distinct()
        )
        cancel_item_ids = {_row_id(v) for v in (new_items_payload or []) if _is_cancel_row(v)}
        for item_id in cancel_item_ids:
            item = ProcurementItem.objects.get(
                pk=item_id,
                tenant_id=tenant_id,
                procurement=locked,
            )
            if item_id in received_item_ids:
                raise ValueError(
                    f'Cannot cancel item {item_id}: it already has received quantities in a batch.'
                )
            if item.lifecycle_state != ProcurementItem.LifecycleState.DRAFT:
                raise ValueError(
                    f'Cannot cancel item {item_id}: only DRAFT lines can be removed. '
                    'Use an amendment to change unreceived quantities/prices, or reverse the receive batch.'
                )

        for row in new_items_payload or []:
            if _is_cancel_row(row):
                item = ProcurementItem.objects.get(
                    pk=_row_id(row),
                    tenant_id=tenant_id,
                    procurement=locked,
                )
                item.lifecycle_state = ProcurementItem.LifecycleState.CANCELLED
                item.save(update_fields=['lifecycle_state', 'updated_at'])
            else:
                _upsert_workspace_item_for_amendment(tenant_id, locked, row)

        after_snapshot = _items_snapshot(locked)
        return ProcurementAmendment.objects.create(
            tenant_id=tenant_id,
            procurement=locked,
            target_type=ProcurementAmendment.TargetType.ITEMS,
            amended_at=timezone.now(),
            changed_by_id=user_id,
            before=before_snapshot,
            after=after_snapshot,
            reason=reason,
        )


def apply_expenses_amendment(
    *,
    tenant_id: int,
    procurement: Procurement,
    new_expenses_payload: list[dict],
    reason: str = '',
    user_id: int | None = None,
) -> 'ProcurementAmendment':
    from apps.partnerships.models import ProcurementAmendment

    ALLOWED = (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED)
    if procurement.status not in ALLOWED:
        raise ValueError(
            f'Expenses amendment only allowed in OPEN or PARTIALLY_RECEIVED status, '
            f'got {procurement.status}.'
        )

    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(pk=procurement.pk, tenant_id=tenant_id)
        if locked.status not in ALLOWED:
            raise ValueError(
                f'Expenses amendment only allowed in OPEN or PARTIALLY_RECEIVED status, '
                f'got {locked.status}.'
            )

        before_snapshot = _expenses_snapshot(locked)

        cancel_expense_ids = {_row_id(v) for v in (new_expenses_payload or []) if _is_cancel_row(v)}
        received_expense_ids = set(
            ProcurementReceiveBatchExpense.objects
            .filter(tenant_id=tenant_id, batch__procurement=locked)
            .values_list('expense_id', flat=True)
            .distinct()
        )
        for expense_id in cancel_expense_ids:
            expense = ProcurementExpense.objects.get(
                pk=expense_id,
                tenant_id=tenant_id,
                procurement=locked,
            )
            if expense_id in received_expense_ids:
                raise ValueError(
                    f'Cannot cancel expense {expense_id}: it already has received facts in a batch.'
                )
            if expense.lifecycle_state != ProcurementExpense.LifecycleState.DRAFT:
                raise ValueError(
                    f'Cannot cancel expense {expense_id}: only DRAFT expenses can be removed. '
                    'Use an amendment to change the remaining amount, or reverse the receive batch.'
                )

        for row in new_expenses_payload or []:
            if _is_cancel_row(row):
                expense = ProcurementExpense.objects.get(
                    pk=_row_id(row),
                    tenant_id=tenant_id,
                    procurement=locked,
                )
                expense.lifecycle_state = ProcurementExpense.LifecycleState.CANCELLED
                expense.save(update_fields=['lifecycle_state', 'updated_at'])
            else:
                expense = _upsert_workspace_expense_for_amendment(tenant_id, locked, row)
                _sync_expense_lifecycle_after_amendment(expense)

        after_snapshot = _expenses_snapshot(locked)
        return ProcurementAmendment.objects.create(
            tenant_id=tenant_id,
            procurement=locked,
            target_type=ProcurementAmendment.TargetType.EXPENSES,
            amended_at=timezone.now(),
            changed_by_id=user_id,
            before=before_snapshot,
            after=after_snapshot,
            reason=reason,
        )


def _is_cancel_row(row) -> bool:
    if isinstance(row, dict):
        return bool(row.get('_cancel') or row.get('cancel'))
    return False


def _row_id(row) -> int:
    if isinstance(row, dict):
        value = row.get('id') or row.get('item_id') or row.get('expense_id')
    else:
        value = row
    if value is None:
        raise ValueError('Amendment row id is required.')
    return int(value)


def _items_snapshot(procurement: Procurement) -> list[dict]:
    return [
        {
            'id': item.id,
            'product_variant_id': item.product_variant_id,
            'quantity': str(item.quantity),
            'unit_purchase_price': str(item.unit_purchase_price),
            'currency': item.currency,
            'fx_rate': str(item.fx_rate),
            'goods_ownership': item.goods_ownership,
            'lifecycle_state': item.lifecycle_state,
        }
        for item in procurement.items.order_by('id')
    ]


def _expenses_snapshot(procurement: Procurement) -> list[dict]:
    return [
        {
            'id': expense.id,
            'expense_type': expense.expense_type,
            'amount': str(expense.amount),
            'currency': expense.currency,
            'fx_rate': str(expense.fx_rate),
            'allocation_method': expense.allocation_method,
            'target_item_ids': list(expense.targets.values_list('item_id', flat=True)),
            'lifecycle_state': expense.lifecycle_state,
        }
        for expense in procurement.expenses.order_by('id')
    ]


def _amendment_item_for_update(tenant_id: int, procurement: Procurement, item_id: int) -> ProcurementItem:
    item = ProcurementItem.objects.select_for_update().get(
        pk=item_id, tenant_id=tenant_id, procurement=procurement,
    )
    blocked = (ProcurementItem.LifecycleState.RECEIVED, ProcurementItem.LifecycleState.CANCELLED)
    if item.lifecycle_state in blocked:
        raise ValueError(
            f'Cannot amend item {item_id} in state {item.lifecycle_state}.'
        )
    if _received_quantity(item) > 0:
        raise ValueError(
            f'Cannot amend item {item_id}: it already has received quantities. '
            'Reverse the receive batch or split/amend only the unreceived line.'
        )
    return item


def _upsert_workspace_item_for_amendment(tenant_id: int, procurement: Procurement, row: dict) -> ProcurementItem:
    item_id = row.get('id') or row.get('item_id')
    current_item = None
    if item_id:
        current_item = _amendment_item_for_update(tenant_id, procurement, int(item_id))
    values = {
        'product_variant_id': int(row['product_variant_id']),
        'quantity': Decimal(str(row['quantity'])),
        'unit_purchase_price': Decimal(str(row['unit_purchase_price'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': _resolve_procurement_row_fx_rate(
            tenant_id=tenant_id,
            procurement=procurement,
            row=row,
            current_fx_rate=current_item.fx_rate if current_item is not None else None,
        ),
        'goods_ownership': procurement.goods_ownership,
    }
    if item_id:
        item = current_item
        for key, val in values.items():
            setattr(item, key, val)
        item.save(update_fields=list(values.keys()) + ['updated_at'])
        return item
    return ProcurementItem.objects.create(
        tenant_id=tenant_id, procurement=procurement, **values,
    )


def _upsert_workspace_item(tenant_id: int, procurement: Procurement, row: dict) -> ProcurementItem:
    item_id = row.get('id') or row.get('item_id')
    current_item = None
    if item_id:
        current_item = _draft_item_for_update(tenant_id, procurement, int(item_id))
    values = {
        'product_variant_id': int(row['product_variant_id']),
        'quantity': Decimal(str(row['quantity'])),
        'unit_purchase_price': Decimal(str(row['unit_purchase_price'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': _resolve_procurement_row_fx_rate(
            tenant_id=tenant_id,
            procurement=procurement,
            row=row,
            current_fx_rate=current_item.fx_rate if current_item is not None else None,
        ),
        'goods_ownership': procurement.goods_ownership,
    }
    if item_id:
        item = current_item
        for key, value in values.items():
            setattr(item, key, value)
        item.save(update_fields=[*values.keys(), 'updated_at'])
        return item
    return ProcurementItem.objects.create(
        tenant_id=tenant_id,
        procurement=procurement,
        lifecycle_state=ProcurementItem.LifecycleState.DRAFT,
        **values,
    )


def _upsert_workspace_expense(tenant_id: int, procurement: Procurement, row: dict) -> ProcurementExpense:
    expense_id = row.get('id') or row.get('expense_id')
    if expense_id and set(row.keys()) <= {'id', 'expense_id', 'target_item_ids'}:
        expense = _draft_expense_for_update(tenant_id, procurement, int(expense_id))
        _replace_expense_targets(
            tenant_id,
            procurement,
            expense,
            row.get('target_item_ids') or [],
        )
        return expense

    current_expense = None
    if expense_id:
        current_expense = _draft_expense_for_update(tenant_id, procurement, int(expense_id))
    values = {
        'expense_type': row['expense_type'],
        'amount': Decimal(str(row['amount'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': _resolve_procurement_row_fx_rate(
            tenant_id=tenant_id,
            procurement=procurement,
            row=row,
            current_fx_rate=current_expense.fx_rate if current_expense is not None else None,
        ),
        'allocation_method': row.get('allocation_method') or ProcurementExpense.AllocationMethod.BY_VALUE,
        'notes': row.get('notes', ''),
    }
    if expense_id:
        expense = current_expense
        for key, value in values.items():
            setattr(expense, key, value)
        expense.save(update_fields=[*values.keys(), 'updated_at'])
    else:
        expense = ProcurementExpense.objects.create(
            tenant_id=tenant_id,
            procurement=procurement,
            lifecycle_state=ProcurementExpense.LifecycleState.DRAFT,
            **values,
        )

    if 'target_item_ids' in row:
        _replace_expense_targets(
            tenant_id,
            procurement,
            expense,
            row.get('target_item_ids') or [],
        )
    return expense


def _amendment_expense_for_update(tenant_id: int, procurement: Procurement, expense_id: int) -> ProcurementExpense:
    expense = ProcurementExpense.objects.select_for_update().get(
        pk=expense_id,
        tenant_id=tenant_id,
        procurement=procurement,
    )
    if expense.lifecycle_state in (
        ProcurementExpense.LifecycleState.RECEIVED,
        ProcurementExpense.LifecycleState.CANCELLED,
    ):
        raise ValueError(
            f'Cannot amend expense {expense_id} in state {expense.lifecycle_state}.'
        )
    return expense


def _upsert_workspace_expense_for_amendment(
    tenant_id: int,
    procurement: Procurement,
    row: dict,
) -> ProcurementExpense:
    expense_id = row.get('id') or row.get('expense_id')
    if not expense_id:
        return _upsert_workspace_expense(tenant_id, procurement, row)

    expense = _amendment_expense_for_update(tenant_id, procurement, int(expense_id))
    allocated_uzs = _expense_allocated_value_uzs(expense)

    if allocated_uzs > 0:
        new_currency = str(row.get('currency') or expense.currency or 'UZS').upper()
        new_fx_rate = _resolve_procurement_row_fx_rate(
            tenant_id=tenant_id,
            procurement=procurement,
            row={**row, 'currency': new_currency},
            current_fx_rate=expense.fx_rate,
        )
        new_type = row.get('expense_type') or expense.expense_type
        if new_currency != str(expense.currency or 'UZS').upper():
            raise ValueError('Cannot change currency of an expense that is already partly received.')
        if new_fx_rate != Decimal(str(expense.fx_rate or '1')):
            raise ValueError('Cannot change FX rate of an expense that is already partly received.')
        if new_type != expense.expense_type:
            raise ValueError('Cannot change type of an expense that is already partly received.')

    values = {
        'expense_type': row.get('expense_type') or expense.expense_type,
        'amount': Decimal(str(row.get('amount', expense.amount))),
        'currency': str(row.get('currency') or expense.currency or 'UZS').upper(),
        'fx_rate': _resolve_procurement_row_fx_rate(
            tenant_id=tenant_id,
            procurement=procurement,
            row={**row, 'currency': row.get('currency') or expense.currency or 'UZS'},
            current_fx_rate=expense.fx_rate,
        ),
        'allocation_method': row.get('allocation_method') or expense.allocation_method,
        'notes': row.get('notes', expense.notes),
    }
    new_total_uzs = (values['amount'] * values['fx_rate']).quantize(Decimal('0.01'))
    if allocated_uzs > new_total_uzs:
        raise ValueError(
            f'Cannot reduce expense below already received amount. '
            f'Already allocated: {allocated_uzs} UZS, new total: {new_total_uzs} UZS.'
        )

    for key, value in values.items():
        setattr(expense, key, value)
    expense.save(update_fields=[*values.keys(), 'updated_at'])

    if 'target_item_ids' in row:
        _replace_expense_targets(
            tenant_id,
            procurement,
            expense,
            row.get('target_item_ids') or [],
        )
    return expense


def _sync_expense_lifecycle_after_amendment(expense: ProcurementExpense) -> None:
    allocated = _expense_allocated_value_uzs(expense)
    if allocated <= 0:
        return
    total = _expense_value_uzs(expense)
    next_state = (
        ProcurementExpense.LifecycleState.RECEIVED
        if allocated >= total - Decimal('0.01')
        else ProcurementExpense.LifecycleState.READY_FOR_RECEIVE
    )
    if expense.lifecycle_state != next_state:
        expense.lifecycle_state = next_state
        expense.save(update_fields=['lifecycle_state', 'updated_at'])


def _draft_item_for_update(tenant_id: int, procurement: Procurement, item_id: int) -> ProcurementItem:
    item = ProcurementItem.objects.select_for_update().get(
        pk=item_id,
        tenant_id=tenant_id,
        procurement=procurement,
    )
    if item.lifecycle_state == ProcurementItem.LifecycleState.CANCELLED:
        raise ValueError('Эта строка уже отменена.')
    if item.lifecycle_state == ProcurementItem.LifecycleState.RECEIVED:
        raise ValueError('Строка уже оприходована — изменения через корректировку (Amendment).')
    if item.lifecycle_state != ProcurementItem.LifecycleState.DRAFT:
        raise ValueError(
            'Строка уже зафиксирована платежом — прямое удаление недоступно. '
            'Используйте «Корректировку» в меню для изменения после оплаты.'
        )
    return item


def _draft_expense_for_update(tenant_id: int, procurement: Procurement, expense_id: int) -> ProcurementExpense:
    expense = ProcurementExpense.objects.select_for_update().get(
        pk=expense_id,
        tenant_id=tenant_id,
        procurement=procurement,
    )
    if expense.lifecycle_state == ProcurementExpense.LifecycleState.CANCELLED:
        raise ValueError('Этот расход уже отменён.')
    if expense.lifecycle_state == ProcurementExpense.LifecycleState.RECEIVED:
        raise ValueError('Расход уже оприходован — изменения через корректировку (Amendment).')
    if expense.lifecycle_state != ProcurementExpense.LifecycleState.DRAFT:
        raise ValueError(
            'Расход уже зафиксирован платежом — прямое удаление недоступно. '
            'Используйте «Корректировку» в меню для изменения после оплаты.'
        )
    return expense


def split_workspace_item(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
) -> tuple[ProcurementItem, ProcurementItem]:
    """Split a draft/receivable item line before posting a partial receive batch."""

    item_id = payload.get('item_id') or payload.get('id')
    split_quantity = Decimal(str(payload.get('quantity') or payload.get('split_quantity') or '0'))
    if not item_id:
        raise ValueError('item_id is required.')
    if split_quantity <= 0:
        raise ValueError('Split quantity must be > 0.')

    with transaction.atomic():
        locked_procurement = Procurement.objects.select_for_update().get(
            pk=procurement.pk,
            tenant_id=tenant_id,
        )
        if locked_procurement.status not in (
            Procurement.Status.OPEN,
            Procurement.Status.PARTIALLY_RECEIVED,
        ):
            raise ValueError(f'Cannot split item in status {locked_procurement.status}.')

        item = ProcurementItem.objects.select_for_update().get(
            pk=int(item_id),
            tenant_id=tenant_id,
            procurement=locked_procurement,
        )
        if item.lifecycle_state not in (
            ProcurementItem.LifecycleState.DRAFT,
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        ):
            raise ValueError('Only draft or receivable item lines can be split.')

        current_quantity = Decimal(str(item.quantity))
        if split_quantity >= current_quantity:
            raise ValueError('Split quantity must be less than current item quantity.')

        remaining_quantity = current_quantity - split_quantity
        item.quantity = split_quantity
        item.save(update_fields=['quantity', 'updated_at'])

        new_item = ProcurementItem.objects.create(
            tenant_id=tenant_id,
            procurement=locked_procurement,
            product_variant_id=item.product_variant_id,
            quantity=remaining_quantity,
            unit_purchase_price=item.unit_purchase_price,
            currency=item.currency,
            fx_rate=item.fx_rate,
            lifecycle_state=item.lifecycle_state,
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
                'procurement_id': locked_procurement.pk,
                'source_item_id': item.pk,
                'new_item_id': new_item.pk,
                'source_quantity': str(split_quantity),
                'new_quantity': str(remaining_quantity),
            },
            tenant_id=tenant_id,
        )
        return item, new_item


def _replace_expense_targets(
    tenant_id: int,
    procurement: Procurement,
    expense: ProcurementExpense,
    item_ids: list[int],
) -> None:
    ids = list(dict.fromkeys(int(item_id) for item_id in item_ids))
    if ids:
        existing = set(
            ProcurementItem.objects.filter(
                tenant_id=tenant_id,
                procurement=procurement,
                pk__in=ids,
            ).values_list('pk', flat=True)
        )
        if existing != set(ids):
            raise ValueError('Some expense targets do not belong to this procurement.')

    ProcurementExpenseTarget.objects.filter(
        tenant_id=tenant_id,
        expense=expense,
    ).exclude(item_id__in=ids).hard_delete()
    ProcurementExpenseTarget.all_objects.filter(
        tenant_id=tenant_id,
        expense=expense,
        item_id__in=ids,
        deleted_at__isnull=False,
    ).delete()
    existing_targets = set(
        ProcurementExpenseTarget.objects.filter(
            tenant_id=tenant_id,
            expense=expense,
            item_id__in=ids,
        ).values_list('item_id', flat=True)
    )
    ProcurementExpenseTarget.objects.bulk_create([
        ProcurementExpenseTarget(
            tenant_id=tenant_id,
            expense=expense,
            item_id=item_id,
        )
        for item_id in ids
        if item_id not in existing_targets
    ])


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


def _validate_source_transition(procurement: Procurement) -> None:
    terms = getattr(procurement, 'terms', None)
    if not terms:
        return
    allowed = allowed_settlements_for_funding(procurement.funding_source)
    if terms.type not in allowed:
        raise ValueError(f'{procurement.funding_source} does not allow {terms.type} settlement.')
    if terms.type in SUPPLIER_REQUIRED_SETTLEMENTS and not procurement.supplier_id:
        raise ValueError(f'{terms.type} settlement requires supplier.')
