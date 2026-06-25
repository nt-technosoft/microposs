"""E20 closed-fund services.

The fund is a real capital pool. It joins an external agreement through its
synthetic holder partner, so existing E11/E18 cash, tags and FIFO economics stay
the only source of money truth.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.models import BusinessInvestorRelation, Partner
from apps.finance.models import Account, CashAccount, Payment
from apps.finance.services import record_capital_pool_contribution

from .models import (
    AgreementPartner,
    FundContribution,
    FundDeployment,
    FundMember,
    FundMemberPositionReadModel,
    FundPositionReadModel,
    FundTermsVersion,
    InvestmentAgreement,
    InvestmentFund,
    PartnerPositionReadModel,
    PayoutPolicy,
)
from .money_utils import ZERO, equity_account_code, money, ratio


def create_investment_fund(
    *,
    tenant_id: int,
    name: str,
    manager_partner_id: int,
    member_partner_ids: list[int],
    currency: str = 'UZS',
    target_amount: Decimal | None = None,
    manager_profit_share: Decimal = Decimal('0'),
    review_at=None,
    offline_agreed_at=None,
    offline_agreement_reference: str = '',
    notes: str = '',
    created_by_id: int | None = None,
    payout_policy: dict | None = None,
) -> InvestmentFund:
    """Create a raisable fund and its synthetic agreement-facing investor."""
    currency = str(currency or 'UZS').upper()
    manager_profit_share = ratio(manager_profit_share)
    if not name.strip():
        raise ValueError('Fund name is required.')
    if not Decimal('0') <= manager_profit_share <= Decimal('1'):
        raise ValueError('manager_profit_share must be in [0, 1].')
    member_ids = sorted({int(item) for item in member_partner_ids})
    if not member_ids:
        raise ValueError('A fund needs at least one member before capital can be raised.')

    with transaction.atomic():
        manager = Partner.objects.select_for_update().filter(
            tenant_id=tenant_id, pk=manager_partner_id, is_active=True,
        ).first()
        if manager is None:
            raise ValueError('Fund manager is not an active business partner.')
        members = list(Partner.objects.filter(
            tenant_id=tenant_id, pk__in=member_ids, is_active=True,
        ))
        if len(members) != len(member_ids):
            raise ValueError('Every fund member must be an active business partner.')

        holder = Partner.objects.create(
            tenant_id=tenant_id,
            role=Partner.Role.INVESTOR,
            display_name=f'Фонд: {name.strip()}',
            is_active=True,
        )
        # Existing agreement validation treats the holder as an investor. This
        # relation is system-created; it is not a marketplace relation.
        BusinessInvestorRelation.objects.create(
            tenant_id=tenant_id,
            partner=holder,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
            created_by_id=created_by_id,
            notes='system_fund_holder',
        )
        account = CashAccount.objects.create(
            tenant_id=tenant_id,
            name=f'Капитал фонда: {name.strip()}',
            currency=currency,
            kind=CashAccount.Kind.FUND_CAPITAL,
            linked_account=Account.objects.get(tenant_id=tenant_id, code='1300'),
            balance=ZERO,
            is_active=True,
        )
        now = timezone.now()
        fund = InvestmentFund.objects.create(
            tenant_id=tenant_id,
            name=name.strip(),
            manager_partner=manager,
            holder_partner=holder,
            capital_account=account,
            status=InvestmentFund.Status.RAISING,
            currency=currency,
            target_amount=money(target_amount) if target_amount is not None else None,
            opened_at=now,
        )
        FundMember.objects.bulk_create([
            FundMember(
                tenant_id=tenant_id,
                fund=fund,
                partner=member,
                joined_at=now,
                offline_agreed_at=offline_agreed_at,
                offline_agreement_reference=offline_agreement_reference,
            )
            for member in members
        ])
        terms = FundTermsVersion.objects.create(
            tenant_id=tenant_id,
            fund=fund,
            version=1,
            effective_at=now,
            review_at=review_at,
            manager_profit_share=manager_profit_share,
            offline_agreed_at=offline_agreed_at,
            offline_agreement_reference=offline_agreement_reference,
            terms_snapshot={
                'name': fund.name,
                'currency': currency,
                'target_amount': str(fund.target_amount) if fund.target_amount is not None else None,
                'manager_partner_id': manager.pk,
                'manager_profit_share': str(manager_profit_share),
                'members': member_ids,
                'waterfall': ['capital_return', 'net_profit', 'manager_fee'],
            },
            notes=notes,
            created_by_id=created_by_id,
        )
        policy_values = payout_policy or {}
        PayoutPolicy.objects.create(
            tenant_id=tenant_id,
            fund_terms=terms,
            review_interval_days=int(policy_values.get('review_interval_days', 30)),
            minimum_available_amount=money(policy_values.get('minimum_available_amount', ZERO)),
            minimum_days_between_payouts=int(policy_values.get('minimum_days_between_payouts', 30)),
            reserve_amount=money(policy_values.get('reserve_amount', ZERO)),
            grace_period_days=int(policy_values.get('grace_period_days', 0)),
            allow_partial=bool(policy_values.get('allow_partial', True)),
        )
        fund.current_terms = terms
        fund.save(update_fields=['current_terms', 'updated_at'])
        rebuild_fund_member_positions(fund)
    return fund


def add_fund_contribution(
    *,
    tenant_id: int,
    fund_id: int,
    partner_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal | None = None,
    date=None,
    notes: str = '',
    client_request_id=None,
    from_cash_account_id: int | None = None,
) -> FundContribution:
    """Record real member capital before the fund's first deployment."""
    amount = money(amount)
    currency = str(currency or 'UZS').upper()
    if amount <= ZERO:
        raise ValueError('Fund contribution amount must be > 0.')
    date = date or timezone.now()
    with transaction.atomic():
        if client_request_id:
            existing = FundContribution.objects.filter(
                tenant_id=tenant_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id, tenant_id=tenant_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fund is closed for new capital after its first deployment.')
        if currency != str(fund.currency).upper():
            raise ValueError('Fund contribution currency must match fund currency.')
        member = FundMember.objects.select_related('partner').filter(
            fund=fund, partner_id=partner_id,
        ).first()
        if member is None:
            raise ValueError('Selected partner is not a member of this fund.')
        contribution = FundContribution.objects.create(
            tenant_id=tenant_id,
            fund=fund,
            member=member,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate or Decimal('1'),
            date=date,
            notes=notes,
            client_request_id=client_request_id,
        )
        payment = record_capital_pool_contribution(
            tenant_id=tenant_id,
            pool_account_id=fund.capital_account_id,
            partner_id=member.partner_id,
            contribution_id=contribution.pk,
            target_type=Payment.TargetType.FUND_CONTRIBUTION,
            amount=amount,
            equity_account_code=equity_account_code(role=member.partner.role, legal_mode=None),
            currency=currency,
            fx_rate=fx_rate,
            paid_at=date,
            from_cash_account_id=from_cash_account_id,
            client_request_id=client_request_id,
            notes=notes,
        )
        contribution.fx_rate = payment.fx_rate
        contribution.fx_rate_source = payment.fx_rate_source
        contribution.fx_rate_date = payment.fx_rate_date
        contribution.save(update_fields=['fx_rate', 'fx_rate_source', 'fx_rate_date', 'updated_at'])
        rebuild_fund_member_positions(fund)
    return contribution


def deploy_fund_to_agreement(
    *,
    tenant_id: int,
    fund_id: int,
    agreement_id: int,
    amount: Decimal,
    date=None,
    notes: str = '',
    client_request_id=None,
) -> FundDeployment:
    """Move real fund-pool cash into an agreement and close the fund to new capital."""
    from .workspace_support import add_agreement_contribution

    amount = money(amount)
    if amount <= ZERO:
        raise ValueError('Fund deployment amount must be > 0.')
    date = date or timezone.now()
    with transaction.atomic():
        if client_request_id:
            existing = FundDeployment.objects.filter(
                tenant_id=tenant_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing
        fund = InvestmentFund.objects.select_for_update().select_related('capital_account').get(
            pk=fund_id, tenant_id=tenant_id,
        )
        if fund.status not in {InvestmentFund.Status.RAISING, InvestmentFund.Status.DEPLOYED}:
            raise ValueError('Only an open fund can make a deployment.')
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id, tenant_id=tenant_id,
        )
        if str(fund.currency).upper() != str(agreement.currency).upper():
            raise ValueError('Fund and agreement currencies must match in MVP.')
        if Decimal(str(fund.capital_account.balance)) < amount:
            raise ValueError('Fund capital pool has insufficient available cash.')
        if not AgreementPartner.objects.filter(
            agreement=agreement,
            partner_id=fund.holder_partner_id,
            role=AgreementPartner.Role.INVESTOR,
        ).exists():
            raise ValueError('Add this fund as an INVESTOR party to the agreement before deployment.')
        contribution = add_agreement_contribution(
            tenant_id=tenant_id,
            agreement_id=agreement.pk,
            partner_id=fund.holder_partner_id,
            amount=amount,
            currency=fund.currency,
            fx_rate=Decimal('1'),
            date=date,
            notes=f'fund_deployment:{fund.pk} {notes}'.strip(),
            client_request_id=client_request_id,
            from_cash_account_id=fund.capital_account_id,
            allow_restricted_source=True,
        )
        deployment = FundDeployment.objects.create(
            tenant_id=tenant_id,
            fund=fund,
            agreement=agreement,
            agreement_contribution=contribution,
            amount=amount,
            currency=fund.currency,
            date=date,
            notes=notes,
            client_request_id=client_request_id,
        )
        if fund.status == InvestmentFund.Status.RAISING:
            fund.status = InvestmentFund.Status.DEPLOYED
            fund.save(update_fields=['status', 'updated_at'])
        rebuild_fund_member_positions(fund)
    return deployment


def rebuild_fund_member_positions(fund: InvestmentFund) -> None:
    """Fold fund contributions and E18 holder positions into member-facing rows."""
    members = list(FundMember.objects.filter(fund=fund).select_related('partner'))
    currency = str(fund.currency or 'UZS').upper()
    paid_by_member = {
        member.pk: sum(
            (money(row.amount) for row in FundContribution.objects.filter(fund=fund, member=member, currency=currency)),
            ZERO,
        )
        for member in members
    }
    total_paid = sum(paid_by_member.values(), ZERO)
    total_deployed = sum(
        (money(row.amount) for row in FundDeployment.objects.filter(fund=fund, currency=currency)),
        ZERO,
    )
    agreement_rows = PartnerPositionReadModel.objects.filter(
        tenant_id=fund.tenant_id,
        agreement__fund_deployments__fund=fund,
        partner_id=fund.holder_partner_id,
        procurement__isnull=True,
        currency=currency,
    ).distinct()
    external_available = sum((money(row.available) for row in agreement_rows), ZERO)
    venture_rows = PartnerPositionReadModel.objects.filter(
        tenant_id=fund.tenant_id,
        agreement__fund_deployments__fund=fund,
        partner_id=fund.holder_partner_id,
        procurement__isnull=False,
        currency='UZS',
    ).distinct()
    gross_profit = sum((money(row.provisional_profit_uzs) for row in venture_rows), ZERO)
    capital_available = sum((money(row.capital_return_available_uzs) for row in venture_rows), ZERO)
    profit_available = sum((money(row.provisional_profit_available_uzs) for row in venture_rows), ZERO)
    manager_share = Decimal(str(getattr(fund.current_terms, 'manager_profit_share', ZERO)))
    manager_fee = money(max(ZERO, profit_available) * manager_share)
    distributable_profit = money(max(ZERO, profit_available) - manager_fee)
    now = timezone.now()
    FundPositionReadModel.all_objects.update_or_create(
        tenant_id=fund.tenant_id,
        fund=fund,
        defaults={
            'currency': currency,
            'paid_in': total_paid,
            'deployed': total_deployed,
            'available': external_available,
            'provisional_profit_uzs': gross_profit,
            'capital_return_available_uzs': capital_available,
            'profit_available_uzs': profit_available,
            'manager_fee_accrued_uzs': manager_fee,
            'computed_at': now,
            'deleted_at': None,
        },
    )
    keep_ids: list[int] = []
    for member in members:
        share = ratio(paid_by_member[member.pk] / total_paid) if total_paid > ZERO else ZERO
        member_fee = manager_fee if member.partner_id == fund.manager_partner_id else ZERO
        row, _ = FundMemberPositionReadModel.all_objects.update_or_create(
            tenant_id=fund.tenant_id,
            fund=fund,
            member=member,
            currency=currency,
            defaults={
                'capital_share': share,
                'paid_in': paid_by_member[member.pk],
                'deployed': money(total_deployed * share),
                'available': money(external_available * share),
                'provisional_profit_uzs': money(gross_profit * share),
                'capital_return_available_uzs': money(capital_available * share),
                'profit_available_uzs': money(distributable_profit * share + member_fee),
                'manager_fee_accrued_uzs': member_fee,
                'computed_at': now,
                'deleted_at': None,
            },
        )
        keep_ids.append(row.pk)
    stale = FundMemberPositionReadModel.all_objects.filter(tenant_id=fund.tenant_id, fund=fund)
    if keep_ids:
        stale = stale.exclude(pk__in=keep_ids)
    stale.delete()


def rebuild_fund_positions_for_agreement(agreement: InvestmentAgreement) -> None:
    for fund in InvestmentFund.objects.filter(
        tenant_id=agreement.tenant_id,
        deployments__agreement=agreement,
    ).distinct():
        rebuild_fund_member_positions(fund)
