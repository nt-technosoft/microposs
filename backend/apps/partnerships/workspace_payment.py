"""workspace_payment.py — cluster C: cost payments, overpayment resolution, supplier payable.

Extracted from workspace.py (E18 Phase 2 / T-2.3, Slice 3).
Shell (workspace.py) imports public functions from here; this module does NOT
import from workspace.py.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.services import publish_event
from apps.finance.models import CashAccount, CashEntry, Payment, PaymentAllocation
from apps.finance.services import (
    create_cash_entry,
    record_generic_cash_payment,
    record_journal_from_cash_entry,
    record_pool_journal_functional,
)
from apps.partnerships.multicurrency import get_or_create_currency_pool
from apps.suppliers.models import SupplierPayable
from apps.suppliers.services import record_payable_payment

from .models import (
    AgreementActionSource,
    AgreementAllocation,
    AgreementConfirmationStatus,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementTerms,
)
from .procurement_cost import procurement_cost_by_currency
from .workspace_common import (
    _derive_items_currency,
    _normalize_currency,
    _require_workspace_agreement,
    _with_client_request_id,
)
from .workspace_payload import _payment_status_block, _terms_status_for_paid_amount
from .workspace_support import append_ledger_entry, get_or_create_ledger, record_agreement_event


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
            from .journal_tags import tag_overpayment_refund
            tag_overpayment_refund(
                tenant_id=tenant_id,
                journal_entry=journal,
                agreement=locked_agreement,
                procurement=locked_procurement,
                partner_id=partner_id,
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


def _has_procurement_cost_payment(procurement: Procurement) -> bool:
    return Payment.objects.filter(
        tenant_id=procurement.tenant_id,
        target_type=Payment.TargetType.PROCUREMENT_COST,
        target_id=procurement.id,
        status=Payment.Status.POSTED,
    ).exists()


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
