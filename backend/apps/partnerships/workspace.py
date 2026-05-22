from __future__ import annotations

from decimal import Decimal

from django.db import models, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import CashAccount, Payment
from apps.finance.services import (
    create_journal_entry,
    record_generic_cash_payment,
    record_partner_capital_contribution_payment,
)
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


ACTION_MAP = {
    'edit_source': 'UPDATE_SOURCE',
    'edit_items': 'UPDATE_ITEMS',
    'pay': 'PAY_COSTS',
    'pay_from_capital_pool': 'PAY_COSTS',
    'pay_supplier_payable': 'PAY_SUPPLIER_PAYABLE',
    'receive': 'RECEIVE_BATCH',
    'amend_terms': 'AMEND_SETTLEMENT',
    'view_history': 'VIEW_HISTORY',
    'cancel': 'CANCEL_PROCUREMENT',
    'reverse_batch': 'REVERSE_BATCH',
    'amend_items': 'AMEND_ITEMS',
    'amend_expenses': 'AMEND_EXPENSES',
}

ACTION_LABELS = {
    'UPDATE_SOURCE': 'Выбрать поставщика',
    'UPDATE_ITEMS': 'Добавить товары',
    'UPDATE_EXPENSES': 'Добавить расходы',
    'UPDATE_SETTLEMENT': 'Выбрать условия',
    'CREATE_INVESTMENT_AGREEMENT': 'Создать договор',
    'LINK_INVESTMENT_AGREEMENT': 'Привязать договор',
    'RECORD_CAPITAL_CONTRIBUTION': 'Внести капитал',
    'ALLOCATE_CAPITAL': 'Распределить капитал',
    'PAY_COSTS': 'Оплатить',
    'PAY_SUPPLIER_PAYABLE': 'Оплатить поставщика',
    'GENERATE_INSTALLMENT_SCHEDULE': 'Сгенерировать график',
    'RECEIVE_BATCH': 'Принять товар',
    'AMEND_SETTLEMENT': 'Изменить условия',
    'AMEND_ITEMS': 'Изменить товары',
    'AMEND_EXPENSES': 'Изменить расходы',
    'RETURN_CONSIGNMENT': 'Вернуть консигнацию',
    'CLOSE_WORKSPACE': 'Закрыть приход',
    'CANCEL_WORKSPACE': 'Отменить приход',
}

SECTION_TITLES = {
    'overview': 'Overview',
    'source': 'Source',
    'items_landed_cost': 'Items & Landed Cost',
    'settlement': 'Settlement',
    'capital': 'Capital',
    'receive': 'Receive',
    'history': 'History',
}

SECTION_KEY_MAP = {
    'items_landed_cost': 'items',
}

FLOW_TITLES = {
    'purchase_intent': 'Goods and landed costs',
    'supplier_settlement': 'Supplier and settlement',
    'funding': 'Money source',
    'payment_obligation': 'Payment / obligation',
    'goods_receipt': 'Goods receipt',
    'history': 'History and audit',
}


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


