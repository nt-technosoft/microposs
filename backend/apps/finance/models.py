"""
Finance domain — Chart of Accounts, journal entries, summaries.
"""

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.core.models import TenantModel, ImmutableMixin


class Account(TenantModel):
    """Chart of Accounts entry."""

    class AccountType(models.TextChoices):
        ASSET = 'asset', 'Актив'
        LIABILITY = 'liability', 'Обязательство'
        EQUITY = 'equity', 'Капитал'
        INCOME = 'income', 'Доход'
        EXPENSE = 'expense', 'Расход'

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )
    is_system = models.BooleanField(
        default=False,
        help_text='System accounts cannot be deleted.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'finance_account'
        unique_together = [('tenant', 'code')]

    def __str__(self):
        return f"{self.code} — {self.name}"


class JournalEntry(ImmutableMixin, TenantModel):
    """
    Accounting journal entry. Created automatically on every
    financial operation. IMMUTABLE after creation.
    """

    class OperationType(models.TextChoices):
        SALE = 'sale', 'Продажа'
        RECEIPT = 'receipt', 'Приход'
        PAYMENT = 'payment', 'Оплата'
        RETURN = 'return', 'Возврат'
        WRITEOFF = 'writeoff', 'Списание'
        TRANSFER = 'transfer', 'Перемещение'
        DEBT_PAYMENT = 'debt_payment', 'Погашение долга'

    operation_type = models.CharField(
        max_length=20,
        choices=OperationType.choices,
    )
    operation_id = models.IntegerField(
        help_text='ID of the source operation.',
    )
    status = models.CharField(
        max_length=20,
        default='confirmed',
    )
    description = models.TextField(blank=True, default='')
    date = models.DateTimeField()
    is_reversal = models.BooleanField(
        default=False,
        help_text='True if this entry reverses another.',
    )
    reversed_entry = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversals',
    )

    class Meta:
        db_table = 'finance_journal_entry'
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['tenant', 'operation_type', 'operation_id']),
        ]

    def __str__(self):
        return f"JE #{self.pk} ({self.operation_type})"

    def delete(self, *args, **kwargs):
        self.soft_delete()


class JournalLine(TenantModel):
    """Single debit or credit line within a journal entry."""

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='journal_lines',
    )
    debit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    credit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    description = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'finance_journal_line'

    def __str__(self):
        if self.debit > 0:
            return f"DR {self.account.code} {self.debit}"
        return f"CR {self.account.code} {self.credit}"


class DailySummary(TenantModel):
    """Pre-aggregated daily P&L summary. Built by Celery tasks."""

    date = models.DateField()
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_cogs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    investor_share = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    net_business_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_sales_count = models.IntegerField(default=0)
    total_returns_count = models.IntegerField(default=0)
    total_writeoffs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        db_table = 'finance_daily_summary'
        unique_together = [('tenant', 'date')]

    def __str__(self):
        return f"Summary {self.date} (tenant={self.tenant_id})"


class CashFlowSummary(TenantModel):
    """Pre-aggregated daily cash flow."""

    date = models.DateField()
    cash_in_sales = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_in_debt_payments = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_in_investor = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_out_purchases = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_out_supplier_payments = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_out_investor_payments = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    net_cash_flow = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        db_table = 'finance_cash_flow_summary'
        unique_together = [('tenant', 'date')]
