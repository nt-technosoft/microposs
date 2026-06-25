"""
Partnerships domain — E07 procurement workspace and investment layer.

Legacy procurement-attached contract/balance classes remain only as reference
while the target workspace services are rebuilt.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TenantModel, ImmutableMixin
from apps.core.exceptions import ImmutableRecordError


class AgreementActionSource(models.TextChoices):
    BUSINESS_RECORDED = 'BUSINESS_RECORDED', 'Зафиксировано бизнесом'
    INVESTOR_SUBMITTED = 'INVESTOR_SUBMITTED', 'Отправлено инвестором'
    SYSTEM = 'SYSTEM', 'Система'
    # E18 Phase 1: capital contribution sourced from reinvested venture profit.
    PROFIT_REINVEST = 'PROFIT_REINVEST', 'Реинвестирование прибыли'


class AgreementConfirmationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Ожидает подтверждения'
    CONFIRMED = 'CONFIRMED', 'Подтверждено'
    DISPUTED = 'DISPUTED', 'Оспаривается'
    CANCELLED = 'CANCELLED', 'Отменено'


class CapitalSettlementSource(models.TextChoices):
    CASH = 'CASH', 'Деньгами (пополнение/из баланса)'
    FROM_PROFIT = 'FROM_PROFIT', 'Из нераспределённой прибыли'


class InvestmentAgreement(TenantModel):
    """Parent investment agreement that can fund multiple concrete procurements."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        PROPOSED = 'PROPOSED', 'Предложен'
        ACCEPTED = 'ACCEPTED', 'Принят'
        REJECTED = 'REJECTED', 'Отклонён'
        OPEN = 'OPEN', 'Открыт'
        ACTIVE = 'ACTIVE', 'Активен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    class LegalMode(models.TextChoices):
        MUDARABA = 'MUDARABA', 'Мудараба'
        MUSHARAKA = 'MUSHARAKA', 'Мушарака'
        HYBRID = 'HYBRID', 'Гибрид'

    class ReconciliationMode(models.TextChoices):
        # E14: how a receive fixes lot ownership when actual ≠ agreed capital.
        # Decided ONCE at agreement creation; the receive only reflects it.
        FACTUAL = 'FACTUAL', 'Динамический пересчёт по факту'
        AGREED = 'AGREED', 'Держим договорные доли (разницу — в долг)'

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    legal_mode = models.CharField(
        max_length=20,
        choices=LegalMode.choices,
        null=True,
        blank=True,
        help_text='Legal/contract label only; not a procurement type.',
    )
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='investment_agreements',
    )
    mudaraba_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        help_text='m in [0..1]; investor profit = capital * m',
    )
    loss_rule = models.CharField(
        max_length=20,
        choices=[('BY_CAPITAL', 'По доле капитала')],
        default='BY_CAPITAL',
    )
    # E14: reconciliation policy chosen at creation. FACTUAL = legacy dynamic
    # recalc; AGREED = hold agreed shares, the funding gap is read as each
    # partner's net capital position (E17). Default FACTUAL keeps existing
    # agreements/behaviour; new agreements created via the UI default to AGREED
    # (product default). Editable later but only affects FUTURE receives (past lot
    # snapshots are immutable, rule #14).
    reconciliation_mode = models.CharField(
        max_length=16,
        choices=ReconciliationMode.choices,
        default=ReconciliationMode.FACTUAL,
    )
    planned_budget = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)
    # E11: real cash pool backing this agreement's capital. Contributions move
    # cash into it; partnership supplier payments draw from it. Nullable during
    # rollout; populated by data migration + on agreement creation.
    capital_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='backed_agreements',
        help_text='E11 capital pool cash account for this agreement.',
    )
    current_terms = models.ForeignKey(
        'AgreementTermsVersion',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='current_for_agreements',
        help_text='Current forward-only terms version. Historical lot snapshots remain authoritative.',
    )

    class Meta:
        db_table = 'partnerships_investment_agreement'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'opened_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_investment_agreement_idempotent',
            ),
        ]

    def __str__(self):
        return f"InvestmentAgreement#{self.pk} {self.status}"

    @property
    def balances(self) -> dict:
        """
        Derived per-currency balance map. Source of truth is the append-only
        event triad: AgreementContribution (+), AgreementWithdrawal (-),
        AgreementAllocation (- TO_PROCUREMENT / + otherwise). Returns
        {currency: 'decimal_string'} to keep the previous JSON shape that
        API callers expect.
        """
        from decimal import Decimal as _D
        totals: dict[str, _D] = {}

        def _bump(cur: str, delta: _D) -> None:
            key = str(cur or 'UZS').upper()
            totals[key] = totals.get(key, _D('0')) + delta

        for c in self.contributions.all():
            _bump(c.currency, _D(str(c.amount)))
        # Only pool-funded returns reduce the agreement pool balance. Recovered
        # proceeds are procurement-scoped venture distributions.
        for w in self.withdrawals.filter(return_kind=AgreementWithdrawal.ReturnKind.FROM_POOL):
            _bump(w.currency, -_D(str(w.amount)))
        for a in self.allocations.all():
            amt = _D(str(a.amount))
            if a.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
                _bump(a.currency, -amt)
            else:
                _bump(a.currency, amt)

        return {
            cur: str(value.quantize(_D('0.01')))
            for cur, value in totals.items()
        }


