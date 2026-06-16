"""workspace_receive.py — cluster D: receive batch creation and reversal.

Extracted from workspace.py (E18 Phase 2 / T-2.3, Slice 4).
Shell (workspace.py) imports public functions from here; this module does NOT
import from workspace.py.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import CashAccount, Payment
from apps.finance.services import (
    create_journal_entry,
    record_capital_pool_payment,
    record_generic_cash_payment,
)
from apps.suppliers.models import SupplierPayable
from apps.suppliers.services import create_payable_from_procurement

from .models import (
    Procurement,
    ProcurementExpense,
    ProcurementItem,
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
)
from .workspace_common import (
    _SUPPLIER_OPTIONAL_TYPES,
    _amount_uzs_to_currency,
    _coerce_datetime,
    _derive_items_currency,
    _expense_is_fully_allocated_after_receive,
    _item_value_uzs,
    _landed_expense_allocations,
    _receive_funding_breakdown,
    _require_workspace_agreement,
)
from .workspace_funding import (
    _pre_allocate_at_receipt_partnership_capital,
    _resolve_workspace_capital_snapshot,
)
from .workspace_payload import _terms_status_for_paid_amount
from .workspace_payment import _has_procurement_cost_payment
from .workspace_support import upsert_supplier_links_for_items


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
        from .read_models import rebuild_agreement_positions
        if procurement.agreement_id:
            rebuild_agreement_positions(procurement.agreement)
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
        from .read_models import rebuild_agreement_positions
        if locked.agreement_id:
            rebuild_agreement_positions(locked.agreement)
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