def build_workspace_payload(procurement: Procurement) -> dict:
    terms = getattr(procurement, 'terms', None)
    receive_batches = list(procurement.receive_batches.all())
    payables = list(SupplierPayable.objects.filter(procurement=procurement))
    has_items = procurement.items.exclude(
        lifecycle_state=ProcurementItem.LifecycleState.CANCELLED,
    ).exists()
    capital_activity = _has_capital_activity(procurement)
    context = ProcurementPolicyContext(
        funding_source=procurement.funding_source,
        settlement_type=getattr(terms, 'type', None),
        status=procurement.status,
        has_supplier=bool(procurement.supplier_id),
        has_investment_agreement=bool(procurement.agreement_id),
        has_items=has_items,
        has_partnership_capital_activity=(
            capital_activity
            and procurement.funding_source != Procurement.FundingSource.PARTNERSHIP
        ),
        has_capital_activity=capital_activity,
        has_payment_activity=_has_payment_activity(procurement, payables),
        has_receive_batches=bool(receive_batches),
        has_installment_schedule=bool(terms and terms.schedule_entries.exists()),
    )
    policy = evaluate_procurement_policy(context)

    return {
        'id': procurement.id,
        'status': procurement.status,
        'display': _display(procurement, policy),
        'flow': _flow_payload(procurement, policy, terms, payables, receive_batches, has_items),
        'policy': _policy_payload(policy, terms),
        'readiness': _readiness_payload(policy.readiness, policy.blocked_reasons),
        'sections': _sections_payload(policy),
        'documents': _documents_payload(
            procurement,
            terms,
            payables,
            receive_batches,
            _payments_for_procurement(procurement, payables),
        ),
        'summaries': _summaries_payload(procurement, payables),
        'history': _history_payload(procurement, receive_batches, payables),
    }


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
    """Keep terms.total_amount_due in sync with items × prices × fx while in DRAFT.

    After items change, the denormalized total on DRAFT terms is recomputed so
    INSTALLMENT/PARTIAL/DEFERRED screens see the current obligation. ACTIVE
    terms are immutable and skipped — amendments cover that path explicitly.
    """
    terms = ProcurementTerms.objects.filter(
        tenant_id=tenant_id, procurement=procurement,
        lifecycle_state=ProcurementTerms.LifecycleState.DRAFT,
    ).first()
    if terms is None:
        return
    total = sum(
        (
            Decimal(str(item.quantity)) * Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate or 1))
            for item in procurement.items.exclude(lifecycle_state=ProcurementItem.LifecycleState.CANCELLED)
        ),
        Decimal('0'),
    )
    new_total = total.quantize(Decimal('0.01'))
    if terms.total_amount_due != new_total:
        terms.total_amount_due = new_total
        terms.save(update_fields=['total_amount_due', 'updated_at'])


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
        cancel_item_ids = {int(v) for v in (new_items_payload or []) if _is_cancel_row(v)}
        for item_id in cancel_item_ids:
            if item_id in received_item_ids:
                raise ValueError(
                    f'Cannot cancel item {item_id}: it already has received quantities in a batch.'
                )

        for row in new_items_payload or []:
            if _is_cancel_row(row):
                item = ProcurementItem.objects.get(
                    pk=int(row.get('id') or row.get('item_id')),
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

        cancel_expense_ids = {int(v) for v in (new_expenses_payload or []) if _is_cancel_row(v)}
        received_expense_ids = set(
            ProcurementReceiveBatchExpense.objects
            .filter(tenant_id=tenant_id, batch__procurement=locked)
            .values_list('expense_id', flat=True)
            .distinct()
        )
        for expense_id in cancel_expense_ids:
            if expense_id in received_expense_ids:
                raise ValueError(
                    f'Cannot cancel expense {expense_id}: it already has received facts in a batch.'
                )

        for row in new_expenses_payload or []:
            if _is_cancel_row(row):
                expense = ProcurementExpense.objects.get(
                    pk=int(row.get('id') or row.get('expense_id')),
                    tenant_id=tenant_id,
                    procurement=locked,
                )
                expense.lifecycle_state = ProcurementExpense.LifecycleState.CANCELLED
                expense.save(update_fields=['lifecycle_state', 'updated_at'])
            else:
                _upsert_workspace_expense(tenant_id, locked, row)

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
    return item


def _upsert_workspace_item_for_amendment(tenant_id: int, procurement: Procurement, row: dict) -> ProcurementItem:
    item_id = row.get('id') or row.get('item_id')
    values = {
        'product_variant_id': int(row['product_variant_id']),
        'quantity': Decimal(str(row['quantity'])),
        'unit_purchase_price': Decimal(str(row['unit_purchase_price'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': Decimal(str(row.get('fx_rate', '1'))),
        'goods_ownership': procurement.goods_ownership,
    }
    if item_id:
        item = _amendment_item_for_update(tenant_id, procurement, int(item_id))
        for key, val in values.items():
            setattr(item, key, val)
        item.save(update_fields=list(values.keys()) + ['updated_at'])
        return item
    return ProcurementItem.objects.create(
        tenant_id=tenant_id, procurement=procurement, **values,
    )


def _upsert_workspace_item(tenant_id: int, procurement: Procurement, row: dict) -> ProcurementItem:
    item_id = row.get('id') or row.get('item_id')
    values = {
        'product_variant_id': int(row['product_variant_id']),
        'quantity': Decimal(str(row['quantity'])),
        'unit_purchase_price': Decimal(str(row['unit_purchase_price'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': Decimal(str(row.get('fx_rate', '1'))),
        'goods_ownership': procurement.goods_ownership,
    }
    if item_id:
        item = _draft_item_for_update(tenant_id, procurement, int(item_id))
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

    values = {
        'expense_type': row['expense_type'],
        'amount': Decimal(str(row['amount'])),
        'currency': str(row.get('currency') or 'UZS').upper(),
        'fx_rate': Decimal(str(row.get('fx_rate', '1'))),
        'allocation_method': row.get('allocation_method') or ProcurementExpense.AllocationMethod.BY_VALUE,
        'notes': row.get('notes', ''),
    }
    if expense_id:
        expense = _draft_expense_for_update(tenant_id, procurement, int(expense_id))
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
    ids = [int(item_id) for item_id in item_ids]
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

    expense.targets.all().delete()
    ProcurementExpenseTarget.objects.bulk_create([
        ProcurementExpenseTarget(
            tenant_id=tenant_id,
            expense=expense,
            item_id=item_id,
        )
        for item_id in ids
    ])


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
    agreement = _require_workspace_agreement(procurement)
    cash_account_id = payload.get('cash_account_id')
    if not cash_account_id:
        raise ValueError('cash_account_id is required for capital contribution.')
    notes = payload.get('notes', '')
    contribution = add_agreement_contribution(
        tenant_id=tenant_id,
        agreement_id=agreement.id,
        partner_id=int(payload['partner_id']),
        amount=Decimal(str(payload['amount'])),
        currency=payload.get('currency', agreement.currency),
        fx_rate=Decimal(str(payload.get('fx_rate', '1'))),
        date=payload.get('date') or payload.get('paid_at'),
        notes=notes,
        client_request_id=client_request_id,
        created_by_id=user_id,
        source=AgreementActionSource.BUSINESS_RECORDED,
        confirmation_status=AgreementConfirmationStatus.CONFIRMED,
    )
    record_partner_capital_contribution_payment(
        tenant_id=tenant_id,
        partner_id=contribution.partner_id,
        contribution_id=contribution.id,
        cash_account_id=int(cash_account_id),
        amount=contribution.amount,
        currency=contribution.currency,
        fx_rate=contribution.fx_rate,
        paid_at=contribution.date,
        client_request_id=client_request_id,
        notes=notes,
    )
    return contribution


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
                },
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

    required_uzs = _draft_cost_total_uzs(
        procurement.items.exclude(lifecycle_state__in=[
            ProcurementItem.LifecycleState.RECEIVED,
            ProcurementItem.LifecycleState.CANCELLED,
        ]),
        procurement.expenses.exclude(lifecycle_state__in=[
            ProcurementExpense.LifecycleState.RECEIVED,
            ProcurementExpense.LifecycleState.CANCELLED,
        ]),
    )
    currency = str(agreement.currency or 'UZS').upper()
    required = (
        _amount_uzs_to_currency(
            tenant_id=tenant_id,
            amount_uzs=required_uzs,
            currency=currency,
            received_at=timezone.now(),
        )
        if required_uzs > 0 else Decimal('0.00')
    )
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
    if procurement.status != Procurement.Status.OPEN:
        raise ValueError('Costs can be paid only while procurement is OPEN.')

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
    if not selected_items and not selected_expenses:
        raise ValueError('No draft items or expenses selected for payment.')

    cash_account = CashAccount.objects.get(pk=cash_account_id, tenant_id=tenant_id, is_active=True)
    amount = payload.get('amount')
    if amount is None:
        if cash_account.currency != 'UZS':
            raise ValueError('amount is required when CashAccount currency is not UZS.')
        amount = _draft_cost_total_uzs(selected_items, selected_expenses)

    payment_currency = payload.get('currency') or cash_account.currency
    payment_fx_rate = payload.get('fx_rate')

    terms = getattr(procurement, 'terms', None)
    if terms is not None:
        terms.activate()

    payment = record_generic_cash_payment(
        tenant_id=tenant_id,
        cash_account_id=cash_account.pk,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.pk,
        amount=Decimal(str(amount)),
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
        allocations = [{
            'cash_account_id': cash_account_id,
            'amount': amount,
            'currency': payload.get('currency') or account.currency,
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
        expense_allocations_uzs = _landed_expense_allocations(items, expenses)
        item_values_uzs = [_item_value_uzs(item) for item in items]
        total_inventory_uzs = (
            sum(item_values_uzs, Decimal('0'))
            + sum(expense_allocations_uzs, Decimal('0'))
        ).quantize(Decimal('0.01'))

        contract_snapshot: dict = {}
        capital_rows: list[dict] = []
        if locked.funding_source == Procurement.FundingSource.PARTNERSHIP:
            if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
                _pre_allocate_at_receipt_partnership_capital(
                    tenant_id=tenant_id,
                    procurement=locked,
                    required_uzs=total_inventory_uzs,
                    raw_allocations=payload.get('capital_allocations'),
                    received_at=received_at,
                )
            contract_snapshot, capital_rows = _resolve_workspace_capital_snapshot(
                tenant_id=tenant_id,
                procurement=locked,
                required_uzs=total_inventory_uzs,
                raw_allocations=payload.get('capital_allocations') or payload.get('allocations'),
                received_at=received_at,
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

        for expense in expenses:
            ProcurementReceiveBatchExpense.objects.create(
                tenant_id=tenant_id,
                batch=batch,
                expense=expense,
                allocated_amount_uzs=_expense_value_uzs(expense),
            )

        if items_to_mark_received:
            ProcurementItem.objects.filter(pk__in=items_to_mark_received).update(
                lifecycle_state=ProcurementItem.LifecycleState.RECEIVED,
                updated_at=received_at,
            )
        if expenses:
            ProcurementExpense.objects.filter(pk__in=[expense.id for expense in expenses]).update(
                lifecycle_state=ProcurementExpense.LifecycleState.RECEIVED,
                updated_at=received_at,
            )

        _sync_procurement_status_after_receive(locked, received_at)
        payable = _ensure_supplier_payable_after_receive(tenant_id, locked, terms)
        _record_receive_journal(
            tenant_id=tenant_id,
            procurement=locked,
            batch=batch,
            amount=total_inventory_uzs,
            payable=payable,
            received_at=received_at,
        )
        upsert_supplier_links_for_items(tenant_id, locked, items, received_at)

        at_receipt_payment = None
        if terms and terms.type == ProcurementTerms.Type.AT_RECEIPT:
            if locked.funding_source == Procurement.FundingSource.OWN_FUNDS:
                pp = payload['payment_payload']
                cash_account = CashAccount.objects.get(
                    pk=pp['cash_account_id'], tenant_id=tenant_id, is_active=True,
                )
                at_receipt_payment = record_generic_cash_payment(
                    tenant_id=tenant_id,
                    cash_account_id=cash_account.pk,
                    target_type=Payment.TargetType.PROCUREMENT_COST,
                    target_id=locked.pk,
                    amount=Decimal(str(pp['amount'])),
                    currency=pp.get('currency') or cash_account.currency,
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


def _display(procurement: Procurement, policy) -> dict:
    next_action = None
    if policy.allowed_actions:
        next_action = ACTION_MAP.get(policy.allowed_actions[0], policy.allowed_actions[0])
    return {
        'title': f'Procurement #{procurement.id}',
        'subtitle': getattr(procurement.supplier, 'name', None),
        'created_at': procurement.opened_at.isoformat(),
        'updated_at': procurement.updated_at.isoformat(),
        'primary_currency': _primary_currency(procurement),
        'next_action': {
            'key': next_action,
            'label': ACTION_LABELS.get(next_action, next_action) if next_action else None,
            'reason': policy.blocked_reasons[0] if policy.blocked_reasons else None,
        },
    }


def _policy_payload(policy, terms) -> dict:
    allowed_actions = [
        ACTION_MAP.get(action, action)
        for action in policy.allowed_actions
    ]
    if policy.normalized_funding_source == Procurement.FundingSource.PARTNERSHIP:
        for action in (
            'CREATE_INVESTMENT_AGREEMENT',
            'LINK_INVESTMENT_AGREEMENT',
            'RECORD_CAPITAL_CONTRIBUTION',
            'ALLOCATE_CAPITAL',
        ):
            if action not in allowed_actions:
                allowed_actions.append(action)
    if 'UPDATE_ITEMS' in allowed_actions and 'SPLIT_ITEM' not in allowed_actions:
        allowed_actions.append('SPLIT_ITEM')
    if getattr(terms, 'type', None) == ProcurementTerms.Type.INSTALLMENT and 'GENERATE_INSTALLMENT_SCHEDULE' not in allowed_actions:
        allowed_actions.append('GENERATE_INSTALLMENT_SCHEDULE')
    return {
        'funding_source': policy.normalized_funding_source,
        'settlement_type': getattr(terms, 'type', None),
        'allowed_settlements': list(policy.allowed_settlements),
        'visible_sections': [_section_key(section) for section in policy.visible_sections],
        'locked_sections': {},
        'allowed_actions': allowed_actions,
        'blocked_reasons': [
            {'code': f'BLOCKED_{index + 1}', 'message': reason}
            for index, reason in enumerate(policy.blocked_reasons)
        ],
    }


def _flow_payload(
    procurement: Procurement,
    policy,
    terms,
    payables,
    receive_batches,
    has_items: bool,
) -> dict:
    readiness = policy.readiness
    purchase_complete = has_items
    settlement_complete = bool(terms and readiness.get('settlement_ready'))
    funding_complete = _funding_flow_complete(procurement)
    payment_complete = _payment_obligation_complete(procurement, terms, payables)
    receipt_complete = procurement.status in (
        Procurement.Status.RECEIVED,
        Procurement.Status.CLOSED,
    )

    steps = [
        _flow_step(
            key='purchase_intent',
            complete=purchase_complete,
            previous_complete=True,
            readiness_keys=['items_ready', 'expenses_ready'],
            primary_actions=['UPDATE_ITEMS', 'UPDATE_EXPENSES', 'SPLIT_ITEM'],
            blocked_reason=None,
        ),
        _flow_step(
            key='supplier_settlement',
            complete=settlement_complete,
            previous_complete=purchase_complete,
            readiness_keys=['source_ready', 'settlement_ready'],
            primary_actions=['UPDATE_SETTLEMENT', 'AMEND_SETTLEMENT', 'GENERATE_INSTALLMENT_SCHEDULE'],
            blocked_reason='Add at least one item before supplier settlement.' if not purchase_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='funding',
            complete=funding_complete,
            previous_complete=purchase_complete and settlement_complete,
            readiness_keys=['source_ready', 'capital_ready'],
            primary_actions=['UPDATE_SOURCE', 'CREATE_INVESTMENT_AGREEMENT', 'LINK_INVESTMENT_AGREEMENT'],
            blocked_reason='Complete supplier settlement before funding.' if not settlement_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='payment_obligation',
            complete=payment_complete,
            previous_complete=purchase_complete and settlement_complete and funding_complete,
            readiness_keys=['payment_ready', 'capital_ready'],
            primary_actions=[
                'PAY_COSTS',
                'PAY_SUPPLIER_PAYABLE',
                'RECORD_CAPITAL_CONTRIBUTION',
                'ALLOCATE_CAPITAL',
                'GENERATE_INSTALLMENT_SCHEDULE',
            ],
            blocked_reason='Complete funding before payment or obligation.' if not funding_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='goods_receipt',
            complete=receipt_complete,
            previous_complete=(
                purchase_complete
                and settlement_complete
                and funding_complete
                and payment_complete
            ),
            readiness_keys=['receive_ready'],
            primary_actions=['RECEIVE_BATCH'],
            blocked_reason='Complete payment/obligation facts before receive.' if not payment_complete else _first_blocker(policy),
        ),
        _flow_step(
            key='history',
            complete=bool(receive_batches) or receipt_complete,
            previous_complete=True,
            readiness_keys=[],
            primary_actions=['VIEW_HISTORY'],
            blocked_reason=None,
        ),
    ]
    current = next((step for step in steps if step['key'] != 'history' and step['status'] != 'complete'), steps[-1])
    allowed = set(_allowed_action_keys(policy, terms))
    next_action = next((action for action in current['primary_actions'] if action in allowed), None)
    return {
        'current_step': current['key'],
        'steps': steps,
        'next_action': next_action,
    }


def _flow_step(
    *,
    key: str,
    complete: bool,
    previous_complete: bool,
    readiness_keys: list[str],
    primary_actions: list[str],
    blocked_reason: str | None,
) -> dict:
    if complete:
        status = 'complete'
        reason = None
    elif previous_complete:
        status = 'ready'
        reason = None
    else:
        status = 'blocked'
        reason = blocked_reason
    return {
        'key': key,
        'title': FLOW_TITLES[key],
        'status': status,
        'readiness_keys': readiness_keys,
        'primary_actions': primary_actions,
        'blocked_reason': reason,
    }


def _funding_flow_complete(procurement: Procurement) -> bool:
    if procurement.funding_source == Procurement.FundingSource.OWN_FUNDS:
        return True
    return bool(procurement.agreement_id)


def _payment_obligation_complete(procurement: Procurement, terms, payables) -> bool:
    if procurement.status in (Procurement.Status.RECEIVED, Procurement.Status.CLOSED):
        return True
    if not terms:
        return False
    if terms.type in (
        ProcurementTerms.Type.DEFERRED,
        ProcurementTerms.Type.INSTALLMENT,
        ProcurementTerms.Type.ON_SALE,
    ):
        return True
    if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
        return _has_capital_activity(procurement)
    return _has_payment_activity(procurement, payables)


def _terms_status_for_paid_amount(total_amount_due: Decimal, paid_amount: Decimal) -> str:
    total = Decimal(str(total_amount_due or 0)).quantize(Decimal('0.01'))
    paid = Decimal(str(paid_amount or 0)).quantize(Decimal('0.01'))
    if total > 0 and paid >= total:
        return ProcurementTerms.Status.FULLY_PAID
    if paid > 0:
        return ProcurementTerms.Status.PARTIALLY_PAID
    return ProcurementTerms.Status.OPEN


def _payment_amount_for_terms(
    *,
    amount: Decimal,
    currency: str,
    fx_rate,
    terms: ProcurementTerms,
) -> Decimal:
    amount = Decimal(str(amount or 0))
    payment_currency = str(currency or 'UZS').upper()
    obligation_currency = str(terms.currency_of_obligation or 'UZS').upper()
    if payment_currency == obligation_currency:
        return amount.quantize(Decimal('0.01'))

    rate = Decimal(str(fx_rate or terms.fx_rate_at_obligation or 1))
    amount_uzs = amount if payment_currency == 'UZS' else amount * rate
    if obligation_currency == 'UZS':
        return amount_uzs.quantize(Decimal('0.01'))
    return (amount_uzs / Decimal(str(terms.fx_rate_at_obligation or 1))).quantize(Decimal('0.01'))


def _allowed_action_keys(policy, terms) -> list[str]:
    actions = [ACTION_MAP.get(action, action) for action in policy.allowed_actions]
    if policy.normalized_funding_source == Procurement.FundingSource.PARTNERSHIP:
        actions.extend([
            'CREATE_INVESTMENT_AGREEMENT',
            'LINK_INVESTMENT_AGREEMENT',
            'RECORD_CAPITAL_CONTRIBUTION',
            'ALLOCATE_CAPITAL',
        ])
    if getattr(terms, 'type', None) == ProcurementTerms.Type.INSTALLMENT:
        actions.append('GENERATE_INSTALLMENT_SCHEDULE')
    return list(dict.fromkeys(actions))


def _first_blocker(policy) -> str | None:
    return policy.blocked_reasons[0] if policy.blocked_reasons else None


def _readiness_payload(readiness: dict[str, bool], blocked_reasons: tuple[str, ...]) -> dict:
    payload = {}
    for key in (
        'source_ready',
        'items_ready',
        'expenses_ready',
        'settlement_ready',
        'capital_ready',
        'payment_ready',
        'receive_ready',
    ):
        ok = bool(readiness.get(key, key == 'expenses_ready'))
        payload[key] = {
            'ok': ok,
            'severity': 'ok' if ok else 'blocked',
            'message': None if ok else (blocked_reasons[0] if blocked_reasons else 'Not ready.'),
            'missing': [] if ok else [key],
        }
    return payload


def _sections_payload(policy) -> list[dict]:
    visible = {_section_key(section) for section in policy.visible_sections}
    sections = []
    for key in ('overview', 'source', 'items', 'settlement', 'capital', 'receive', 'history'):
        sections.append({
            'key': key,
            'title': SECTION_TITLES.get(key, key.title()),
            'visible': key in visible,
            'locked': False,
            'locked_reason': None,
            'readiness_key': f'{key}_ready' if key in ('source', 'settlement', 'capital', 'receive') else None,
        })
    return sections


def _documents_payload(procurement: Procurement, terms, payables, receive_batches, payments) -> dict:
    return {
        'procurement': {
            'id': procurement.id,
            'status': procurement.status,
            'supplier_id': procurement.supplier_id,
            'supplier_name': getattr(procurement.supplier, 'name', None),
            'primary_currency': procurement.primary_currency,
            'notes': procurement.notes,
            'opened_at': procurement.opened_at.isoformat(),
            'closed_at': procurement.closed_at.isoformat() if procurement.closed_at else None,
        },
        'source': {
            'funding_source': procurement.funding_source,
            'supplier_required': bool(terms and terms.type != 'PREPAID'),
            'supplier_id': procurement.supplier_id,
            'investment_agreement_required': procurement.funding_source == Procurement.FundingSource.PARTNERSHIP,
            'investment_agreement_id': procurement.agreement_id,
        },
        'items': [_item_payload(item) for item in procurement.items.all()],
        'expenses': [_expense_payload(expense) for expense in procurement.expenses.all()],
        'settlement': _settlement_payload(terms),
        'payables': [_payable_payload(payable) for payable in payables],
        'payments': [_payment_payload(payment) for payment in payments],
        'investment': _investment_payload(procurement),
        'receive_batches': [_receive_batch_payload(batch) for batch in receive_batches],
        'lots_preview': [],
        'payment_status': _payment_status_block(terms, payments, items=list(procurement.items.all())),
    }


def _item_payload(item) -> dict:
    return {
        'id': item.id,
        'product_variant_id': item.product_variant_id,
        'product_variant_name': str(item.product_variant),
        'quantity': str(item.quantity),
        'unit_purchase_price': str(item.unit_purchase_price),
        'currency': item.currency,
        'fx_rate': str(item.fx_rate),
        'goods_ownership': item.goods_ownership,
        'lifecycle_state': item.lifecycle_state,
        'payment_state': _legacy_payment_state(item.lifecycle_state),
        'received_quantity': str(_received_quantity(item)),
        'remaining_quantity': str(Decimal(str(item.quantity)) - _received_quantity(item)),
        'locked_reason': None if item.lifecycle_state == item.LifecycleState.DRAFT else 'Line already has facts.',
    }


def _expense_payload(expense) -> dict:
    return {
        'id': expense.id,
        'expense_type': expense.expense_type,
        'amount': str(expense.amount),
        'currency': expense.currency,
        'fx_rate': str(expense.fx_rate),
        'allocation_method': expense.allocation_method,
        'target_item_ids': list(expense.targets.values_list('item_id', flat=True)),
        'lifecycle_state': expense.lifecycle_state,
        'payment_state': _legacy_payment_state(expense.lifecycle_state),
        'locked_reason': None if expense.lifecycle_state == expense.LifecycleState.DRAFT else 'Expense already has facts.',
    }


def _payment_status_block(terms, payments: list, items=None) -> dict:
    """obligation vs paid delta — surfaced to UI after item/expense amendments (OPEN-S7.1).
    Obligation is derived from current item costs (UZS) so amendments are immediately reflected."""
    if items is not None:
        obligation = sum(
            (
                Decimal(str(item.quantity)) * Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
                for item in items
                if item.lifecycle_state not in ('CANCELLED', 'RECEIVED')
            ),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
    else:
        obligation = Decimal(str(getattr(terms, 'total_amount_due', 0) or 0)).quantize(Decimal('0.01'))
    paid = (
        sum((Decimal(str(p.amount)) for p in payments), Decimal('0')).quantize(Decimal('0.01'))
        if payments else Decimal('0')
    )
    delta = paid - obligation
    if obligation == 0 and paid == 0:
        state = 'unpaid'
    elif paid == 0:
        state = 'unpaid'
    elif delta < 0:
        state = 'underpaid'
    elif delta == 0:
        state = 'paid_full'
    else:
        state = 'overpaid'
    return {
        'obligation_amount': str(obligation),
        'paid_amount': str(paid),
        'delta': str(delta),
        'state': state,
        'currency': str(getattr(terms, 'currency_of_obligation', 'UZS')) if terms else 'UZS',
    }


def _settlement_payload(terms) -> dict | None:
    if not terms:
        return None
    return {
        'id': terms.id,
        'type': terms.type,
        'currency_of_obligation': terms.currency_of_obligation,
        'fx_rate_at_obligation': str(terms.fx_rate_at_obligation),
        'total_amount_due': str(terms.total_amount_due),
        'paid_amount': str(terms.paid_amount),
        'remaining_amount': str(terms.remaining_amount),
        'deadline_date': terms.deadline_date.isoformat() if terms.deadline_date else None,
        'consignment_mode': None,
        'notes': terms.notes,
        'schedule': [
            {
                'id': row.id,
                'sequence_number': row.sequence_number,
                'due_date': row.due_date.isoformat(),
                'amount': str(row.amount),
                'currency': row.currency,
                'status': row.status,
                'paid_at': row.paid_at.isoformat() if row.paid_at else None,
                'paid_amount': str(row.paid_amount),
            }
            for row in terms.schedule_entries.order_by('sequence_number')
        ],
    }


def _payable_payload(payable) -> dict:
    return {
        'id': payable.id,
        'supplier_id': payable.supplier_id,
        'supplier_name': getattr(payable.supplier, 'name', None),
        'original_amount': str(payable.original_amount),
        'paid_amount': str(payable.paid_amount),
        'remaining_amount': str(payable.remaining_amount),
        'currency': payable.currency_of_obligation,
        'status': payable.status,
        'due_date': payable.deadline_date.isoformat() if payable.deadline_date else None,
    }


def _payment_payload(payment: Payment) -> dict:
    return {
        'id': payment.id,
        'target_type': payment.target_type,
        'target_id': payment.target_id,
        'source_type': payment.source_type,
        'source_id': payment.source_id,
        'amount': str(payment.amount),
        'currency': payment.currency,
        'fx_rate': str(payment.fx_rate),
        'status': payment.status,
        'paid_at': payment.paid_at.isoformat(),
        'journal_entry_id': payment.journal_entry_id,
    }


def _investment_payload(procurement: Procurement) -> dict | None:
    agreement = procurement.agreement
    if not agreement:
        return None
    available = _agreement_available_by_partner(agreement)
    return {
        'agreement_id': agreement.id,
        'agreement_label': f'Investment agreement #{agreement.id}',
        'legal_mode': agreement.legal_mode,
        'currency': agreement.currency,
        'planned_budget': str(agreement.planned_budget),
        'partners': [
            {
                'partner_id': member.partner_id,
                'partner_name': getattr(member.partner, 'display_name', str(member.partner_id)),
                'role': member.role,
                'planned_capital_share': str(member.planned_capital_share),
                'profit_share': str(member.profit_share),
            }
            for member in agreement.partners.select_related('partner').all()
        ],
        'commitments': [
            {
                'id': commitment.id,
                'partner_id': commitment.partner_id,
                'partner_name': getattr(commitment.partner, 'display_name', str(commitment.partner_id)),
                'amount': str(commitment.amount),
                'currency': commitment.currency,
                'fx_rate': str(commitment.fx_rate),
                'date': commitment.date.isoformat(),
                'source': commitment.source,
                'confirmation_status': commitment.confirmation_status,
                'notes': commitment.notes,
            }
            for commitment in agreement.commitments.select_related('partner').all()
        ],
        'contributions': [
            {
                'id': contribution.id,
                'partner_id': contribution.partner_id,
                'partner_name': getattr(contribution.partner, 'display_name', str(contribution.partner_id)),
                'amount': str(contribution.amount),
                'currency': contribution.currency,
                'fx_rate': str(contribution.fx_rate),
                'date': contribution.date.isoformat(),
                'source': contribution.source,
                'confirmation_status': contribution.confirmation_status,
                'notes': contribution.notes,
            }
            for contribution in agreement.contributions.select_related('partner').all()
        ],
        'allocations': [
            {
                'id': allocation.id,
                'procurement_id': allocation.procurement_id,
                'partner_id': allocation.partner_id,
                'partner_name': getattr(allocation.partner, 'display_name', str(allocation.partner_id)),
                'direction': allocation.direction,
                'amount': str(allocation.amount),
                'currency': allocation.currency,
                'fx_rate': str(allocation.fx_rate),
                'date': allocation.date.isoformat(),
                'source': allocation.source,
                'confirmation_status': allocation.confirmation_status,
                'notes': allocation.notes,
            }
            for allocation in agreement.allocations.select_related('partner').filter(procurement=procurement)
        ],
        'events': [
            {
                'id': event.id,
                'event_type': event.event_type,
                'occurred_at': event.occurred_at.isoformat(),
                'source': event.source,
                'actor_user_id': event.actor_user_id,
                'actor_partner_id': event.actor_partner_id,
                'actor_partner_name': getattr(event.actor_partner, 'display_name', None),
                'related_model': event.related_model,
                'related_id': event.related_id,
                'payload': event.payload,
            }
            for event in agreement.events.select_related('actor_user', 'actor_partner').all()[:30]
        ],
        'available_by_partner': {
            str(partner_id): {
                currency: str(amount)
                for currency, amount in amounts.items()
            }
            for partner_id, amounts in available.items()
        },
    }


def _receive_batch_payload(batch) -> dict:
    capital_rows = list(batch.capital_allocations.select_related('partner').all())
    return {
        'id': batch.id,
        'received_at': batch.received_at.isoformat(),
        'warehouse_id': batch.warehouse_id,
        'warehouse_name': getattr(batch.warehouse, 'name', ''),
        'status': 'POSTED',
        'inventory_total_uzs': str(batch.total_inventory_uzs),
        'lines': [
            {
                'id': line.id,
                'item_id': line.item_id,
                'lot_id': line.lot_id,
                'product_variant_id': line.item.product_variant_id,
                'product_variant_name': str(line.item.product_variant),
                'quantity_planned': str(line.quantity_planned),
                'quantity_received': str(line.quantity_received),
                'quantity': str(line.quantity_received),
                'discrepancy_reason': line.discrepancy_reason,
                'unit_purchase_price_uzs': str(line.unit_purchase_price_uzs),
                'allocated_expense_uzs': str(line.allocated_expense_uzs),
                'landed_cost_per_unit_uzs': str(line.landed_cost_per_unit_uzs),
            }
            for line in batch.lines.select_related('item__product_variant', 'lot').all()
        ],
        'expenses': [
            {
                'id': row.id,
                'expense_id': row.expense_id,
                'expense_type': row.expense.expense_type,
                'allocated_amount_uzs': str(row.allocated_amount_uzs),
            }
            for row in batch.expenses.select_related('expense').all()
        ],
        'capital_snapshot': (
            {
                'currency': getattr(batch.procurement.agreement, 'currency', 'UZS'),
                'required_amount': str(sum(
                    (Decimal(str(row.amount_contract_currency)) for row in capital_rows),
                    Decimal('0'),
                ).quantize(Decimal('0.01'))),
                'partners': [
                    {
                        'partner_id': row.partner_id,
                        'partner_name': getattr(row.partner, 'display_name', str(row.partner_id)),
                        'capital_amount': str(row.amount_contract_currency),
                        'capital_share': str(row.capital_share),
                        'profit_share': str(row.profit_share),
                    }
                    for row in capital_rows
                ],
            }
            if capital_rows else None
        ),
        'journal_entry_id': None,
    }


def _summaries_payload(procurement: Procurement, payables) -> dict:
    item_total = sum(
        (
            Decimal(str(item.quantity))
            * Decimal(str(item.unit_purchase_price))
            * Decimal(str(item.fx_rate))
            for item in procurement.items.all()
        ),
        Decimal('0'),
    )
    expense_total = sum(
        (
            Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))
            for expense in procurement.expenses.all()
        ),
        Decimal('0'),
    )
    payable_total = sum(
        (Decimal(str(payable.remaining_amount)) for payable in payables),
        Decimal('0'),
    )
    return {
        'items_total_uzs': str(item_total.quantize(Decimal('0.01'))),
        'expenses_total_uzs': str(expense_total.quantize(Decimal('0.01'))),
        'payables_total': str(payable_total.quantize(Decimal('0.01'))),
        'receive_batches_count': procurement.receive_batches.count(),
    }


def _history_payload(procurement: Procurement, receive_batches, payables) -> list[dict]:
    history = [{
        'kind': 'WORKSPACE_OPENED',
        'date': procurement.opened_at.isoformat(),
        'title': 'Workspace opened',
        'document_id': procurement.id,
    }]
    history.extend({
        'kind': 'RECEIVE_BATCH_POSTED',
        'date': batch.received_at.isoformat(),
        'title': f'Receive batch #{batch.id}',
        'document_id': batch.id,
    } for batch in receive_batches)
    history.extend({
        'kind': 'SUPPLIER_PAYABLE_CREATED',
        'date': payable.created_at.isoformat(),
        'title': f'Supplier payable #{payable.id}',
        'document_id': payable.id,
    } for payable in payables)
    return sorted(history, key=lambda item: item['date'], reverse=True)


def _section_key(section: str) -> str:
    return SECTION_KEY_MAP.get(section, section)


def _primary_currency(procurement: Procurement) -> str:
    return _normalize_currency(procurement.primary_currency)


def _normalize_currency(value: str | None) -> str:
    return 'USD' if str(value or 'UZS').upper() == 'USD' else 'UZS'


def _has_capital_activity(procurement: Procurement) -> bool:
    """Any AgreementAllocation touched this procurement."""
    return AgreementAllocation.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
    ).exists()


def _has_payment_activity(procurement: Procurement, payables) -> bool:
    return any(item.lifecycle_state != item.LifecycleState.DRAFT for item in procurement.items.all()) or bool(payables)


def _check_prepaid_coverage(tenant_id: int, procurement: Procurement, payload: dict) -> None:
    """PREPAID: items being received must not exceed total payments made so far."""
    from apps.inventory.models import Lot

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


def _legacy_payment_state(lifecycle_state: str) -> str:
    if lifecycle_state == 'READY_FOR_RECEIVE':
        return 'PAID'
    if lifecycle_state == 'RECEIVED':
        return 'PAID'
    return 'UNPAID'


def _received_quantity(item) -> Decimal:
    total = sum(
        (Decimal(str(row.quantity_received)) for row in item.receive_batch_lines.all()),
        Decimal('0'),
    )
    return total.quantize(Decimal('0.001'))


def _coerce_datetime(value):
    if not value:
        return None
    if hasattr(value, 'isoformat'):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValueError('Invalid datetime value.')
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def _receivable_line_states(procurement: Procurement, terms) -> tuple[str, ...]:
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


def _item_value_uzs(item) -> Decimal:
    return (
        Decimal(str(item.quantity))
        * Decimal(str(item.unit_purchase_price))
        * Decimal(str(item.fx_rate))
    ).quantize(Decimal('0.01'))


def _expense_value_uzs(expense) -> Decimal:
    return (Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))).quantize(Decimal('0.01'))


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
            raise ValueError('Partial receive requires explicit expense item targets.')
        touches_selected = bool(target_ids & selected_item_ids)
        touches_delayed = bool(target_ids - selected_item_ids)
        if touches_selected and touches_delayed:
            raise ValueError('Expense targets selected and delayed items. Split the expense first.')
        if touches_selected:
            selected.append(expense)
    return selected


def _landed_expense_allocations(items: list, expenses: list) -> list[Decimal]:
    allocations = [Decimal('0.00') for _ in items]
    if not items:
        return allocations

    item_values = [_item_value_uzs(item) for item in items]
    item_quantities = [Decimal(str(item.quantity)) for item in items]
    item_indexes = {item.id: index for index, item in enumerate(items)}

    for expense in expenses:
        target_ids = {target.item_id for target in expense.targets.all()}
        target_indexes = (
            [item_indexes[item_id] for item_id in target_ids if item_id in item_indexes]
            if target_ids else list(range(len(items)))
        )
        if not target_indexes:
            continue
        bases = (
            [item_values[index] for index in target_indexes]
            if expense.allocation_method == ProcurementExpense.AllocationMethod.BY_VALUE
            else [item_quantities[index] for index in target_indexes]
        )
        total_base = sum(bases, Decimal('0'))
        expense_amount = _expense_value_uzs(expense)
        remaining = expense_amount
        for local_index, item_index in enumerate(target_indexes):
            if local_index == len(target_indexes) - 1:
                amount = remaining
            elif total_base > 0:
                amount = (expense_amount * bases[local_index] / total_base).quantize(Decimal('0.01'))
                remaining -= amount
            else:
                amount = Decimal('0.00')
            allocations[item_index] = (allocations[item_index] + amount).quantize(Decimal('0.01'))
    return allocations


def _draft_cost_total_uzs(items, expenses) -> Decimal:
    item_total = sum(
        Decimal(str(item.quantity)) * Decimal(str(item.unit_purchase_price)) * Decimal(str(item.fx_rate))
        for item in items
    )
    expense_total = sum(
        Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))
        for expense in expenses
    )
    return (item_total + expense_total).quantize(Decimal('0.01'))


def _payments_for_procurement(procurement: Procurement, payables) -> list[Payment]:
    payable_ids = [payable.id for payable in payables]
    target_filter = (
        models.Q(target_type=Payment.TargetType.PROCUREMENT_COST, target_id=procurement.id)
        | models.Q(target_type=Payment.TargetType.SUPPLIER_PAYABLE, target_id__in=payable_ids)
    )
    return list(
        Payment.objects
        .filter(tenant_id=procurement.tenant_id)
        .filter(target_filter)
        .order_by('-paid_at', '-id')
    )


def _pre_allocate_at_receipt_partnership_capital(
    *,
    tenant_id: int,
    procurement: Procurement,
    required_uzs: Decimal,
    raw_allocations: list[dict] | None,
    received_at,
) -> None:
    """
    PARTNERSHIP × AT_RECEIPT: atomically draw from the agreement's capital pool
    by creating AgreementAllocation(TO_PROCUREMENT) records so that
    _resolve_workspace_capital_snapshot can proceed normally.
    Derives amounts from planned shares when raw_allocations is absent.
    """
    agreement = _require_workspace_agreement(procurement)
    currency = str(agreement.currency or 'UZS').upper()
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
) -> tuple[dict, list[dict]]:
    agreement = _require_workspace_agreement(procurement)
    currency = str(agreement.currency or 'UZS').upper()
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

    partners_meta = []
    for member in members:
        amount = amounts.get(member.partner_id, Decimal('0')).quantize(Decimal('0.01'))
        capital_share = (amount / required).quantize(Decimal('0.000001')) if required > 0 else Decimal('0')
        partners_meta.append({
            'partner_id': member.partner_id,
            'role': member.role,
            'capital_amount_contract_currency': str(amount),
            'capital_share': str(capital_share),
        })
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


def _amount_uzs_to_currency(*, tenant_id: int, amount_uzs: Decimal, currency: str, received_at) -> Decimal:
    amount_uzs = Decimal(str(amount_uzs)).quantize(Decimal('0.01'))
    if currency == 'UZS':
        return amount_uzs
    from apps.finance.fx_rates import resolve_fx_rate_snapshot

    rate = resolve_fx_rate_snapshot(
        tenant_id=tenant_id,
        operation_currency=currency,
        operation_at=received_at,
    )
    return (amount_uzs / Decimal(str(rate))).quantize(Decimal('0.01'))


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


def _ensure_supplier_payable_after_receive(tenant_id: int, procurement: Procurement, terms):
    if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
        return None  # CONSIGNED → payable создаётся per-sale, не at-receive
    if not terms or terms.type == ProcurementTerms.Type.PREPAID:
        return None
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
    if procurement.funding_source == Procurement.FundingSource.OWN_FUNDS and already_paid:
        return
    credit_code = '2000' if payable else ('3100' if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP else '1000')
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


def _require_workspace_agreement(procurement: Procurement) -> InvestmentAgreement:
    if procurement.funding_source != Procurement.FundingSource.PARTNERSHIP:
        raise ValueError('Capital actions are available only for PARTNERSHIP procurement.')
    if not procurement.agreement_id:
        raise ValueError('Investment agreement is required.')
    return procurement.agreement


def _with_client_request_id(notes: str, client_request_id: str | None) -> str:
    if not client_request_id:
        return notes or ''
    marker = f'client_request_id:{client_request_id}'
    if marker in (notes or ''):
        return notes
    return f'{notes or ""} {marker}'.strip()


def _add_amount(target: dict[int, dict[str, Decimal]], partner_id: int, currency: str, amount: Decimal) -> None:
    bucket = target.setdefault(int(partner_id), {})
    currency = str(currency or 'UZS').upper()
    bucket[currency] = (bucket.get(currency, Decimal('0')) + Decimal(str(amount))).quantize(Decimal('0.01'))


def _agreement_available_by_partner(agreement: InvestmentAgreement) -> dict[int, dict[str, Decimal]]:
    available: dict[int, dict[str, Decimal]] = {}
    for contribution in agreement.contributions.all():
        _add_amount(available, contribution.partner_id, contribution.currency, contribution.amount)
    for withdrawal in agreement.withdrawals.all():
        _add_amount(available, withdrawal.partner_id, withdrawal.currency, -Decimal(str(withdrawal.amount)))
    for allocation in agreement.allocations.all():
        signed = Decimal(str(allocation.amount))
        if allocation.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
            signed = -signed
        _add_amount(available, allocation.partner_id, allocation.currency, signed)
    return available


def _ensure_source_editable(procurement: Procurement) -> None:
    if procurement.status != Procurement.Status.OPEN:
        raise ValueError('Source can be edited only while procurement is OPEN.')
    if procurement.receive_batches.exists():
        raise ValueError('Source cannot be edited after receive batches exist.')
    if _has_payment_activity(
        procurement,
        SupplierPayable.objects.filter(procurement=procurement),
    ):
        raise ValueError('Source cannot be edited after payment facts exist.')
    if _has_capital_activity(procurement):
        raise ValueError('Source cannot be edited after capital activity exists.')


def _validate_source_transition(procurement: Procurement) -> None:
    terms = getattr(procurement, 'terms', None)
    if not terms:
        return
    allowed = allowed_settlements_for_funding(procurement.funding_source)
    if terms.type not in allowed:
        raise ValueError(f'{procurement.funding_source} does not allow {terms.type} settlement.')
    if terms.type in SUPPLIER_REQUIRED_SETTLEMENTS and not procurement.supplier_id:
        raise ValueError(f'{terms.type} settlement requires supplier.')
