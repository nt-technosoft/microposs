"""
Suppliers business logic — A/P management, payments, payables, schedules.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event

from .models import (
    Supplier,
    SupplierPayment,
    SupplierPayable,
    PaymentSchedule,
)

_CENT = Decimal('0.01')
_ZERO = Decimal('0')


def _q(amount) -> Decimal:
    return Decimal(str(amount or 0)).quantize(_CENT)


def record_supplier_payment(
    tenant_id: int,
    supplier_id: int,
    amount: Decimal,
    payment_method: str,
    notes: str = '',
    payment_date=None,
    operation_currency: str = 'UZS',
    operation_amount: Decimal | None = None,
    fx_rate_snapshot: Decimal | None = None,
    functional_amount_uzs: Decimal | None = None,
) -> SupplierPayment:
    """
    Record a payment to supplier. Reduces outstanding_balance (A/P).
    Creates journal entry for the payment.
    """
    with transaction.atomic():
        supplier = Supplier.objects.select_for_update().get(
            pk=supplier_id,
            tenant_id=tenant_id,
        )

        payment_dt = payment_date or timezone.now()
        currency = str(operation_currency or 'UZS').upper()
        rate = None
        functional_amount = (
            Decimal(str(functional_amount_uzs)).quantize(Decimal('0.01'))
            if functional_amount_uzs is not None
            else None
        )
        operation_amount_value = (
            Decimal(str(operation_amount)).quantize(Decimal('0.01'))
            if operation_amount is not None
            else None
        )

        if currency == 'UZS':
            rate = Decimal('1')
            if operation_amount_value is None:
                operation_amount_value = amount
            if functional_amount is None:
                functional_amount = amount
        else:
            from apps.finance.fx_rates import resolve_fx_rate_snapshot, to_functional_amount_uzs

            rate = resolve_fx_rate_snapshot(
                tenant_id=tenant_id,
                operation_currency=currency,
                operation_at=payment_dt,
                fx_rate_snapshot=fx_rate_snapshot,
            )
            if operation_amount_value is None:
                operation_amount_value = (amount / rate).quantize(Decimal('0.01'))
            if functional_amount is None:
                functional_amount = to_functional_amount_uzs(
                    operation_amount=operation_amount_value,
                    operation_currency=currency,
                    fx_rate_snapshot=rate,
                )

        payment = SupplierPayment.objects.create(
            tenant_id=tenant_id,
            supplier=supplier,
            amount=functional_amount,
            operation_currency=currency,
            operation_amount=operation_amount_value,
            fx_rate_snapshot=rate,
            functional_amount_uzs=functional_amount,
            payment_method=payment_method,
            date=payment_dt,
            notes=notes,
        )

        supplier.outstanding_balance = models.F('outstanding_balance') - functional_amount
        supplier.save(update_fields=['outstanding_balance', 'updated_at'])
        supplier.refresh_from_db()

        # Create journal entry
        from apps.finance.services import record_supplier_payment_journal
        record_supplier_payment_journal(
            tenant_id=tenant_id,
            payment_id=payment.pk,
            amount=amount,
            date=payment.date,
        )

        publish_event(
            event_type='supplier.payment',
            payload={
                'supplier_id': supplier_id,
                'payment_id': payment.pk,
                'amount': str(functional_amount),
                'remaining_balance': str(supplier.outstanding_balance),
            },
            tenant_id=tenant_id,
        )

    return payment


def get_supplier_payables_summary(tenant_id: int) -> list[dict]:
    """Get all suppliers with outstanding payables."""
    return list(
        Supplier.objects.filter(
            tenant_id=tenant_id,
            outstanding_balance__gt=0,
            is_active=True,
        ).values(
            'id', 'name', 'phone', 'outstanding_balance',
        ).order_by('-outstanding_balance')
    )


# =========================================================================
# E01 — Payables and multi-cash payments
# =========================================================================


def create_payable_from_procurement(
    *,
    tenant_id: int,
    procurement_id: int,
    supplier_id: int,
    terms,
    deadline_date=None,
) -> SupplierPayable:
    """
    Create a SupplierPayable for a procurement that has non-PREPAID terms.

    The obligation amount/currency/FX-rate is taken from `terms`
    (ProcurementTerms instance — see partnerships.models). The payable's
    `original_amount = terms.total_amount_due` (in obligation currency).

    Caller (procurement.confirm) is responsible for the surrounding
    transaction.atomic() block.
    """
    if terms.type == 'PREPAID':
        raise ValueError('PREPAID terms do not produce a payable.')

    amount = _q(terms.total_amount_due)
    paid = _q(getattr(terms, 'paid_amount', _ZERO) or _ZERO)
    if amount <= _ZERO:
        raise ValueError('Cannot create payable with non-positive amount.')
    if paid < _ZERO:
        raise ValueError('Cannot create payable with negative paid amount.')
    if paid > amount:
        raise ValueError('Cannot create payable with paid amount above original amount.')

    remaining = _q(amount - paid)
    if remaining <= _ZERO:
        status = SupplierPayable.Status.FULLY_PAID
    elif paid > _ZERO:
        status = SupplierPayable.Status.PARTIALLY_PAID
    else:
        status = SupplierPayable.Status.OPEN

    payable = SupplierPayable.objects.create(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        procurement_id=procurement_id,
        settlement=terms,
        original_amount=amount,
        paid_amount=paid,
        remaining_amount=remaining,
        currency_of_obligation=str(terms.currency_of_obligation or 'UZS').upper(),
        fx_rate_at_obligation=Decimal(str(terms.fx_rate_at_obligation or 1)),
        status=status,
        reason=SupplierPayable.Reason.PROCUREMENT,
        deadline_date=deadline_date,
    )
    Supplier.objects.filter(pk=supplier_id, tenant_id=tenant_id).update(
        outstanding_balance=models.F('outstanding_balance') + remaining,
        updated_at=timezone.now(),
    )
    return payable


def _resolve_payment_allocations(
    *,
    tenant_id: int,
    allocations: list[dict],
    obligation_currency: str,
    payment_dt,
) -> tuple[Decimal, Decimal, Decimal | None, list[dict]]:
    """
    Validate and normalize a multi-cash allocation list.

    Returns:
        (total_in_obligation_currency, total_functional_uzs, fx_rate_snapshot, normalized_allocations)

    Each allocation is `{cash_account_id: int, amount: Decimal, currency: str}`.
    The `amount` is the amount paid from that cash account in its own currency.
    Conversion to obligation_currency is done via FX-rate snapshot.

    For multi-currency mixes, a single FX snapshot per non-base currency is
    used (resolved at payment_dt). Returned `fx_rate_snapshot` is the rate
    used to convert obligation_currency ↔ UZS (functional), `None` if
    obligation is UZS.
    """
    from apps.finance.fx_rates import resolve_fx_rate_snapshot

    if not allocations:
        raise ValueError('At least one allocation is required.')

    obligation_currency = str(obligation_currency or 'UZS').upper()
    normalized: list[dict] = []
    total_uzs = _ZERO

    for raw in allocations:
        cash_account_id = int(raw['cash_account_id'])
        cur = str(raw.get('currency') or 'UZS').upper()
        amt = Decimal(str(raw['amount']))
        if amt <= 0:
            raise ValueError(f'Allocation amount must be > 0 (got {amt}).')

        if cur == 'UZS':
            rate = Decimal('1')
            amt_uzs = _q(amt)
        else:
            rate = resolve_fx_rate_snapshot(
                tenant_id=tenant_id,
                operation_currency=cur,
                operation_at=payment_dt,
            )
            amt_uzs = _q(amt * rate)

        total_uzs += amt_uzs
        normalized.append({
            'cash_account_id': cash_account_id,
            'amount': str(_q(amt)),
            'currency': cur,
            'fx_rate': str(rate),
            'amount_uzs': str(amt_uzs),
        })

    # Convert total_uzs back to obligation currency to know how much payable to reduce
    if obligation_currency == 'UZS':
        obligation_rate = Decimal('1')
        total_in_obligation = _q(total_uzs)
        rate_for_snapshot: Decimal | None = None
    else:
        obligation_rate = resolve_fx_rate_snapshot(
            tenant_id=tenant_id,
            operation_currency=obligation_currency,
            operation_at=payment_dt,
        )
        # total_in_obligation = total_uzs / rate (UZS -> obligation_currency)
        total_in_obligation = _q(total_uzs / obligation_rate) if obligation_rate else _ZERO
        rate_for_snapshot = obligation_rate

    return total_in_obligation, _q(total_uzs), rate_for_snapshot, normalized


def record_payable_payment(
    *,
    tenant_id: int,
    payable_id: int,
    allocations: list[dict],
    payment_date=None,
    schedule_entry_id: int | None = None,
    notes: str = '',
    client_request_id=None,
) -> SupplierPayment:
    """
    Multi-cash payment against a SupplierPayable.

    Each entry in `allocations` represents money flowing from a CashAccount
    in its own currency. The total is normalized to UZS (functional) and to
    the obligation currency to reduce the payable.

    Idempotency: pass `client_request_id` (UUID-able) to safely retry.
    Returns the recorded SupplierPayment.

    Side effects (atomic):
      - SupplierPayment row (with `allocations` JSON snapshot)
      - SupplierPayable.paid_amount += total_in_obligation
      - SupplierPayable.remaining_amount -= total_in_obligation
      - SupplierPayable.status transitions to PARTIALLY_PAID / FULLY_PAID
      - If `schedule_entry_id` given — its `paid_amount`/`status` updated
      - Supplier.outstanding_balance reduced by total_uzs
      - JournalEntry (DR Payables / CR Cash) recorded
      - OutboxEvent('supplier.payment')
    """
    payment_dt = payment_date or timezone.now()

    with transaction.atomic():
        # Idempotency short-circuit
        if client_request_id is not None:
            existing = (
                SupplierPayment.objects
                .filter(tenant_id=tenant_id, client_request_id=client_request_id)
                .first()
            )
            if existing is not None:
                return existing

        payable = (
            SupplierPayable.objects
            .select_for_update()
            .get(pk=payable_id, tenant_id=tenant_id)
        )
        if payable.status in (
            SupplierPayable.Status.FULLY_PAID,
            SupplierPayable.Status.CANCELLED,
        ):
            raise ValueError(
                f'Cannot pay against payable in status {payable.status}.'
            )

        total_obligation, total_uzs, fx_rate, normalized = _resolve_payment_allocations(
            tenant_id=tenant_id,
            allocations=allocations,
            obligation_currency=payable.currency_of_obligation,
            payment_dt=payment_dt,
        )

        if total_obligation <= _ZERO:
            raise ValueError('Total allocation must yield a positive obligation amount.')
        if total_obligation > payable.remaining_amount:
            raise ValueError(
                f'Payment {total_obligation} exceeds remaining {payable.remaining_amount} '
                f'on payable {payable_id}.'
            )

        # Decide payment_method: CASH if all allocations from cash; MIXED if >1 different accounts;
        # treat single-allocation as CASH for backward compat.
        if len(normalized) > 1:
            payment_method = SupplierPayment.PaymentMethod.MIXED
        else:
            payment_method = SupplierPayment.PaymentMethod.CASH

        # Resolve schedule entry if provided
        schedule_entry = None
        if schedule_entry_id is not None:
            schedule_entry = (
                PaymentSchedule.objects
                .select_for_update()
                .get(pk=schedule_entry_id, tenant_id=tenant_id)
            )

        # Create payment row
        payment = SupplierPayment.objects.create(
            tenant_id=tenant_id,
            supplier_id=payable.supplier_id,
            payable=payable,
            schedule_entry=schedule_entry,
            amount=total_uzs,  # functional amount in UZS for backward compat with old reports
            operation_currency=payable.currency_of_obligation,
            operation_amount=total_obligation,
            fx_rate_snapshot=fx_rate or Decimal('1'),
            functional_amount_uzs=total_uzs,
            payment_method=payment_method,
            allocations=normalized,
            date=payment_dt,
            notes=notes,
            client_request_id=client_request_id,
        )

        # Update payable
        new_paid = _q(Decimal(str(payable.paid_amount)) + total_obligation)
        new_remaining = _q(Decimal(str(payable.original_amount)) - new_paid)
        if new_remaining <= _ZERO:
            new_status = SupplierPayable.Status.FULLY_PAID
            new_remaining = _ZERO
        else:
            new_status = SupplierPayable.Status.PARTIALLY_PAID
        payable.paid_amount = new_paid
        payable.remaining_amount = new_remaining
        payable.status = new_status
        payable.save(update_fields=[
            'paid_amount', 'remaining_amount', 'status', 'updated_at',
        ])

        # Update schedule entry if any
        if schedule_entry is not None:
            sched_paid = _q(Decimal(str(schedule_entry.paid_amount)) + total_obligation)
            schedule_entry.paid_amount = sched_paid
            if sched_paid >= _q(schedule_entry.amount):
                schedule_entry.status = PaymentSchedule.Status.PAID
                schedule_entry.paid_at = payment_dt
            schedule_entry.save(update_fields=[
                'paid_amount', 'status', 'paid_at', 'updated_at',
            ])

        # Update supplier aggregate (legacy balance — uses UZS functional)
        Supplier.objects.filter(pk=payable.supplier_id, tenant_id=tenant_id).update(
            outstanding_balance=models.F('outstanding_balance') - total_uzs,
            updated_at=timezone.now(),
        )

        from apps.finance.models import Payment
        from apps.finance.services import record_generic_cash_payment

        first_finance_payment = None
        finance_client_request_id = client_request_id if len(normalized) == 1 else None
        for allocation in normalized:
            finance_payment = record_generic_cash_payment(
                tenant_id=tenant_id,
                cash_account_id=allocation['cash_account_id'],
                target_type=Payment.TargetType.SUPPLIER_PAYABLE,
                target_id=payable.pk,
                amount=Decimal(str(allocation['amount'])),
                currency=allocation['currency'],
                fx_rate=Decimal(str(allocation['fx_rate'])),
                paid_at=payment_dt,
                counterpart_account_code='2000',
                operation_type='supplier_payment',
                description=f'Supplier payable #{payable.pk} payment',
                client_request_id=finance_client_request_id,
                notes=notes,
            )
            if first_finance_payment is None:
                first_finance_payment = finance_payment

        if first_finance_payment is not None:
            payment.payment = first_finance_payment
            payment.save(update_fields=['payment', 'updated_at'])

        publish_event(
            event_type='supplier.payment',
            payload={
                'payment_id': payment.pk,
                'supplier_id': payable.supplier_id,
                'payable_id': payable.pk,
                'total_obligation': str(total_obligation),
                'total_uzs': str(total_uzs),
                'payable_status': payable.status,
            },
            tenant_id=tenant_id,
        )

    return payment
