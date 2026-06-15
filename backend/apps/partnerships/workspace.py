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
    _payment_status_block,
    _terms_status_for_paid_amount,
    build_workspace_payload,
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


def reverse_workspace_receive_batch(
    *,
    tenant_id: int,
    batch_id: int,
    reason: str = '',
) -> 'ProcurementReceiveBatch':
    from apps.inventory.models import Lot, LotStock, StockMovement

    with transaction.atomic():
        batch = (
            ProcurementReceiveBatch.objects
            .select_for_update()
            .select_related('procurement')
            .get(pk=batch_id, tenant_id=tenant_id)
        )

        if batch.is_reversal:
            raise ValueError(f'Batch #{batch_id} is already a reversal — cannot reverse a reversal.')
        if batch.reversal_batches.exists():
            raise ValueError(f'Batch #{batch_id} has already been reversed.')

        lot_ids = list(
            ProcurementReceiveBatchLine.objects
            .filter(tenant_id=tenant_id, batch=batch)
            .values_list('lot_id', flat=True)
        )
        sold_lot_ids = list(
            Lot.objects
            .filter(pk__in=lot_ids)
            .filter(sale_lines__isnull=False)
            .values_list('pk', flat=True)
            .distinct()
        )
        if sold_lot_ids:
            raise ValueError(
                f'Cannot reverse batch #{batch_id}: lots {sorted(sold_lot_ids)} have existing sales. '
                'Post-sale inventory corrections are not supported in E09 MVP.'
            )

        procurement = batch.procurement
        received_at = timezone.now()

        reversal_batch = ProcurementReceiveBatch(
            tenant_id=tenant_id,
            procurement=procurement,
            warehouse=batch.warehouse,
            received_at=received_at,
            items_count=batch.items_count,
            total_inventory_uzs=-batch.total_inventory_uzs,
            is_reversal=True,
            reversed_batch=batch,
        )
        reversal_batch.save()

        items_to_reopen: list[int] = []
        for line in batch.lines.select_related('lot', 'item').all():
            lot = line.lot
            qty = int(line.quantity_received)

            Lot.objects.filter(pk=lot.pk).update(reversed=True, is_active=False)
            LotStock.objects.filter(lot=lot, warehouse=batch.warehouse).update(quantity_remaining=0)

            StockMovement.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                quantity=-qty,
                from_location=batch.warehouse,
                reference_type='procurement_receive_batch_reversal',
                reference_id=reversal_batch.pk,
            )
            items_to_reopen.append(line.item_id)

        if items_to_reopen:
            ProcurementItem.objects.filter(pk__in=items_to_reopen).update(
                lifecycle_state=ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
                updated_at=received_at,
            )

        _sync_procurement_status_after_reversal(procurement, received_at)

        # E17: reversal is only reachable while the batch is fully unsold (sales
        # block it above), so the whole funding event unwinds. The agreed-vs-paid
        # gap is no longer reified as a CapitalAdvance, so there is nothing to
        # cancel — the net capital position recomputes from the remaining
        # (non-reversed) batches automatically.

        publish_event(
            event_type='receive_batch.reversed',
            payload={
                'procurement_id': procurement.pk,
                'original_batch_id': batch.pk,
                'reversal_batch_id': reversal_batch.pk,
                'reason': reason,
            },
            tenant_id=tenant_id,
        )
        return reversal_batch


def _sync_procurement_status_after_reversal(procurement: Procurement, reversed_at) -> None:
    active_non_reversal_batches = (
        ProcurementReceiveBatch.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement, is_reversal=False)
        .exclude(reversal_batches__isnull=False)
        .exists()
    )
    new_status = Procurement.Status.PARTIALLY_RECEIVED if active_non_reversal_batches else Procurement.Status.OPEN
    if procurement.status != new_status:
        Procurement.objects.filter(pk=procurement.pk).update(
            status=new_status, updated_at=reversed_at,
        )
        procurement.status = new_status


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


def pay_workspace_costs(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
) -> Payment:
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        raise ValueError('PARTNERSHIP cost payments require capital pool actions first.')
    terms = getattr(procurement, 'terms', None)
    if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
        raise ValueError('AT_RECEIPT procurement pays only at receive moment, use receive action.')
    if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
        raise ValueError('Costs can be paid only while procurement is OPEN or PARTIALLY_RECEIVED.')

    cash_account_id = payload.get('cash_account_id')
    if not cash_account_id:
        raise ValueError('cash_account_id is required.')

    item_ids = payload.get('item_ids') or payload.get('target_item_ids')
    expense_ids = payload.get('expense_ids') or payload.get('target_expense_ids')
    items = procurement.items.filter(lifecycle_state='DRAFT')
    expenses = procurement.expenses.filter(lifecycle_state='DRAFT')
    if item_ids is not None:
        items = items.filter(id__in=item_ids)
        if expense_ids is None:
            expenses = expenses.none()
    if expense_ids is not None:
        expenses = expenses.filter(id__in=expense_ids)
        if item_ids is None:
            items = items.none()

    selected_items = list(items)
    selected_expenses = list(expenses)
    amount = payload.get('amount')
    is_delta_payment = amount is not None and item_ids is None and expense_ids is None
    if not selected_items and not selected_expenses and not is_delta_payment:
        raise ValueError('No draft items or expenses selected for payment.')

    cash_account = CashAccount.objects.get(pk=cash_account_id, tenant_id=tenant_id, is_active=True)

    terms = getattr(procurement, 'terms', None)
    currency_of_obligation = (
        str(terms.currency_of_obligation).upper() if terms and terms.currency_of_obligation
        else (
            _derive_items_currency(list(selected_items))
            if selected_items
            else str(payload.get('currency') or cash_account.currency or 'UZS').upper()
        )
    )

    if str(cash_account.currency).upper() != currency_of_obligation:
        raise ValueError(
            f'Касса в {cash_account.currency}, обязательство в {currency_of_obligation}. '
            f'Сделайте обмен валют через «Касса → Обменять валюту».'
        )

    payment_currency = currency_of_obligation
    payment_fx_rate = payload.get('fx_rate')

    if amount is None:
        amount = _draft_cost_total_in_obligation_currency(selected_items, selected_expenses)
    amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('Payment amount must be > 0.')

    if terms is not None:
        terms.activate()

    payment = record_generic_cash_payment(
        tenant_id=tenant_id,
        cash_account_id=cash_account.pk,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.pk,
        amount=amount,
        currency=payment_currency,
        fx_rate=payment_fx_rate,
        counterpart_account_code='1100',
        operation_type='procurement_payment',
        description=f'Procurement #{procurement.pk} costs payment',
        client_request_id=client_request_id,
        notes=payload.get('notes', ''),
    )

    if terms and terms.type == ProcurementTerms.Type.PARTIAL:
        # terms.paid_amount is derived from the finance.Payment we just
        # created (PROCUREMENT_COST target). Only status is stored.
        terms.refresh_from_db()
        new_status = _terms_status_for_paid_amount(terms.total_amount_due, terms.paid_amount)
        if new_status != terms.status:
            terms.status = new_status
            terms.save(update_fields=['status', 'updated_at'])

    item_type = procurement.items.model
    expense_type = procurement.expenses.model
    item_type.objects.filter(pk__in=[item.pk for item in selected_items]).update(
        lifecycle_state=item_type.LifecycleState.READY_FOR_RECEIVE,
        updated_at=timezone.now(),
    )
    expense_type.objects.filter(pk__in=[expense.pk for expense in selected_expenses]).update(
        lifecycle_state=expense_type.LifecycleState.READY_FOR_RECEIVE,
        updated_at=timezone.now(),
    )
    return payment


