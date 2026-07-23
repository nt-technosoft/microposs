"""E20 terms, payout, review and dispute lifecycle services.

Eligibility is automated; money is not. A policy creates a transparent due
obligation, while the existing capital/dividend services remain responsible for
recording a real direct-agreement payment.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
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
    AgreementPartner,
    CapitalRollover,
    PartnerPositionReadModel,
    PayoutObligation,
    PayoutDecision,
    PayoutDecisionAllocation,
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
        'min_contribution_amount': str(fund.min_contribution_amount),
        'visibility': fund.visibility,
        'manager_profile_id': fund.manager_profile_id,
        'manager_partner_id': fund.manager_partner_id,
        'manager_profit_share': str(manager_profit_share),
        'member_profiles': sorted(row.profile_id for row in fund.members.all() if row.profile_id),
        'legacy_member_partners': sorted(row.partner_id for row in fund.members.all() if row.partner_id),
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
        'trigger_mode': PayoutPolicy.TriggerMode.ANY,
    }
    if previous is not None:
        values.update({
            'review_interval_days': previous.review_interval_days,
            'minimum_available_amount': previous.minimum_available_amount,
            'minimum_days_between_payouts': previous.minimum_days_between_payouts,
            'reserve_amount': previous.reserve_amount,
            'grace_period_days': previous.grace_period_days,
            'allow_partial': previous.allow_partial,
            'trigger_mode': previous.trigger_mode,
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
            trigger_mode=str(policy_values.get('trigger_mode') or PayoutPolicy.TriggerMode.ANY).upper(),
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
            trigger_mode=str(values.get('trigger_mode') or PayoutPolicy.TriggerMode.ANY).upper(),
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
    recipient_filter = {}
    if values.get('recipient_id') is not None:
        recipient_filter['recipient_id'] = values['recipient_id']
    elif values.get('recipient_profile_id') is not None:
        recipient_filter['recipient_profile_id'] = values['recipient_profile_id']
    else:
        raise ValueError('Payout recipient is required.')
    filters = {
        **owner_filter,
        **recipient_filter,
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
    """Evaluate cadence/threshold at group level.

    ANY keeps the previous default behaviour: a configured threshold can trigger
    early, otherwise cadence opens the review. ALL requires cadence and threshold.
    """
    threshold = Decimal(str(policy.minimum_available_amount))
    baseline = policy.last_evaluated_at or effective_at
    interval_ready = now >= baseline + timedelta(days=policy.review_interval_days)
    total_available = money(sum((money(amount) for amount in available_amounts), ZERO))
    threshold_ready = threshold <= ZERO or total_available >= threshold
    if policy.trigger_mode == PayoutPolicy.TriggerMode.ALL:
        return interval_ready and threshold_ready
    if threshold > ZERO and threshold_ready:
        return True
    return interval_ready


def _decision_key(decision_type: str) -> str:
    if decision_type == PayoutDecision.DecisionType.CAPITALIZE_PROFIT:
        return 'provisional_profit_available_uzs'
    return 'capital_return_available_uzs'


def _decision_rows(*, agreement: InvestmentAgreement, decision_type: str) -> list[dict]:
    members = {
        row.partner_id: row
        for row in agreement.partners.select_related('partner').all()
    }
    key = _decision_key(decision_type)
    rows = []
    for row in (
        PartnerPositionReadModel.objects
        .filter(tenant_id=agreement.tenant_id, agreement=agreement, procurement__isnull=False, currency='UZS')
        .select_related('procurement', 'partner')
        .order_by('procurement_id', 'partner_id')
    ):
        member = members.get(row.partner_id)
        if member is None or member.role == AgreementPartner.Role.OPERATOR:
            continue
        available = money(getattr(row, key, ZERO))
        if available <= ZERO:
            continue
        rows.append({
            'procurement_id': row.procurement_id,
            'partner_id': row.partner_id,
            'partner_name': row.partner.display_name,
            'role': member.role,
            'available_uzs': available,
            'negative_position_uzs': money(row.negative_position_uzs),
        })
    return rows


def _proportional_allocation(rows: list[dict], amount: Decimal) -> list[dict]:
    amount = money(amount)
    total_available = money(sum((row['available_uzs'] for row in rows), ZERO))
    if amount <= ZERO or total_available <= ZERO:
        return []
    amount = min(amount, total_available)
    allocations = []
    eligible_rows = [row for row in rows if row['available_uzs'] > ZERO]
    for row in eligible_rows:
        take = min(money(amount * row['available_uzs'] / total_available), row['available_uzs'])
        if take > ZERO:
            allocations.append({
                'procurement_id': row['procurement_id'],
                'partner_id': row['partner_id'],
                'partner_name': row['partner_name'],
                'amount_uzs': take,
                'available_uzs': row['available_uzs'],
            })
    residue = money(amount - sum((row['amount_uzs'] for row in allocations), ZERO))
    if residue > ZERO:
        for row in allocations:
            headroom = money(row['available_uzs'] - row['amount_uzs'])
            if headroom <= ZERO:
                continue
            top_up = min(headroom, residue)
            row['amount_uzs'] = money(row['amount_uzs'] + top_up)
            residue = money(residue - top_up)
            if residue <= ZERO:
                break
    elif residue < ZERO:
        excess = money(-residue)
        for row in reversed(allocations):
            take_back = min(row['amount_uzs'], excess)
            row['amount_uzs'] = money(row['amount_uzs'] - take_back)
            excess = money(excess - take_back)
            if excess <= ZERO:
                break
    allocations = [row for row in allocations if row['amount_uzs'] > ZERO]
    return allocations


def _normalise_allocation_payload(payload: list[dict] | None) -> list[dict]:
    rows = []
    for item in payload or []:
        rows.append({
            'procurement_id': int(item.get('procurement_id')),
            'partner_id': int(item.get('partner_id')),
            'amount_uzs': money(item.get('amount_uzs') or item.get('amount') or ZERO),
        })
    return rows


def _settle_capital_return_obligation_for_decision(
    *,
    agreement: InvestmentAgreement,
    procurement_id: int,
    partner_id: int,
    amount_uzs: Decimal,
    decision: PayoutDecision,
    settled_at,
    withdrawal=None,
) -> PayoutObligation | None:
    obligation = (
        PayoutObligation.objects
        .select_for_update()
        .filter(
            agreement=agreement,
            procurement_id=procurement_id,
            recipient_id=partner_id,
            kind=PayoutObligation.Kind.CAPITAL_RETURN,
            status__in=[
                PayoutObligation.Status.PENDING,
                PayoutObligation.Status.RECORDED,
                PayoutObligation.Status.DISPUTED,
            ],
        )
        .order_by('due_at', 'id')
        .first()
    )
    if obligation is None:
        return None
    remaining = money(Decimal(str(obligation.amount)) - Decimal(str(obligation.paid_amount)))
    actual = min(money(amount_uzs), remaining)
    if actual <= ZERO:
        return obligation

    PayoutSettlement.objects.create(
        tenant_id=agreement.tenant_id,
        obligation=obligation,
        amount=actual,
        settled_at=settled_at,
        evidence=(
            f'E23 payout decision #{decision.pk}: {decision.decision_type}. '
            'Recovered-capital claim settled by group decision.'
        ),
        capital_withdrawal=withdrawal,
    )
    if withdrawal is not None and obligation.capital_withdrawal_id is None:
        obligation.capital_withdrawal = withdrawal
    obligation.paid_amount = money(Decimal(str(obligation.paid_amount)) + actual)
    obligation.recorded_at = settled_at
    obligation.notes = '\n'.join(part for part in [
        obligation.notes,
        f'E23 group decision #{decision.pk} settled {actual} UZS as {decision.decision_type}.',
    ] if part)
    if Decimal(str(obligation.paid_amount)) >= Decimal(str(obligation.amount)):
        obligation.status = PayoutObligation.Status.CONFIRMED
        obligation.confirmed_at = settled_at
    else:
        obligation.status = PayoutObligation.Status.PENDING
        obligation.confirmed_at = None
    obligation.save(update_fields=[
        'capital_withdrawal', 'paid_amount', 'status', 'recorded_at',
        'confirmed_at', 'notes', 'updated_at',
    ])
    return obligation


def _currency_fx_snapshot(*, tenant_id: int, currency: str, when):
    from apps.finance.fx_rates import resolve_fx_rate_snapshot_details

    return resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id,
        operation_currency=str(currency or 'UZS').upper(),
        operation_at=when,
        fx_rate_snapshot=None,
    )


def _native_amount_from_uzs(*, tenant_id: int, currency: str, amount_uzs: Decimal, when) -> tuple[Decimal, object]:
    snapshot = _currency_fx_snapshot(tenant_id=tenant_id, currency=currency, when=when)
    rate = Decimal(str(snapshot.rate or Decimal('1')))
    if rate <= ZERO:
        raise ValueError(f'Invalid FX rate for {currency}.')
    return money(Decimal(str(amount_uzs)) / rate), snapshot


def _decision_spacing_ready(*, agreement: InvestmentAgreement, policy: PayoutPolicy, now) -> tuple[bool, str, object]:
    previous = (
        PayoutDecision.objects
        .filter(agreement=agreement, status=PayoutDecision.Status.CONFIRMED)
        .order_by('-confirmed_at', '-decided_at')
        .first()
    )
    if previous is None:
        return True, '', None
    baseline = previous.confirmed_at or previous.decided_at
    ready_at = baseline + timedelta(days=policy.minimum_days_between_payouts)
    if now >= ready_at:
        return True, '', previous
    return False, f'Новая операция доступна после {ready_at.date().isoformat()}.', previous


def build_payout_decision_preview(
    *,
    agreement: InvestmentAgreement,
    decision_type: str,
    amount_uzs=None,
    allocations: list[dict] | None = None,
    from_account_id: int | None = None,
    now=None,
) -> dict:
    """Preview a policy-gated agreement group decision without moving money."""
    now = now or timezone.now()
    decision_type = str(decision_type or '').upper()
    if decision_type not in PayoutDecision.DecisionType.values:
        return {
            'allowed': False,
            'decision_type': decision_type,
            'blocking_reasons': ['Unsupported decision_type.'],
            'allocations': [],
        }
    agreement = InvestmentAgreement.objects.select_related('current_terms').get(pk=agreement.pk)
    policy = _policy_for_agreement(agreement)
    reasons: list[str] = []
    if policy is None:
        reasons.append('Agreement has no payout policy.')
    rows = _decision_rows(agreement=agreement, decision_type=decision_type)
    total_available = money(sum((row['available_uzs'] for row in rows), ZERO))
    reserve = money(policy.reserve_amount) if policy else ZERO
    eligible_total = max(ZERO, money(total_available - reserve))
    requested_amount = money(amount_uzs if amount_uzs is not None else eligible_total)
    if requested_amount <= ZERO:
        reasons.append('Decision amount must be positive.')
    if requested_amount > eligible_total:
        reasons.append(f'Decision amount exceeds policy-eligible total {eligible_total} UZS.')

    interval_ready = False
    threshold_ready = False
    spacing_ready = True
    last_decision = None
    trigger_mode = PayoutPolicy.TriggerMode.ANY
    if policy is not None and agreement.current_terms_id:
        trigger_mode = policy.trigger_mode or PayoutPolicy.TriggerMode.ANY
        baseline = agreement.current_terms.effective_at
        last_decision = (
            PayoutDecision.objects
            .filter(agreement=agreement, status=PayoutDecision.Status.CONFIRMED)
            .order_by('-confirmed_at', '-decided_at')
            .first()
        )
        if last_decision:
            baseline = last_decision.confirmed_at or last_decision.decided_at
        interval_ready = now >= baseline + timedelta(days=policy.review_interval_days)
        threshold = money(policy.minimum_available_amount)
        threshold_ready = threshold <= ZERO or eligible_total >= threshold
        spacing_ready, spacing_reason, _previous = _decision_spacing_ready(
            agreement=agreement, policy=policy, now=now,
        )
        if not spacing_ready:
            reasons.append(spacing_reason)
        trigger_ready = (
            interval_ready and threshold_ready
            if trigger_mode == PayoutPolicy.TriggerMode.ALL
            else (interval_ready or (threshold > ZERO and threshold_ready))
        )
        if not trigger_ready:
            if trigger_mode == PayoutPolicy.TriggerMode.ALL:
                reasons.append('Payout policy requires both review interval and group threshold.')
            else:
                reasons.append('Payout policy has not reached review interval or group threshold.')
        if not policy.allow_partial and requested_amount != eligible_total:
            reasons.append('This payout policy does not allow partial decisions.')

    if any(row['negative_position_uzs'] > ZERO for row in rows):
        reasons.append('Some eligible rows have negative partner position; settle debts first.')

    if decision_type == PayoutDecision.DecisionType.CAPITALIZE_PROFIT:
        reasons.append('Profit capitalization requires an explicit terms amendment before execution.')

    allocation_payload = _normalise_allocation_payload(allocations)
    row_index = {(row['procurement_id'], row['partner_id']): row for row in rows}
    if allocation_payload:
        default_allocations_by_key = {}
        allocation_total = ZERO
        for item in allocation_payload:
            key = (item['procurement_id'], item['partner_id'])
            source = row_index.get(key)
            if source is None:
                reasons.append('Allocation row is not eligible for this decision.')
                continue
            amount = money(item['amount_uzs'])
            if amount < ZERO:
                reasons.append('Allocation row amount must be non-negative.')
            allocation_total += amount
            existing = default_allocations_by_key.get(key)
            if existing is None:
                default_allocations_by_key[key] = {
                    'procurement_id': item['procurement_id'],
                    'partner_id': item['partner_id'],
                    'partner_name': source['partner_name'],
                    'amount_uzs': amount,
                    'available_uzs': source['available_uzs'],
                }
            else:
                existing['amount_uzs'] = money(existing['amount_uzs'] + amount)
            if default_allocations_by_key[key]['amount_uzs'] > source['available_uzs']:
                reasons.append('Allocation row exceeds available recovered amount.')
        if allocation_total != requested_amount:
            reasons.append('Allocation rows must sum to the decision amount.')
        default_allocations = list(default_allocations_by_key.values())
    else:
        default_allocations = _proportional_allocation(rows, requested_amount)

    account_payload = None
    if decision_type in {
        PayoutDecision.DecisionType.PAY_OUT,
        PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
    }:
        if from_account_id is None:
            reasons.append('Source operating cash account is required for payout decisions.')
        else:
            from apps.finance.models import CashAccount
            from apps.finance.services import require_operating_cash_account
            account = CashAccount.objects.filter(
                tenant_id=agreement.tenant_id,
                pk=from_account_id,
                is_active=True,
            ).first()
            if account is None:
                reasons.append('Source cash account was not found.')
            else:
                try:
                    require_operating_cash_account(account, action='Payout decision')
                except ValueError as error:
                    reasons.append(str(error))
                account_currency = str(account.currency).upper()
                native_required = requested_amount
                if decision_type == PayoutDecision.DecisionType.PAY_OUT and account_currency != 'UZS':
                    reasons.append('Recovered capital payout currently requires a UZS operating cash account.')
                if decision_type == PayoutDecision.DecisionType.ROLL_OVER_CAPITAL:
                    try:
                        native_required, _snapshot = _native_amount_from_uzs(
                            tenant_id=agreement.tenant_id,
                            currency=account_currency,
                            amount_uzs=requested_amount,
                            when=now,
                        )
                    except ValueError as error:
                        reasons.append(str(error))
                if money(account.balance) < native_required:
                    reasons.append(
                        f'Insufficient cash account balance: {money(account.balance)} {account_currency}.'
                    )
                account_payload = {
                    'id': account.id,
                    'name': account.name,
                    'currency': account.currency,
                    'balance': str(money(account.balance)),
                    'required_amount': str(native_required),
                }

    return {
        'allowed': not reasons,
        'agreement_id': agreement.id,
        'decision_type': decision_type,
        'currency': 'UZS',
        'amount_uzs': str(requested_amount),
        'total_available_uzs': str(total_available),
        'eligible_total_uzs': str(eligible_total),
        'reserve_amount_uzs': str(reserve),
        'trigger_mode': trigger_mode,
        'interval_ready': interval_ready,
        'threshold_ready': threshold_ready,
        'spacing_ready': spacing_ready,
        'last_decision_id': last_decision.id if last_decision else None,
        'source_account': account_payload,
        'allocations': [
            {
                **row,
                'amount_uzs': str(row['amount_uzs']),
                'available_uzs': str(row['available_uzs']),
            }
            for row in default_allocations
        ],
        'constraints': [
            {
                'procurement_id': row['procurement_id'],
                'partner_id': row['partner_id'],
                'available_uzs': str(row['available_uzs']),
                'negative_position_uzs': str(row['negative_position_uzs']),
            }
            for row in rows
        ],
        'blocking_reasons': reasons,
    }


def execute_payout_decision(
    *,
    agreement: InvestmentAgreement,
    decision_type: str,
    amount_uzs,
    allocations: list[dict] | None,
    from_account_id: int | None,
    client_request_id=None,
    notes: str = '',
    created_by_id: int | None = None,
    now=None,
) -> dict:
    now = now or timezone.now()
    decision_type = str(decision_type or '').upper()
    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement.pk,
            tenant_id=agreement.tenant_id,
        )
        if client_request_id:
            existing = PayoutDecision.objects.filter(
                tenant_id=agreement.tenant_id,
                client_request_id=client_request_id,
            ).first()
            if existing:
                return serialize_payout_decision(existing)
        preview = build_payout_decision_preview(
            agreement=agreement,
            decision_type=decision_type,
            amount_uzs=amount_uzs,
            allocations=allocations,
            from_account_id=from_account_id,
            now=now,
        )
        if not preview['allowed']:
            raise ValueError('; '.join(preview['blocking_reasons']) or 'Decision is blocked.')
        try:
            with transaction.atomic():
                decision = PayoutDecision.objects.create(
                    tenant_id=agreement.tenant_id,
                    agreement=agreement,
                    decision_type=decision_type,
                    amount_uzs=money(amount_uzs),
                    currency='UZS',
                    source_account_id=from_account_id,
                    decided_at=now,
                    confirmed_at=now,
                    status=PayoutDecision.Status.CONFIRMED,
                    notes=notes,
                    client_request_id=client_request_id,
                )
        except IntegrityError:
            if client_request_id:
                existing = PayoutDecision.objects.filter(
                    tenant_id=agreement.tenant_id,
                    client_request_id=client_request_id,
                ).first()
                if existing:
                    return serialize_payout_decision(existing)
            raise
        created = []
        if decision_type == PayoutDecision.DecisionType.PAY_OUT:
            from .workspace_support import add_agreement_withdrawal, record_agreement_event
            for row in preview['allocations']:
                withdrawal = add_agreement_withdrawal(
                    tenant_id=agreement.tenant_id,
                    agreement_id=agreement.id,
                    procurement_id=int(row['procurement_id']),
                    from_account_id=from_account_id,
                    partner_id=int(row['partner_id']),
                    amount=money(row['amount_uzs']),
                    currency='UZS',
                    reason='policy-group-decision-payout',
                    created_by_id=created_by_id,
                )
                PayoutDecisionAllocation.objects.create(
                    tenant_id=agreement.tenant_id,
                    decision=decision,
                    procurement_id=int(row['procurement_id']),
                    partner_id=int(row['partner_id']),
                    amount_uzs=money(row['amount_uzs']),
                    available_uzs=money(row['available_uzs']),
                    capital_withdrawal=withdrawal,
                )
                _settle_capital_return_obligation_for_decision(
                    agreement=agreement,
                    procurement_id=int(row['procurement_id']),
                    partner_id=int(row['partner_id']),
                    amount_uzs=money(row['amount_uzs']),
                    decision=decision,
                    settled_at=now,
                    withdrawal=withdrawal,
                )
                created.append({'type': 'withdrawal', 'id': withdrawal.id})
            record_agreement_event(
                tenant_id=agreement.tenant_id,
                agreement=agreement,
                event_type='payout_decision.pay_out',
                actor_user_id=created_by_id,
                related_model='PayoutDecision',
                related_id=decision.pk,
                payload={'amount_uzs': str(decision.amount_uzs), 'rows': len(preview['allocations'])},
            )
        elif decision_type == PayoutDecision.DecisionType.ROLL_OVER_CAPITAL:
            _execute_capital_rollover(decision=decision, preview=preview, from_account_id=from_account_id, now=now)
            created = [{'type': 'capital_rollover', 'count': len(preview['allocations'])}]
        else:
            raise ValueError('Profit capitalization is not executable without an explicit terms amendment.')
        return {**serialize_payout_decision(decision), 'created': created}


def _execute_capital_rollover(*, decision: PayoutDecision, preview: dict, from_account_id: int, now) -> None:
    from apps.finance.models import CashAccount, CashEntry
    from apps.finance.services import create_cash_entry, create_journal_entry, require_operating_cash_account
    from .models import CurrencyConversionLot
    from .multicurrency import get_or_create_currency_pool
    from .workspace_support import record_agreement_event
    from .read_models import rebuild_agreement_positions

    agreement = decision.agreement
    amount_uzs = money(decision.amount_uzs)
    source = CashAccount.objects.select_for_update().get(pk=from_account_id, tenant_id=agreement.tenant_id)
    require_operating_cash_account(source, action='Capital rollover')
    source_currency = str(source.currency).upper()
    source_amount, source_fx = _native_amount_from_uzs(
        tenant_id=agreement.tenant_id,
        currency=source_currency,
        amount_uzs=amount_uzs,
        when=now,
    )
    pool = get_or_create_currency_pool(
        tenant_id=agreement.tenant_id,
        agreement=agreement,
        currency=source_currency,
    )
    if money(source.balance) < source_amount:
        raise ValueError(f'Insufficient cash account balance: {money(source.balance)} {source_currency}.')
    if not source.linked_account_id or not pool.linked_account_id:
        raise ValueError('Cash accounts must have linked GL accounts.')

    create_cash_entry(
        tenant_id=agreement.tenant_id,
        account=source,
        direction=CashEntry.Direction.OUT,
        amount=source_amount,
        date=now,
        source_ref_type='capital_rollover_decision',
        source_ref_id=decision.pk,
    )
    create_cash_entry(
        tenant_id=agreement.tenant_id,
        account=pool,
        direction=CashEntry.Direction.IN,
        amount=source_amount,
        date=now,
        source_ref_type='capital_rollover_decision',
        source_ref_id=decision.pk,
    )
    create_journal_entry(
        tenant_id=agreement.tenant_id,
        operation_type='transfer',
        operation_id=decision.pk,
        lines=[
            {'account_code': pool.linked_account.code, 'debit': amount_uzs, 'credit': Decimal('0'),
             'description': f'Capital rollover decision #{decision.pk} — into pool'},
            {'account_code': source.linked_account.code, 'debit': Decimal('0'), 'credit': amount_uzs,
             'description': f'Capital rollover decision #{decision.pk} — from operating cash'},
        ],
        description=f'Capital rollover decision #{decision.pk}',
        date=now,
    )
    base_currency = str(agreement.currency or 'UZS').upper()
    if source_currency != base_currency:
        base_snapshot = _currency_fx_snapshot(
            tenant_id=agreement.tenant_id,
            currency=base_currency,
            when=now,
        )
        base_rate = Decimal(str(base_snapshot.rate or Decimal('1')))
        if base_rate <= ZERO:
            raise ValueError(f'Invalid FX rate for agreement base currency {base_currency}.')
        if base_currency == 'UZS':
            base_cost = Decimal(str(amount_uzs))
        else:
            base_cost = Decimal(str(amount_uzs)) / base_rate
        if base_cost <= ZERO:
            raise ValueError('Capital rollover base cost must be positive.')
        CurrencyConversionLot.objects.create(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            base_currency=base_currency,
            currency=source_currency,
            rate=(source_amount / base_cost).quantize(Decimal('0.00000001')),
            amount_initial=source_amount,
            amount_remaining=source_amount,
            base_cost_initial=base_cost.quantize(Decimal('0.000001')),
            base_cost_remaining=base_cost.quantize(Decimal('0.000001')),
            converted_at=now,
            source_ref=f'capital_rollover:{decision.pk}',
        )

    allocated_native = ZERO
    rows = list(preview['allocations'])
    for index, row in enumerate(rows):
        row_uzs = money(row['amount_uzs'])
        if index == len(rows) - 1:
            row_native = money(source_amount - allocated_native)
        else:
            row_native = money(row_uzs / Decimal(str(source_fx.rate)))
            allocated_native = money(allocated_native + row_native)
        rollover = CapitalRollover.objects.create(
            tenant_id=agreement.tenant_id,
            decision=decision,
            agreement=agreement,
            procurement_id=int(row['procurement_id']),
            partner_id=int(row['partner_id']),
            from_account=source,
            amount=row_native,
            currency=source_currency,
            fx_rate=source_fx.rate,
            fx_rate_source=source_fx.source,
            fx_rate_date=source_fx.rate_date,
            amount_uzs=row_uzs,
            date=now,
            notes='policy-group-decision-rollover',
        )
        PayoutDecisionAllocation.objects.create(
            tenant_id=agreement.tenant_id,
            decision=decision,
            procurement_id=int(row['procurement_id']),
            partner_id=int(row['partner_id']),
            amount_uzs=money(row['amount_uzs']),
            available_uzs=money(row['available_uzs']),
            capital_rollover=rollover,
        )
        _settle_capital_return_obligation_for_decision(
            agreement=agreement,
            procurement_id=int(row['procurement_id']),
            partner_id=int(row['partner_id']),
            amount_uzs=row_uzs,
            decision=decision,
            settled_at=now,
            withdrawal=None,
        )
    record_agreement_event(
        tenant_id=agreement.tenant_id,
        agreement=agreement,
        event_type='payout_decision.roll_over_capital',
        related_model='PayoutDecision',
        related_id=decision.pk,
        payload={'amount_uzs': str(decision.amount_uzs), 'rows': len(preview['allocations'])},
    )
    publish_event(
        event_type='partnership.capital_rollover_recorded',
        payload={'agreement_id': agreement.pk, 'decision_id': decision.pk, 'amount_uzs': str(decision.amount_uzs)},
        tenant_id=agreement.tenant_id,
    )
    rebuild_agreement_positions(agreement)


def serialize_payout_decision(decision: PayoutDecision) -> dict:
    allocations = []
    for row in decision.allocations.select_related('partner', 'procurement').all():
        allocations.append({
            'id': row.id,
            'procurement_id': row.procurement_id,
            'partner_id': row.partner_id,
            'partner_name': row.partner.display_name,
            'amount_uzs': str(money(row.amount_uzs)),
            'available_uzs': str(money(row.available_uzs)),
            'capital_withdrawal_id': row.capital_withdrawal_id,
            'capital_rollover_id': row.capital_rollover_id,
        })
    return {
        'id': decision.id,
        'agreement_id': decision.agreement_id,
        'decision_type': decision.decision_type,
        'amount_uzs': str(money(decision.amount_uzs)),
        'currency': decision.currency,
        'source_account_id': decision.source_account_id,
        'decided_at': decision.decided_at.isoformat(),
        'confirmed_at': decision.confirmed_at.isoformat() if decision.confirmed_at else None,
        'status': decision.status,
        'notes': decision.notes,
        'allocations': allocations,
    }


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
            recipient_id = row.member.partner_id
            recipient_profile_id = row.member.profile_id if not recipient_id else None
            if not recipient_id and not recipient_profile_id:
                continue
            for kind, available in (
                (PayoutObligation.Kind.PROFIT, Decimal(str(row.profit_available_uzs))),
                (PayoutObligation.Kind.CAPITAL_RETURN, Decimal(str(row.capital_return_available_uzs))),
            ):
                amount = _eligible_after_policy(amount=available, policy=policy)
                if amount <= ZERO:
                    continue
                existing = PayoutObligation.objects.filter(fund=fund, kind=kind)
                if recipient_id:
                    existing = existing.filter(recipient_id=recipient_id)
                else:
                    existing = existing.filter(recipient_profile_id=recipient_profile_id)
                if not _may_open_next_obligation(queryset=existing, now=now, policy=policy):
                    continue
                obligation, was_created = _create_payout_obligation_if_absent(
                    tenant_id=fund.tenant_id,
                    fund=fund,
                    recipient_id=recipient_id,
                    recipient_profile_id=recipient_profile_id,
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
        manager_member_filter = Q()
        if fund.manager_profile_id:
            manager_member_filter |= Q(member__profile_id=fund.manager_profile_id)
        if fund.manager_partner_id:
            manager_member_filter |= Q(member__partner_id=fund.manager_partner_id)
        manager_is_member = (
            FundMemberPositionReadModel.objects.filter(fund=fund)
            .filter(manager_member_filter)
            .exists()
            if manager_member_filter else False
        )
        manager_fee = Decimal(str(getattr(fund_position, 'manager_fee_accrued_uzs', ZERO)))
        if not manager_is_member and manager_fee > ZERO and fund.manager_partner_id:
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
                        recipient_profile_id=None,
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
        elif not manager_is_member and manager_fee > ZERO and fund.manager_profile_id:
            existing = PayoutObligation.objects.filter(
                fund=fund,
                recipient_profile_id=fund.manager_profile_id,
                kind=PayoutObligation.Kind.PROFIT,
            )
            if _may_open_next_obligation(queryset=existing, now=now, policy=policy):
                obligation, was_created = _create_payout_obligation_if_absent(
                    tenant_id=fund.tenant_id,
                    fund=fund,
                    recipient_id=None,
                    recipient_profile_id=fund.manager_profile_id,
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


def open_dispute(
    *,
    obligation: PayoutObligation,
    raised_by_id: int | None = None,
    raised_by_profile_id: int | None = None,
    statement: str,
    evidence: str = '',
) -> DisputeCase:
    if not statement.strip():
        raise ValueError('A dispute statement is required.')
    with transaction.atomic():
        locked = PayoutObligation.objects.select_for_update().get(pk=obligation.pk)
        if raised_by_id is None and raised_by_profile_id is None:
            raise ValueError('Payout dispute recipient is required.')
        if raised_by_id is not None and raised_by_id != locked.recipient_id:
            raise ValueError('Only the payout recipient can open this dispute.')
        if raised_by_profile_id is not None and raised_by_profile_id != locked.recipient_profile_id:
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
            raised_by_profile_id=raised_by_profile_id,
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
