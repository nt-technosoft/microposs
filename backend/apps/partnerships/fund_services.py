"""Investor-owned closed-fund services.

Fundraising is owned by investor profiles and remains off the business GL until
the fund is deployed into a concrete investment agreement. At deployment the
business still sees one synthetic investor holder, so existing E11/E18 cash,
tags and FIFO economics stay the only source of agreement money truth.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.models import BusinessInvestorRelation, InvestmentProfile, Partner
from apps.core.services import get_or_create_investment_profile

from .models import (
    AgreementPartner,
    CapitalCommitment,
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
from .money_utils import ZERO, money, ratio


def create_investment_fund(
    *,
    tenant_id: int | None = None,
    name: str,
    manager_profile_id: int | None = None,
    manager_partner_id: int | None = None,
    member_profile_ids: list[int] | None = None,
    member_partner_ids: list[int] | None = None,
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
    """Create a raisable fund owned by an investor profile."""
    currency = str(currency or 'UZS').upper()
    manager_profit_share = ratio(manager_profit_share)
    if not name.strip():
        raise ValueError('Fund name is required.')
    if not Decimal('0') <= manager_profit_share <= Decimal('1'):
        raise ValueError('manager_profit_share must be in [0, 1].')
    member_profile_ids = member_profile_ids or []
    member_partner_ids = member_partner_ids or []
    member_profile_ids = sorted({int(item) for item in member_profile_ids})
    legacy_member_partner_ids = sorted({int(item) for item in member_partner_ids})
    min_contribution_amount = money(min_contribution_amount)
    if target_amount is not None and money(target_amount) <= ZERO:
        raise ValueError('target_amount must be positive when provided.')
    if min_contribution_amount < ZERO:
        raise ValueError('min_contribution_amount cannot be negative.')
    if visibility not in InvestmentFund.Visibility.values:
        raise ValueError('Unsupported fund visibility.')
    if tenant_id is None and review_at is not None:
        raise ValueError('Fund review date requires a business tenant; set review terms after deployment.')

    with transaction.atomic():
        manager_partner = None
        if manager_partner_id is not None:
            manager_query = Partner.objects.select_for_update().filter(pk=manager_partner_id, is_active=True)
            if tenant_id is not None:
                manager_query = manager_query.filter(tenant_id=tenant_id)
            manager_partner = manager_query.first()
            if manager_partner is None:
                raise ValueError('Fund manager is not an active business partner.')
            if manager_partner.user_id and manager_profile_id is None:
                manager_profile = get_or_create_investment_profile(
                    manager_partner.user,
                    manager_partner.display_name,
                )
            else:
                manager_profile = None
        else:
            manager_profile = None
        if manager_profile_id is not None:
            manager_profile = InvestmentProfile.objects.select_for_update().filter(
                pk=manager_profile_id,
                is_active=True,
            ).first()
        if manager_profile is None:
            raise ValueError('Fund manager investment profile is required.')

        holder = None
        if tenant_id is not None and manager_partner is not None:
            holder = Partner.objects.create(
                tenant_id=tenant_id,
                role=Partner.Role.INVESTOR,
                display_name=f'Фонд: {name.strip()}',
                is_active=True,
            )
            BusinessInvestorRelation.objects.create(
                tenant_id=tenant_id,
                partner=holder,
                status=BusinessInvestorRelation.Status.ACTIVE,
                source=BusinessInvestorRelation.Source.MANUAL,
                created_by_id=created_by_id,
                notes='system_fund_holder',
            )

        member_profiles = list(InvestmentProfile.objects.filter(
            pk__in=member_profile_ids,
            is_active=True,
        ))
        if len(member_profiles) != len(member_profile_ids):
            raise ValueError('Every fund member must be an active investment profile.')

        legacy_members = []
        if legacy_member_partner_ids:
            legacy_query = Partner.objects.filter(pk__in=legacy_member_partner_ids, is_active=True)
            if tenant_id is not None:
                legacy_query = legacy_query.filter(tenant_id=tenant_id)
            legacy_members = list(legacy_query)
            if len(legacy_members) != len(legacy_member_partner_ids):
                raise ValueError('Every fund member must be an active business partner.')

        now = timezone.now()
        fund = InvestmentFund.objects.create(
            tenant_id=tenant_id,
            name=name.strip(),
            manager_profile=manager_profile,
            manager_partner=manager_partner,
            holder_partner=holder,
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
                profile=profile,
                joined_at=now,
                offline_agreed_at=offline_agreed_at,
                offline_agreement_reference=offline_agreement_reference,
            )
            for profile in member_profiles
        ] + [
            FundMember(
                tenant_id=tenant_id,
                fund=fund,
                partner=member,
                profile=get_or_create_investment_profile(member.user, member.display_name) if member.user_id else None,
                joined_at=now,
                offline_agreed_at=offline_agreed_at,
                offline_agreement_reference=offline_agreement_reference,
            )
            for member in legacy_members
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
                'manager_profile_id': manager_profile.pk,
                'manager_partner_id': manager_partner.pk if manager_partner else None,
                'manager_profit_share': str(manager_profit_share),
                'member_profiles': [profile.pk for profile in member_profiles],
                'legacy_member_partners': legacy_member_partner_ids,
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
    tenant_id: int | None = None,
    fund_id: int,
    profile_id: int | None = None,
    partner_id: int | None = None,
    requested_amount: Decimal,
    message: str = '',
) -> FundApplication:
    requested_amount = money(requested_amount)
    if requested_amount <= ZERO:
        raise ValueError('Requested amount must be > 0.')
    with transaction.atomic():
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fund is not accepting applications.')
        if requested_amount < money(fund.min_contribution_amount):
            raise ValueError('Requested amount is below fund minimum contribution.')
        profile = None
        partner = None
        if profile_id is not None:
            profile = InvestmentProfile.objects.filter(pk=profile_id, is_active=True).first()
            if profile is None:
                raise ValueError('Fund application profile was not found.')
            if FundMember.objects.filter(fund=fund, profile=profile, status=FundMember.Status.ACTIVE).exists():
                raise ValueError('Investor profile is already an active fund member.')
        elif partner_id is not None:
            partner_query = Partner.objects.filter(pk=partner_id, is_active=True)
            if tenant_id is not None:
                partner_query = partner_query.filter(tenant_id=tenant_id)
            partner = partner_query.first()
            if partner is None:
                raise ValueError('Fund application partner was not found.')
            if partner.user_id:
                profile = get_or_create_investment_profile(partner.user, partner.display_name)
            if FundMember.objects.filter(fund=fund, partner=partner, status=FundMember.Status.ACTIVE).exists():
                raise ValueError('Partner is already an active fund member.')
        else:
            raise ValueError('Fund application profile is required.')

        lookup = {'fund': fund, 'status': FundApplication.Status.PENDING}
        if profile is not None:
            lookup['profile'] = profile
        else:
            lookup['partner'] = partner
        application, created = FundApplication.objects.get_or_create(
            **lookup,
            defaults={
                'tenant_id': fund.tenant_id,
                'partner': partner,
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
    tenant_id: int | None = None,
    fund_id: int,
    application_id: int,
    approved_amount: Decimal | None = None,
    decided_by_id: int | None = None,
) -> FundApplication:
    with transaction.atomic():
        application = FundApplication.objects.select_for_update().filter(
            pk=application_id,
            fund_id=fund_id,
        ).first()
        if application is None:
            raise ValueError('Fund application was not found.')
        if application.status != FundApplication.Status.PENDING:
            raise ValueError('Only pending applications can be approved.')
        fund = InvestmentFund.objects.select_for_update().get(pk=application.fund_id)
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
        member_lookup = {'fund': fund}
        if application.profile_id:
            member_lookup['profile'] = application.profile
        else:
            member_lookup['partner'] = application.partner
        FundMember.objects.update_or_create(
            **member_lookup,
            defaults={
                'tenant_id': fund.tenant_id,
                'partner': application.partner,
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
    tenant_id: int | None = None,
    fund_id: int,
    approvals: list[dict],
) -> dict:
    """Preview approval batch without changing application/member state."""
    fund = InvestmentFund.objects.get(pk=fund_id)
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
        application = FundApplication.objects.select_related('partner', 'profile').filter(
            pk=int(item['application_id']),
            fund=fund,
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
            'profile_id': application.profile_id,
            'partner_name': application.profile.display_name if application.profile_id else application.partner.display_name,
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
    tenant_id: int | None = None,
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
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fundraising terms cannot be changed after deployment.')
        if fund.tenant_id is None and review_at is not None:
            raise ValueError('Fund review date requires a business tenant; set review terms after deployment.')
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
    tenant_id: int | None = None,
    fund_id: int,
    application_id: int,
    decided_by_id: int | None = None,
) -> FundApplication:
    application = FundApplication.objects.select_related('fund').filter(
        pk=application_id,
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
    tenant_id: int | None = None,
    fund_id: int,
    profile_id: int | None = None,
    partner_id: int | None = None,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal | None = None,
    date=None,
    notes: str = '',
    client_request_id=None,
) -> FundContribution:
    """Record confirmed member capital before deployment.

    This is a fund-side offline fact. It does not create business GL/cash rows;
    business accounting starts only when the fund deploys into an agreement.
    """
    amount = money(amount)
    currency = str(currency or 'UZS').upper()
    if amount <= ZERO:
        raise ValueError('Fund contribution amount must be > 0.')
    date = date or timezone.now()
    with transaction.atomic():
        if client_request_id:
            existing = FundContribution.objects.filter(
                fund_id=fund_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return existing
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Fund is closed for new capital after its first deployment.')
        if currency != str(fund.currency).upper():
            raise ValueError('Fund contribution currency must match fund currency.')
        member_query = FundMember.objects.select_related('partner', 'profile').filter(
            fund=fund,
            status=FundMember.Status.ACTIVE,
        )
        if profile_id is not None:
            member_query = member_query.filter(profile_id=profile_id)
        elif partner_id is not None:
            member_query = member_query.filter(partner_id=partner_id)
        else:
            raise ValueError('Fund contribution profile is required.')
        member = member_query.first()
        if member is None:
            raise ValueError('Selected partner is not an active member of this fund.')
        if member.approved_amount and money(member.confirmed_amount) + amount > money(member.approved_amount):
            raise ValueError('Contribution exceeds approved member amount.')
        if fund.target_amount is not None and _confirmed_capital(fund) + amount > money(fund.target_amount):
            raise ValueError('Fund hard cap would be exceeded. Amend terms before accepting more capital.')
        contribution = FundContribution.objects.create(
            tenant_id=fund.tenant_id,
            fund=fund,
            member=member,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate or Decimal('1'),
            date=date,
            notes=notes,
            client_request_id=client_request_id,
        )
        member.confirmed_amount = money(member.confirmed_amount) + amount
        member.save(update_fields=['confirmed_amount', 'updated_at'])
        rebuild_fund_member_positions(fund)
    return contribution


def ensure_fund_holder_partner(
    *,
    fund: InvestmentFund,
    tenant_id: int,
    created_by_id: int | None = None,
) -> Partner:
    """Create or reuse the business-side synthetic investor for this fund."""
    if fund.holder_partner_id and fund.holder_partner.tenant_id == tenant_id:
        return fund.holder_partner
    holder = Partner.objects.create(
        tenant_id=tenant_id,
        role=Partner.Role.INVESTOR,
        display_name=f'Фонд: {fund.name}',
        is_active=True,
    )
    BusinessInvestorRelation.objects.get_or_create(
        tenant_id=tenant_id,
        partner=holder,
        defaults={
            'status': BusinessInvestorRelation.Status.ACTIVE,
            'source': BusinessInvestorRelation.Source.MANUAL,
            'created_by_id': created_by_id,
            'notes': 'system_fund_holder',
        },
    )
    fund.holder_partner = holder
    if fund.tenant_id is None:
        fund.tenant_id = tenant_id
    fund.save(update_fields=['holder_partner', 'tenant', 'updated_at'])
    return holder


def _ensure_fund_agreement_party(
    *,
    agreement: InvestmentAgreement,
    fund: InvestmentFund,
    holder: Partner,
    tenant_id: int,
    created_by_id: int | None,
) -> AgreementPartner:
    existing = AgreementPartner.objects.filter(
        agreement=agreement,
        partner_id=holder.pk,
        role=AgreementPartner.Role.INVESTOR,
    ).first()
    if existing is not None:
        return existing

    candidates = list(AgreementPartner.objects.select_for_update().filter(
        agreement=agreement,
        role=AgreementPartner.Role.INVESTOR,
    ))
    if len(candidates) != 1:
        raise ValueError('Add this fund as one negotiated INVESTOR party before deployment.')

    placeholder = candidates[0]
    if agreement.contributions.filter(partner_id=placeholder.partner_id).exists():
        raise ValueError('Cannot replace an investor that already has agreement contributions.')

    placeholder_partner_id = placeholder.partner_id
    placeholder.partner = holder
    placeholder.save(update_fields=['partner', 'updated_at'])
    CapitalCommitment.objects.filter(
        agreement=agreement,
        partner_id=placeholder_partner_id,
    ).update(partner_id=holder.pk)

    from .lifecycle_services import create_agreement_terms_version

    create_agreement_terms_version(
        agreement=agreement,
        notes=f'Fund holder linked for deployment: fund_id={fund.pk}',
        created_by_id=created_by_id,
    )
    return placeholder


def deploy_fund_to_agreement(
    *,
    tenant_id: int,
    fund_id: int,
    agreement_id: int,
    amount: Decimal,
    date=None,
    notes: str = '',
    client_request_id=None,
    created_by_id: int | None = None,
) -> FundDeployment:
    """Deploy confirmed fund capital into a business agreement."""
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
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id)
        if fund.status not in {InvestmentFund.Status.RAISING, InvestmentFund.Status.DEPLOYED}:
            raise ValueError('Only an open fund can make a deployment.')
        if FundApplication.objects.filter(fund=fund, status=FundApplication.Status.PENDING).exists():
            raise ValueError('Resolve pending fund applications before deployment.')
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id, tenant_id=tenant_id,
        )
        if str(fund.currency).upper() != str(agreement.currency).upper():
            raise ValueError('Fund and agreement currencies must match in MVP.')
        deployed_total = sum(
            (money(row.amount) for row in FundDeployment.objects.filter(fund=fund, currency=fund.currency)),
            ZERO,
        )
        if _confirmed_capital(fund) - deployed_total < amount:
            raise ValueError('Fund confirmed capital is insufficient for this deployment.')
        holder = ensure_fund_holder_partner(
            fund=fund,
            tenant_id=tenant_id,
            created_by_id=created_by_id,
        )
        _ensure_fund_agreement_party(
            agreement=agreement,
            fund=fund,
            holder=holder,
            tenant_id=tenant_id,
            created_by_id=created_by_id,
        )
        contribution = add_agreement_contribution(
            tenant_id=tenant_id,
            agreement_id=agreement.pk,
            partner_id=holder.pk,
            amount=amount,
            currency=fund.currency,
            fx_rate=Decimal('1'),
            date=date,
            notes=f'fund_deployment:{fund.pk} {notes}'.strip(),
            client_request_id=client_request_id,
            created_by_id=created_by_id,
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
    tenant_id: int | None = None,
    fund_id: int,
    profile_id: int | None = None,
    partner_id: int | None = None,
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
        fund = InvestmentFund.objects.select_for_update().get(pk=fund_id)
        if fund.status != InvestmentFund.Status.RAISING:
            raise ValueError('Members cannot exit or be removed after fund deployment.')
        member_query = FundMember.objects.select_for_update().filter(
            fund=fund,
            status=FundMember.Status.ACTIVE,
        )
        if profile_id is not None:
            member_query = member_query.filter(profile_id=profile_id)
        elif partner_id is not None:
            member_query = member_query.filter(partner_id=partner_id)
        else:
            raise ValueError('Fund member profile is required.')
        member = member_query.get()
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
            tenant_id=fund.tenant_id,
            fund=fund,
            member=member,
            reason=reason,
            refund_amount=refund_amount,
            currency=fund.currency,
            refunded_at=refunded_at,
            notes=notes,
            client_request_id=client_request_id,
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
    members = list(FundMember.objects.filter(fund=fund, status=FundMember.Status.ACTIVE).select_related('partner', 'profile'))
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
    venture_rows = PartnerPositionReadModel.objects.none()
    if fund.holder_partner_id:
        venture_rows = PartnerPositionReadModel.objects.filter(
            agreement__fund_deployments__fund=fund,
            partner_id=fund.holder_partner_id,
            procurement__isnull=False,
            currency='UZS',
        ).distinct()
    external_available = max(ZERO, money(total_paid - total_deployed))
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
    capital_paid_by_profile: dict[int, Decimal] = {}
    for row in PayoutObligation.objects.filter(
        fund=fund,
        kind=PayoutObligation.Kind.CAPITAL_RETURN,
    ).values('recipient_id', 'recipient_profile_id', 'paid_amount'):
        if row['recipient_id']:
            partner_id = int(row['recipient_id'])
            capital_paid_by_partner[partner_id] = money(
                capital_paid_by_partner.get(partner_id, ZERO) + money(row['paid_amount'])
            )
        elif row['recipient_profile_id']:
            profile_id = int(row['recipient_profile_id'])
            capital_paid_by_profile[profile_id] = money(
                capital_paid_by_profile.get(profile_id, ZERO) + money(row['paid_amount'])
            )
    profit_available = sum((money(row.provisional_profit_available_uzs) for row in venture_rows), ZERO)
    manager_share = Decimal(str(getattr(fund.current_terms, 'manager_profit_share', ZERO)))
    manager_fee = money(max(ZERO, profit_available) * manager_share)
    distributable_profit = money(max(ZERO, profit_available) - manager_fee)
    capital_available_by_member: dict[int, Decimal] = {}
    for member in members:
        share = ratio(paid_by_member[member.pk] / total_paid) if total_paid > ZERO else ZERO
        gross_member_capital = money(gross_capital_available * share)
        paid_to_member = (
            capital_paid_by_partner.get(member.partner_id, ZERO)
            if member.partner_id
            else capital_paid_by_profile.get(member.profile_id, ZERO)
        )
        capital_available_by_member[member.pk] = max(ZERO, money(gross_member_capital - paid_to_member))
    capital_available = sum(capital_available_by_member.values(), ZERO)
    now = timezone.now()
    FundPositionReadModel.all_objects.update_or_create(
        fund=fund,
        defaults={
            'tenant_id': fund.tenant_id,
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
        member_fee = manager_fee if (
            member.profile_id and member.profile_id == fund.manager_profile_id
        ) or (
            member.partner_id and member.partner_id == fund.manager_partner_id
        ) else ZERO
        row, _ = FundMemberPositionReadModel.all_objects.update_or_create(
            fund=fund,
            member=member,
            currency=currency,
            defaults={
                'tenant_id': fund.tenant_id,
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
    stale = FundMemberPositionReadModel.all_objects.filter(fund=fund)
    if keep_ids:
        stale = stale.exclude(pk__in=keep_ids)
    stale.delete()


def rebuild_fund_positions_for_agreement(agreement: InvestmentAgreement) -> None:
    for fund in InvestmentFund.objects.filter(
        tenant_id=agreement.tenant_id,
        deployments__agreement=agreement,
    ).distinct():
        rebuild_fund_member_positions(fund)
