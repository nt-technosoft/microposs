from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from uuid import uuid4

from apps.core.models import BusinessInvestorRelation, Partner
from apps.core.exceptions import ImmutableRecordError
from apps.partnerships.fund_services import (
    add_fund_contribution,
    amend_fundraising_terms,
    approve_fund_application,
    create_investment_fund,
    deploy_fund_to_agreement,
    exit_fund_member,
    preview_fund_application_approvals,
    rebuild_fund_member_positions,
    submit_fund_application,
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
    FundApplication,
    FundMember,
    FundMemberExit,
    FundMemberPositionReadModel,
    InvestmentFund,
    PartnerPositionReadModel,
    PayoutObligation,
    PayoutPolicy,
    FundPositionReadModel,
    Procurement,
)
from apps.partnerships.serializers import (
    InvestmentAgreementDetailSerializer,
    InvestmentAgreementListSerializer,
)
from apps.finance.models import Payment
from apps.finance.services import record_generic_cash_payment
from apps.partnerships.workspace_support import (
    add_agreement_contribution,
    create_investment_agreement,
)
from apps.partnerships.workspace import build_workspace_payload, create_workspace
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

    def test_multi_party_agreement_serializers_report_investor_pool_shares(self):
        second = self._second_investor()
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.375'),
            planned_budget=Decimal('1000'),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '300', 'profit_share': '0.112500'},
                {'partner_id': second.id, 'role': 'INVESTOR', 'planned_capital_share': '500', 'profit_share': '0.187500'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '200', 'profit_share': '0.70'},
            ],
        )

        list_data = InvestmentAgreementListSerializer(agreement).data
        detail_data = InvestmentAgreementDetailSerializer(agreement).data

        for payload in (list_data, detail_data):
            self.assertEqual(payload['investor_shares']['capital_percent'], 80)
            self.assertEqual(payload['investor_shares']['profit_percent'], 30)
            self.assertEqual(payload['investor_shares']['investors_count'], 2)

    def test_procurement_workspace_payload_reports_investor_pool_shares(self):
        second = self._second_investor()
        agreement = create_investment_agreement(
            tenant_id=self.business.id,
            mudaraba_ratio=Decimal('0.375'),
            planned_budget=Decimal('1000'),
            partners=[
                {'partner_id': self.investor.id, 'role': 'INVESTOR', 'planned_capital_share': '300', 'profit_share': '0.112500'},
                {'partner_id': second.id, 'role': 'INVESTOR', 'planned_capital_share': '500', 'profit_share': '0.187500'},
                {'partner_id': self.operator.id, 'role': 'OPERATOR', 'planned_capital_share': '200', 'profit_share': '0.70'},
            ],
        )
        procurement = create_workspace(
            tenant_id=self.business.id,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            supplier_id=self.ctx['supplier'].id,
            agreement_id=agreement.id,
        )

        investment = build_workspace_payload(procurement)['documents']['investment']

        self.assertEqual(investment['investor_shares']['capital_percent'], 80)
        self.assertEqual(investment['investor_shares']['profit_percent'], 30)
        self.assertEqual(investment['investor_shares']['investors_count'], 2)

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
        with self.assertRaisesMessage(ValueError, 'after fund deployment'):
            exit_fund_member(
                tenant_id=self.business.id,
                fund_id=fund.id,
                partner_id=self.investor.id,
                reason=FundMemberExit.Reason.MEMBER_EXIT,
            )

    def test_fund_member_capital_return_survives_agreement_withdrawal(self):
        second = self._second_investor()
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Returned capital fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[self.investor.id, second.id],
            currency='UZS',
            manager_profit_share=Decimal('0'),
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
        deploy_fund_to_agreement(
            tenant_id=self.business.id,
            fund_id=fund.id,
            agreement_id=agreement.id,
            amount=Decimal('800'),
        )
        procurement = Procurement.objects.create(
            tenant=self.business,
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        PartnerPositionReadModel.objects.update_or_create(
            tenant=self.business,
            agreement=agreement,
            procurement=None,
            partner=fund.holder_partner,
            currency='UZS',
            defaults={
                'available': Decimal('-80'),
                'computed_at': timezone.now(),
            },
        )
        venture_row = PartnerPositionReadModel.objects.create(
            tenant=self.business,
            agreement=agreement,
            procurement=procurement,
            partner=fund.holder_partner,
            currency='UZS',
            provisional_profit_available_uzs=Decimal('20'),
            capital_return_available_uzs=Decimal('80'),
            computed_at=timezone.now(),
        )

        rebuild_fund_member_positions(fund)
        fund.position_row.refresh_from_db()
        self.assertEqual(fund.position_row.available, Decimal('0.00'))
        self.assertEqual(fund.position_row.capital_return_available_uzs, Decimal('80.00'))
        self.assertEqual(
            FundMemberPositionReadModel.objects.get(fund=fund, member__partner=self.investor).capital_return_available_uzs,
            Decimal('48.00'),
        )
        self.assertEqual(
            FundMemberPositionReadModel.objects.get(fund=fund, member__partner=second).capital_return_available_uzs,
            Decimal('32.00'),
        )

        venture_row.capital_return_available_uzs = Decimal('0')
        venture_row.capital_returned_uzs = Decimal('80')
        venture_row.save(update_fields=['capital_return_available_uzs', 'capital_returned_uzs', 'updated_at'])
        rebuild_fund_member_positions(fund)
        fund.position_row.refresh_from_db()
        self.assertEqual(fund.position_row.available, Decimal('0.00'))
        self.assertEqual(fund.position_row.capital_return_available_uzs, Decimal('80.00'))
        self.assertEqual(
            FundMemberPositionReadModel.objects.get(fund=fund, member__partner=self.investor).capital_return_available_uzs,
            Decimal('48.00'),
        )

        PayoutObligation.objects.create(
            tenant=self.business,
            fund=fund,
            recipient=self.investor,
            kind=PayoutObligation.Kind.CAPITAL_RETURN,
            amount=Decimal('48'),
            paid_amount=Decimal('10'),
            currency='UZS',
            due_at=timezone.now(),
        )
        rebuild_fund_member_positions(fund)
        fund.position_row.refresh_from_db()
        self.assertEqual(fund.position_row.capital_return_available_uzs, Decimal('70.00'))
        self.assertEqual(
            FundMemberPositionReadModel.objects.get(fund=fund, member__partner=self.investor).capital_return_available_uzs,
            Decimal('38.00'),
        )

    def test_fund_application_approval_hard_cap_and_pre_deployment_exit_refund(self):
        second = self._second_investor()
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Applications fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[],
            currency='UZS',
            target_amount=Decimal('1000'),
            min_contribution_amount=Decimal('100'),
            visibility=InvestmentFund.Visibility.PUBLIC_LISTING,
        )

        application = submit_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            requested_amount=Decimal('600'),
        )
        self.assertEqual(application.status, FundApplication.Status.PENDING)
        approve_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            application_id=application.id,
            approved_amount=Decimal('600'),
            decided_by_id=self.ctx['owner'].id,
        )
        member = FundMember.objects.get(fund=fund, partner=self.investor)
        self.assertEqual(member.approved_amount, Decimal('600.00'))

        second_application = submit_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=second.id,
            requested_amount=Decimal('500'),
        )
        with self.assertRaisesMessage(ValueError, 'hard cap'):
            approve_fund_application(
                tenant_id=self.business.id,
                fund_id=fund.id,
                application_id=second_application.id,
                approved_amount=Decimal('500'),
            )

        add_fund_contribution(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            amount=Decimal('600'),
            currency='UZS',
        )
        fund.refresh_from_db()
        self.assertEqual(fund.capital_account.balance, Decimal('600.00'))

        exit_row = exit_fund_member(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            reason=FundMemberExit.Reason.MEMBER_EXIT,
        )
        fund.capital_account.refresh_from_db()
        member.refresh_from_db()
        self.assertEqual(exit_row.refund_amount, Decimal('600.00'))
        self.assertEqual(fund.capital_account.balance, Decimal('0.00'))
        self.assertEqual(member.status, FundMember.Status.EXITED)

    def test_fund_approval_preview_and_terms_amendment_allow_explicit_target_change(self):
        second = self._second_investor()
        fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Target amendment fund',
            manager_partner_id=self.operator.id,
            member_partner_ids=[],
            currency='UZS',
            target_amount=Decimal('1000'),
            min_contribution_amount=Decimal('100'),
        )
        first = submit_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=self.investor.id,
            requested_amount=Decimal('700'),
        )
        approve_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            application_id=first.id,
            approved_amount=Decimal('700'),
        )
        second_application = submit_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            partner_id=second.id,
            requested_amount=Decimal('400'),
        )

        preview = preview_fund_application_approvals(
            tenant_id=self.business.id,
            fund_id=fund.id,
            approvals=[{'application_id': second_application.id, 'approved_amount': Decimal('400')}],
        )
        self.assertTrue(preview['exceeds_target'])
        self.assertEqual(preview['after_approved_amount'], '1100.00')

        with self.assertRaisesMessage(ValueError, 'hard cap'):
            approve_fund_application(
                tenant_id=self.business.id,
                fund_id=fund.id,
                application_id=second_application.id,
                approved_amount=Decimal('400'),
            )

        amended = amend_fundraising_terms(
            tenant_id=self.business.id,
            fund_id=fund.id,
            target_amount=Decimal('1200'),
            min_contribution_amount=Decimal('100'),
            visibility=InvestmentFund.Visibility.PUBLIC_LISTING,
        )
        fund.refresh_from_db()
        self.assertEqual(fund.target_amount, Decimal('1200.00'))
        self.assertEqual(fund.visibility, InvestmentFund.Visibility.PUBLIC_LISTING)
        self.assertEqual(amended.version, 2)
        self.assertEqual(amended.terms_snapshot['target_amount'], '1200.00')

        approve_fund_application(
            tenant_id=self.business.id,
            fund_id=fund.id,
            application_id=second_application.id,
            approved_amount=Decimal('400'),
        )
        self.assertEqual(FundMember.objects.get(fund=fund, partner=second).approved_amount, Decimal('400.00'))

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


