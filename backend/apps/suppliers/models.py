"""
Suppliers domain — suppliers, payments, consignment agreements.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel


class Supplier(TenantModel):
    """Supplier entity."""

    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    outstanding_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        help_text='How much business owes this supplier (A/P).',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppliers_supplier'

    def __str__(self):
        return self.name


class SupplierPayment(TenantModel):
    """Payment to a supplier (reduces A/P)."""

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличные'
        BANK = 'bank', 'Банковский перевод'

    supplier = models.ForeignKey(
        Supplier,
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
        db_table = 'suppliers_payment'


class ConsignmentAgreement(TenantModel):
    """Terms for consignment with a specific supplier."""

    class RuleType(models.TextChoices):
        MARGIN = 'margin', 'Фиксированная маржа'
        COMMISSION = 'commission', 'Процент комиссии'

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='consignment_agreements',
    )
    rule_type = models.CharField(
        max_length=20,
        choices=RuleType.choices,
    )
    rule_value = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        help_text='Margin amount or commission percentage.',
    )
    damage_liability_on_business = models.BooleanField(
        default=True,
        help_text='If True, damage/loss of consignment goods is on business.',
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'suppliers_consignment_agreement'