def resolve_workspace_overpayment(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
    user_id: int | None = None,
):
    if procurement.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
        raise ValueError('Overpayment can be resolved only while procurement is OPEN or PARTIALLY_RECEIVED.')

    currency = _normalize_currency(payload.get('currency') or None)
    payments = list(Payment.objects.filter(
        tenant_id=tenant_id,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.pk,
        status=Payment.Status.POSTED,
    ))
    capital_allocations = []
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        capital_allocations = list(AgreementAllocation.objects.filter(
            tenant_id=tenant_id,
            procurement=procurement,
            confirmation_status=AgreementConfirmationStatus.CONFIRMED,
        ))
    status = _payment_status_block(
        getattr(procurement, 'terms', None),
        payments,
        items=list(procurement.items.all()),
        expenses=list(procurement.expenses.all()),
        capital_allocations=capital_allocations,
    )
    overpaid_by_currency = {
        c: -Decimal(str(value)).quantize(Decimal('0.01'))
        for c, value in status.get('remaining_by_currency', {}).items()
        if Decimal(str(value)) < 0
    }
    if not overpaid_by_currency:
        raise ValueError('Procurement has no overpayment to resolve.')
    if payload.get('currency') is None and len(overpaid_by_currency) == 1:
        currency = next(iter(overpaid_by_currency))
    max_amount = overpaid_by_currency.get(currency, Decimal('0.00'))
    if max_amount <= 0:
        raise ValueError(f'No overpayment in {currency}.')

    amount = Decimal(str(payload.get('amount') or max_amount)).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('Overpayment amount must be > 0.')
    if amount > max_amount:
        raise ValueError(f'Overpayment amount cannot exceed {max_amount} {currency}.')

    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        return _return_partnership_overpayment_to_pool(
            tenant_id=tenant_id,
            procurement=procurement,
            amount=amount,
            currency=currency,
            payload=payload,
            client_request_id=client_request_id,
            user_id=user_id,
        )
    return _record_own_funds_overpayment_refund(
        tenant_id=tenant_id,
        procurement=procurement,
        amount=amount,
        currency=currency,
        payload=payload,
        client_request_id=client_request_id,
    )


