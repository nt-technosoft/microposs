"""
Customers business logic — receivable ledger, debt tracking, payments.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event
from apps.finance.models import CashAccount, CashEntry
from apps.finance.services import create_cash_entry, record_journal_from_cash_entry

from .models import Customer, CustomerPayment, Receivable, ReceivableEntry


def get_or_create_receivable(customer: Customer, tenant_id: int) -> Receivable:
    receivable, _ = Receivable.objects.get_or_create(
        customer=customer,
        tenant_id=tenant_id,
        defaults={'balances': {}},
    )
    return receivable


def accrue_debt(
    *,
    tenant_id: int,
    customer_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    due_date=None,
    source_ref: str = '',
    date=None,
) -> ReceivableEntry:
    """
    Record a DEBT_ACCRUED entry and update Receivable.balances.
    Called when a sale has unpaid amount (credit sale or partial payment).
    """
    if date is None:
        date = timezone.now()

    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(
            pk=customer_id, tenant_id=tenant_id,
        )
        receivable = get_or_create_receivable(customer, tenant_id)
        receivable = Receivable.objects.select_for_update().get(pk=receivable.pk)

        entry = ReceivableEntry.objects.create(
            tenant_id=tenant_id,
            receivable=receivable,
            date=date,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            entry_type=ReceivableEntry.EntryType.DEBT_ACCRUED,
            due_date=due_date,
            source_ref=source_ref,
        )

        balances = dict(receivable.balances)
        key = currency.upper()
        balances[key] = str(
            Decimal(str(balances.get(key, '0'))) + amount
        )
        receivable.balances = balances
        receivable.save(update_fields=['balances', 'updated_at'])

        publish_event(
            event_type='customer.debt_accrued',
            payload={
                'customer_id': customer_id,
                'amount': str(amount),
                'currency': currency,
                'source_ref': source_ref,
            },
            tenant_id=tenant_id,
        )

    return entry


def record_customer_payment(
    tenant_id: int,
    customer_id: int,
    amount: Decimal,
    payment_method: str,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    notes: str = '',
    payment_date=None,
    account_id: int | None = None,
) -> CustomerPayment:
    """
    Record a customer debt repayment.
    Creates ReceivableEntry(REPAYMENT), reduces Receivable.balances,
    keeps CustomerPayment for audit trail.
    CashEntry created in PR-7 when CashAccount is available.
    """
    if payment_date is None:
        payment_date = timezone.now()

    currency = currency.upper()

    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(
            pk=customer_id, tenant_id=tenant_id,
        )
        receivable = get_or_create_receivable(customer, tenant_id)
        receivable = Receivable.objects.select_for_update().get(pk=receivable.pk)

        payment = CustomerPayment.objects.create(
            tenant_id=tenant_id,
            customer=customer,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            payment_method=payment_method,
            date=payment_date,
            notes=notes,
        )

        account = None
        cash_entry = None
        if account_id is not None:
            account = CashAccount.objects.select_for_update().filter(
                pk=account_id,
                tenant_id=tenant_id,
            ).first()
            if account is not None:
                cash_entry = create_cash_entry(
                    tenant_id=tenant_id,
                    account=account,
                    direction=CashEntry.Direction.IN,
                    amount=amount,
                    date=payment_date,
                    source_ref_type='customer_payment',
                    source_ref_id=payment.pk,
                )

        ReceivableEntry.objects.create(
            tenant_id=tenant_id,
            receivable=receivable,
            date=payment_date,
            amount=-amount,
            currency=currency,
            fx_rate=fx_rate,
            entry_type=ReceivableEntry.EntryType.REPAYMENT,
            source_ref=f'customer_payment:{payment.pk}',
        )

        balances = dict(receivable.balances)
        key = currency
        balances[key] = str(
            Decimal(str(balances.get(key, '0'))) - amount
        )
        receivable.balances = balances
        receivable.save(update_fields=['balances', 'updated_at'])

        from apps.finance.services import record_debt_payment_journal
        record_debt_payment_journal(
            tenant_id=tenant_id,
            payment_id=payment.pk,
            amount=amount,
            payment_type=payment_method,
            date=payment.date,
        )

        if cash_entry is not None and account is not None and account.linked_account_id:
            record_journal_from_cash_entry(
                tenant_id=tenant_id,
                cash_entry=cash_entry,
                operation_type='debt_payment',
                operation_id=payment.pk,
                counterpart_account_code='1200',
                description=f'Customer payment #{payment.pk}',
                date=payment.date,
            )

        publish_event(
            event_type='customer.payment',
            payload={
                'customer_id': customer_id,
                'payment_id': payment.pk,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )

    return payment


def get_customer_debt_summary(tenant_id: int) -> list[dict]:
    """
    Customers with outstanding debt — aggregated from Receivable.balances.
    Returns customers where any currency balance > 0.
    """
    from django.db.models import Q
    result = []
    receivables = (
        Receivable.objects
        .filter(tenant_id=tenant_id, customer__is_active=True)
        .select_related('customer')
        .exclude(balances={})
    )
    for r in receivables:
        total_uzs = r.balance_uzs
        if total_uzs > 0:
            result.append({
                'id': r.customer_id,
                'name': r.customer.name,
                'phone': r.customer.phone,
                'outstanding_balance': total_uzs,
                'balances': r.balances,
            })
    result.sort(key=lambda x: x['outstanding_balance'], reverse=True)
    return result