class PartnerPositionReadModel(TenantModel):
    """E18 Phase 3 shadow read-model for partner money positions."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='partner_position_rows',
    )
    procurement = models.ForeignKey(
        'Procurement',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='partner_position_rows',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='position_read_model_rows',
    )
    currency = models.CharField(max_length=3, default='UZS')

    available = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    deployed = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    paid_in = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    net = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    owed = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    withdrawable = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))

    deployed_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_recovered_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    provisional_profit_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    loss_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    partner_liability_loss_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_returned_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    dividends_paid_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    profit_to_capital_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    remaining_inventory_capital_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    liability_capital_recovered_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_return_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    provisional_profit_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    negative_position_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    negative_liability_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    negative_capital_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    negative_dividend_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    debt_repaid_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))

    computed_at = models.DateTimeField()

    MONEY_FIELDS = (
        'available',
        'deployed',
        'paid_in',
        'net',
        'owed',
        'withdrawable',
        'deployed_uzs',
        'capital_recovered_uzs',
        'provisional_profit_uzs',
        'loss_uzs',
        'partner_liability_loss_uzs',
        'capital_returned_uzs',
        'dividends_paid_uzs',
        'profit_to_capital_uzs',
        'remaining_inventory_capital_uzs',
        'liability_capital_recovered_uzs',
        'capital_return_available_uzs',
        'provisional_profit_available_uzs',
        'negative_position_uzs',
        'negative_liability_uzs',
        'negative_capital_uzs',
        'negative_dividend_uzs',
        'debt_repaid_uzs',
    )

    class Meta:
        db_table = 'partnerships_partner_position_read_model'
        indexes = [
            models.Index(fields=['tenant', 'agreement', 'partner', 'currency'], name='pprm_agreement_idx'),
            models.Index(fields=['tenant', 'procurement', 'partner', 'currency'], name='pprm_procurement_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'agreement', 'procurement', 'partner', 'currency'],
                name='uq_partner_position_read_model',
                nulls_distinct=False,
            ),
        ]

    @property
    def identity_key(self) -> tuple[int | None, int, str]:
        return (self.procurement_id, self.partner_id, str(self.currency or 'UZS').upper())

    @property
    def money_payload(self) -> dict[str, Decimal]:
        return {field: getattr(self, field) for field in self.MONEY_FIELDS}


class PartnerJournalLineTag(TenantModel):
    """Partnership-owned analytical tag for finance journal lines."""

    class Pocket(models.TextChoices):
        CAPITAL = 'CAPITAL', 'Capital'
        PROCEEDS = 'PROCEEDS', 'Proceeds'
        DISTRIBUTION = 'DISTRIBUTION', 'Distribution'

    class Flow(models.TextChoices):
        CONTRIBUTION = 'CONTRIBUTION', 'Contribution'
        POOL_RETURN = 'POOL_RETURN', 'Pool return'
        PROCEEDS_RETURN = 'PROCEEDS_RETURN', 'Proceeds return'
        DIVIDEND = 'DIVIDEND', 'Dividend'
        PROFIT_TO_CAPITAL = 'PROFIT_TO_CAPITAL', 'Profit to capital'
        CAPITAL_RETURN = 'CAPITAL_RETURN', 'Capital return'
        OVERPAYMENT_REFUND = 'OVERPAYMENT_REFUND', 'Overpayment refund'
        DEBT_REPAID_LIABILITY = 'DEBT_REPAID_LIABILITY', 'Debt repaid liability'
        DEBT_REPAID_CAPITAL = 'DEBT_REPAID_CAPITAL', 'Debt repaid capital'
        DEBT_REPAID_DIVIDEND = 'DEBT_REPAID_DIVIDEND', 'Debt repaid dividend'

    journal_line = models.ForeignKey(
        'finance.JournalLine',
        on_delete=models.CASCADE,
        related_name='partner_tags',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='journal_line_tags',
    )
    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='journal_line_tags',
    )
    procurement = models.ForeignKey(
        'Procurement',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='journal_line_tags',
    )
    pocket = models.CharField(max_length=16, choices=Pocket.choices)
    flow = models.CharField(max_length=32, choices=Flow.choices, default=Flow.CONTRIBUTION)

    class Meta:
        db_table = 'partnerships_partner_journal_line_tag'
        indexes = [
            models.Index(fields=['tenant', 'agreement', 'partner', 'pocket'], name='pjlt_agreement_idx'),
            models.Index(fields=['tenant', 'procurement', 'partner', 'pocket'], name='pjlt_procurement_idx'),
            models.Index(fields=['journal_line'], name='pjlt_line_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['journal_line', 'partner', 'agreement', 'procurement', 'pocket'],
                name='uq_partner_journal_line_tag',
                nulls_distinct=False,
            ),
        ]


class AgreementPartner(TenantModel):
    """A partner participating in a parent investment agreement."""

    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='partners',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    planned_capital_share = models.DecimalField(max_digits=14, decimal_places=2)
    profit_share = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal('0'))

    class Meta:
        db_table = 'partnerships_agreement_partner'
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['agreement', 'partner', 'role'],
                name='uq_agreement_partner_role',
            ),
        ]


# E20 — Contract terms, payout policy and lifecycle. These records are not a
# second money ledger: actual cash remains in Payment/GL and position read models.
class AgreementTermsVersion(TenantModel):
    """Forward-only agreement terms accepted outside the platform if needed."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='terms_versions',
    )
    version = models.PositiveIntegerField()
    effective_at = models.DateTimeField()
    review_at = models.DateTimeField(null=True, blank=True)
    offline_agreed_at = models.DateTimeField(null=True, blank=True)
    offline_agreement_reference = models.CharField(max_length=255, blank=True, default='')
    terms_snapshot = models.JSONField(
        default=dict,
        help_text='Immutable economic parties and rule inputs captured when this version became effective.',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_terms_versions_created',
    )

    class Meta:
        db_table = 'partnerships_agreement_terms_version'
        ordering = ['agreement_id', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['agreement', 'version'],
                name='uq_agreement_terms_version',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('AgreementTermsVersion is append-only. Create a new version instead.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('AgreementTermsVersion is append-only.')


class InvestmentFund(TenantModel):
    """Closed-capital fund that participates in agreements through one holder partner."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        RAISING = 'RAISING', 'Сбор капитала'
        DEPLOYED = 'DEPLOYED', 'Закрыт для новых взносов'
        CLOSED = 'CLOSED', 'Закрыт'

    name = models.CharField(max_length=255)
    manager_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='managed_investment_funds',
    )
    holder_partner = models.OneToOneField(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='managed_fund_holder',
        help_text='Synthetic investor partner representing this fund in external agreements.',
    )
    capital_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        related_name='backed_investment_funds',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3, default='UZS')
    target_amount = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    current_terms = models.ForeignKey(
        'FundTermsVersion',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='current_for_funds',
    )

    class Meta:
        db_table = 'partnerships_investment_fund'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'manager_partner']),
        ]


class FundTermsVersion(TenantModel):
    """Forward-only fund rules, including disclosed manager profit participation."""

    fund = models.ForeignKey(
        InvestmentFund,
        on_delete=models.CASCADE,
        related_name='terms_versions',
    )
    version = models.PositiveIntegerField()
    effective_at = models.DateTimeField()
    review_at = models.DateTimeField(null=True, blank=True)
    manager_profit_share = models.DecimalField(max_digits=7, decimal_places=6, default=Decimal('0'))
    offline_agreed_at = models.DateTimeField(null=True, blank=True)
    offline_agreement_reference = models.CharField(max_length=255, blank=True, default='')
    terms_snapshot = models.JSONField(
        default=dict,
        help_text='Immutable fund parties and waterfall inputs captured when this version became effective.',
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='fund_terms_versions_created',
    )

    class Meta:
        db_table = 'partnerships_fund_terms_version'
        ordering = ['fund_id', '-version']
        constraints = [
            models.UniqueConstraint(fields=['fund', 'version'], name='uq_fund_terms_version'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('FundTermsVersion is append-only. Create a new version instead.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('FundTermsVersion is append-only.')


class PayoutPolicy(TenantModel):
    """Eligibility policy; it creates obligations but never moves money automatically."""

    agreement_terms = models.OneToOneField(
        AgreementTermsVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='payout_policy',
    )
    fund_terms = models.OneToOneField(
        FundTermsVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='payout_policy',
    )
    review_interval_days = models.PositiveIntegerField(default=30)
    minimum_available_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    minimum_days_between_payouts = models.PositiveIntegerField(default=30)
    reserve_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    grace_period_days = models.PositiveIntegerField(default=0)
    allow_partial = models.BooleanField(default=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'partnerships_payout_policy'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(agreement_terms__isnull=False, fund_terms__isnull=True)
                    | models.Q(agreement_terms__isnull=True, fund_terms__isnull=False)
                ),
                name='payout_policy_exactly_one_terms_owner',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            original = self.__class__.all_objects.get(pk=self.pk)
            immutable_fields = (
                'agreement_terms_id', 'fund_terms_id', 'review_interval_days',
                'minimum_available_amount', 'minimum_days_between_payouts',
                'reserve_amount', 'grace_period_days', 'allow_partial',
            )
            if any(getattr(self, field) != getattr(original, field) for field in immutable_fields):
                raise ImmutableRecordError('PayoutPolicy is fixed by its terms version. Create amended terms instead.')
        return super().save(*args, **kwargs)


class FundMember(TenantModel):
    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, related_name='members')
    partner = models.ForeignKey('core.Partner', on_delete=models.PROTECT, related_name='fund_memberships')
    joined_at = models.DateTimeField()
    offline_agreed_at = models.DateTimeField(null=True, blank=True)
    offline_agreement_reference = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'partnerships_fund_member'
        constraints = [
            models.UniqueConstraint(fields=['fund', 'partner'], name='uq_fund_member'),
        ]


class FundContribution(TenantModel):
    """Actual member money entering the fund pool; append-only like agreement contributions."""

    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, related_name='contributions')
    member = models.ForeignKey(FundMember, on_delete=models.PROTECT, related_name='contributions')
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_fund_contribution'
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_fund_contribution_idempotent',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('FundContribution is append-only. Record a reversal instead.')


class FundDeployment(TenantModel):
    """One actual transfer from the closed fund pool into an external agreement."""

    fund = models.ForeignKey(InvestmentFund, on_delete=models.PROTECT, related_name='deployments')
    agreement = models.ForeignKey(InvestmentAgreement, on_delete=models.PROTECT, related_name='fund_deployments')
    agreement_contribution = models.OneToOneField(
        'AgreementContribution',
        on_delete=models.PROTECT,
        related_name='fund_deployment',
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    date = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_fund_deployment'
        ordering = ['-date', '-id']
        indexes = [models.Index(fields=['fund', 'agreement'])]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_fund_deployment_idempotent',
            ),
        ]


class FundMemberPositionReadModel(TenantModel):
    """Materialized member view derived from fund facts and E18 holder positions."""

    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, related_name='member_position_rows')
    member = models.ForeignKey(FundMember, on_delete=models.CASCADE, related_name='position_rows')
    currency = models.CharField(max_length=3, default='UZS')
    capital_share = models.DecimalField(max_digits=12, decimal_places=9, default=Decimal('0'))
    paid_in = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    deployed = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    available = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    provisional_profit_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_return_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    profit_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    manager_fee_accrued_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    computed_at = models.DateTimeField()

    class Meta:
        db_table = 'partnerships_fund_member_position_read_model'
        constraints = [
            models.UniqueConstraint(fields=['fund', 'member', 'currency'], name='uq_fund_member_position'),
        ]


class FundPositionReadModel(TenantModel):
    """Fund-level position, including manager fee when the manager is not a member."""

    fund = models.OneToOneField(InvestmentFund, on_delete=models.CASCADE, related_name='position_row')
    currency = models.CharField(max_length=3, default='UZS')
    paid_in = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    deployed = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    available = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    provisional_profit_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_return_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    profit_available_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    manager_fee_accrued_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    computed_at = models.DateTimeField()

    class Meta:
        db_table = 'partnerships_fund_position_read_model'


class PayoutObligation(TenantModel):
    """A due action derived from terms; payment is separately recorded and confirmed."""

    class Kind(models.TextChoices):
        PROFIT = 'PROFIT', 'Прибыль'
        CAPITAL_RETURN = 'CAPITAL_RETURN', 'Возврат капитала'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает выплаты'
        RECORDED = 'RECORDED', 'Зафиксировано бизнесом'
        CONFIRMED = 'CONFIRMED', 'Подтверждено получателем'
        DISPUTED = 'DISPUTED', 'Оспаривается'
        WAIVED = 'WAIVED', 'Отменено соглашением'

    agreement = models.ForeignKey(InvestmentAgreement, on_delete=models.CASCADE, null=True, blank=True, related_name='payout_obligations')
    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, null=True, blank=True, related_name='payout_obligations')
    recipient = models.ForeignKey('core.Partner', on_delete=models.PROTECT, related_name='payout_obligations')
    procurement = models.ForeignKey('Procurement', on_delete=models.PROTECT, null=True, blank=True, related_name='payout_obligations')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    currency = models.CharField(max_length=3, default='UZS')
    due_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    recorded_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    dividend_payment = models.OneToOneField('DividendPayment', on_delete=models.PROTECT, null=True, blank=True, related_name='payout_obligation')
    capital_withdrawal = models.OneToOneField('AgreementWithdrawal', on_delete=models.PROTECT, null=True, blank=True, related_name='payout_obligation')
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_payout_obligation'
        ordering = ['due_at', 'id']
        indexes = [
            models.Index(fields=['agreement', 'status', 'due_at']),
            models.Index(fields=['fund', 'status', 'due_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(agreement__isnull=False, fund__isnull=True)
                    | models.Q(agreement__isnull=True, fund__isnull=False)
                ),
                name='payout_obligation_exactly_one_owner',
            ),
            models.UniqueConstraint(
                fields=['agreement', 'recipient', 'procurement', 'kind'],
                condition=(
                    models.Q(agreement__isnull=False)
                    & models.Q(status__in=['PENDING', 'RECORDED', 'DISPUTED'])
                ),
                nulls_distinct=False,
                name='uq_agreement_open_payout_obligation',
            ),
            models.UniqueConstraint(
                fields=['fund', 'recipient', 'kind'],
                condition=(
                    models.Q(fund__isnull=False)
                    & models.Q(status__in=['PENDING', 'RECORDED', 'DISPUTED'])
                ),
                name='uq_fund_open_payout_obligation',
            ),
        ]


class PayoutSettlement(TenantModel):
    """One factual partial or full payment reported against a payout obligation.

    Direct agreement payouts reference an immutable payment/withdrawal. Fund
    payouts may be settled outside the business ledger, so they retain the
    external evidence and declared amount rather than inventing a GL entry.
    """

    obligation = models.ForeignKey(
        PayoutObligation,
        on_delete=models.CASCADE,
        related_name='settlements',
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    settled_at = models.DateTimeField()
    evidence = models.TextField(blank=True, default='')
    dividend_payment = models.OneToOneField(
        'DividendPayment',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payout_settlement',
    )
    capital_withdrawal = models.OneToOneField(
        'AgreementWithdrawal',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payout_settlement',
    )

    class Meta:
        db_table = 'partnerships_payout_settlement'
        ordering = ['settled_at', 'id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(dividend_payment__isnull=False, capital_withdrawal__isnull=True)
                    | models.Q(dividend_payment__isnull=True, capital_withdrawal__isnull=False)
                    | models.Q(dividend_payment__isnull=True, capital_withdrawal__isnull=True)
                ),
                name='payout_settlement_at_most_one_direct_payment',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('PayoutSettlement is append-only. Record a correcting settlement instead.')

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('PayoutSettlement is append-only. Record a correcting settlement instead.')
        return super().save(*args, **kwargs)


class ContractReview(TenantModel):
    class Resolution(models.TextChoices):
        CONTINUE = 'CONTINUE', 'Продолжить'
        ORDERLY_SALE = 'ORDERLY_SALE', 'План распродажи'
        WRITE_OFF = 'WRITE_OFF', 'Зафиксировать убыток'
        BUYOUT = 'BUYOUT', 'Добровольный выкуп'
        DISPUTE = 'DISPUTE', 'Зафиксировать спор'

    agreement = models.ForeignKey(InvestmentAgreement, on_delete=models.CASCADE, null=True, blank=True, related_name='contract_reviews')
    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, null=True, blank=True, related_name='contract_reviews')
    due_at = models.DateTimeField()
    resolution = models.CharField(max_length=20, choices=Resolution.choices, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True, blank=True, related_name='contract_reviews_resolved')
    extension_until = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_contract_review'
        indexes = [models.Index(fields=['agreement', 'due_at']), models.Index(fields=['fund', 'due_at'])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(agreement__isnull=False, fund__isnull=True)
                    | models.Q(agreement__isnull=True, fund__isnull=False)
                ),
                name='contract_review_exactly_one_owner',
            ),
        ]


class DisputeCase(TenantModel):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        RESOLVED = 'RESOLVED', 'Урегулирован'
        REJECTED = 'REJECTED', 'Отклонён'

    agreement = models.ForeignKey(InvestmentAgreement, on_delete=models.CASCADE, null=True, blank=True, related_name='disputes')
    fund = models.ForeignKey(InvestmentFund, on_delete=models.CASCADE, null=True, blank=True, related_name='disputes')
    obligation = models.ForeignKey(PayoutObligation, on_delete=models.PROTECT, null=True, blank=True, related_name='disputes')
    raised_by = models.ForeignKey('core.Partner', on_delete=models.PROTECT, related_name='raised_disputes')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    evidence = models.TextField(blank=True, default='')
    statement = models.TextField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_dispute_case'
        indexes = [models.Index(fields=['agreement', 'status']), models.Index(fields=['fund', 'status'])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(agreement__isnull=False, fund__isnull=True)
                    | models.Q(agreement__isnull=True, fund__isnull=False)
                ),
                name='dispute_case_exactly_one_owner',
            ),
        ]


class CapitalCommitment(TenantModel):
    """Planned capital intent by a participant before actual money is received."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='commitments',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='capital_commitments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='capital_commitments_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='capital_commitments_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_capital_commitment'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_capital_commitment_idempotent',
            ),
        ]