def _record_own_funds_overpayment_refund(
    *,
    tenant_id: int,
    procurement: Procurement,
    amount: Decimal,
    currency: str,
    payload: dict,
    client_request_id: str | None,
) -> Payment:
    cash_account_id = payload.get('cash_account_id')
    if not cash_account_id:
        raise ValueError('cash_account_id is required to receive supplier refund.')
    paid_at = _resolve_action_datetime(payload.get('date') or payload.get('paid_at'))

    with transaction.atomic():
        if client_request_id:
            existing = Payment.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing

        account = CashAccount.objects.select_for_update().get(
            pk=cash_account_id,
            tenant_id=tenant_id,
            is_active=True,
        )
        if account.kind == CashAccount.Kind.AGREEMENT_CAPITAL:
            raise ValueError('Use partnership overpayment action for agreement capital accounts.')
        if str(account.currency or '').upper() != currency:
            raise ValueError(f'Cash account currency must be {currency}.')

        original_payment = (
            Payment.objects
            .filter(
                tenant_id=tenant_id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=procurement.pk,
                source_type=Payment.SourceType.CASH_ACCOUNT,
                currency=currency,
                status=Payment.Status.POSTED,
                reversed_payment__isnull=True,
            )
            .order_by('-paid_at', '-id')
            .first()
        )
        if original_payment is None:
            raise ValueError('No posted procurement payment found for this currency.')

        fx_rate = Decimal(str(payload.get('fx_rate') or original_payment.fx_rate or '1')).quantize(Decimal('0.000001'))
        payment = Payment.objects.create(
            tenant_id=tenant_id,
            source_type=Payment.SourceType.CASH_ACCOUNT,
            source_id=account.pk,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.pk,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            paid_at=paid_at,
            client_request_id=client_request_id,
            reversed_payment=original_payment,
            notes=payload.get('notes') or f'Overpayment refund for procurement #{procurement.pk}',
        )
        PaymentAllocation.objects.create(
            tenant_id=tenant_id,
            payment=payment,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.pk,
            amount=amount,
            currency=currency,
        )
        cash_entry = create_cash_entry(
            tenant_id=tenant_id,
            account=account,
            direction=CashEntry.Direction.IN,
            amount=amount,
            date=paid_at,
            source_ref_type='finance_payment',
            source_ref_id=payment.pk,
        )
        journal = record_journal_from_cash_entry(
            tenant_id=tenant_id,
            cash_entry=cash_entry,
            operation_type='payment_refund',
            operation_id=payment.pk,
            counterpart_account_code='1100',
            description=f'Procurement #{procurement.pk} overpayment refund',
            date=paid_at,
        )
        payment.journal_entry = journal
        payment.save(update_fields=['journal_entry', 'updated_at'])

        publish_event(
            event_type='finance.payment.reversed',
            payload={
                'payment_id': payment.pk,
                'reversed_payment_id': original_payment.pk,
                'target_type': payment.target_type,
                'target_id': payment.target_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
        return payment


def _return_partnership_overpayment_to_pool(
    *,
    tenant_id: int,
    procurement: Procurement,
    amount: Decimal,
    currency: str,
    payload: dict,
    client_request_id: str | None,
    user_id: int | None,
) -> list[AgreementAllocation]:
    paid_at = _resolve_action_datetime(payload.get('date') or payload.get('paid_at'))
    agreement = _require_workspace_agreement(procurement)

    with transaction.atomic():
        if client_request_id:
            existing = list(AgreementAllocation.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
                direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
            ))
            if existing:
                return existing

        locked_agreement = (
            InvestmentAgreement.objects
            .select_for_update()
            .prefetch_related('partners', 'allocations')
            .get(pk=agreement.pk, tenant_id=tenant_id)
        )
        locked_procurement = Procurement.objects.select_for_update().get(
            pk=procurement.pk,
            tenant_id=tenant_id,
        )
        pool = get_or_create_currency_pool(
            tenant_id=tenant_id,
            agreement=locked_agreement,
            currency=currency,
        )
        pool = CashAccount.objects.select_for_update().get(
            pk=pool.pk,
            tenant_id=tenant_id,
            is_active=True,
        )
        if str(pool.currency or '').upper() != currency:
            raise ValueError(f'Agreement capital pool currency must be {currency}.')

        partner_splits = _resolve_overpayment_partner_splits(
            locked_procurement,
            currency=currency,
            requested_partner_id=payload.get('partner_id'),
            amount=amount,
        )
        fx_rate = Decimal(str(payload.get('fx_rate') or '1')).quantize(Decimal('0.000001'))
        original_payment = (
            Payment.objects
            .filter(
                tenant_id=tenant_id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=locked_procurement.pk,
                source_type=Payment.SourceType.CAPITAL_POOL,
                source_id=pool.pk,
                currency=currency,
                status=Payment.Status.POSTED,
                reversed_payment__isnull=True,
            )
            .order_by('-paid_at', '-id')
            .first()
        )
        if original_payment is not None:
            fx_rate = Decimal(str(payload.get('fx_rate') or original_payment.fx_rate or fx_rate)).quantize(Decimal('0.000001'))

        payment = Payment.objects.create(
            tenant_id=tenant_id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            source_id=pool.pk,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=locked_procurement.pk,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            paid_at=paid_at,
            reversed_payment=original_payment,
            notes=f'Capital pool return for procurement #{locked_procurement.pk}',
        )
        PaymentAllocation.objects.create(
            tenant_id=tenant_id,
            payment=payment,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=locked_procurement.pk,
            amount=amount,
            currency=currency,
        )
        cash_entry = create_cash_entry(
            tenant_id=tenant_id,
            account=pool,
            direction=CashEntry.Direction.IN,
            amount=amount,
            date=paid_at,
            source_ref_type='finance_payment',
            source_ref_id=payment.pk,
        )
        functional_amount = (amount * fx_rate).quantize(Decimal('0.01'))
        journal = record_pool_journal_functional(
            tenant_id=tenant_id,
            cash_entry=cash_entry,
            functional_amount_uzs=functional_amount,
            operation_type='capital_return',
            operation_id=payment.pk,
            counterpart_account_code='1100',
            description=f'Procurement #{locked_procurement.pk} overpayment returned to capital pool',
            date=paid_at,
        )
        payment.journal_entry = journal
        payment.save(update_fields=['journal_entry', 'updated_at'])

        allocations: list[AgreementAllocation] = []
        for partner_id, split_amount in partner_splits:
            allocation = AgreementAllocation.objects.create(
                tenant_id=tenant_id,
                agreement=locked_agreement,
                procurement=locked_procurement,
                partner_id=partner_id,
                direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
                amount=split_amount,
                currency=currency,
                fx_rate=fx_rate,
                date=paid_at,
                source=AgreementActionSource.BUSINESS_RECORDED,
                confirmation_status=AgreementConfirmationStatus.CONFIRMED,
                created_by_id=user_id,
                actor_partner_id=partner_id,
                notes=_with_client_request_id(
                    payload.get('notes') or f'Overpayment returned from procurement #{locked_procurement.pk}',
                    client_request_id,
                ),
                client_request_id=client_request_id,
            )
            allocations.append(allocation)
            ledger = get_or_create_ledger(
                procurement_id=locked_procurement.pk,
                partner_id=partner_id,
                tenant_id=tenant_id,
            )
            append_ledger_entry(
                ledger=ledger,
                entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
                amount=split_amount,
                currency=currency,
                fx_rate=fx_rate,
                source_ref=f'allocation:{allocation.pk}',
                date=paid_at,
            )
            record_agreement_event(
                tenant_id=tenant_id,
                agreement=locked_agreement,
                event_type='allocation.from_procurement',
                source=AgreementActionSource.BUSINESS_RECORDED,
                actor_user_id=user_id,
                actor_partner_id=partner_id,
                related_model='AgreementAllocation',
                related_id=allocation.pk,
                payload={
                    'procurement_id': locked_procurement.pk,
                    'partner_id': partner_id,
                    'amount': str(split_amount),
                    'currency': currency,
                    'payment_id': payment.pk,
                },
            )
        publish_event(
            event_type='investment_agreement.returned_from_procurement',
            payload={
                'agreement_id': locked_agreement.pk,
                'procurement_id': locked_procurement.pk,
                'allocation_ids': [allocation.pk for allocation in allocations],
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )
        return allocations


def _resolve_overpayment_partner_splits(
    procurement: Procurement,
    *,
    currency: str,
    requested_partner_id,
    amount: Decimal,
) -> list[tuple[int, Decimal]]:
    net_by_partner: dict[int, Decimal] = {}
    for allocation in AgreementAllocation.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
        currency=currency,
        confirmation_status=AgreementConfirmationStatus.CONFIRMED,
    ):
        delta = Decimal(str(allocation.amount))
        if allocation.direction == AgreementAllocation.Direction.FROM_PROCUREMENT:
            delta = -delta
        net_by_partner[allocation.partner_id] = (
            net_by_partner.get(allocation.partner_id, Decimal('0')) + delta
        ).quantize(Decimal('0.01'))

    if requested_partner_id:
        partner_id = int(requested_partner_id)
        available = net_by_partner.get(partner_id, Decimal('0.00'))
        if available < amount:
            raise ValueError(f'Selected partner has only {available} {currency} allocated to this procurement.')
        return [(partner_id, amount)]

    candidates = sorted(net_by_partner.items(), key=lambda row: row[1], reverse=True)
    remaining = amount
    splits: list[tuple[int, Decimal]] = []
    for partner_id, available in candidates:
        if available <= 0:
            continue
        split = min(available, remaining).quantize(Decimal('0.01'))
        if split <= 0:
            continue
        splits.append((partner_id, split))
        remaining = (remaining - split).quantize(Decimal('0.01'))
        if remaining <= 0:
            return splits
    raise ValueError('Partner allocations cannot cover this overpayment amount.')


def _resolve_action_datetime(value):
    if not value:
        return timezone.now()
    if hasattr(value, 'isoformat'):
        return value
    parsed = parse_datetime(str(value))
    return parsed or timezone.now()


def pay_workspace_supplier_payable(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
    client_request_id: str | None = None,
):
    terms = getattr(procurement, 'terms', None)
    if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
        raise ValueError('AT_RECEIPT procurement pays only at receive moment, use receive action.')
    payable_id = payload.get('payable_id')
    if not payable_id:
        raise ValueError('payable_id is required.')
    payable = SupplierPayable.objects.get(
        pk=payable_id,
        tenant_id=tenant_id,
        procurement=procurement,
    )

    terms = getattr(procurement, 'terms', None)
    if terms is not None:
        terms.activate()

    allocations = payload.get('allocations')
    if not allocations:
        cash_account_id = payload.get('cash_account_id')
        amount = payload.get('amount')
        if not cash_account_id or amount is None:
            raise ValueError('cash_account_id and amount are required.')
        account = CashAccount.objects.get(pk=cash_account_id, tenant_id=tenant_id, is_active=True)
        obligation_currency = str(payable.currency_of_obligation).upper()
        if str(account.currency).upper() != obligation_currency:
            raise ValueError(
                f'Касса в {account.currency}, обязательство в {obligation_currency}. '
                f'Сделайте обмен валют через «Касса → Обменять валюту».'
            )
        allocations = [{
            'cash_account_id': cash_account_id,
            'amount': amount,
            'currency': obligation_currency,
        }]

    return record_payable_payment(
        tenant_id=tenant_id,
        payable_id=payable.pk,
        allocations=allocations,
        payment_date=payload.get('paid_at'),
        schedule_entry_id=payload.get('schedule_entry_id'),
        notes=payload.get('notes', ''),
        client_request_id=client_request_id,
    )


def receive_workspace_batch(
    *,
    tenant_id: int,
    procurement: Procurement,
    payload: dict,
) -> ProcurementReceiveBatch:
    warehouse_id = payload.get('warehouse_id') or payload.get('destination_warehouse_id')
    if not warehouse_id:
        raise ValueError('warehouse_id is required.')
    received_at = _coerce_datetime(payload.get('received_at')) or timezone.now()

    with transaction.atomic():
        locked = Procurement.objects.select_for_update().get(pk=procurement.pk, tenant_id=tenant_id)
        if locked.status not in (Procurement.Status.OPEN, Procurement.Status.PARTIALLY_RECEIVED):
            raise ValueError(f'Cannot receive procurement in status {locked.status}.')

        terms = getattr(locked, 'terms', None)
        if terms and terms.type == ProcurementTerms.Type.INSTALLMENT and not terms.schedule_entries.exists():
            raise ValueError('INSTALLMENT settlement requires payment schedule.')
        if terms and terms.type == ProcurementTerms.Type.PARTIAL and not _has_procurement_cost_payment(locked):
            raise ValueError('PARTIAL settlement requires an upfront payment before receive.')
        if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
            if locked.funding_source == Procurement.FundingSource.OWN_FUNDS:
                if not payload.get('payment_payload'):
                    raise ValueError('AT_RECEIPT OWN_FUNDS procurement requires payment_payload in receive action.')
        if terms and terms.type == ProcurementTerms.Type.PREPAID:
            _check_prepaid_coverage(tenant_id, locked, payload)
        if terms is not None:
            terms.activate()
        allowed_states = _receivable_line_states(locked, terms)
        requested_item_ids = {int(item_id) for item_id in payload.get('item_ids') or []}
        items_qs = (
            ProcurementItem.objects
            .select_for_update()
            .filter(tenant_id=tenant_id, procurement=locked, lifecycle_state__in=allowed_states)
            .select_related('product_variant')
        )
        if requested_item_ids:
            items_qs = items_qs.filter(pk__in=requested_item_ids)
        items = list(items_qs)
        if requested_item_ids and {item.id for item in items} != requested_item_ids:
            raise ValueError('Some selected items are not receivable or do not belong to this procurement.')
        if not items:
            raise ValueError('No receivable items selected.')

        selected_item_ids = {item.id for item in items}

        # Parse and validate discrepancy info from payload (Slice 3 / Wave A)
        raw_discrepancies = payload.get('item_discrepancies') or {}
        discrepancy_map: dict[int, dict] = {}
        for item in items:
            raw = raw_discrepancies.get(str(item.id)) or raw_discrepancies.get(item.id) or {}
            qty_planned = Decimal(str(item.quantity))
            qty_received_raw = raw.get('qty_received')
            qty_received = Decimal(str(qty_received_raw)) if qty_received_raw is not None else qty_planned
            reason = str(raw.get('discrepancy_reason') or ProcurementReceiveBatchLine.DiscrepancyReason.NONE).upper()
            if qty_received > qty_planned:
                raise ValueError(
                    f'Item #{item.id}: qty_received ({qty_received}) cannot exceed '
                    f'qty_planned ({qty_planned}).'
                )
            if qty_received < qty_planned and reason == ProcurementReceiveBatchLine.DiscrepancyReason.NONE:
                raise ValueError(
                    f'Item #{item.id}: discrepancy_reason is required when qty_received ({qty_received}) '
                    f'< qty_planned ({qty_planned}).'
                )
            discrepancy_map[item.id] = {
                'qty_received': qty_received,
                'reason': reason,
            }

        has_delayed_lines = ProcurementItem.objects.filter(
            tenant_id=tenant_id,
            procurement=locked,
        ).exclude(
            lifecycle_state__in=[ProcurementItem.LifecycleState.RECEIVED, ProcurementItem.LifecycleState.CANCELLED],
        ).exclude(pk__in=selected_item_ids).exists()

        expenses = _expenses_for_receive(
            procurement=locked,
            selected_item_ids=selected_item_ids,
            allowed_states=allowed_states,
            is_partial_receive=has_delayed_lines,
        )
        expense_allocations_uzs, expense_values_uzs = _landed_expense_allocations(items, expenses)
        item_values_uzs = [_item_value_uzs(item) for item in items]
        total_inventory_uzs = (
            sum(item_values_uzs, Decimal('0'))
            + sum(expense_allocations_uzs, Decimal('0'))
        ).quantize(Decimal('0.01'))

        contract_snapshot: dict = {}
        capital_rows: list[dict] = []
        # E14/E17: the reconciliation path (AGREED = hold agreed shares, gap shows
        # as a net capital position; FACTUAL = dynamic recalc) is fixed on the
        # AGREEMENT at creation — the receive only reflects it, it does not
        # re-choose. Read from the agreement.
        share_basis = 'FACTUAL'
        if locked.funding_source == Procurement.FundingSource.PARTNERSHIP:
            _agreement_for_basis = _require_workspace_agreement(locked)
            share_basis = str(_agreement_for_basis.reconciliation_mode or 'FACTUAL').upper()
            # E12: fund the receive out of the capital pools, per obligation
            # currency (base direct; non-base via FIFO cost-basis). The returned
            # base cost drives shares — honest acquisition cost, not market rate.
            required_base = None
            if locked.goods_ownership != Procurement.GoodsOwnership.CONSIGNED and total_inventory_uzs > 0:
                native_by_ccy, func_by_ccy = _receive_funding_breakdown(
                    items,
                    item_values_uzs,
                    expenses,
                    expense_allocations_uzs,
                    expense_values_uzs,
                )
                if _partnership_receive_lines_already_paid(items, expenses):
                    required_base = _prepaid_partnership_receive_base_cost(
                        tenant_id=tenant_id,
                        procurement=locked,
                        native_by_ccy=native_by_ccy,
                        func_by_ccy=func_by_ccy,
                        received_at=received_at,
                    )
                else:
                    required_base = _fund_partnership_receive_from_pools(
                        tenant_id=tenant_id,
                        procurement=locked,
                        native_by_ccy=native_by_ccy,
                        func_by_ccy=func_by_ccy,
                        received_at=received_at,
                    )
            if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
                _pre_allocate_at_receipt_partnership_capital(
                    tenant_id=tenant_id,
                    procurement=locked,
                    required_uzs=total_inventory_uzs,
                    raw_allocations=payload.get('capital_allocations'),
                    received_at=received_at,
                    required_base=required_base,
                )
            contract_snapshot, capital_rows = _resolve_workspace_capital_snapshot(
                tenant_id=tenant_id,
                procurement=locked,
                required_uzs=total_inventory_uzs,
                raw_allocations=payload.get('capital_allocations') or payload.get('allocations'),
                received_at=received_at,
                required_base=required_base,
                share_basis=share_basis,
            )

        batch = ProcurementReceiveBatch.objects.create(
            tenant_id=tenant_id,
            procurement=locked,
            warehouse_id=warehouse_id,
            received_at=received_at,
            items_count=len(items),
            total_inventory_uzs=total_inventory_uzs,
        )
        for row in capital_rows:
            ProcurementReceiveBatchCapitalAllocation.objects.create(
                tenant_id=tenant_id,
                batch=batch,
                partner_id=row['partner_id'],
                role=row['role'],
                amount_contract_currency=row['amount_contract_currency'],
                capital_share=row['capital_share'],
                profit_share=row['profit_share'],
            )

        # E17 T-2.1: the AGREED funding gap (agreed shares vs actual cash) is no
        # longer reified as a CapitalAdvance. Shares stay pinned to the agreed
        # snapshot (Rule #14); the gap is read as the partner's net capital
        # position (partner_capital_positions: owed / withdrawable) and settled
        # via settle-partner-capital. Single source of truth = net position.

        from apps.inventory.models import Lot, LotStock, StockMovement

        items_to_mark_received: list[int] = []

        for item, allocated_expense_uzs in zip(items, expense_allocations_uzs):
            disc = discrepancy_map[item.id]
            qty_received = disc['qty_received']
            discrepancy_reason = disc['reason']
            qty_planned = Decimal(str(item.quantity))

            # ACCEPT_AS_SHORTFALL → consider item fully received at qty_received
            if discrepancy_reason == ProcurementReceiveBatchLine.DiscrepancyReason.ACCEPT_AS_SHORTFALL:
                ProcurementItem.objects.filter(pk=item.id).update(quantity=qty_received)
                item.quantity = qty_received
                items_to_mark_received.append(item.id)
            elif qty_received >= qty_planned:
                items_to_mark_received.append(item.id)
            # else: partial with MISSING_EXPECTED_LATER/DAMAGED/QUALITY_REJECT → item stays open

            item_unit_price_uzs = (
                Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
            ).quantize(Decimal('0.01'))
            quantity = int(qty_received)
            if quantity <= 0:
                raise ValueError('Item quantity must be positive.')
            landed_per_unit = (
                item_unit_price_uzs + (Decimal(str(allocated_expense_uzs)) / Decimal(str(quantity)))
            ).quantize(Decimal('0.01'))
            lot = Lot.objects.create(
                tenant_id=tenant_id,
                procurement_item=item,
                product_variant_id=item.product_variant_id,
                quantity_initial=quantity,
                unit_purchase_price=item_unit_price_uzs,
                landed_cost_per_unit=landed_per_unit,
                contract_snapshot=contract_snapshot,
                received_at=received_at,
                is_owned=(item.goods_ownership == Procurement.GoodsOwnership.OWNED),
                is_active=True,
            )
            LotStock.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                warehouse_id=warehouse_id,
                quantity_remaining=quantity,
            )
            StockMovement.objects.create(
                tenant_id=tenant_id,
                lot=lot,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity=quantity,
                to_location_id=warehouse_id,
                reference_type='procurement_receive_batch',
                reference_id=batch.id,
            )
            ProcurementReceiveBatchLine.objects.create(
                tenant_id=tenant_id,
                batch=batch,
                item=item,
                lot=lot,
                quantity_planned=qty_planned,
                quantity_received=qty_received,
                discrepancy_reason=discrepancy_reason,
                unit_purchase_price_uzs=item_unit_price_uzs,
                allocated_expense_uzs=allocated_expense_uzs,
                landed_cost_per_unit_uzs=landed_per_unit,
            )

        expenses_to_mark_received: list[int] = []
        for expense in expenses:
            allocated_amount_uzs = Decimal(str(expense_values_uzs.get(expense.id, Decimal('0.00')))).quantize(Decimal('0.01'))
            if allocated_amount_uzs <= 0:
                continue
            is_fully_allocated = _expense_is_fully_allocated_after_receive(expense, allocated_amount_uzs)
            ProcurementReceiveBatchExpense.objects.create(
                tenant_id=tenant_id,
                batch=batch,
                expense=expense,
                allocated_amount_uzs=allocated_amount_uzs,
            )
            if is_fully_allocated:
                expenses_to_mark_received.append(expense.id)

        if items_to_mark_received:
            ProcurementItem.objects.filter(pk__in=items_to_mark_received).update(
                lifecycle_state=ProcurementItem.LifecycleState.RECEIVED,
                updated_at=received_at,
            )
        if expenses_to_mark_received:
            ProcurementExpense.objects.filter(pk__in=expenses_to_mark_received).update(
                lifecycle_state=ProcurementExpense.LifecycleState.RECEIVED,
                updated_at=received_at,
            )

        _sync_procurement_status_after_receive(locked, received_at)
        payable = _ensure_supplier_payable_after_receive(tenant_id, locked, terms)
        if locked.funding_source != Procurement.FundingSource.PARTNERSHIP:
            _record_receive_journal(
                tenant_id=tenant_id,
                procurement=locked,
                batch=batch,
                amount=total_inventory_uzs,
                payable=payable,
                received_at=received_at,
            )
        # PARTNERSHIP receives were already funded from the capital pools above
        # (E12 _fund_partnership_receive_from_pools), per obligation currency.
        upsert_supplier_links_for_items(tenant_id, locked, items, received_at)

        at_receipt_payment = None
        if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
            if locked.funding_source == Procurement.FundingSource.OWN_FUNDS:
                pp = payload['payment_payload']
                cash_account = CashAccount.objects.get(
                    pk=pp['cash_account_id'], tenant_id=tenant_id, is_active=True,
                )
                # Money discipline: an AT_RECEIPT obligation is paid only from a
                # cash account in the obligation's currency. No implicit
                # conversion and no paying a foreign-currency obligation from a
                # mismatched account (that booked e.g. $440 as 440 UZS).
                obligation_currency = (
                    str(terms.currency_of_obligation).upper()
                    if terms.currency_of_obligation
                    else _derive_items_currency(list(items))
                )
                if str(cash_account.currency).upper() != obligation_currency:
                    raise ValueError(
                        f'Касса в {cash_account.currency}, обязательство в {obligation_currency}. '
                        f'Оплатить можно только с кассы в валюте обязательства — '
                        f'пополните её или сделайте обмен через «Касса → Обменять валюту».'
                    )
                at_receipt_payment = record_generic_cash_payment(
                    tenant_id=tenant_id,
                    cash_account_id=cash_account.pk,
                    target_type=Payment.TargetType.PROCUREMENT_COST,
                    target_id=locked.pk,
                    amount=Decimal(str(pp['amount'])),
                    currency=obligation_currency,
                    fx_rate=pp.get('fx_rate'),
                    counterpart_account_code='1100',
                    operation_type='procurement_payment',
                    description=f'Procurement #{locked.pk} AT_RECEIPT payment',
                    client_request_id=pp.get('client_request_id'),
                    notes=pp.get('notes', ''),
                )
                terms.refresh_from_db()
                new_status = _terms_status_for_paid_amount(terms.total_amount_due, terms.paid_amount)
                if new_status != terms.status:
                    terms.status = new_status
                    terms.save(update_fields=['status', 'updated_at'])
            # PARTNERSHIP × AT_RECEIPT: capital was drawn atomically via
            # _pre_allocate_at_receipt_partnership_capital; no separate CashAccount payment.

        publish_event(
            event_type='procurement.receive_batch_posted',
            payload={
                'procurement_id': locked.id,
                'receive_batch_id': batch.id,
                'warehouse_id': warehouse_id,
                'items_count': len(items),
                'total_inventory_uzs': str(total_inventory_uzs),
                'payable_id': payable.id if payable else None,
                'at_receipt_payment_id': at_receipt_payment.id if at_receipt_payment else None,
            },
            tenant_id=tenant_id,
        )
        return batch


