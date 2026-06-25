"""E20 terms, payout, review and dispute lifecycle services.

Eligibility is automated; money is not. A policy creates a transparent due
obligation, while the existing capital/dividend services remain responsible for
recording a real direct-agreement payment.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.services import publish_event

from .models import (
    AgreementTermsVersion,
    ContractReview,
    DisputeCase,
    FundMemberPositionReadModel,
    FundPositionReadModel,
    FundTermsVersion,
    InvestmentAgreement,
    InvestmentFund,
    PartnerPositionReadModel,
    PayoutObligation,
    PayoutPolicy,
    PayoutSettlement,
)
from .money_utils import ZERO, money


def _agreement_terms_snapshot(agreement: InvestmentAgreement) -> dict:
    """Capture the legal/economic inputs; future UI changes cannot rewrite terms."""
    return {
        'legal_mode': agreement.legal_mode,
        'reconciliation_mode': agreement.reconciliation_mode,
        'loss_rule': agreement.loss_rule,
        'mudaraba_ratio': str(agreement.mudaraba_ratio),
        'planned_budget': str(agreement.planned_budget),
        'currency': str(agreement.currency or 'UZS').upper(),
        'parties': [
            {
                'partner_id': row.partner_id,
                'role': row.role,
                'planned_capital_share': str(row.planned_capital_share),
                'profit_share': str(row.profit_share),
            }
            for row in agreement.partners.order_by('role', 'partner_id')
        ],
    }


def _fund_terms_snapshot(fund: InvestmentFund, manager_profit_share: Decimal) -> dict:
    return {
        'name': fund.name,
        'currency': str(fund.currency or 'UZS').upper(),
        'target_amount': str(fund.target_amount) if fund.target_amount is not None else None,
        'manager_partner_id': fund.manager_partner_id,
        'manager_profit_share': str(manager_profit_share),
        'members': sorted(row.partner_id for row in fund.members.all()),
        'waterfall': ['capital_return', 'net_profit', 'manager_fee'],
    }


def _policy_values(previous: PayoutPolicy | None, override: dict | None) -> dict:
    """An amendment inherits the active policy unless a field is explicitly changed."""
    values = {
        'review_interval_days': 30,
        'minimum_available_amount': ZERO,
        'minimum_days_between_payouts': 30,
        'reserve_amount': ZERO,
        'grace_period_days': 0,
        'allow_partial': True,
    }
    if previous is not None:
        values.update({
            'review_interval_days': previous.review_interval_days,
            'minimum_available_amount': previous.minimum_available_amount,
            'minimum_days_between_payouts': previous.minimum_days_between_payouts,
            'reserve_amount': previous.reserve_amount,
            'grace_period_days': previous.grace_period_days,
            'allow_partial': previous.allow_partial,
        })
    values.update(override or {})
    return values


def create_agreement_terms_version(
    *,
    agreement: InvestmentAgreement,
    review_at=None,
    offline_agreed_at=None,
    offline_agreement_reference: str = '',
    notes: str = '',
    created_by_id: int | None = None,
    payout_policy: dict | None = None,
) -> AgreementTermsVersion:
    """Append a forward-only terms version and make it current."""
    with transaction.atomic():
        locked = InvestmentAgreement.objects.select_for_update().get(pk=agreement.pk)
        next_version = (locked.terms_versions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
        previous = locked.current_terms
        terms = AgreementTermsVersion.objects.create(
            tenant_id=locked.tenant_id,
            agreement=locked,
            version=next_version,
            effective_at=timezone.now(),
            review_at=review_at,
            offline_agreed_at=offline_agreed_at,
            offline_agreement_reference=offline_agreement_reference,
            terms_snapshot=_agreement_terms_snapshot(locked),
            notes=notes,
            created_by_id=created_by_id,
        )
        policy_values = _policy_values(
            getattr(previous, 'payout_policy', None) if previous else None,
            payout_policy,
        )
        PayoutPolicy.objects.create(
            tenant_id=locked.tenant_id,
            agreement_terms=terms,
            review_interval_days=int(policy_values.get('review_interval_days', 30)),
            minimum_available_amount=money(policy_values.get('minimum_available_amount', ZERO)),
            minimum_days_between_payouts=int(policy_values.get('minimum_days_between_payouts', 30)),
            reserve_amount=money(policy_values.get('reserve_amount', ZERO)),
            grace_period_days=int(policy_values.get('grace_period_days', 0)),
            allow_partial=bool(policy_values.get('allow_partial', True)),
        )
        locked.current_terms = terms
        locked.save(update_fields=['current_terms', 'updated_at'])
        # Keep the caller's newly-created agreement coherent without requiring
        # every service caller to reload it before serialisation.
        agreement.current_terms = terms
    return terms


def create_fund_terms_version(
    *,
    fund: InvestmentFund,
    review_at=None,
    manager_profit_share=None,
    offline_agreed_at=None,
    offline_agreement_reference: str = '',
    notes: str = '',
    created_by_id: int | None = None,
    payout_policy: dict | None = None,
) -> FundTermsVersion:
    with transaction.atomic():
        locked = InvestmentFund.objects.select_for_update().get(pk=fund.pk)
        previous = locked.current_terms
        share = Decimal(str(manager_profit_share)) if manager_profit_share is not None else Decimal(str(getattr(previous, 'manager_profit_share', ZERO)))
        if not ZERO <= share <= Decimal('1'):
            raise ValueError('manager_profit_share must be in [0, 1].')
        next_version = (locked.terms_versions.order_by('-version').values_list('version', flat=True).first() or 0) + 1
        terms = FundTermsVersion.objects.create(
            tenant_id=locked.tenant_id,
            fund=locked,
            version=next_version,
            effective_at=timezone.now(),
            review_at=review_at,
            manager_profit_share=share,
            offline_agreed_at=offline_agreed_at,
            offline_agreement_reference=offline_agreement_reference,
            terms_snapshot=_fund_terms_snapshot(locked, share),
            notes=notes,
            created_by_id=created_by_id,
        )
        values = _policy_values(
            getattr(previous, 'payout_policy', None) if previous else None,
            payout_policy,
        )
        PayoutPolicy.objects.create(
            tenant_id=locked.tenant_id,
            fund_terms=terms,
            review_interval_days=int(values.get('review_interval_days', 30)),
            minimum_available_amount=money(values.get('minimum_available_amount', ZERO)),
            minimum_days_between_payouts=int(values.get('minimum_days_between_payouts', 30)),
            reserve_amount=money(values.get('reserve_amount', ZERO)),
            grace_period_days=int(values.get('grace_period_days', 0)),
            allow_partial=bool(values.get('allow_partial', True)),
        )
        locked.current_terms = terms
        locked.save(update_fields=['current_terms', 'updated_at'])
        fund.current_terms = terms
    return terms


def _policy_for_agreement(agreement: InvestmentAgreement) -> PayoutPolicy | None:
    if not agreement.current_terms_id:
        return None
    return getattr(agreement.current_terms, 'payout_policy', None)


def _policy_for_fund(fund: InvestmentFund) -> PayoutPolicy | None:
    if not fund.current_terms_id:
        return None
    return getattr(fund.current_terms, 'payout_policy', None)


def _eligible_after_policy(*, amount: Decimal, policy: PayoutPolicy) -> Decimal:
    eligible = money(amount - Decimal(str(policy.reserve_amount)))
    if eligible < Decimal(str(policy.minimum_available_amount)):
        return ZERO
    return max(ZERO, eligible)


def _may_open_next_obligation(*, queryset, now, policy: PayoutPolicy) -> bool:
    if queryset.filter(status__in=[
        PayoutObligation.Status.PENDING,
        PayoutObligation.Status.RECORDED,
        PayoutObligation.Status.DISPUTED,
    ]).exists():
        return False
    previous = queryset.filter(status=PayoutObligation.Status.CONFIRMED).order_by('-confirmed_at').first()
    if previous and previous.confirmed_at:
        return now >= previous.confirmed_at + timedelta(days=policy.minimum_days_between_payouts)
    return True


def _create_payout_obligation_if_absent(**values) -> tuple[PayoutObligation | None, bool]:
    """Race-safe create under the partial active-obligation unique constraints."""
    agreement_id = values.get('agreement_id') or getattr(values.get('agreement'), 'pk', None)
    fund_id = values.get('fund_id') or getattr(values.get('fund'), 'pk', None)
    owner_filter = {'agreement_id': agreement_id} if agreement_id else {'fund_id': fund_id}
    filters = {
        **owner_filter,
        'recipient_id': values['recipient_id'],
        'kind': values['kind'],
        'status__in': [
            PayoutObligation.Status.PENDING,
            PayoutObligation.Status.RECORDED,
            PayoutObligation.Status.DISPUTED,
        ],
    }
    if agreement_id:
        filters['procurement_id'] = values.get('procurement_id')
    try:
        with transaction.atomic():
            return PayoutObligation.objects.create(**values), True
    except IntegrityError:
        return PayoutObligation.objects.filter(**filters).first(), False


def _policy_evaluation_due(*, policy: PayoutPolicy, effective_at, available_amounts: list[Decimal], now) -> bool:
    """A positive configured threshold can trigger early; otherwise use cadence."""
    threshold = Decimal(str(policy.minimum_available_amount))
    if threshold > ZERO and any(amount >= threshold for amount in available_amounts):
        return True
    baseline = policy.last_evaluated_at or effective_at
    return now >= baseline + timedelta(days=policy.review_interval_days)


def evaluate_agreement_payout_obligations(*, agreement: InvestmentAgreement, now=None) -> list[PayoutObligation]:
    """Create due profit/capital actions from E18 venture rows, without paying."""
    now = now or timezone.now()
    agreement = InvestmentAgreement.objects.select_related('current_terms').get(pk=agreement.pk)
    policy = _policy_for_agreement(agreement)
    if policy is None:
        return []
    created: list[PayoutObligation] = []
    with transaction.atomic():
        policy = PayoutPolicy.objects.select_for_update().get(pk=policy.pk)
        rows = PartnerPositionReadModel.objects.filter(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            procurement__isnull=False,
            currency='UZS',
        )
        values = [
            Decimal(str(row.provisional_profit_available_uzs))
            for row in rows
        ] + [
            Decimal(str(row.capital_return_available_uzs))
            for row in rows
        ]
        if not _policy_evaluation_due(
            policy=policy,
            effective_at=agreement.current_terms.effective_at,
            available_amounts=values,
            now=now,
        ):
            return []
        for row in rows:
            for kind, available in (
                (PayoutObligation.Kind.PROFIT, Decimal(str(row.provisional_profit_available_uzs))),
                (PayoutObligation.Kind.CAPITAL_RETURN, Decimal(str(row.capital_return_available_uzs))),
            ):
                amount = _eligible_after_policy(amount=available, policy=policy)
                if amount <= ZERO:
                    continue
                existing = PayoutObligation.objects.filter(
                    agreement=agreement,
                    recipient_id=row.partner_id,
                    procurement_id=row.procurement_id,
                    kind=kind,
                )
                if not _may_open_next_obligation(queryset=existing, now=now, policy=policy):
                    continue
                obligation, was_created = _create_payout_obligation_if_absent(
                    tenant_id=agreement.tenant_id,
                    agreement=agreement,
                    recipient_id=row.partner_id,
                    procurement_id=row.procurement_id,
                    kind=kind,
                    amount=amount,
                    currency='UZS',
                    due_at=now + timedelta(days=policy.grace_period_days),
                    notes='Created from payout policy eligibility.',
                )
                if not was_created:
                    continue
                created.append(obligation)
                publish_event(
                    event_type='partnership.payout_obligation_due',
                    payload={'agreement_id': agreement.pk, 'obligation_id': obligation.pk, 'kind': kind},
                    tenant_id=agreement.tenant_id,
                )
        policy.last_evaluated_at = now
        policy.save(update_fields=['last_evaluated_at', 'updated_at'])
    return created


def evaluate_fund_payout_obligations(*, fund: InvestmentFund, now=None) -> list[PayoutObligation]:
    """Create member-facing fund payout actions from the materialized fund view."""
    now = now or timezone.now()
    fund = InvestmentFund.objects.select_related('current_terms').get(pk=fund.pk)
    policy = _policy_for_fund(fund)
    if policy is None:
        return []
    created: list[PayoutObligation] = []
    with transaction.atomic():
        policy = PayoutPolicy.objects.select_for_update().get(pk=policy.pk)
        rows = FundMemberPositionReadModel.objects.filter(fund=fund, currency=fund.currency).select_related('member')
        values = [
            Decimal(str(row.profit_available_uzs))
            for row in rows
        ] + [
            Decimal(str(row.capital_return_available_uzs))
            for row in rows
        ]
        fund_position = FundPositionReadModel.objects.filter(fund=fund).first()
        values.append(Decimal(str(getattr(fund_position, 'manager_fee_accrued_uzs', ZERO))))
        if not _policy_evaluation_due(
            policy=policy,
            effective_at=fund.current_terms.effective_at,
            available_amounts=values,
            now=now,
        ):
            return []
        for row in rows:
            for kind, available in (
                (PayoutObligation.Kind.PROFIT, Decimal(str(row.profit_available_uzs))),
                (PayoutObligation.Kind.CAPITAL_RETURN, Decimal(str(row.capital_return_available_uzs))),
            ):
                amount = _eligible_after_policy(amount=available, policy=policy)
                if amount <= ZERO:
                    continue
                existing = PayoutObligation.objects.filter(
                    fund=fund, recipient_id=row.member.partner_id, kind=kind,
                )
                if not _may_open_next_obligation(queryset=existing, now=now, policy=policy):
                    continue
                obligation, was_created = _create_payout_obligation_if_absent(
                    tenant_id=fund.tenant_id,
                    fund=fund,
                    recipient_id=row.member.partner_id,
                    kind=kind,
                    amount=amount,
                    currency='UZS',
                    due_at=now + timedelta(days=policy.grace_period_days),
                    notes='Created from fund payout policy eligibility.',
                )
                if not was_created:
                    continue
                created.append(obligation)
                publish_event(
                    event_type='partnership.fund_payout_obligation_due',
                    payload={'fund_id': fund.pk, 'obligation_id': obligation.pk, 'kind': kind},
                    tenant_id=fund.tenant_id,
                )
        # A manager outside the member pool still receives a disclosed fee.
        # Member-managers already receive this fee in their member position.
        manager_is_member = FundMemberPositionReadModel.objects.filter(
            fund=fund,
            member__partner_id=fund.manager_partner_id,
        ).exists()
        manager_fee = Decimal(str(getattr(fund_position, 'manager_fee_accrued_uzs', ZERO)))
        if not manager_is_member and manager_fee > ZERO:
            existing = PayoutObligation.objects.filter(
                fund=fund,
                recipient_id=fund.manager_partner_id,
                kind=PayoutObligation.Kind.PROFIT,
            )
            if _may_open_next_obligation(queryset=existing, now=now, policy=policy):
                obligation, was_created = _create_payout_obligation_if_absent(
                    tenant_id=fund.tenant_id,
                    fund=fund,
                    recipient_id=fund.manager_partner_id,
                    kind=PayoutObligation.Kind.PROFIT,
                    amount=manager_fee,
                    currency='UZS',
                    due_at=now + timedelta(days=policy.grace_period_days),
                    notes='Disclosed manager fee from fund waterfall.',
                )
                if was_created:
                    created.append(obligation)
                    publish_event(
                        event_type='partnership.fund_payout_obligation_due',
                        payload={'fund_id': fund.pk, 'obligation_id': obligation.pk, 'kind': 'MANAGER_FEE'},
                        tenant_id=fund.tenant_id,
                    )
        policy.last_evaluated_at = now
        policy.save(update_fields=['last_evaluated_at', 'updated_at'])
    return created


def agreement_has_funding_hold(*, agreement: InvestmentAgreement, now=None) -> bool:
    """Only substantiated overdue agreement claims restrict *new* funding."""
    now = now or timezone.now()
    return DisputeCase.objects.filter(
        agreement=agreement,
        status=DisputeCase.Status.OPEN,
        obligation__status=PayoutObligation.Status.DISPUTED,
        obligation__due_at__lt=now,
    ).exists()


def _policy_for_obligation(obligation: PayoutObligation) -> PayoutPolicy | None:
    if obligation.agreement_id:
        return _policy_for_agreement(obligation.agreement)
    if obligation.fund_id:
        return _policy_for_fund(obligation.fund)
    return None


def record_payout_obligation(
    *,
    obligation: PayoutObligation,
    payment=None,
    withdrawal=None,
    amount=None,
    evidence: str = '',
    notes: str = '',
) -> PayoutObligation:
    """Append a factual payment report; it never fabricates a financial entry.

    A partial report remains pending after recipient confirmation until the
    agreed amount is fully settled. The actual direct-agreement payment is
    linked to its immutable existing record.
    """
    with transaction.atomic():
        # The owner FKs are nullable by design (agreement XOR fund). PostgreSQL
        # cannot lock the nullable side of a select_related outer join.
        locked = PayoutObligation.objects.select_for_update().get(pk=obligation.pk)
        if locked.status not in {PayoutObligation.Status.PENDING, PayoutObligation.Status.DISPUTED}:
            raise ValueError('Only a pending or disputed payout obligation can be recorded.')
        if payment is not None and withdrawal is not None:
            raise ValueError('A payout report can reference only one direct payment.')
        if payment is not None:
            if locked.kind != PayoutObligation.Kind.PROFIT:
                raise ValueError('A capital-return obligation cannot be settled by a dividend payment.')
            if (
                payment.partner_id != locked.recipient_id
                or payment.procurement_id != locked.procurement_id
            ):
                raise ValueError('Dividend payment does not belong to this payout obligation.')
            actual = money(payment.amount)
        elif withdrawal is not None:
            if locked.kind != PayoutObligation.Kind.CAPITAL_RETURN:
                raise ValueError('A profit obligation cannot be settled by a capital withdrawal.')
            if (
                withdrawal.partner_id != locked.recipient_id
                or withdrawal.agreement_id != locked.agreement_id
                or withdrawal.procurement_id != locked.procurement_id
            ):
                raise ValueError('Capital withdrawal does not belong to this payout obligation.')
            actual = money(withdrawal.amount)
        elif locked.fund_id:
            if amount is None:
                raise ValueError('An external fund payout amount is required.')
            actual = money(amount)
        else:
            raise ValueError('A direct agreement obligation needs a recorded dividend or capital withdrawal.')
        if actual <= ZERO:
            raise ValueError('Payout report amount must be positive.')
        remaining = money(Decimal(str(locked.amount)) - Decimal(str(locked.paid_amount)))
        if actual > remaining:
            raise ValueError('Payout report exceeds the remaining obligation amount.')
        policy = _policy_for_obligation(locked)
        if actual < remaining and policy is not None and not policy.allow_partial:
            raise ValueError('This payout policy does not allow partial payments.')
        PayoutSettlement.objects.create(
            tenant_id=locked.tenant_id,
            obligation=locked,
            amount=actual,
            settled_at=timezone.now(),
            evidence=evidence or notes,
            dividend_payment=payment,
            capital_withdrawal=withdrawal,
        )
        if payment is not None and locked.dividend_payment_id is None:
            locked.dividend_payment = payment
        if withdrawal is not None and locked.capital_withdrawal_id is None:
            locked.capital_withdrawal = withdrawal
        locked.paid_amount = money(Decimal(str(locked.paid_amount)) + actual)
        locked.notes = '\n'.join(part for part in [locked.notes, notes] if part)
        locked.status = PayoutObligation.Status.RECORDED
        locked.recorded_at = timezone.now()
        locked.save(update_fields=[
            'dividend_payment', 'capital_withdrawal', 'paid_amount', 'status',
            'recorded_at', 'notes', 'updated_at',
        ])
    return locked


def confirm_payout_obligation(*, obligation: PayoutObligation) -> PayoutObligation:
    with transaction.atomic():
        locked = PayoutObligation.objects.select_for_update().get(pk=obligation.pk)
        if locked.status != PayoutObligation.Status.RECORDED:
            raise ValueError('Only a recorded payout can be confirmed.')
        fully_paid = Decimal(str(locked.paid_amount)) >= Decimal(str(locked.amount))
        locked.status = (
            PayoutObligation.Status.CONFIRMED
            if fully_paid
            else PayoutObligation.Status.PENDING
        )
        locked.confirmed_at = timezone.now() if fully_paid else None
        locked.save(update_fields=['status', 'confirmed_at', 'updated_at'])
    return locked


def open_dispute(*, obligation: PayoutObligation, raised_by_id: int, statement: str, evidence: str = '') -> DisputeCase:
    if not statement.strip():
        raise ValueError('A dispute statement is required.')
    with transaction.atomic():
        locked = PayoutObligation.objects.select_for_update().get(pk=obligation.pk)
        if raised_by_id != locked.recipient_id:
            raise ValueError('Only the payout recipient can open this dispute.')
        if locked.status == PayoutObligation.Status.CONFIRMED:
            raise ValueError('A confirmed payout cannot be disputed through this flow.')
        if locked.disputes.filter(status=DisputeCase.Status.OPEN).exists():
            raise ValueError('This payout already has an open dispute.')
        dispute = DisputeCase.objects.create(
            tenant_id=locked.tenant_id,
            agreement_id=locked.agreement_id,
            fund_id=locked.fund_id,
            obligation=locked,
            raised_by_id=raised_by_id,
            statement=statement.strip(),
            evidence=evidence,
        )
        locked.status = PayoutObligation.Status.DISPUTED
        locked.save(update_fields=['status', 'updated_at'])
    return dispute


def resolve_dispute(*, dispute: DisputeCase, accepted: bool, resolution_notes: str = '') -> DisputeCase:
    with transaction.atomic():
        locked = DisputeCase.objects.select_for_update().select_related('obligation').get(pk=dispute.pk)
        if locked.status != DisputeCase.Status.OPEN:
            raise ValueError('Only an open dispute can be resolved.')
        locked.status = DisputeCase.Status.RESOLVED if accepted else DisputeCase.Status.REJECTED
        locked.resolved_at = timezone.now()
        locked.resolution_notes = resolution_notes
        locked.save(update_fields=['status', 'resolved_at', 'resolution_notes', 'updated_at'])
        if locked.obligation and locked.obligation.status == PayoutObligation.Status.DISPUTED:
            locked.obligation.status = PayoutObligation.Status.PENDING
            locked.obligation.save(update_fields=['status', 'updated_at'])
    return locked


def ensure_contract_review(*, agreement: InvestmentAgreement | None = None, fund: InvestmentFund | None = None, now=None) -> ContractReview | None:
    """Create the review reminder at terms expiry; never auto-close the contract."""
    now = now or timezone.now()
    if bool(agreement) == bool(fund):
        raise ValueError('Provide exactly one agreement or fund.')
    if agreement:
        agreement = InvestmentAgreement.objects.select_related('current_terms').get(pk=agreement.pk)
        terms = agreement.current_terms
    else:
        fund = InvestmentFund.objects.select_related('current_terms').get(pk=fund.pk)
        terms = fund.current_terms
    review_at = getattr(terms, 'review_at', None)
    if review_at is None or review_at > now:
        return None
    owner_filter = {'agreement': agreement} if agreement else {'fund': fund}
    review, _ = ContractReview.objects.get_or_create(
        tenant=(agreement or fund).tenant,
        due_at=review_at,
        defaults=owner_filter,
        **owner_filter,
    )
    return review


def resolve_contract_review(*, review: ContractReview, resolution: str, resolved_by_id: int | None, extension_until=None, notes: str = '') -> ContractReview:
    if resolution not in ContractReview.Resolution.values:
        raise ValueError('Unsupported contract review resolution.')
    with transaction.atomic():
        locked = ContractReview.objects.select_for_update().get(pk=review.pk)
        if locked.resolution:
            raise ValueError('This contract review has already been resolved.')
        locked.resolution = resolution
        locked.resolved_at = timezone.now()
        locked.resolved_by_id = resolved_by_id
        locked.extension_until = extension_until
        locked.notes = notes
        locked.save(update_fields=['resolution', 'resolved_at', 'resolved_by', 'extension_until', 'notes', 'updated_at'])
    return locked
