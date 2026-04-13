"""
Suppliers business logic — A/P management, payments.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event

from .models import Supplier, SupplierPayment


def record_supplier_payment(
    tenant_id: int,
    supplier_id: int,
    amount: Decimal,
    payment_method: str,
    notes: str = '',
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

        payment = SupplierPayment.objects.create(
            tenant_id=tenant_id,
            supplier=supplier,
            amount=amount,
            payment_method=payment_method,
            date=timezone.now(),
            notes=notes,
        )

        supplier.outstanding_balance = models.F('outstanding_balance') - amount
        supplier.save(update_fields=['outstanding_balance', 'updated_at'])
        supplier.refresh_from_db()

        # Create journal entry
        from apps.finance.services import record_supplier_payment_journal
        record_supplier_payment_journal(
            tenant_id=tenant_id,
            payment_id=payment.pk,
            amount=amount,
        )

        publish_event(
            event_type='supplier.payment',
            payload={
                'supplier_id': supplier_id,
                'payment_id': payment.pk,
                'amount': str(amount),
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