def _check_prepaid_coverage(tenant_id: int, procurement: Procurement, payload: dict) -> None:
    """PREPAID: items being received must not exceed total payments made so far."""
    from apps.inventory.models import Lot

    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        # Partnership prepayment is capital allocated to the procurement, not a cash Payment row.
        return

    total_paid_uzs = (
        Payment.objects
        .filter(
            tenant_id=tenant_id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement.id,
            status=Payment.Status.POSTED,
        )
        .aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
    )
    total_paid_uzs = Decimal(str(total_paid_uzs)).quantize(Decimal('0.01'))

    item_discrepancies = payload.get('item_discrepancies') or {}
    requested_item_ids = {int(x) for x in payload.get('item_ids') or []}

    items_qs = ProcurementItem.objects.filter(
        tenant_id=tenant_id,
        procurement=procurement,
        lifecycle_state__in=(
            ProcurementItem.LifecycleState.DRAFT,
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        ),
    )
    if requested_item_ids:
        items_qs = items_qs.filter(pk__in=requested_item_ids)

    cost_uzs = Decimal('0')
    for item in items_qs:
        raw = item_discrepancies.get(str(item.id)) or item_discrepancies.get(item.id) or {}
        qty_received_raw = raw.get('qty_received')
        qty = Decimal(str(qty_received_raw)) if qty_received_raw is not None else Decimal(str(item.quantity))
        item_cost_uzs = qty * Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
        cost_uzs += item_cost_uzs

    already_received_cost_uzs = Decimal('0')
    for lot in Lot.objects.filter(
        tenant_id=tenant_id,
        procurement_item__procurement=procurement,
        reversed=False,
    ):
        already_received_cost_uzs += (
            Decimal(str(lot.quantity_initial)) * Decimal(str(lot.unit_purchase_price))
        )

    total_cost_uzs = (cost_uzs + already_received_cost_uzs).quantize(Decimal('0.01'))
    if total_cost_uzs > total_paid_uzs:
        raise ValueError(
            f'Cannot receive items exceeding payment coverage in PREPAID procurement. '
            f'Total cost: {total_cost_uzs} UZS, total paid: {total_paid_uzs} UZS. '
            f'Pay {total_cost_uzs - total_paid_uzs} UZS more before receiving.'
        )


