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
from apps.finance.models import Account, CashAccount, CashEntry, Payment
from apps.finance.services import create_cash_entry, record_capital_pool_contribution

from .models import (
    AgreementPartner,
    FundApplication,
    FundContribution,
    FundDeployment,
    FundMember,
    FundMemberExit,
    FundMemberPositionReadModel,
    FundPositionReadModel,
    FundTermsVersion,
    InvestmentAgreement,
    InvestmentFund,
    PartnerPositionReadModel,
    PayoutObligation,
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
    min_contribution_amount: Decimal = Decimal('0'),
    visibility: str = InvestmentFund.Visibility.PRIVATE_INVITE,
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
    min_contribution_amount = money(min_contribution_amount)
    if target_amount is not None and money(target_amount) <= ZERO:
        raise ValueError('target_amount must be positive when provided.')
    if min_contribution_amount < ZERO:
        raise ValueError('min_contribution_amount cannot be negative.')
    if visibility not in InvestmentFund.Visibility.values:
        raise ValueError('Unsupported fund visibility.')

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
            visibility=visibility,
            currency=currency,
            target_amount=money(target_amount) if target_amount is not None else None,
            min_contribution_amount=min_contribution_amount,
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
                'min_contribution_amount': str(fund.min_contribution_amount),
                'visibility': visibility,
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


def _confirmed_capital(fund: InvestmentFund) -> Decimal:
    contributions = sum(
        (money(row.amount) for row in FundContribution.objects.filter(fund=fund, currency=fund.currency)),
        ZERO,
    )
    exits = sum(
        (money(row.refund_amount) for row in FundMemberExit.objects.filter(fund=fund, currency=fund.currency)),
        ZERO,
    )
    return money(contributions - exits)


def submit_fund_application(
    *,
    tenant_id: int,
    fund_id: int,
    partner_id: int,
    requested_amount: Decimal,
    message: str = '',
) -> FundApplication:
    requested_amount = money(requested_amount)
    if requested_amount <= ZERO:
        raise ValueError('Requested amount must be > 0.')
    with transaction.atomic():
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id, tenant_id=tenant_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fund is not accepting applications.')
        if requested_amount < money(fund.min_contribution_amount):
            raise ValueError('Requested amount is below fund minimum contribution.')
        partner = Partner.objects.filter(pk=partner_id, tenant_id=tenant_id, is_active=True).first()
        if partner is None:
            raise ValueError('Fund application partner was not found.')
        if FundMember.objects.filter(fund=fund, partner=partner, status=FundMember.Status.ACTIVE).exists():
            raise ValueError('Partner is already an active fund member.')
        application, created = FundApplication.objects.get_or_create(
            tenant_id=tenant_id,
            fund=fund,
            partner=partner,
            status=FundApplication.Status.PENDING,
            defaults={
                'requested_amount': requested_amount,
                'currency': fund.currency,
                'message': message,
            },
        )
        if not created:
            application.requested_amount = requested_amount
            application.message = message
            application.save(update_fields=['requested_amount', 'message', 'updated_at'])
    return application


def approve_fund_application(
    *,
    tenant_id: int,
    fund_id: int,
    application_id: int,
    approved_amount: Decimal | None = None,
    decided_by_id: int | None = None,
) -> FundApplication:
    with transaction.atomic():
        application = FundApplication.objects.select_for_update().select_related('fund', 'partner').filter(
            pk=application_id,
            tenant_id=tenant_id,
            fund_id=fund_id,
        ).first()
        if application is None:
            raise ValueError('Fund application was not found.')
        if application.status != FundApplication.Status.PENDING:
            raise ValueError('Only pending applications can be approved.')
        fund = InvestmentFund.objects.select_for_update().get(pk=application.fund_id, tenant_id=tenant_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fund is closed for new members after deployment.')
        amount = money(approved_amount if approved_amount is not None else application.requested_amount)
        if amount <= ZERO:
            raise ValueError('Approved amount must be > 0.')
        if amount > money(application.requested_amount):
            raise ValueError('Approved amount cannot exceed requested amount.')
        if amount < money(fund.min_contribution_amount):
            raise ValueError('Approved amount is below fund minimum contribution.')
        if fund.target_amount is not None:
            active_approved = sum(
                (money(row.approved_amount) for row in FundMember.objects.filter(
                    fund=fund,
                    status=FundMember.Status.ACTIVE,
                )),
                ZERO,
            )
            if active_approved + amount > money(fund.target_amount):
                raise ValueError('Fund hard cap would be exceeded. Amend terms before approving more capital.')
        application.status = FundApplication.Status.APPROVED
        application.approved_amount = amount
        application.decided_by_id = decided_by_id
        application.decided_at = timezone.now()
        application.save(update_fields=['status', 'approved_amount', 'decided_by', 'decided_at', 'updated_at'])
        FundMember.objects.update_or_create(
            tenant_id=tenant_id,
            fund=fund,
            partner=application.partner,
            defaults={
                'application': application,
                'status': FundMember.Status.ACTIVE,
                'approved_amount': amount,
                'confirmed_amount': ZERO,
                'joined_at': timezone.now(),
                'exited_at': None,
                'offline_agreed_at': application.decided_at,
                'offline_agreement_reference': 'fund-application-approved',
            },
        )
        rebuild_fund_member_positions(fund)
    return application


def preview_fund_application_approvals(
    *,
    tenant_id: int,
    fund_id: int,
    approvals: list[dict],
) -> dict:
    """Preview approval batch without changing application/member state."""
    fund = InvestmentFund.objects.get(pk=fund_id, tenant_id=tenant_id)
    if fund.status != InvestmentFund.Status.RAISING:
        raise ValueError('Fund is closed for new members after deployment.')
    active_approved = sum(
        (money(row.approved_amount) for row in FundMember.objects.filter(
            fund=fund,
            status=FundMember.Status.ACTIVE,
        )),
        ZERO,
    )
    rows = []
    batch_total = ZERO
    for item in approvals:
        application = FundApplication.objects.select_related('partner').filter(
            pk=int(item['application_id']),
            fund=fund,
            tenant_id=tenant_id,
            status=FundApplication.Status.PENDING,
        ).first()
        if application is None:
            raise ValueError('Fund application was not found.')
        amount = money(item.get('approved_amount') or application.requested_amount)
        if amount <= ZERO:
            raise ValueError('Approved amount must be > 0.')
        if amount > money(application.requested_amount):
            raise ValueError('Approved amount cannot exceed requested amount.')
        if amount < money(fund.min_contribution_amount):
            raise ValueError('Approved amount is below fund minimum contribution.')
        batch_total += amount
        rows.append({
            'application_id': application.pk,
            'partner_id': application.partner_id,
            'partner_name': application.partner.display_name,
            'requested_amount': str(money(application.requested_amount)),
            'approved_amount': str(amount),
            'currency': fund.currency,
        })
    target_amount = money(fund.target_amount) if fund.target_amount is not None else None
    after_total = money(active_approved + batch_total)
    return {
        'fund_id': fund.pk,
        'currency': fund.currency,
        'target_amount': str(target_amount) if target_amount is not None else None,
        'active_approved_amount': str(money(active_approved)),
        'batch_approved_amount': str(money(batch_total)),
        'after_approved_amount': str(after_total),
        'exceeds_target': bool(target_amount is not None and after_total > target_amount),
        'rows': rows,
    }


def amend_fundraising_terms(
    *,
    tenant_id: int,
    fund_id: int,
    target_amount: Decimal | None = None,
    min_contribution_amount: Decimal | None = None,
    visibility: str | None = None,
    review_at=None,
    manager_profit_share: Decimal | None = None,
    offline_agreed_at=None,
    offline_agreement_reference: str = '',
    notes: str = '',
    created_by_id: int | None = None,
    payout_policy: dict | None = None,
) -> FundTermsVersion:
    """Explicit pre-deployment fundraising amendment + immutable terms version."""
    from .lifecycle_services import create_fund_terms_version

    with transaction.atomic():
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id, tenant_id=tenant_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fundraising terms cannot be changed after deployment.')
        updates: list[str] = []
        if target_amount is not None:
            target = money(target_amount)
            if target <= ZERO:
                raise ValueError('target_amount must be positive when provided.')
            confirmed = _confirmed_capital(fund)
            approved = sum(
                (money(row.approved_amount) for row in FundMember.objects.filter(
                    fund=fund,
                    status=FundMember.Status.ACTIVE,
                )),
                ZERO,
            )
            if target < confirmed or target < approved:
                raise ValueError('target_amount cannot be below approved or confirmed fund capital.')
            fund.target_amount = target
            updates.append('target_amount')
        if min_contribution_amount is not None:
            minimum = money(min_contribution_amount)
            if minimum < ZERO:
                raise ValueError('min_contribution_amount cannot be negative.')
            fund.min_contribution_amount = minimum
            updates.append('min_contribution_amount')
        if visibility is not None:
            if visibility not in InvestmentFund.Visibility.values:
                raise ValueError('Unsupported fund visibility.')
            fund.visibility = visibility
            updates.append('visibility')
        if updates:
            updates.append('updated_at')
            fund.save(update_fields=updates)
        return create_fund_terms_version(
            fund=fund,
            review_at=review_at,
            manager_profit_share=manager_profit_share,
            offline_agreed_at=offline_agreed_at,
            offline_agreement_reference=offline_agreement_reference,
            notes=notes,
            created_by_id=created_by_id,
            payout_policy=payout_policy,
        )


def reject_fund_application(
    *,
    tenant_id: int,
    fund_id: int,
    application_id: int,
    decided_by_id: int | None = None,
) -> FundApplication:
    application = FundApplication.objects.select_related('fund').filter(
        pk=application_id,
        tenant_id=tenant_id,
        fund_id=fund_id,
    ).first()
    if application is None:
        raise ValueError('Fund application was not found.')
    if application.status != FundApplication.Status.PENDING:
        raise ValueError('Only pending applications can be rejected.')
    application.status = FundApplication.Status.REJECTED
    application.decided_by_id = decided_by_id
    application.decided_at = timezone.now()
    application.save(update_fields=['status', 'decided_by', 'decided_at', 'updated_at'])
    return application


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
            fund=fund, partner_id=partner_id, status=FundMember.Status.ACTIVE,
        ).first()
        if member is None:
            raise ValueError('Selected partner is not an active member of this fund.')
        if member.approved_amount and money(member.confirmed_amount) + amount > money(member.approved_amount):
            raise ValueError('Contribution exceeds approved member amount.')
        if fund.target_amount is not None and _confirmed_capital(fund) + amount > money(fund.target_amount):
            raise ValueError('Fund hard cap would be exceeded. Amend terms before accepting more capital.')
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
        member.confirmed_amount = money(member.confirmed_amount) + amount
        member.save(update_fields=['confirmed_amount', 'updated_at'])
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
        if FundApplication.objects.filter(fund=fund, status=FundApplication.Status.PENDING).exists():
            raise ValueError('Resolve pending fund applications before deployment.')
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


def exit_fund_member(
    *,
    tenant_id: int,
    fund_id: int,
    partner_id: int,
    reason: str,
    notes: str = '',
    client_request_id=None,
) -> FundMemberExit:
    if reason not in FundMemberExit.Reason.values:
        raise ValueError('Unsupported fund member exit reason.')
    with transaction.atomic():
        if client_request_id:
            existing = FundMemberExit.objects.filter(
                tenant_id=tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing
        fund = InvestmentFund.objects.select_for_update().select_related('capital_account').get(
            pk=fund_id,
            tenant_id=tenant_id,
        )
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Members cannot exit or be removed after fund deployment.')
        member = FundMember.objects.select_for_update().get(
            fund=fund,
            partner_id=partner_id,
            status=FundMember.Status.ACTIVE,
        )
        refund_amount = sum(
            (money(row.amount) for row in FundContribution.objects.filter(fund=fund, member=member, currency=fund.currency)),
            ZERO,
        ) - sum(
            (money(row.refund_amount) for row in FundMemberExit.objects.filter(fund=fund, member=member, currency=fund.currency)),
            ZERO,
        )
        refund_amount = money(max(ZERO, refund_amount))
        refunded_at = timezone.now()
        exit_row = FundMemberExit.objects.create(
            tenant_id=tenant_id,
            fund=fund,
            member=member,
            reason=reason,
            refund_amount=refund_amount,
            currency=fund.currency,
            refunded_at=refunded_at,
            notes=notes,
            client_request_id=client_request_id,
        )
        if refund_amount > ZERO:
            create_cash_entry(
                tenant_id=tenant_id,
                account=fund.capital_account,
                direction=CashEntry.Direction.OUT,
                amount=refund_amount,
                date=refunded_at,
                source_ref_type='fund_member_exit',
                source_ref_id=exit_row.pk,
            )
        member.status = (
            FundMember.Status.EXITED
            if reason == FundMemberExit.Reason.MEMBER_EXIT
            else FundMember.Status.REMOVED
        )
        member.confirmed_amount = ZERO
        member.exited_at = exit_row.refunded_at
        member.save(update_fields=['status', 'confirmed_amount', 'exited_at', 'updated_at'])
        rebuild_fund_member_positions(fund)
    return exit_row


def rebuild_fund_member_positions(fund: InvestmentFund) -> None:
    """Fold fund contributions and E18 holder positions into member-facing rows."""
    members = list(FundMember.objects.filter(fund=fund, status=FundMember.Status.ACTIVE).select_related('partner'))
    currency = str(fund.currency or 'UZS').upper()
    paid_by_member = {
        member.pk: money(sum(
            (money(row.amount) for row in FundContribution.objects.filter(fund=fund, member=member, currency=currency)),
            ZERO,
        ) - sum(
            (money(row.refund_amount) for row in FundMemberExit.objects.filter(fund=fund, member=member, currency=currency)),
            ZERO,
        ))
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
    external_available = max(ZERO, sum((money(row.available) for row in agreement_rows), ZERO))
    venture_rows = PartnerPositionReadModel.objects.filter(
        tenant_id=fund.tenant_id,
        agreement__fund_deployments__fund=fund,
        partner_id=fund.holder_partner_id,
        procurement__isnull=False,
        currency='UZS',
    ).distinct()
    gross_profit = sum((money(row.provisional_profit_uzs) for row in venture_rows), ZERO)
    gross_capital_available = sum(
        (
            money(row.capital_return_available_uzs)
            + money(row.capital_returned_uzs)
            for row in venture_rows
        ),
        ZERO,
    )
    capital_paid_by_partner: dict[int, Decimal] = {}
    for row in PayoutObligation.objects.filter(
        fund=fund,
        kind=PayoutObligation.Kind.CAPITAL_RETURN,
    ).values('recipient_id', 'paid_amount'):
        partner_id = int(row['recipient_id'])
        capital_paid_by_partner[partner_id] = money(
            capital_paid_by_partner.get(partner_id, ZERO) + money(row['paid_amount'])
        )
    profit_available = sum((money(row.provisional_profit_available_uzs) for row in venture_rows), ZERO)
    manager_share = Decimal(str(getattr(fund.current_terms, 'manager_profit_share', ZERO)))
    manager_fee = money(max(ZERO, profit_available) * manager_share)
    distributable_profit = money(max(ZERO, profit_available) - manager_fee)
    capital_available_by_member: dict[int, Decimal] = {}
    for member in members:
        share = ratio(paid_by_member[member.pk] / total_paid) if total_paid > ZERO else ZERO
        gross_member_capital = money(gross_capital_available * share)
        paid_to_member = capital_paid_by_partner.get(member.partner_id, ZERO)
        capital_available_by_member[member.pk] = max(ZERO, money(gross_member_capital - paid_to_member))
    capital_available = sum(capital_available_by_member.values(), ZERO)
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
                'capital_return_available_uzs': capital_available_by_member.get(member.pk, ZERO),
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