class Procurement(ImmutableMixin, TenantModel):
    """
    E07 purchase/workspace root.

    Funding source, supplier settlement, payments, investment agreement and
    receive batches are separate documents coordinated by workspace services.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыт'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Частично оприходовано'
        RECEIVED = 'RECEIVED', 'Получен'
        CLOSED = 'CLOSED', 'Закрыт'
        CANCELLED = 'CANCELLED', 'Отменён'

    class FundingSource(models.TextChoices):
        OWN_FUNDS = 'OWN_FUNDS', 'Собственные средства'
        PARTNERSHIP = 'PARTNERSHIP', 'Партнёрский капитал'

    class GoodsOwnership(models.TextChoices):
        OWNED = 'OWNED', 'Свой товар'
        CONSIGNED = 'CONSIGNED', 'На реализации'

    funding_source = models.CharField(
        max_length=20,
        choices=FundingSource.choices,
        default=FundingSource.OWN_FUNDS,
        help_text='E07 target funding axis.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    primary_currency = models.CharField(
        max_length=3,
        default='UZS',
        help_text='Workspace display/default currency for item and expense drafts.',
    )
    opened_at = models.DateTimeField()
    received_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurements',
    )
    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurements',
    )
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_procurement'
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'funding_source']),
            models.Index(fields=['tenant', 'agreement']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_procurement_idempotent',
            ),
        ]

    def __str__(self):
        return f"Procurement#{self.pk} {self.funding_source}/{self.status}"

    @property
    def goods_ownership(self) -> str:
        """Derived from payment_timing: ON_SALE → CONSIGNED, else → OWNED.

        Goods ownership is not a user choice — it follows the settlement type.
        Items keep a denormalized copy for Lot creation, kept in sync by
        upsert_procurement_terms_draft's cascade.
        """
        terms = getattr(self, 'terms', None)
        if terms is not None and terms.type == ProcurementTerms.Type.ON_SALE:
            return self.GoodsOwnership.CONSIGNED
        return self.GoodsOwnership.OWNED


class ProcurementItem(TenantModel):
    """A line item on a procurement — product variant + planned quantity."""

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        READY_FOR_RECEIVE = 'READY_FOR_RECEIVE', 'Готово к приёмке'
        RECEIVED = 'RECEIVED', 'Оприходовано'
        CANCELLED = 'CANCELLED', 'Отменено'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product_variant = models.ForeignKey(
        'catalog.ProductVariant',
        on_delete=models.PROTECT,
        related_name='procurement_items',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_purchase_price = models.DecimalField(max_digits=14, decimal_places=6)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    goods_ownership = models.CharField(
        max_length=12,
        choices=[
            (Procurement.GoodsOwnership.OWNED, Procurement.GoodsOwnership.OWNED.label),
            (Procurement.GoodsOwnership.CONSIGNED, Procurement.GoodsOwnership.CONSIGNED.label),
        ],
        default=Procurement.GoodsOwnership.OWNED,
        help_text='E09 Wave A: per-item ownership axis (OWNED or CONSIGNED).',
    )
    lifecycle_state = models.CharField(
        max_length=24,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_item'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'lifecycle_state']),
        ]


class ProcurementExpense(TenantModel):
    """Landed cost components — logistics, duties, fees, etc."""

    class ExpenseType(models.TextChoices):
        LOGISTICS = 'LOGISTICS', 'Логистика'
        CUSTOMS = 'CUSTOMS', 'Таможня'
        FEE = 'FEE', 'Комиссия'
        OTHER = 'OTHER', 'Прочее'

    class AllocationMethod(models.TextChoices):
        BY_VALUE = 'BY_VALUE', 'Пропорционально стоимости'
        BY_QUANTITY = 'BY_QUANTITY', 'Пропорционально количеству'
        BY_WEIGHT = 'BY_WEIGHT', 'Пропорционально весу'

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        READY_FOR_RECEIVE = 'READY_FOR_RECEIVE', 'Готово к приёмке'
        RECEIVED = 'RECEIVED', 'Оприходовано'
        CANCELLED = 'CANCELLED', 'Отменено'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.CASCADE,
        related_name='expenses',
    )
    expense_type = models.CharField(max_length=20, choices=ExpenseType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    allocation_method = models.CharField(
        max_length=20,
        choices=AllocationMethod.choices,
        default=AllocationMethod.BY_VALUE,
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    lifecycle_state = models.CharField(
        max_length=24,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
    )

    class Meta:
        db_table = 'partnerships_procurement_expense'
        indexes = [
            models.Index(fields=['procurement']),
            models.Index(fields=['procurement', 'lifecycle_state']),
        ]


class ProcurementExpenseTarget(TenantModel):
    """Explicit item scope for a procurement expense. Empty target set means all items."""

    expense = models.ForeignKey(
        ProcurementExpense,
        on_delete=models.CASCADE,
        related_name='targets',
    )
    item = models.ForeignKey(
        ProcurementItem,
        on_delete=models.CASCADE,
        related_name='expense_targets',
    )

    class Meta:
        db_table = 'partnerships_procurement_expense_target'
        indexes = [
            models.Index(fields=['expense']),
            models.Index(fields=['item']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['expense', 'item'],
                name='uq_procurement_expense_target',
            ),
        ]


class ProcurementReceiveBatch(TenantModel):
    """One physical receive operation inside a procurement."""

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='receive_batches',
    )
    warehouse = models.ForeignKey(
        'inventory.Warehouse',
        on_delete=models.PROTECT,
        related_name='procurement_receive_batches',
    )
    received_at = models.DateTimeField()
    items_count = models.PositiveIntegerField(default=0)
    total_inventory_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    is_reversal = models.BooleanField(default=False)
    reversed_batch = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversal_batches',
    )

    class Meta:
        db_table = 'partnerships_procurement_receive_batch'
        ordering = ['-received_at', '-id']
        indexes = [
            models.Index(fields=['procurement', 'received_at'], name='partnership_procure_f0a2ed_idx'),
            models.Index(fields=['warehouse'], name='partnership_warehou_3f31c8_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatch is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatch is append-only.')


class ProcurementReceiveBatchLine(TenantModel):
    """A received procurement item snapshot inside a receive batch."""

    class DiscrepancyReason(models.TextChoices):
        NONE = 'NONE', 'Без расхождения'
        MISSING_EXPECTED_LATER = 'MISSING_EXPECTED_LATER', 'Не привезли, ждём'
        DAMAGED = 'DAMAGED', 'Повреждён'
        QUALITY_REJECT = 'QUALITY_REJECT', 'Отказ по качеству'
        ACCEPT_AS_SHORTFALL = 'ACCEPT_AS_SHORTFALL', 'Закрыть с недостачей'

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    item = models.ForeignKey(
        ProcurementItem,
        on_delete=models.PROTECT,
        related_name='receive_batch_lines',
    )
    lot = models.OneToOneField(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='receive_batch_line',
    )
    quantity_planned = models.DecimalField(max_digits=14, decimal_places=3)
    quantity_received = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0'))
    discrepancy_reason = models.CharField(
        max_length=30,
        choices=DiscrepancyReason.choices,
        default=DiscrepancyReason.NONE,
    )
    unit_purchase_price_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    allocated_expense_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    landed_cost_per_unit_uzs = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_line'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_5e6e1d_idx'),
            models.Index(fields=['item'], name='partnership_item_id_bf9414_idx'),
            models.Index(fields=['lot'], name='partnership_lot_id_776a8e_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchLine is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchLine is append-only.')


class ProcurementReceiveBatchExpense(TenantModel):
    """Expense amount fixed into a receive batch."""

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='expenses',
    )
    expense = models.ForeignKey(
        ProcurementExpense,
        on_delete=models.PROTECT,
        related_name='receive_batch_expenses',
    )
    allocated_amount_uzs = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_expense'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_2b88d7_idx'),
            models.Index(fields=['expense'], name='partnership_expense_cebc8a_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchExpense is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchExpense is append-only.')


class ProcurementReceiveBatchCapitalAllocation(TenantModel):
    """Capital/profit snapshot fixed for one receive batch."""

    batch = models.ForeignKey(
        ProcurementReceiveBatch,
        on_delete=models.CASCADE,
        related_name='capital_allocations',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='procurement_receive_batch_allocations',
    )
    role = models.CharField(max_length=20, choices=[('INVESTOR', 'Инвестор'), ('OPERATOR', 'Оператор')])
    amount_contract_currency = models.DecimalField(max_digits=20, decimal_places=2)
    capital_share = models.DecimalField(max_digits=8, decimal_places=6)
    profit_share = models.DecimalField(max_digits=8, decimal_places=6)

    class Meta:
        db_table = 'partnerships_procurement_receive_batch_capital_allocation'
        indexes = [
            models.Index(fields=['batch'], name='partnership_batch_i_19d320_idx'),
            models.Index(fields=['partner'], name='partnership_partner_32d0cb_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'partner'],
                name='uq_receive_batch_capital_partner',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementReceiveBatchCapitalAllocation is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementReceiveBatchCapitalAllocation is append-only.')


class CapitalAdvance(TenantModel):
    """Historical E14 shell. E17 stopped reifying partner capital gaps as debt;
    live settlement reads partner_capital_positions directly."""

    class RepaymentMode(models.TextChoices):
        LUMP = 'LUMP', 'Единым платежом'
        FROM_PROFIT = 'FROM_PROFIT', 'Из прибыли'

    class Status(models.TextChoices):
        OUTSTANDING = 'OUTSTANDING', 'Не погашен'
        PARTIAL = 'PARTIAL', 'Частично погашен'
        SETTLED = 'SETTLED', 'Погашен'
        CANCELLED = 'CANCELLED', 'Аннулирован (реверс)'

    agreement = models.ForeignKey(
        InvestmentAgreement, on_delete=models.PROTECT, related_name='capital_advances',
    )
    batch = models.ForeignKey(
        ProcurementReceiveBatch, on_delete=models.PROTECT, related_name='capital_advances',
    )
    debtor = models.ForeignKey(
        'core.Partner', on_delete=models.PROTECT, related_name='capital_advances_owed',
    )
    creditor = models.ForeignKey(
        'core.Partner', on_delete=models.PROTECT, null=True, blank=True,
        related_name='capital_advances_due',
        help_text='Partner who covered the shortfall. NULL = pool-mediated.',
    )
    principal = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    repayment_mode = models.CharField(
        max_length=16, choices=RepaymentMode.choices, default=RepaymentMode.LUMP,
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OUTSTANDING,
    )
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_capital_advance'
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['batch']),
            models.Index(fields=['status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_capital_advance_idempotent',
            ),
        ]

    @property
    def settled_amount(self) -> Decimal:
        return Decimal('0.00')

    @property
    def outstanding_balance(self) -> Decimal:
        return (Decimal(self.principal) - self.settled_amount).quantize(Decimal('0.01'))


class InvestmentContract(TenantModel):
    """
    Musharaka+Mudaraba hybrid contract attached to a partnership procurement.
    Profit formula:
      profit_investor_i = capital_i * mudaraba_ratio
      profit_operator = capital_op + Σ(capital_investor_i * (1 - mudaraba_ratio))
    Loss rule: by capital share (shariah hardcode).
    """

    class LossRule(models.TextChoices):
        BY_CAPITAL = 'BY_CAPITAL', 'По доле капитала'

    procurement = models.OneToOneField(
        Procurement,
        on_delete=models.CASCADE,
        related_name='contract',
    )
    mudaraba_ratio = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        help_text='m in [0..1]; investor profit = capital * m',
    )
    loss_rule = models.CharField(
        max_length=20,
        choices=LossRule.choices,
        default=LossRule.BY_CAPITAL,
    )
    planned_budget = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')

    class Meta:
        db_table = 'partnerships_investment_contract'


class ContractPartner(TenantModel):
    """A single partner participating in an InvestmentContract."""

    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'

    contract = models.ForeignKey(
        InvestmentContract,
        on_delete=models.CASCADE,
        related_name='contract_partners',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='contract_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    planned_capital_share = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text='Planned capital in contract currency',
    )
    profit_share = models.DecimalField(
        max_digits=7,
        decimal_places=6,
        help_text='Derived profit ratio (snapshot) — recomputed on receive',
        default=Decimal('0'),
    )

    class Meta:
        db_table = 'partnerships_contract_partner'
        indexes = [
            models.Index(fields=['contract']),
            models.Index(fields=['partner']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'partner', 'role'],
                name='uq_contract_partner_role',
            ),
        ]


class AgreementContribution(TenantModel):
    """A partner adds money into the parent investment agreement balance."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='contributions',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_contributions',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    date = models.DateTimeField()
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_contributions_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_contributions_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_contribution'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_agreement_contribution_idempotent',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementContribution is append-only. Record a reversal instead.')