def _has_procurement_cost_payment(procurement: Procurement) -> bool:
    return Payment.objects.filter(
        tenant_id=procurement.tenant_id,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.id,
        status=Payment.Status.POSTED,
    ).exists()


def _receivable_line_states(procurement: Procurement, terms) -> tuple[str, ...]:
    if terms and terms.type == ProcurementTerms.Type.PREPAID:
        return (ProcurementItem.LifecycleState.READY_FOR_RECEIVE,)
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        return (
            ProcurementItem.LifecycleState.DRAFT,
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        )
    if terms and terms.type != ProcurementTerms.Type.PREPAID:
        return (
            ProcurementItem.LifecycleState.DRAFT,
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        )
    return (ProcurementItem.LifecycleState.READY_FOR_RECEIVE,)


def _expenses_for_receive(
    *,
    procurement: Procurement,
    selected_item_ids: set[int],
    allowed_states: tuple[str, ...],
    is_partial_receive: bool,
) -> list:
    expenses = list(
        procurement.expenses
        .filter(lifecycle_state__in=allowed_states)
        .prefetch_related('targets')
    )
    if not is_partial_receive:
        return expenses

    selected = []
    for expense in expenses:
        target_ids = {target.item_id for target in expense.targets.all()}
        if not target_ids:
            selected.append(expense)
            continue
        touches_selected = bool(target_ids & selected_item_ids)
        if touches_selected:
            selected.append(expense)
    return selected


