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