class AgreementWithdrawal(TenantModel):
    """Money returned from the parent investment agreement to a partner."""

    class ReturnKind(models.TextChoices):
        FROM_POOL = 'FROM_POOL', 'From pool'
        FROM_PROCEEDS = 'FROM_PROCEEDS', 'From proceeds'

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='withdrawals',
    )
    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='capital_withdrawals',
        help_text='E16: procurement-venture this capital return is attributed to.',
    )
    paid_from_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_capital_withdrawals',
        help_text='E16: operating cash source when returning recovered proceeds directly.',
    )
    return_kind = models.CharField(
        max_length=16,
        choices=ReturnKind.choices,
        default=ReturnKind.FROM_POOL,
        help_text='E18: explicit capital return classification.',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_withdrawals',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    date = models.DateTimeField()
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_withdrawals_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_withdrawals_acted',
    )
    reason = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_withdrawal'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_agreement_withdrawal_idempotent',
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementWithdrawal is append-only. Record a reversal instead.')


class AgreementAllocation(TenantModel):
    """Capital moved between parent agreement balance and a concrete procurement."""

    class Direction(models.TextChoices):
        TO_PROCUREMENT = 'TO_PROCUREMENT', 'В приход'
        FROM_PROCUREMENT = 'FROM_PROCUREMENT', 'Из прихода'

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.PROTECT,
        related_name='allocations',
    )
    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='agreement_allocations',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='agreement_allocations',
    )
    direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.TO_PROCUREMENT,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    date = models.DateTimeField()
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    confirmation_status = models.CharField(
        max_length=20,
        choices=AgreementConfirmationStatus.choices,
        default=AgreementConfirmationStatus.CONFIRMED,
    )
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_allocations_created',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_allocations_acted',
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_agreement_allocation'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['agreement']),
            models.Index(fields=['procurement']),
            models.Index(fields=['partner']),
            models.Index(fields=['confirmation_status']),
            models.Index(fields=['tenant', 'client_request_id']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementAllocation is append-only. Record a reversal instead.')


class AgreementEvent(TenantModel):
    """Append-only audit event for agreement-level workflow and money facts."""

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='events',
    )
    event_type = models.CharField(max_length=80)
    occurred_at = models.DateTimeField()
    actor_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_events',
    )
    actor_partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='agreement_events',
    )
    source = models.CharField(
        max_length=24,
        choices=AgreementActionSource.choices,
        default=AgreementActionSource.BUSINESS_RECORDED,
    )
    related_model = models.CharField(max_length=80, blank=True, default='')
    related_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)

    class Meta:
        db_table = 'partnerships_agreement_event'
        ordering = ['-occurred_at', '-id']
        indexes = [
            models.Index(fields=['agreement', 'event_type']),
            models.Index(fields=['tenant', 'occurred_at']),
            models.Index(fields=['related_model', 'related_id']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('AgreementEvent is append-only. Physical delete forbidden.')


# ─── Partner Ledger ────────────────────────────────────────────────────────────

class ProcurementPartnerLedger(TenantModel):
    """
    Per-procurement ledger for a single partner.
    Accumulates capital in/out, accrued profit, dividends paid, losses.
    Replaces the old denormalized InvestorSummary.
    """

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='partner_ledgers',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='ledgers',
    )

    class Meta:
        db_table = 'partnerships_partner_ledger'
        constraints = [
            models.UniqueConstraint(
                fields=['procurement', 'partner'],
                name='uq_ledger_procurement_partner',
            ),
        ]
        indexes = [
            models.Index(fields=['tenant', 'partner']),
        ]

    def __str__(self):
        return f"Ledger procurement={self.procurement_id} partner={self.partner_id}"


class PartnerLedgerEntry(TenantModel):
    """
    Immutable double-entry line on a partner ledger.
    Always append-only — never update or delete.
    """

    class EntryType(models.TextChoices):
        CAPITAL_IN = 'CAPITAL_IN', 'Внос капитала'
        CAPITAL_OUT = 'CAPITAL_OUT', 'Вывод капитала'
        PROFIT_ACCRUED = 'PROFIT_ACCRUED', 'Начислена прибыль'
        PROFIT_REVERSED = 'PROFIT_REVERSED', 'Сторно прибыли'
        DIVIDEND_PAID = 'DIVIDEND_PAID', 'Выплачен дивиденд'
        # E18 Phase 1: venture profit consumed by reinvestment as pool capital.
        PROFIT_TO_CAPITAL = 'PROFIT_TO_CAPITAL', 'Прибыль → капитал'
        LOSS_INCURRED = 'LOSS_INCURRED', 'Зафиксирован убыток'
        ADVANCE_OUT = 'ADVANCE_OUT', 'Капитальный аванс (выдан)'
        ADVANCE_REPAID = 'ADVANCE_REPAID', 'Капитальный аванс (погашен)'

    ledger = models.ForeignKey(
        ProcurementPartnerLedger,
        on_delete=models.PROTECT,
        related_name='entries',
    )
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Snapshot rate to UZS for this ledger entry.',
    )
    functional_amount_uzs = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Entry amount converted to tenant functional currency (UZS).',
    )
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    source_ref = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='E.g. "sale_line:42", "risk_event:7", "contribution:3"',
    )

    class Meta:
        db_table = 'partnerships_ledger_entry'
        indexes = [
            models.Index(fields=['ledger', 'entry_type']),
            models.Index(fields=['tenant', 'date']),
        ]

    def save(self, *args, **kwargs):
        if self.amount and not self.functional_amount_uzs:
            if str(self.currency).upper() == 'UZS':
                self.fx_rate = Decimal('1')
                self.functional_amount_uzs = Decimal(str(self.amount)).quantize(Decimal('0.01'))
            else:
                self.functional_amount_uzs = (
                    Decimal(str(self.amount)) * Decimal(str(self.fx_rate or Decimal('1')))
                ).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('PartnerLedgerEntry is append-only. Physical delete forbidden.')


