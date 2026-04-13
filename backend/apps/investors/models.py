"""
Investors domain — investors, contracts, profit records.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

from apps.core.models import TenantModel, ImmutableMixin


class Investor(TenantModel):
    """Investor entity."""

    user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='investor_profiles',
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'investors_investor'

    def __str__(self):
        return self.name


class InvestorContract(ImmutableMixin, TenantModel):
    """
    Investment contract. Root of all investor relationships.
    One investor can have multiple contracts with different terms.
    """

    class ContractType(models.TextChoices):
        MUDARABA = 'MUDARABA', 'Мудараба'
        MUSHARAKA = 'MUSHARAKA', 'Мушарака'

    class ContractStatus(models.TextChoices):
        ACTIVE = 'active', 'Активный'
        CLOSED = 'closed', 'Закрыт'

    investor = models.ForeignKey(
        Investor,
        on_delete=models.PROTECT,
        related_name='contracts',
    )
    contract_type = models.CharField(
        max_length=20,
        choices=ContractType.choices,
    )
    default_profit_ratio = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('1'))],
        help_text='Default investor profit share for this contract.',
    )
    status = models.CharField(
        max_length=10,
        choices=ContractStatus.choices,
        default=ContractStatus.ACTIVE,
    )
    start_date = models.DateField()
    closed_at = models.DateTimeField(null=True, blank=True)
    final_settlement = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Total amount owed to investor at closure.',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'investors_contract'

    def __str__(self):
        return f"Contract #{self.pk} ({self.investor.name}, {self.contract_type})"


class InvestorProfitRecord(TenantModel):
    """
    Records each profit/loss event for an investor.
    Created per SaleLine or per RiskEvent.
    """

    class RecordType(models.TextChoices):
        PROFIT = 'profit', 'Прибыль'
        LOSS = 'loss', 'Убыток'
        CAPITAL_RETURN = 'capital_return', 'Возврат капитала'

    contract = models.ForeignKey(
        InvestorContract,
        on_delete=models.PROTECT,
        related_name='profit_records',
    )
    investor = models.ForeignKey(
        Investor,
        on_delete=models.PROTECT,
        related_name='profit_records',
    )
    record_type = models.CharField(
        max_length=20,
        choices=RecordType.choices,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    source_type = models.CharField(
        max_length=50,
        help_text='E.g., sale_line, risk_event.',
    )
    source_id = models.IntegerField()
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=500, blank=True, default='')

    class Meta:
        db_table = 'investors_profit_record'
        indexes = [
            models.Index(fields=['contract', 'created_at']),
            models.Index(fields=['investor', 'record_type']),
        ]


class InvestorSummary(TenantModel):
    """
    Denormalized dashboard data for investor cabinet.
    Updated by Celery after each relevant event.
    """

    investor = models.ForeignKey(
        Investor,
        on_delete=models.CASCADE,
        related_name='summaries',
    )
    contract = models.ForeignKey(
        InvestorContract,
        on_delete=models.CASCADE,
        related_name='summary',
    )
    total_invested = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    in_stock_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_sold_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_profit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_losses = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    turnover_ratio = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    business_owes = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'investors_summary'
        unique_together = [('investor', 'contract')]
