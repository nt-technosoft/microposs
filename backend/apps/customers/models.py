"""
Customers domain — customers, debt tracking, payments.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel


class Customer(TenantModel):
    """Customer entity for credit sales (A/R)."""

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    outstanding_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='How much this customer owes (A/R).',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'customers_customer'
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return self.name


class CustomerPayment(TenantModel):
    """Debt repayment by customer (reduces A/R)."""

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличные'
        BANK = 'bank', 'Банковский перевод'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
    )
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'customers_payment'
