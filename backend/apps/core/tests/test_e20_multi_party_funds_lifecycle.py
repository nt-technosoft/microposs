from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone
from uuid import uuid4

from apps.core.models import BusinessInvestorRelation, Partner
from apps.core.exceptions import ImmutableRecordError
from apps.partnerships.fund_services import (
    add_fund_contribution,
    create_investment_fund,
    deploy_fund_to_agreement,
)
from apps.partnerships.lifecycle_services import (
    agreement_has_funding_hold,
    confirm_payout_obligation,
    create_agreement_terms_version,
    ensure_contract_review,
    evaluate_agreement_payout_obligations,
    evaluate_fund_payout_obligations,
    open_dispute,
    record_payout_obligation,
    resolve_contract_review,
)
from apps.partnerships.models import (
    AgreementPartner,
    InvestmentFund,
    PartnerPositionReadModel,
    PayoutObligation,
    PayoutPolicy,
    FundPositionReadModel,
)
from apps.finance.models import Payment
from apps.finance.services import record_generic_cash_payment
from apps.partnerships.workspace_support import (
    add_agreement_contribution,
    create_investment_agreement,
)
from apps.partnerships.tasks import evaluate_due_contract_lifecycle

from ._helpers import build_tenant


class E20MultiPartyFundsLifecycleTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.operator = self.ctx['operator']
        self.investor = self.ctx['investor']

    def _second_investor(self):
        partner = Partner.objects.create(
            tenant=self.business,
            role=Partner.Role.INVESTOR,
            display_name='Second investor',
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=self.business,
            partner=partner,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
        )
        return partner

    def test_multi_party_agreement_creates_versioned_terms_and_payout_policy(self):
        second = self._second_investor()
        review_at = timezone.now() + timedelta(days=90)
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('1000'),
            review_at=review_at,
            offline_agreed_at=timezone.now(),
            offline_agreement_reference='offline-v1',
            payout_policy={
                'review_interval_days': 14,
                'minimum_available_amount': '50',
                'minimum_days_between_payouts': 7,
                'reserve_amount': '10',
                'grace_period_days': 2,
                'allow_partial': True,
            },
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '400', 'profit_share': '0.20'},
                {'partner_id': second.id, 'role': 'INVESTOR', 'planned_capital_share': '400', 'profit_share': '0.20'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '200', 'profit_share': '0.60'},
            ],
        )

        self.assertEqual(agreement.partners.count(), 3)
        self.assertIsNotNone(agreement.current_terms_id)
        self.assertEqual(agreement.current_terms.version, 1)
        self.assertEqual(agreement.current_terms.payout_policy.review_interval_days, 14)
        self.assertEqual(agreement.current_terms.review_at, review_at)
        self.assertEqual(len(agreement.current_terms.terms_snapshot['parties']), 3)

        amended = create_agreement_terms_version(
            agreement=agreement,
            offline_agreed_at=timezone.now(),
            offline_agreement_reference='offline-v2',
            payout_policy={'grace_period_days': 5},
        )
        self.assertEqual(amended.version, 2)
        self.assertEqual(amended.payout_policy.review_interval_days, 14)
        self.assertEqual(amended.payout_policy.grace_period_days, 5)
        self.assertEqual(amended.terms_snapshot['parties'], agreement.current_terms.terms_snapshot['parties'])

    def test_closed_fund_deploys_via_holder_and_blocks_new_contribution(self):
        second = self._second_investor()
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Friends fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id, second.id],
            currency='UZS',
            manager_profit_share=Decimal('0.10'),
        )
        add_fund_contribution(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            amount=Decimal('600'),
            currency='UZS',
        )
        add_fund_contribution(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=second.id,
            amount=Decimal('400'),
            currency='UZS',
        )
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('1000'),
            partners=[
                {'partner_id': fund.holder_partner_id, 'role': 'INVESTOR', 'planned_capital_share': '800', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '200', 'profit_share': '0.60'},
            ],
        )

        deployment = deploy_fund_to_agreement(
            tenant_id=self.business.id,
            fund_id=fund.id,
            agreement_id=agreement.id,
            amount=Decimal('800'),
        )
        fund.refresh_from_db()
        self.assertEqual(fund.status, InvestmentFund.Status.DEPLOYED)
        self.assertEqual(deployment.agreement_contribution.partner_id, fund.holder_partner_id)
        self.assertEqual(fund.capital_account.balance, Decimal('200.00'))
        self.assertEqual(fund.member_position_rows.get(member__partner=self.investor).capital_share, Decimal('0.600000000'))
        with self.assertRaisesMessage(ValueError, 'closed for new capital'):
            add_fund_contribution(
                tenant_id=self.business.id,
                fund_id=fund.id,
                partner_id=self.investor.id,
                amount=Decimal('1'),
                currency='UZS',
            )

    def test_overdue_dispute_holds_only_new_agreement_funding(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            payout_policy={'minimum_available_amount': '1'},
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        PartnerPositionReadModel.objects.create(
            tenant=self.business,
            agreement=agreement,
            procurement_id=None,
            partner=self.investor,
            currency='UZS',
            computed_at=timezone.now(),
        )
        # A procurement-level row is enough for the policy engine; it does not
        # need a real payment to demonstrate that eligibility never auto-pays.
        from apps.partnerships.models import Procurement
        procurement = Procurement.objects.create(
            tenant=self.business,
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        PartnerPositionReadModel.objects.create(
            tenant=self.business,
            agreement=agreement,
            procurement=procurement,
            partner=self.investor,
            currency='UZS',
            provisional_profit_available_uzs=Decimal('120'),
            capital_return_available_uzs=Decimal('80'),
            computed_at=timezone.now(),
        )
        rows = evaluate_agreement_payout_obligations(agreement=agreement)
        self.assertEqual({row.kind for row in rows}, {PayoutObligation.Kind.PROFIT, PayoutObligation.Kind.CAPITAL_RETURN})
        obligation = next(row for row in rows if row.kind == PayoutObligation.Kind.PROFIT)
        open_dispute(
            obligation=obligation,
            raised_by_id=self.investor.id,
            statement='The agreed payout has not been made.',
        )
        with self.assertRaisesMessage(ValueError, 'already has an open dispute'):
            open_dispute(
                obligation=obligation,
                raised_by_id=self.investor.id,
                statement='Duplicate complaint.',
            )
        self.assertTrue(agreement_has_funding_hold(agreement=agreement, now=timezone.now() + timedelta(seconds=1)))
        with self.assertRaisesMessage(ValueError, 'New funding is temporarily restricted'):
            add_agreement_contribution(
                tenant_id=self.business.id,
                agreement_id=agreement.id,
                partner_id=self.investor.id,
                amount=Decimal('1'),
                currency='UZS',
            )

    def test_policy_cadence_and_partial_fund_payout_are_explicit(self):
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Partial payout fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id],
            currency='UZS',
        )
        obligation = PayoutObligation.objects.create(
            tenant=self.business,
            fund=fund,
            recipient=self.investor,
            kind=PayoutObligation.Kind.PROFIT,
            amount=Decimal('100'),
            currency='UZS',
            due_at=timezone.now(),
        )
        record_payout_obligation(
            obligation=obligation,
            amount=Decimal('40'),
            evidence='cash receipt 1',
        )
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, PayoutObligation.Status.RECORDED)
        self.assertEqual(obligation.paid_amount, Decimal('40.00'))
        confirm_payout_obligation(obligation=obligation)
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, PayoutObligation.Status.PENDING)
        record_payout_obligation(
            obligation=obligation,
            amount=Decimal('60'),
            evidence='cash receipt 2',
        )
        confirm_payout_obligation(obligation=obligation)
        obligation.refresh_from_db()
        self.assertEqual(obligation.status, PayoutObligation.Status.CONFIRMED)
        self.assertEqual(obligation.settlements.count(), 2)

        PayoutPolicy.objects.filter(fund_terms_id=fund.current_terms_id).update(allow_partial=False)
        blocked = PayoutObligation.objects.create(
            tenant=self.business,
            fund=fund,
            recipient=self.investor,
            kind=PayoutObligation.Kind.PROFIT,
            amount=Decimal('100'),
            currency='UZS',
            due_at=timezone.now(),
        )
        with self.assertRaisesMessage(ValueError, 'does not allow partial'):
            record_payout_obligation(obligation=blocked, amount=Decimal('50'))

    def test_scheduled_lifecycle_respects_cadence_and_creates_due_actions(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        from apps.partnerships.models import Procurement
        procurement = Procurement.objects.create(
            tenant=self.business,
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        PartnerPositionReadModel.objects.create(
            tenant=self.business,
            agreement=agreement,
            procurement=procurement,
            partner=self.investor,
            currency='UZS',
            provisional_profit_available_uzs=Decimal('25'),
            capital_return_available_uzs=Decimal('50'),
            computed_at=timezone.now(),
        )
        self.assertEqual(evaluate_agreement_payout_obligations(agreement=agreement), [])
        # The same default policy becomes due only on its 30-day cadence. The
        # scheduled task is the production path that invokes that check.
        type(agreement.current_terms).objects.filter(pk=agreement.current_terms_id).update(
            effective_at=timezone.now() - timedelta(days=31),
        )
        result = evaluate_due_contract_lifecycle()
        self.assertEqual(result['agreement_obligations'], 2)
        self.assertEqual(PayoutObligation.objects.filter(agreement=agreement).count(), 2)

    def test_fund_pool_is_restricted_and_nonmember_manager_fee_is_payable(self):
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Manager outside fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id],
            currency='UZS',
            manager_profit_share=Decimal('0.10'),
        )
        with self.assertRaisesMessage(ValueError, 'restricted capital pool'):
            record_generic_cash_payment(
                tenant_id=self.business.id,
                cash_account_id=fund.capital_account_id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=1,
                amount=Decimal('1'),
                counterpart_account_code='1100',
            )
        FundPositionReadModel.objects.filter(fund=fund).update(
            manager_fee_accrued_uzs=Decimal('10.00'),
        )
        PayoutPolicy.objects.filter(fund_terms_id=fund.current_terms_id).update(
            minimum_available_amount=Decimal('1'),
        )
        rows = evaluate_fund_payout_obligations(fund=fund)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].recipient_id, self.operator.id)
        self.assertEqual(rows[0].amount, Decimal('10.00'))

    def test_active_payout_obligation_is_unique_while_pending(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        PayoutObligation.objects.create(
            tenant=self.business,
            agreement=agreement,
            recipient=self.investor,
            kind=PayoutObligation.Kind.PROFIT,
            amount=Decimal('1'),
            currency='UZS',
            due_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutObligation.objects.create(
                tenant=self.business,
                agreement=agreement,
                recipient=self.investor,
                kind=PayoutObligation.Kind.PROFIT,
                amount=Decimal('1'),
                currency='UZS',
                due_at=timezone.now(),
            )

    def test_terms_are_append_only_and_fund_events_are_idempotent(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        agreement.current_terms.notes = 'attempted rewrite'
        with self.assertRaises(ImmutableRecordError):
            agreement.current_terms.save()

        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Idempotent fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id],
            currency='UZS',
        )
        request_id = uuid4()
        first = add_fund_contribution(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            amount=Decimal('100'),
            currency='UZS',
            client_request_id=request_id,
        )
        duplicate = add_fund_contribution(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            amount=Decimal('100'),
            currency='UZS',
            client_request_id=request_id,
        )
        self.assertEqual(first.pk, duplicate.pk)
        self.assertEqual(fund.contributions.count(), 1)

    def test_review_records_buyout_and_writeoff_decisions_without_auto_liquidation(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            review_at=timezone.now() - timedelta(days=1),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        buyout = resolve_contract_review(
            review=ensure_contract_review(agreement=agreement),
            resolution='BUYOUT',
            resolved_by_id=None,
            notes='Offline buyout price agreed.',
        )
        self.assertEqual(buyout.resolution, 'BUYOUT')
        agreement.refresh_from_db()
        self.assertNotEqual(agreement.status, agreement.Status.CLOSED)

        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Review fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id],
            currency='UZS',
            review_at=timezone.now() - timedelta(days=1),
        )
        writeoff = resolve_contract_review(
            review=ensure_contract_review(fund=fund),
            resolution='WRITE_OFF',
            resolved_by_id=None,
            notes='Confirmed real loss recorded offline.',
        )
        self.assertEqual(writeoff.resolution, 'WRITE_OFF')

    def test_review_is_reminder_not_automatic_close(self):
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100'),
            review_at=timezone.now() - timedelta(days=1),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '80', 'profit_share': '0.40'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '20', 'profit_share': '0.60'},
            ],
        )
        review = ensure_contract_review(agreement=agreement)
        agreement.refresh_from_db()
        self.assertIsNotNone(review)
        self.assertNotEqual(agreement.status, agreement.Status.CLOSED)
