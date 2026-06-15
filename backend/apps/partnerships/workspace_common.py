"""workspace_common.py — shared utilities across workspace clusters (A/B/C/D/E).

Helpers with ≥2 cluster callers live here so no cluster module imports the
shell (workspace.py).  The shell and all cluster modules import from here;
this module does NOT import from workspace.py.

Audit reference: E18 Фаза 2 / T-2.3 (инвариант 2).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.finance.fx_rates import resolve_fx_rate_snapshot

from .models import (
    AgreementAllocation,
    InvestmentAgreement,
    Procurement,
    ProcurementExpense,
    ProcurementItem,
    ProcurementReceiveBatchExpense,
    ProcurementTerms,
)

# Used by _documents_payload (A) and _ensure_supplier_payable_after_receive (D).
_SUPPLIER_OPTIONAL_TYPES = {ProcurementTerms.Type.PREPAID, ProcurementTerms.Type.AT_RECEIPT}


def _normalize_currency(value: str | None) -> str:
    return 'USD' if str(value or 'UZS').upper() == 'USD' else 'UZS'


def _resolve_workspace_fx_rate(
    *,
    tenant_id: int,
    currency: str | None,
    fx_rate,
    operation_at=None,
) -> Decimal:
    normalized_currency = _normalize_currency(currency)
    raw_fx = fx_rate
    if raw_fx in ('', '0', 0):
        raw_fx = None
    return resolve_fx_rate_snapshot(
        tenant_id=tenant_id,
        operation_currency=normalized_currency,
        operation_at=operation_at,
        fx_rate_snapshot=raw_fx,
    )


def _resolve_procurement_row_fx_rate(
    *,
    tenant_id: int,
    procurement: Procurement,
    row: dict,
    current_fx_rate=None,
) -> Decimal:
    currency = _normalize_currency(row.get('currency'))
    raw_fx = row.get('fx_rate')
    if raw_fx is None and current_fx_rate is not None:
        raw_fx = current_fx_rate
    return _resolve_workspace_fx_rate(
        tenant_id=tenant_id,
        currency=currency,
        fx_rate=raw_fx,
        operation_at=procurement.opened_at,
    )


def _primary_currency(procurement: Procurement) -> str:
    return _normalize_currency(procurement.primary_currency)


def _has_capital_activity(procurement: Procurement) -> bool:
    """Any AgreementAllocation touched this procurement."""
    return AgreementAllocation.objects.filter(
        tenant_id=procurement.tenant_id,
        procurement=procurement,
    ).exists()


def _has_payment_activity(procurement: Procurement, payables) -> bool:
    return any(item.lifecycle_state != item.LifecycleState.DRAFT for item in procurement.items.all()) or bool(payables)


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


def _item_value_uzs(item) -> Decimal:
    return (
        Decimal(str(item.quantity))
        * Decimal(str(item.unit_purchase_price))
        * Decimal(str(item.fx_rate))
    ).quantize(Decimal('0.01'))


def _expense_value_uzs(expense) -> Decimal:
    return (Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))).quantize(Decimal('0.01'))


def _expense_allocated_value_uzs(expense) -> Decimal:
    return (
        ProcurementReceiveBatchExpense.objects
        .filter(expense=expense)
        .aggregate(total=models.Sum('allocated_amount_uzs'))['total']
        or Decimal('0.00')
    ).quantize(Decimal('0.01'))


def _expense_remaining_value_uzs(expense) -> Decimal:
    return max(Decimal('0.00'), _expense_value_uzs(expense) - _expense_allocated_value_uzs(expense)).quantize(Decimal('0.01'))


def _remaining_item_quantity(item) -> Decimal:
    return max(Decimal('0.000'), Decimal(str(item.quantity)) - _received_quantity(item)).quantize(Decimal('0.001'))


def _remaining_item_value_uzs(item) -> Decimal:
    return (
        _remaining_item_quantity(item)
        * Decimal(str(item.unit_purchase_price))
        * Decimal(str(item.fx_rate))
    ).quantize(Decimal('0.01'))


def _remaining_obligation_cost_by_currency(items, expenses) -> dict[str, Decimal]:
    cost_map: dict[str, Decimal] = {}
    for item in items:
        remaining_qty = _remaining_item_quantity(item)
        if remaining_qty <= 0:
            continue
        currency = str(item.currency or 'UZS').upper()
        amount = (remaining_qty * Decimal(str(item.unit_purchase_price))).quantize(Decimal('0.01'))
        cost_map[currency] = (cost_map.get(currency, Decimal('0.00')) + amount).quantize(Decimal('0.01'))
    for expense in expenses:
        remaining_uzs = _expense_remaining_value_uzs(expense)
        if remaining_uzs <= 0:
            continue
        currency = str(expense.currency or 'UZS').upper()
        fx_rate = Decimal(str(expense.fx_rate or '1'))
        native_amount = (remaining_uzs / fx_rate if fx_rate else remaining_uzs).quantize(Decimal('0.01'))
        cost_map[currency] = (cost_map.get(currency, Decimal('0.00')) + native_amount).quantize(Decimal('0.01'))
    return cost_map


def _remaining_obligation_cost_uzs(items, expenses) -> Decimal:
    item_total = sum((_remaining_item_value_uzs(item) for item in items), Decimal('0.00'))
    expense_total = sum((_expense_remaining_value_uzs(expense) for expense in expenses), Decimal('0.00'))
    return (item_total + expense_total).quantize(Decimal('0.01'))


def _expense_is_fully_allocated_after_receive(expense, current_allocated_uzs: Decimal) -> bool:
    allocated = (_expense_allocated_value_uzs(expense) + Decimal(str(current_allocated_uzs))).quantize(Decimal('0.01'))
    return allocated >= (_expense_value_uzs(expense) - Decimal('0.01'))


def _landed_expense_allocations(items: list, expenses: list) -> tuple[list[Decimal], dict[int, Decimal]]:
    allocations = [Decimal('0.00') for _ in items]
    expense_values_uzs: dict[int, Decimal] = {}
    if not items:
        return allocations, expense_values_uzs

    item_indexes = {item.id: index for index, item in enumerate(items)}

    for expense in expenses:
        target_ids = {target.item_id for target in expense.targets.all()}
        scope_qs = ProcurementItem.objects.filter(
            tenant_id=expense.tenant_id,
            procurement=expense.procurement,
        ).exclude(
            lifecycle_state=ProcurementItem.LifecycleState.CANCELLED,
        ).exclude(
            lifecycle_state=ProcurementItem.LifecycleState.RECEIVED,
        ).order_by('id')
        if target_ids:
            scope_qs = scope_qs.filter(pk__in=target_ids)
        scope_items = list(scope_qs)
        selected_scope_ids = {item.id for item in scope_items} & set(item_indexes)
        if not selected_scope_ids:
            continue
        scope_bases = (
            {item.id: _remaining_item_value_uzs(item) for item in scope_items}
            if expense.allocation_method == ProcurementExpense.AllocationMethod.BY_VALUE
            else {item.id: _remaining_item_quantity(item) for item in scope_items}
        )
        total_base = sum(scope_bases.values(), Decimal('0'))
        expense_amount = _expense_remaining_value_uzs(expense)
        if expense_amount <= 0:
            continue
        remaining = expense_amount
        for local_index, scope_item in enumerate(scope_items):
            if local_index == len(scope_items) - 1:
                amount = remaining
            elif total_base > 0:
                amount = (expense_amount * scope_bases[scope_item.id] / total_base).quantize(Decimal('0.01'))
                remaining -= amount
            else:
                amount = Decimal('0.00')
            if scope_item.id not in selected_scope_ids:
                continue
            item_index = item_indexes[scope_item.id]
            allocations[item_index] = (allocations[item_index] + amount).quantize(Decimal('0.01'))
            expense_values_uzs[expense.id] = (
                expense_values_uzs.get(expense.id, Decimal('0.00')) + amount
            ).quantize(Decimal('0.01'))
    return allocations, expense_values_uzs


def _derive_items_currency(items) -> str:
    """Return the single currency shared by all items, or 'UZS' if no items.

    Raises ValueError on mixed currencies.
    """
    currencies = {str(item.currency or 'UZS').upper() for item in items}
    if len(currencies) > 1:
        raise ValueError(
            'Все товары прихода должны быть в одной валюте. '
            f'Найдено: {", ".join(sorted(currencies))}.'
        )
    return currencies.pop() if currencies else 'UZS'


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


def _add_amount(target: dict[int, dict[str, Decimal]], partner_id: int, currency: str, amount: Decimal) -> None:
    bucket = target.setdefault(int(partner_id), {})
    currency = str(currency or 'UZS').upper()
    bucket[currency] = (bucket.get(currency, Decimal('0')) + Decimal(str(amount))).quantize(Decimal('0.01'))


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