class E21FundPermissionApiTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.operator = self.ctx['operator']
        self.investor = self.ctx['investor']
        self.manager_user = User.objects.create_user(username='fund_manager', password='x')
        self.manager_partner = Partner.objects.create(
            tenant=self.business,
            role=Partner.Role.INVESTOR,
            display_name='Fund manager',
            user=self.manager_user,
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=self.business,
            partner=self.manager_partner,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
        )
        self.other_user = User.objects.create_user(username='other_investor', password='x')
        self.other_partner = Partner.objects.create(
            tenant=self.business,
            role=Partner.Role.INVESTOR,
            display_name='Other investor',
            user=self.other_user,
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=self.business,
            partner=self.other_partner,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
        )
        self.fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Permission fund',
            manager_partner_id=self.manager_partner.id,
            member_partner_ids=[],
            currency='UZS',
            target_amount=Decimal('1000'),
            visibility=InvestmentFund.Visibility.PUBLIC_LISTING,
        )

    def test_fund_application_and_manager_actions_are_actor_bound(self):
        self.client.force_authenticate(user=self.ctx['investor'].user)

        impersonation = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/',
            {'partner_id': self.other_partner.id, 'requested_amount': '100'},
            format='json',
        )
        self.assertEqual(impersonation.status_code, status.HTTP_403_FORBIDDEN)

        own_application = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/',
            {'partner_id': self.investor.id, 'requested_amount': '100'},
            format='json',
        )
        self.assertEqual(own_application.status_code, status.HTTP_201_CREATED)

        investor_approval = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/{own_application.data["id"]}/approve/',
            {'approved_amount': '100'},
            format='json',
        )
        self.assertEqual(investor_approval.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.ctx['owner'])
        owner_approval = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/{own_application.data["id"]}/approve/',
            {'approved_amount': '100'},
            format='json',
        )
        self.assertEqual(owner_approval.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.manager_user)
        manager_approval = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/{own_application.data["id"]}/approve/',
            {'approved_amount': '100'},
            format='json',
        )
        self.assertEqual(manager_approval.status_code, status.HTTP_200_OK)

    def test_approval_url_cannot_cross_apply_application_from_other_fund(self):
        second_fund = create_investment_fund(
            tenant_id=self.business.id,
            name='Second permission fund',
            manager_partner_id=self.manager_partner.id,
            member_partner_ids=[],
            currency='UZS',
            target_amount=Decimal('1000'),
        )
        application = submit_fund_application(
            tenant_id=self.business.id,
            fund_id=second_fund.id,
            partner_id=self.investor.id,
            requested_amount=Decimal('100'),
        )

        self.client.force_authenticate(user=self.manager_user)
        response = self.client.post(
            f'/api/v1/partnerships/funds/{self.fund.id}/applications/{application.id}/approve/',
            {'approved_amount': '100'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FundApplication.objects.get(pk=application.id).status, FundApplication.Status.PENDING)

    def test_invite_lookup_does_not_require_existing_tenant_relation(self):
        outside_user = User.objects.create_user(username='outside_investor', password='x')
        self.client.force_authenticate(user=outside_user)

        response = self.client.get(
            f'/api/v1/partnerships/funds/by-invite/{self.fund.invite_token}/',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.fund.id)
        self.assertEqual(response.data['invite_path'], f'/investor/funds/join/{self.fund.invite_token}')

    def test_investor_fund_list_and_create_work_without_active_business_context(self):
        investor_user = User.objects.create_user(username='standalone_fund_investor', password='x')
        investor_partner = Partner.objects.create(
            tenant=self.business,
            role=Partner.Role.INVESTOR,
            display_name='Standalone fund investor',
            user=investor_user,
            is_active=True,
        )
        self.client.force_authenticate(user=investor_user)

        list_response = self.client.get('/api/v1/partnerships/funds/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        list_rows = list_response.data.get('results', list_response.data)
        self.assertEqual([row['id'] for row in list_rows], [self.fund.id])

        create_response = self.client.post(
            '/api/v1/partnerships/funds/',
            {
                'name': 'Investor cabinet fund',
                'manager_partner_id': investor_partner.id,
                'member_partner_ids': [],
                'currency': 'UZS',
                'target_amount': '5000',
                'min_contribution_amount': '100',
                'visibility': InvestmentFund.Visibility.PRIVATE_INVITE,
                'manager_profit_share': '0',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['manager_partner'], investor_partner.id)
        self.assertEqual(create_response.data['manager_partner_name'], investor_partner.display_name)
        self.assertEqual(InvestmentFund.objects.get(pk=create_response.data['id']).tenant_id, self.business.id)

        detail_response = self.client.get(f'/api/v1/partnerships/funds/{create_response.data["id"]}/')
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['id'], create_response.data['id'])

    def test_business_operator_profile_cannot_create_fund(self):
        self.client.force_authenticate(user=self.ctx['owner'])

        response = self.client.post(
            '/api/v1/partnerships/funds/',
            {
                'name': 'Business-side fund',
                'manager_partner_id': self.operator.id,
                'member_partner_ids': [],
                'currency': 'UZS',
                'target_amount': '5000',
                'visibility': InvestmentFund.Visibility.PRIVATE_INVITE,
                'manager_profit_share': '0',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(InvestmentFund.objects.filter(name='Business-side fund').exists())