class ProcurementSaleRealization(TenantModel):
    """Append-only partner-level realization for one partnership sale slice.

    A sale line converts inventory into proceeds. This event records the
    partner economics of that conversion, but it is not final profit settlement:
    final entitlement is determined by a venture settlement snapshot.
    """

    class EventType(models.TextChoices):
        REALIZATION = 'REALIZATION', 'Реализация'
        REVERSAL = 'REVERSAL', 'Сторно реализации'
        LOSS = 'LOSS', 'Убыток без продажи'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='sale_realizations',
    )
    sale_line = models.ForeignKey(
        'sales.SaleLine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='partnership_realizations',
    )
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='partnership_realizations',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='procurement_sale_realizations',
    )
    role = models.CharField(max_length=20, blank=True, default='')
    event_type = models.CharField(
        max_length=16,
        choices=EventType.choices,
        default=EventType.REALIZATION,
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    sale_proceeds_currency = models.CharField(max_length=3, default='UZS')
    sale_proceeds_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    sale_fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    cost_basis_currency = models.CharField(max_length=3, default='UZS')
    cost_basis_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    cost_fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    sale_proceeds_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    cost_basis_uzs = models.DecimalField(max_digits=20, decimal_places=2)
    cost_basis_at_sale_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    capital_share = models.DecimalField(max_digits=8, decimal_places=6)
    profit_share = models.DecimalField(max_digits=8, decimal_places=6)
    capital_recovered_currency = models.CharField(max_length=3, default='UZS')
    capital_recovered_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    profit_currency = models.CharField(max_length=3, default='UZS')
    profit_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    loss_currency = models.CharField(max_length=3, default='UZS')
    loss_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    fx_gain_loss_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    is_partner_liability = models.BooleanField(
        default=False,
        help_text='True when loss is assigned as partner liability, not ordinary venture loss.',
    )
    capital_recovered_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    provisional_profit_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    loss_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    source_ref = models.CharField(max_length=100, blank=True, default='')
    reversal_of = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversal_events',
    )

    class Meta:
        db_table = 'partnerships_procurement_sale_realization'
        indexes = [
            models.Index(fields=['procurement', 'partner'], name='psr_proc_partner_idx'),
            models.Index(fields=['sale_line'], name='psr_line_idx'),
            models.Index(fields=['tenant', 'event_type'], name='psr_event_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['sale_line', 'partner', 'event_type'],
                condition=models.Q(event_type='REALIZATION'),
                name='uq_sale_realization_line_partner',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementSaleRealization is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementSaleRealization is append-only.')


class ProcurementVentureSettlement(TenantModel):
    """Constructive/final settlement snapshot for one procurement venture."""

    class SettlementType(models.TextChoices):
        CONSTRUCTIVE = 'CONSTRUCTIVE', 'Конструктивная ликвидация'
        FINAL = 'FINAL', 'Финальная ликвидация'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='venture_settlements',
    )
    settlement_type = models.CharField(max_length=16, choices=SettlementType.choices)
    settled_at = models.DateTimeField()
    inventory_value_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    reserve_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    totals = models.JSONField(default=dict, blank=True)
    partner_positions = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_procurement_venture_settlement'
        indexes = [
            models.Index(fields=['procurement', 'settled_at'], name='pvs_proc_idx'),
            models.Index(fields=['tenant', 'settlement_type'], name='pvs_type_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_procurement_venture_settlement_idempotent',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementVentureSettlement is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementVentureSettlement is append-only.')


class ProcurementPartnerVentureDebtRepayment(TenantModel):
    """E17 T-5.3: append-only repayment of a partner's negative venture position.

    The debtor brings real cash into operating cash; this collects the
    receivable. The repaid amount is split (at repayment time) across the
    negative-position components by waterfall (liability → over-returned capital
    → over-paid dividend) and stored here as a stable fact. Originals
    (withdrawals/dividends/liability losses) are never mutated — the position
    folds these `repaid_*` terms in to reduce negative_position.
    """

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='debt_repayments',
    )
    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='venture_debt_repayments',
    )
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    paid_to_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        related_name='venture_debt_repayments',
    )
    amount_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    # Component breakdown (functional UZS) — waterfall allocation at repayment time.
    repaid_liability_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    repaid_capital_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    repaid_dividend_uzs = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0'))
    date = models.DateTimeField()
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_partner_venture_debt_repayment'
        indexes = [
            models.Index(fields=['procurement', 'partner'], name='pvdr_proc_partner_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_partner_venture_debt_repayment_idempotent',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ImmutableRecordError('ProcurementPartnerVentureDebtRepayment is immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError('ProcurementPartnerVentureDebtRepayment is append-only.')


class DividendPayment(TenantModel):
    """
    Actual dividend payout to a partner from procurement profit.
    Invariant enforced in services: amount <= profit_pending_payout.
    """

    partner = models.ForeignKey(
        'core.Partner',
        on_delete=models.PROTECT,
        related_name='dividend_payments',
    )
    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='dividend_payments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UZS')
    fx_rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal('1'))
    fx_rate_source = models.CharField(max_length=16, blank=True, default='')
    fx_rate_date = models.DateField(null=True, blank=True)
    paid_from_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
    )
    date = models.DateTimeField()

    class Meta:
        db_table = 'partnerships_dividend_payment'
        indexes = [
            models.Index(fields=['partner', 'date']),
            models.Index(fields=['procurement']),
        ]