def _draft_cost_total_uzs(items, expenses) -> Decimal:
    """Thin alias for reporting — use procurement_cost_uzs_for_reporting directly."""
    return procurement_cost_uzs_for_reporting(items, expenses)


def _draft_cost_total_in_obligation_currency(items, expenses) -> Decimal:
    """Thin alias — delegates to procurement_cost_by_currency (single-currency path).

    Returns the single obligation-currency total. Mixed currencies raise via
    _derive_items_currency at save time; here we assume single-currency input.
    """
    cost_map = procurement_cost_by_currency(items, expenses)
    if not cost_map:
        return Decimal('0.00')
    if len(cost_map) > 1:
        raise ValueError(
            'Mixed currencies in obligation cost — only one currency allowed per procurement. '
            f'Found: {", ".join(sorted(cost_map))}.'
        )
    return next(iter(cost_map.values()))


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


def _sync_procurement_status_after_receive(procurement: Procurement, received_at) -> None:
    has_pending = (
        ProcurementItem.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement)
        .exclude(lifecycle_state__in=[ProcurementItem.LifecycleState.RECEIVED, ProcurementItem.LifecycleState.CANCELLED])
        .exists()
        or ProcurementExpense.objects
        .filter(tenant_id=procurement.tenant_id, procurement=procurement)
        .exclude(lifecycle_state__in=[ProcurementExpense.LifecycleState.RECEIVED, ProcurementExpense.LifecycleState.CANCELLED])
        .exists()
    )
    if has_pending:
        procurement.status = Procurement.Status.PARTIALLY_RECEIVED
        procurement.save(update_fields=['status', 'updated_at'])
    else:
        procurement.status = Procurement.Status.RECEIVED
        procurement.received_at = received_at
        procurement.save(update_fields=['status', 'received_at', 'updated_at'])


