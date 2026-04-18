"""
Customers business logic — debt tracking, payments.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event

from .models import Customer, CustomerPayment


def record_customer_payment(
    tenant_id: int,
    customer_id: int,
    amount: Decimal,
    payment_method: str,
    notes: str = '',
    payment_date=None,
    operation_currency: str = 'UZS',
    operation_amount: Decimal | None = None,
    fx_rate_snapshot: Decimal | None = None,
    functional_amount_uzs: Decimal | None = None,
) -> CustomerPayment:
    """
    Record a customer debt payment. Reduces outstanding_balance.
    Creates journal entry for the payment.
    """
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(
            pk=customer_id,
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
            from apps.finance.services import resolve_fx_rate_snapshot, to_functional_amount_uzs

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

        payment = CustomerPayment.objects.create(
            tenant_id=tenant_id,
            customer=customer,
            amount=functional_amount,
            operation_currency=currency,
            operation_amount=operation_amount_value,
            fx_rate_snapshot=rate,
            functional_amount_uzs=functional_amount,
            payment_method=payment_method,
            date=payment_dt,
            notes=notes,
        )

        customer.outstanding_balance = models.F('outstanding_balance') - functional_amount
        customer.save(update_fields=['outstanding_balance', 'updated_at'])
        customer.refresh_from_db()

        # Create journal entry
        from apps.finance.services import record_debt_payment_journal
        record_debt_payment_journal(
            tenant_id=tenant_id,
            payment_id=payment.pk,
            amount=amount,
            payment_type=payment_method,
            date=payment.date,
        )

        publish_event(
            event_type='customer.payment',
            payload={
                'customer_id': customer_id,
                'payment_id': payment.pk,
                'amount': str(functional_amount),
                'remaining_balance': str(customer.outstanding_balance),
            },
            tenant_id=tenant_id,
        )

    return payment


def get_customer_debt_summary(tenant_id: int) -> list[dict]:
    """Get all customers with outstanding debt."""
    return list(
        Customer.objects.filter(
            tenant_id=tenant_id,
            outstanding_balance__gt=0,
            is_active=True,
        ).values(
            'id', 'name', 'phone', 'outstanding_balance',
        ).order_by('-outstanding_balance')
    )
