"""
Customers domain — customers, receivable ledger, payments.
"""

from decimal import Decimal

from django.db import models
from django.core.validators import MinValueValidator

from apps.core.models import TenantModel


class Customer(TenantModel):
    """Customer entity for credit sales (A/R)."""

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'customers_customer'
        indexes = [
            models.Index(fields=['tenant', 'name']),
        ]

    def __str__(self):
        return self.name

    @property
    def outstanding_balance(self) -> Decimal:
        """
        Computed A/R balance in UZS — sum of all ReceivableEntry amounts.
        Positive = customer owes us.
        Frontend compat shim until PR-11 migrates to Receivable.balances.
        """
        try:
            return self.receivable.balance_uzs
        except Receivable.DoesNotExist:
            return Decimal('0')


class Receivable(TenantModel):
    """
    Per-customer receivable ledger.
    balances: Map<currency, decimal_string> — running totals per currency.
    """

    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name='receivable',
    )
    balances = models.JSONField(
        default=dict,
        help_text='Map<currency, decimal_string>. Positive = owes us.',
    )

    class Meta:
        db_table = 'customers_receivable'

    @property
    def balance_uzs(self) -> Decimal:
        """Sum of all currency balances treated as UZS (simple sum for UI shim)."""
        return sum(Decimal(str(v)) for v in self.balances.values()) if self.balances else Decimal('0')


class ReceivableEntry(TenantModel):
    """
    Append-only ledger entry for a customer's receivable.
    Never update or delete.
    """

    class EntryType(models.TextChoices):
        DEBT_ACCRUED = 'DEBT_ACCRUED', 'Долг начислен'
        REPAYMENT = 'REPAYMENT', 'Погашение'
        ADJUSTMENT = 'ADJUSTMENT', 'Корректировка'
        WRITE_OFF = 'WRITE_OFF', 'Списание'

    receivable = models.ForeignKey(
        Receivable,
        on_delete=models.PROTECT,
        related_name='entries',
    )
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal('1'),
    )
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    due_date = models.DateField(null=True, blank=True)
    source_ref = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='E.g. "sale:42", "customer_payment:7"',
    )

    class Meta:
        db_table = 'customers_receivable_entry'
        indexes = [
            models.Index(fields=['receivable', 'entry_type']),
            models.Index(fields=['tenant', 'date']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('ReceivableEntry is append-only. Physical delete forbidden.')


class CustomerPayment(TenantModel):
    """Historical debt repayment record. Kept for audit trail."""

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
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal('1'),
    )
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'customers_payment'
        indexes = [
            models.Index(fields=['tenant', 'date']),
        ]
