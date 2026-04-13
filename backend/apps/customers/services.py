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

        payment = CustomerPayment.objects.create(
            tenant_id=tenant_id,
            customer=customer,
            amount=amount,
            payment_method=payment_method,
            date=timezone.now(),
            notes=notes,
        )

        customer.outstanding_balance = models.F('outstanding_balance') - amount
        customer.save(update_fields=['outstanding_balance', 'updated_at'])
        customer.refresh_from_db()

        # Create journal entry
        from apps.finance.services import record_debt_payment_journal
        record_debt_payment_journal(
            tenant_id=tenant_id,
            payment_id=payment.pk,
            amount=amount,
            payment_type=payment_method,
        )

        publish_event(
            event_type='customer.payment',
            payload={
                'customer_id': customer_id,
                'payment_id': payment.pk,
                'amount': str(amount),
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
