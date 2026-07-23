"""workspace_amendments.py — cluster E: source/settlement/lines editing, amendments, cancel, split.

Extracted from workspace.py (E18 Phase 2 / T-2.3, Slice 5).
Shell (workspace.py) imports public functions from here; this module does NOT
import from workspace.py.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import Payment

from .models import (
    Procurement,
    ProcurementExpense,
    ProcurementExpenseTarget,
    ProcurementItem,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
)
from .policies import SUPPLIER_REQUIRED_SETTLEMENTS, allowed_settlements_for_funding
from .procurement_cost import active_procurement_lines
from .workspace_common import (
    _ensure_source_editable,
    _expense_allocated_value_uzs,
    _expense_value_uzs,
    _normalize_currency,
    _received_quantity,
    _remaining_obligation_cost_by_currency,
    _resolve_procurement_row_fx_rate,
)
from .workspace_support import apply_terms_amendment, upsert_procurement_terms_draft


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


def _validate_source_transition(procurement: Procurement) -> None:
    terms = getattr(procurement, 'terms', None)
    if not terms:
        return
    allowed = allowed_settlements_for_funding(procurement.funding_source)
    if terms.type not in allowed:
        raise ValueError(f'{procurement.funding_source} does not allow {terms.type} settlement.')
    if terms.type in SUPPLIER_REQUIRED_SETTLEMENTS and not procurement.supplier_id:
        raise ValueError(f'{terms.type} settlement requires supplier.')