# =========================================================================
# E01 — Procurement Terms, Amendments, Consignment Returns
# =========================================================================


class ProcurementTerms(TenantModel):
    """
    Payment terms attached to a Procurement (OneToOne).

    Captures the obligation structure: type (PREPAID/PARTIAL/DEFERRED/
    INSTALLMENT/ON_SALE), obligation currency with FX snapshot, total
    amount due, and (for DEFERRED) deadline / (for INSTALLMENT) a schedule
    in `suppliers.PaymentSchedule`.

    For CONSIGNMENT, references the existing `suppliers.ConsignmentAgreement`.
    """

    class Type(models.TextChoices):
        PREPAID = 'PREPAID', 'Полная предоплата'
        AT_RECEIPT = 'AT_RECEIPT', 'Оплата по получению'
        PARTIAL = 'PARTIAL', 'Частичная оплата'
        DEFERRED = 'DEFERRED', 'Отсрочка'
        INSTALLMENT = 'INSTALLMENT', 'Рассрочка'
        ON_SALE = 'ON_SALE', 'Оплата после продажи'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Открыты'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Частично оплачены'
        FULLY_PAID = 'FULLY_PAID', 'Полностью оплачены'
        CANCELLED = 'CANCELLED', 'Отменены'

    class LifecycleState(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        ACTIVE = 'ACTIVE', 'Активный'

    procurement = models.OneToOneField(
        Procurement,
        on_delete=models.CASCADE,
        related_name='terms',
    )
    type = models.CharField(max_length=16, choices=Type.choices)
    lifecycle_state = models.CharField(
        max_length=8,
        choices=LifecycleState.choices,
        default=LifecycleState.DRAFT,
        help_text=(
            'DRAFT — terms still being negotiated, fully mutable. '
            'ACTIVE — locked after first finance.Payment or ReceiveBatch; '
            'semantic changes require ProcurementTermsAmendment.'
        ),
    )
    currency_of_obligation = models.CharField(max_length=3, default='UZS')
    fx_rate_at_obligation = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        default=Decimal('1'),
        help_text='Snapshot of FX rate at obligation date; not revalued.',
    )
    total_amount_due = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        help_text='Total obligation in `currency_of_obligation` (Σ items × prices × fx).',
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    deadline_date = models.DateField(
        null=True,
        blank=True,
        help_text='Only for DEFERRED type. Null otherwise (schedule covers INSTALLMENT).',
    )
    consignment_agreement = models.ForeignKey(
        'suppliers.ConsignmentAgreement',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurement_terms',
        help_text='Only for ON_SALE type.',
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_procurement_terms'
        indexes = [
            models.Index(fields=['tenant', 'type', 'status']),
            models.Index(fields=['tenant', 'status', 'deadline_date']),
        ]

    def __str__(self):
        return f"Terms#{self.pk} type={self.type} status={self.status}"

    _MUTABLE_AFTER_ACTIVATION = frozenset({
        'status', 'lifecycle_state', 'updated_at',
    })

    def save(self, *args, **kwargs):
        if self.pk:
            original = ProcurementTerms.objects.filter(pk=self.pk).first()
            if original is not None and original.lifecycle_state == self.LifecycleState.ACTIVE:
                update_fields = kwargs.get('update_fields')
                if update_fields is not None:
                    changing = set(update_fields) - self._MUTABLE_AFTER_ACTIVATION
                else:
                    changing = set()
                    for f in self._meta.fields:
                        name = f.name
                        if name in self._MUTABLE_AFTER_ACTIVATION:
                            continue
                        if getattr(original, name) != getattr(self, name):
                            changing.add(name)
                if changing:
                    from apps.core.exceptions import ImmutableRecordError
                    raise ImmutableRecordError(
                        f"ProcurementTerms#{self.pk} is ACTIVE; "
                        f"cannot modify {sorted(changing)}. Use "
                        f"ProcurementTermsAmendment for semantic changes."
                    )
        super().save(*args, **kwargs)

    def activate(self) -> bool:
        """
        Idempotent transition DRAFT → ACTIVE. Returns True if transition
        happened, False if already ACTIVE. Called at the boundary moments
        (first Payment, first ReceiveBatch) — see workspace_support for the
        canonical activation points.
        """
        if self.lifecycle_state == self.LifecycleState.ACTIVE:
            return False
        self.lifecycle_state = self.LifecycleState.ACTIVE
        self.save(update_fields=['lifecycle_state', 'updated_at'])
        return True

    @property
    def paid_amount(self) -> Decimal:
        """
        Derived: sum of linked finance.Payment(target=PROCUREMENT_COST,
        target_id=self.procurement_id) functional UZS, converted to
        obligation currency via `fx_rate_at_obligation` snapshot.

        Special case: PREPAID terms represent a synthetic full-settlement at
        terms creation (supplier paid in cash before the document existed),
        so paid_amount == total_amount_due without requiring a linked
        Payment. All other types derive from finance.Payment events.

        See SupplierPayable.paid_amount for rationale on snapshot rate.
        """
        if self.type == self.Type.PREPAID:
            return Decimal(str(self.total_amount_due or 0))

        from apps.finance.models import Payment
        from django.db.models import F, Sum

        agg = Payment.objects.filter(
            tenant_id=self.tenant_id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=self.procurement_id,
            status=Payment.Status.POSTED,
        ).aggregate(total_uzs=Sum(F('amount') * F('fx_rate')))
        total_uzs = agg['total_uzs'] or Decimal('0')
        rate = Decimal(str(self.fx_rate_at_obligation or 1))
        if rate == 0:
            return Decimal('0')
        capped = min(
            Decimal(str(self.total_amount_due or 0)),
            (Decimal(str(total_uzs)) / rate).quantize(Decimal('0.01')),
        )
        return capped

    @property
    def remaining_amount(self) -> Decimal:
        return (Decimal(str(self.total_amount_due or 0)) - self.paid_amount).quantize(Decimal('0.01'))


class ProcurementTermsAmendment(TenantModel):
    """
    Explicit amendment to a ProcurementTerms after the procurement has been
    received. Captures before/after snapshot for audit. Silent edits to
    ProcurementTerms are forbidden — every change must produce an amendment.
    """

    terms = models.ForeignKey(
        ProcurementTerms,
        on_delete=models.PROTECT,
        related_name='amendments',
    )
    amended_at = models.DateTimeField()
    changed_by_user = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='procurement_terms_amendments',
    )
    change_payload = models.JSONField(
        help_text='Snapshot {before: {...}, after: {...}} of changed fields.',
    )
    reason = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_procurement_terms_amendment'
        indexes = [
            models.Index(fields=['terms', 'amended_at']),
        ]