def _partnership_receive_lines_already_paid(items, expenses) -> bool:
    lines = [*items, *expenses]
    return bool(lines) and all(
        line.lifecycle_state == line.LifecycleState.READY_FOR_RECEIVE
        for line in lines
    )


def _prepaid_partnership_receive_base_cost(
    *, tenant_id: int, procurement: Procurement, native_by_ccy, func_by_ccy, received_at,
) -> Decimal:
    agreement = _require_workspace_agreement(procurement)
    base_ccy = str(agreement.currency or 'UZS').upper()
    total_base_cost = Decimal('0')
    for ccy in sorted(func_by_ccy.keys()):
        native_amt = Decimal(str(native_by_ccy[ccy])).quantize(Decimal('0.01'))
        if native_amt <= 0:
            continue
        if ccy == base_ccy:
            total_base_cost += native_amt
        else:
            total_base_cost += _amount_uzs_to_currency(
                tenant_id=tenant_id,
                amount_uzs=Decimal(str(func_by_ccy[ccy])).quantize(Decimal('0.01')),
                currency=base_ccy,
                received_at=received_at,
            )
    return total_base_cost.quantize(Decimal('0.01'))


def _fund_partnership_receive_from_pools(
    *, tenant_id: int, procurement: Procurement, native_by_ccy, func_by_ccy, received_at,
) -> Decimal:
    """E12: fund a partnership receive batch out of the agreement's capital pools,
    per obligation currency. Returns the total base-currency cost (cost-basis).

    - Base-currency costs are paid straight from the base pool; base cost = native.
    - Non-base costs are paid from that currency's sub-pool, and their base cost
      is the FIFO cost-basis (real conversion rate), NOT the receive-day market
      rate — so shares/snapshot use the honest acquisition cost.

    GL books DR 1100 / CR 1300 in functional UZS per currency; equity was already
    recognised at contribution, so receive never re-credits 3100/3000.
    """
    from apps.partnerships.multicurrency import (
        get_or_create_currency_pool,
        spend_pool_cost_basis,
    )

    agreement = _require_workspace_agreement(procurement)
    if not agreement.capital_account_id:
        raise ValueError('Partnership agreement has no capital pool.')
    base_ccy = str(agreement.currency or 'UZS').upper()

    total_base_cost = Decimal('0')
    for ccy in sorted(func_by_ccy.keys()):
        func_uzs = Decimal(str(func_by_ccy[ccy])).quantize(Decimal('0.01'))
        native_amt = Decimal(str(native_by_ccy[ccy])).quantize(Decimal('0.01'))
        if func_uzs <= 0 or native_amt <= 0:
            continue

        pool = get_or_create_currency_pool(
            tenant_id=tenant_id, agreement=agreement, currency=ccy,
        )
        if ccy == base_ccy:
            base_cost_ccy = native_amt
        else:
            # FIFO cost-basis of the spent foreign currency (full precision).
            base_cost_ccy = spend_pool_cost_basis(
                tenant_id=tenant_id, agreement_id=agreement.id,
                currency=ccy, amount=native_amt,
                source_ref=f'procurement:{procurement.pk}',
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
            paid_at=received_at,
            operation_type='procurement_payment',
            description=f'Procurement #{procurement.pk} funded from capital pool ({ccy})',
        )
        total_base_cost += Decimal(str(base_cost_ccy))

    return total_base_cost.quantize(Decimal('0.01'))



