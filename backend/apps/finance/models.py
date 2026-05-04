"""
Finance domain — Chart of Accounts, journal entries, cash layer, summaries.
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
        raise ValueError('Physical delete forbidden for JournalEntry.')


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


class Expense(TenantModel):
    """First-class non-supplier expense operation."""

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Наличные'
        BANK = 'bank', 'Банковский перевод'

    title = models.CharField(max_length=255)
    category = models.CharField(max_length=120, blank=True, default='')
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    source_account_code = models.CharField(max_length=20, default='1000')
    operation_currency = models.CharField(max_length=3, default='UZS')
    operation_amount = models.DecimalField(max_digits=16, decimal_places=2)
    fx_rate_snapshot = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        null=True,
        blank=True,
    )
    functional_amount_uzs = models.DecimalField(max_digits=16, decimal_places=2)
    occurred_at = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_expense'
        indexes = [
            models.Index(fields=['tenant', 'occurred_at']),
            models.Index(fields=['tenant', 'operation_currency']),
        ]

    def __str__(self):
        return f"Expense #{self.pk}: {self.title}"


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
    total_return_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_return_restock_cogs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_return_disposal_loss = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
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
    cash_out_expenses = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_out_refunds = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    cash_out_investor_payments = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    net_cash_flow = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        db_table = 'finance_cash_flow_summary'
        unique_together = [('tenant', 'date')]


class ExchangeRate(TenantModel):
    """
    Historical FX rate snapshot (base -> quote) for a specific date.
    Keeps immutable-by-date operational trace for financial operations.
    """

    class Source(models.TextChoices):
        CBU = 'CBU', 'Central Bank of Uzbekistan'
        MANUAL = 'MANUAL', 'Manual override'

    base_currency = models.CharField(max_length=3, default='USD')
    quote_currency = models.CharField(max_length=3, default='UZS')
    rate_date = models.DateField()
    rate = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
    )
    source = models.CharField(
        max_length=12,
        choices=Source.choices,
        default=Source.CBU,
    )
    is_manual = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default='')
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'finance_exchange_rate'
        unique_together = [('tenant', 'base_currency', 'quote_currency', 'rate_date')]
        indexes = [
            models.Index(fields=['tenant', 'base_currency', 'quote_currency', 'rate_date']),
            models.Index(fields=['tenant', 'rate_date']),
        ]

    def __str__(self):
        return (
            f"{self.base_currency}/{self.quote_currency} "
            f"{self.rate} ({self.rate_date})"
        )


class CashAccount(TenantModel):
    """
    Operational cash register / card terminal / bank account.
    Mono-currency. balance is a running total maintained by services.
    """

    class Kind(models.TextChoices):
        CASH = 'cash', 'Касса наличных'
        CARD_TERMINAL = 'card_terminal', 'Карт-терминал'
        BANK = 'bank', 'Банковский счёт'

    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=3, default='UZS')
    balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal('0'),
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.CASH,
    )
    linked_account = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cash_accounts',
        help_text='COA account for bookkeeping journal lines.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'finance_cash_account'
        indexes = [
            models.Index(fields=['tenant', 'currency']),
        ]

    def __str__(self):
        return f"{self.name} ({self.currency})"


class CashEntry(TenantModel):
    """
    Append-only ledger entry for a CashAccount.
    Each financial operation that touches cash creates one or more entries.
    """

    class Direction(models.TextChoices):
        IN = 'IN', 'Приход'
        OUT = 'OUT', 'Расход'

    account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name='entries',
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateTimeField()
    source_ref_type = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='E.g. "sale", "expense", "customer_payment".',
    )
    source_ref_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='PK of the source object.',
    )

    class Meta:
        db_table = 'finance_cash_entry'
        indexes = [
            models.Index(fields=['account', 'date']),
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['source_ref_type', 'source_ref_id']),
        ]

    def __str__(self):
        return f"CashEntry {self.direction} {self.amount} ({self.account})"


class CurrencyExchange(TenantModel):
    """
    Atomic currency exchange between two CashAccounts.
    Both account balances are adjusted and a JournalEntry is created.
    """

    from_account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name='exchanges_out',
    )
    to_account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name='exchanges_in',
    )
    from_amount = models.DecimalField(max_digits=14, decimal_places=2)
    from_currency = models.CharField(max_length=3)
    to_amount = models.DecimalField(max_digits=14, decimal_places=2)
    to_currency = models.CharField(max_length=3)
    effective_rate = models.DecimalField(max_digits=14, decimal_places=6)
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_currency_exchange'
        indexes = [
            models.Index(fields=['tenant', 'date']),
        ]

    def __str__(self):
        return (
            f"Exchange {self.from_amount}{self.from_currency}"
            f"→{self.to_amount}{self.to_currency}"
        )


class Refund(TenantModel):
    """
    Customer refund record. Ties back to a sales.Return (optional).
    Method RECEIVABLE_OFFSET does not touch a CashAccount — it cancels debt.
    """

    class Method(models.TextChoices):
        CASH = 'cash', 'Наличные'
        PLASTIK = 'plastik', 'Карт-терминал'
        TRANSFER = 'transfer', 'Перевод'
        RECEIVABLE_OFFSET = 'receivable_offset', 'Зачёт долга'

    customer = models.ForeignKey(
        'customers.Customer',
        on_delete=models.PROTECT,
        related_name='refunds',
        null=True,
        blank=True,
    )
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('1'),
    )
    account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='refunds',
        help_text='Null for RECEIVABLE_OFFSET method.',
    )
    method = models.CharField(max_length=20, choices=Method.choices)
    return_ref = models.ForeignKey(
        'sales.Return',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='refunds',
    )

    class Meta:
        db_table = 'finance_refund'
        indexes = [
            models.Index(fields=['tenant', 'date']),
            models.Index(fields=['customer', 'date']),
        ]

    def __str__(self):
        return f"Refund #{self.pk} {self.amount}{self.currency} ({self.method})"


class OwnerContribution(TenantModel):
    """
    Owner / equity injection into a CashAccount.
    DR CashAccount | CR Owner equity.
    """

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    currency = models.CharField(max_length=3, default='UZS')
    to_account = models.ForeignKey(
        CashAccount,
        on_delete=models.PROTECT,
        related_name='contributions',
    )
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_owner_contribution'
        indexes = [
            models.Index(fields=['tenant', 'date']),
        ]

    def __str__(self):
        return f"OwnerContribution {self.amount}{self.currency} → {self.to_account}"