class ConsignmentReturn(TenantModel):
    """
    A return document for a CONSIGNMENT-typed procurement. Each return can
    contain multiple lines, each with its own `disposition` — allowing mixed
    scenarios (some lines returned to supplier, some disposed, some converted
    to owned inventory).
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Черновик'
        CONFIRMED = 'CONFIRMED', 'Подтверждён'
        CANCELLED = 'CANCELLED', 'Отменён'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='consignment_returns',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='consignment_returns',
    )
    return_date = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField(blank=True, default='')
    client_request_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'partnerships_consignment_return'
        indexes = [
            models.Index(fields=['tenant', 'procurement']),
            models.Index(fields=['tenant', 'status', 'return_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'client_request_id'],
                condition=models.Q(client_request_id__isnull=False),
                name='uq_consignment_return_idempotent',
            ),
        ]


class ConsignmentReturnLine(TenantModel):
    """
    A single line of a ConsignmentReturn. The `disposition` determines what
    happens to this quantity of this lot:

    - RETURN_TO_SUPPLIER     stock -, payable - (supplier takes goods back)
    - DISPOSE_SUPPLIER_LOSS  stock -, payable - (supplier eats the loss)
    - DISPOSE_BUSINESS_LOSS  stock -, no payable change (business eats loss)
    - CONVERT_TO_OWN         split lot: old consignment lot quantity -,
                             new owned Lot created at `agreed_price_per_unit`
                             + payable + for the conversion
    """

    class Disposition(models.TextChoices):
        RETURN_TO_SUPPLIER = 'RETURN_TO_SUPPLIER', 'Возврат поставщику'
        DISPOSE_SUPPLIER_LOSS = 'DISPOSE_SUPPLIER_LOSS', 'Списание (на поставщике)'
        DISPOSE_BUSINESS_LOSS = 'DISPOSE_BUSINESS_LOSS', 'Списание (на бизнесе)'
        CONVERT_TO_OWN = 'CONVERT_TO_OWN', 'Перевод в собственность'

    consignment_return = models.ForeignKey(
        ConsignmentReturn,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    lot = models.ForeignKey(
        'inventory.Lot',
        on_delete=models.PROTECT,
        related_name='consignment_return_lines',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text='Quantity from the lot being processed under this disposition.',
    )
    disposition = models.CharField(
        max_length=24,
        choices=Disposition.choices,
    )
    agreed_price_per_unit = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        help_text=(
            'Agreed unit price for the disposition. '
            'For RETURN/DISPOSE_*: amount of payable reduction per unit. '
            'For CONVERT_TO_OWN: buyout price per unit.'
        ),
    )
    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_consignment_return_line'
        indexes = [
            models.Index(fields=['consignment_return']),
            models.Index(fields=['lot']),
        ]


class ProcurementAmendment(TenantModel):
    """
    Append-only audit record for changes to items or expenses after OPEN/PARTIALLY_RECEIVED.
    Before/after snapshots are stored as JSON. Payments are not affected — delta is surfaced
    to the UI via the workspace payload's payment_status block (E09 Slice 7 / OPEN-S7.1).
    """

    class TargetType(models.TextChoices):
        ITEMS = 'ITEMS', 'Товары'
        EXPENSES = 'EXPENSES', 'Расходы'
        SUPPLIER = 'SUPPLIER', 'Поставщик'

    procurement = models.ForeignKey(
        Procurement,
        on_delete=models.PROTECT,
        related_name='amendments',
    )
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    amended_at = models.DateTimeField()
    changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    before = models.JSONField()
    after = models.JSONField()
    reason = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'partnerships_procurement_amendment'
        indexes = [
            models.Index(fields=['procurement', 'amended_at']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('ProcurementAmendment is append-only.')


# =========================================================================
# E12 — Multi-currency capital pool (FIFO cost-basis)
# =========================================================================


class AgreementCurrencyPool(TenantModel):
    """E12: physical cash sub-pool of an agreement in one currency.

    The base (accounting) currency pool is `InvestmentAgreement.capital_account`.
    Non-base currencies obtained via real conversion get their own
    `AGREEMENT_CAPITAL` CashAccount, registered here so the agreement can hold
    and spend several currencies while shares stay in the base currency.
    """

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='currency_pools',
    )
    currency = models.CharField(max_length=3)
    cash_account = models.ForeignKey(
        'finance.CashAccount',
        on_delete=models.PROTECT,
        related_name='+',
    )

    class Meta:
        db_table = 'partnerships_agreement_currency_pool'
        constraints = [
            models.UniqueConstraint(
                fields=['agreement', 'currency'],
                name='uq_agreement_currency_pool',
            ),
        ]
        indexes = [
            models.Index(fields=['agreement', 'currency']),
        ]


class CurrencyConversionLot(TenantModel):
    """E12: FIFO cost-basis lot created by converting agreement-pool money into
    another currency (a real spot sarf).

    The conversion fact is append-only; `amount_remaining` / `base_cost_remaining`
    are mutable running state (like `CashAccount.balance` / `LotStock`). Spending
    the held currency consumes lots oldest-first; the base-currency cost of a
    spend is the sum of consumed `base_cost`. High precision (no premature
    rounding) — money math must not lose value on large sums.
    """

    agreement = models.ForeignKey(
        InvestmentAgreement,
        on_delete=models.CASCADE,
        related_name='conversion_lots',
    )
    base_currency = models.CharField(max_length=3, help_text='Agreement accounting currency.')
    currency = models.CharField(max_length=3, help_text='Currency held by this lot (conversion target).')
    rate = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        help_text='Held currency per 1 base currency at conversion.',
    )
    amount_initial = models.DecimalField(max_digits=20, decimal_places=6)
    amount_remaining = models.DecimalField(max_digits=20, decimal_places=6)
    base_cost_initial = models.DecimalField(
        max_digits=20, decimal_places=6,
        help_text='Base-currency amount given up to acquire this lot (cost basis).',
    )
    base_cost_remaining = models.DecimalField(max_digits=20, decimal_places=6)
    converted_at = models.DateTimeField()
    source_ref = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        db_table = 'partnerships_currency_conversion_lot'
        ordering = ['converted_at', 'id']  # FIFO
        indexes = [
            models.Index(fields=['agreement', 'currency', 'converted_at']),
            models.Index(fields=['tenant', 'currency']),
        ]