def _ensure_supplier_payable_after_receive(tenant_id: int, procurement: Procurement, terms):
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        return None  # E11: partnership cost is settled from the capital pool, no supplier A/P
    if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
        return None  # CONSIGNED → payable создаётся per-sale, не at-receive
    if not terms or terms.type in _SUPPLIER_OPTIONAL_TYPES:
        return None  # PREPAID and AT_RECEIPT settle in cash immediately — no payable needed
    existing = SupplierPayable.objects.filter(
        tenant_id=tenant_id,
        procurement=procurement,
        reason=SupplierPayable.Reason.PROCUREMENT,
    ).first()
    if existing:
        return existing
    if not procurement.supplier_id:
        raise ValueError(f'Supplier is required for {terms.type} settlement.')
    return create_payable_from_procurement(
        tenant_id=tenant_id,
        procurement_id=procurement.id,
        supplier_id=procurement.supplier_id,
        terms=terms,
        deadline_date=terms.deadline_date,
    )


def _record_receive_journal(*, tenant_id: int, procurement: Procurement, batch, amount: Decimal, payable, received_at) -> None:
    # PARTNERSHIP receives are funded from the capital pool
    # (_draw_partnership_inventory_from_pool); this path is OWN_FUNDS only.
    if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
        return  # CONSIGNED inventory не на нашем балансе — никакого journal
    if amount <= 0:
        return
    already_paid = Payment.objects.filter(
        tenant_id=tenant_id,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.id,
        status=Payment.Status.POSTED,
    ).exists()
    if already_paid:
        return
    credit_code = '2000' if payable else '1000'
    create_journal_entry(
        tenant_id=tenant_id,
        operation_type='receipt',
        operation_id=batch.id,
        lines=[
            {
                'account_code': '1100',
                'debit': amount,
                'credit': Decimal('0'),
                'description': f'Procurement #{procurement.id} batch #{batch.id} inventory receipt',
            },
            {
                'account_code': credit_code,
                'debit': Decimal('0'),
                'credit': amount,
                'description': f'Procurement #{procurement.id} batch #{batch.id} funding source',
            },
        ],
        description=f'Procurement #{procurement.id} receive batch #{batch.id}',
        date=received_at,
    )


def _validate_source_transition(procurement: Procurement) -> None:
    terms = getattr(procurement, 'terms', None)
    if not terms:
        return
    allowed = allowed_settlements_for_funding(procurement.funding_source)
    if terms.type not in allowed:
        raise ValueError(f'{procurement.funding_source} does not allow {terms.type} settlement.')
    if terms.type in SUPPLIER_REQUIRED_SETTLEMENTS and not procurement.supplier_id:
        raise ValueError(f'{terms.type} settlement requires supplier.')
