from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.fx_rates import upsert_exchange_rate
from apps.finance.models import CashAccount
from apps.finance.models import ExchangeRate
from apps.finance.serializers import ProcurementProfitabilitySerializer
from apps.finance.services import record_owner_contribution
from apps.finance.services import get_procurement_profitability_rows
from apps.partnerships.advances import partner_capital_positions
from apps.partnerships.agreement_services import (
    agreement_close_blocking_reasons,
    agreement_pool_reconciliation_residual,
    agreement_profit_reinvestment_residual,
)
from apps.partnerships.lifecycle_services import (
    build_payout_decision_preview,
    create_agreement_terms_version,
    execute_payout_decision,
)
from apps.partnerships.models import (
    AgreementActionSource,
    AgreementConfirmationStatus,
    AgreementContribution,
    AgreementCurrencyPool,
    AgreementPartner,
    CapitalRollover,
    CurrencyConversionLot,
    InvestmentAgreement,
    PartnerPositionReadModel,
    PayoutDecision,
    PayoutObligation,
    PayoutPolicy,
    Procurement,
)
from apps.partnerships.read_models import rebuild_agreement_positions
from apps.partnerships.venture import procurement_venture_positions
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action
from apps.sales.models import PosSession, SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session


def _seed_uzs_received_procurement(ctx):
    procurement = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='CREATE_INVESTMENT_AGREEMENT',
        payload={'payload': {
            'mudaraba_ratio': Decimal('0.571429'),
            'planned_budget': Decimal('1000000.00'),
            'currency': 'UZS',
            'payout_policy': {
                'review_interval_days': 30,
                'minimum_available_amount': Decimal('1.00'),
                'minimum_days_between_payouts': 0,
                'reserve_amount': Decimal('0.00'),
                'allow_partial': True,
                'trigger_mode': PayoutPolicy.TriggerMode.ANY,
            },
            'partners': [
                {
                    'partner_id': ctx['investor'].id,
                    'role': 'INVESTOR',
                    'planned_capital_share': Decimal('700000.00'),
                    'profit_share': Decimal('0.4'),
                },
                {
                    'partner_id': ctx['operator'].id,
                    'role': 'OPERATOR',
                    'planned_capital_share': Decimal('300000.00'),
                    'profit_share': Decimal('0.6'),
                },
            ],
        }},
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='UPDATE_ITEMS',
        payload={'payload': {
            'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('100000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            'expenses': [],
        }},
    )
    for partner_id, amount in (
        (ctx['investor'].id, Decimal('700000.00')),
        (ctx['operator'].id, Decimal('300000.00')),
    ):
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': partner_id,
                'amount': amount,
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }},
        )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='ALLOCATE_CAPITAL',
        payload={'payload': {'allocations': [
            {
                'partner_id': ctx['investor'].id,
                'amount': Decimal('700000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            },
            {
                'partner_id': ctx['operator'].id,
                'amount': Decimal('300000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            },
        ]}},
    )
    return dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='RECEIVE_BATCH',
        payload={'payload': {'warehouse_id': ctx['storage'].id}},
    )


def _sell_half(ctx):
    session = PosSession.objects.filter(
        tenant=ctx['business'],
        location=ctx['store'],
        status=PosSession.SessionStatus.OPEN,
    ).first() or open_session(ctx)
    return create_sale(
        tenant_id=ctx['business'].id,
        pos_session_id=session.id,
        location_id=ctx['store'].id,
        sold_by_id=ctx['cashier'].id,
        customer_id=ctx['customer'].id,
        lines=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal('5'),
            'unit_price': Decimal('240000.00'),
        }],
        payments=[{
            'amount': Decimal('1200000.00'),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
            'method': SalePayment.Method.CASH,
            'account_id': ctx['cash_account'].id,
        }],
    )


class CapitalRolloverDecisionTests(TestCase):
    def test_rollover_moves_cash_to_pool_without_increasing_external_paid_in(self):
        ctx = build_tenant()
        procurement = _seed_uzs_received_procurement(ctx)
        _sell_half(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        rebuild_agreement_positions(agreement)

        before_venture = procurement_venture_positions(procurement=procurement)[ctx['investor'].id]
        before_paid_in = partner_capital_positions(agreement)[ctx['investor'].id]['paid_in']
        pool = CashAccount.objects.get(pk=agreement.capital_account_id)
        pool_before = pool.balance

        self.assertEqual(before_venture['capital_return_available_uzs'], Decimal('350000.00'))

        preview = build_payout_decision_preview(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('100000.00'),
            from_account_id=ctx['cash_account'].id,
        )
        self.assertTrue(preview['allowed'], preview['blocking_reasons'])

        result = execute_payout_decision(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('100000.00'),
            allocations=None,
            from_account_id=ctx['cash_account'].id,
            client_request_id='00000000-0000-0000-0000-000000000023',
            notes='test rollover',
        )

        self.assertEqual(result['decision_type'], PayoutDecision.DecisionType.ROLL_OVER_CAPITAL)
        rollover = CapitalRollover.objects.get(
            agreement=agreement,
            procurement=procurement,
            partner=ctx['investor'],
        )
        self.assertEqual(rollover.amount_uzs, Decimal('100000.00'))

        pool.refresh_from_db()
        self.assertEqual(pool.balance, pool_before + Decimal('100000.00'))
        self.assertEqual(agreement_pool_reconciliation_residual(agreement), Decimal('0.00'))
        self.assertEqual(
            partner_capital_positions(agreement)[ctx['investor'].id]['paid_in'],
            before_paid_in,
        )
        from apps.partnerships.workspace_common import _agreement_available_by_partner

        self.assertEqual(
            _agreement_available_by_partner(agreement)[ctx['investor'].id]['UZS'],
            Decimal('100000.00'),
        )

        after_venture = procurement_venture_positions(procurement=procurement)[ctx['investor'].id]
        self.assertEqual(after_venture['capital_rolled_to_pool_uzs'], Decimal('100000.00'))
        self.assertEqual(after_venture['capital_return_available_uzs'], Decimal('250000.00'))

        read_row = PartnerPositionReadModel.objects.get(
            agreement=agreement,
            procurement=procurement,
            partner=ctx['investor'],
            currency='UZS',
        )
        self.assertEqual(read_row.capital_rolled_to_pool_uzs, Decimal('100000.00'))
        self.assertEqual(read_row.capital_return_available_uzs, Decimal('250000.00'))

    def test_group_payout_and_rollover_settle_matching_capital_return_obligations(self):
        ctx = build_tenant()
        procurement = _seed_uzs_received_procurement(ctx)
        _sell_half(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        payout_obligation = PayoutObligation.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            procurement=procurement,
            recipient=ctx['investor'],
            kind=PayoutObligation.Kind.CAPITAL_RETURN,
            amount=Decimal('100000.00'),
            currency='UZS',
            due_at=timezone.now(),
        )

        payout = execute_payout_decision(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.PAY_OUT,
            amount_uzs=Decimal('100000.00'),
            allocations=None,
            from_account_id=ctx['cash_account'].id,
            client_request_id='00000000-0000-0000-0000-000000000025',
        )

        payout_obligation.refresh_from_db()
        self.assertEqual(payout['decision_type'], PayoutDecision.DecisionType.PAY_OUT)
        self.assertEqual(payout_obligation.status, PayoutObligation.Status.CONFIRMED)
        self.assertEqual(payout_obligation.paid_amount, Decimal('100000.00'))
        self.assertIsNotNone(payout_obligation.capital_withdrawal_id)

        rollover_obligation = PayoutObligation.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            procurement=procurement,
            recipient=ctx['investor'],
            kind=PayoutObligation.Kind.CAPITAL_RETURN,
            amount=Decimal('100000.00'),
            currency='UZS',
            due_at=timezone.now(),
        )
        execute_payout_decision(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('100000.00'),
            allocations=None,
            from_account_id=ctx['cash_account'].id,
            client_request_id='00000000-0000-0000-0000-000000000026',
        )

        rollover_obligation.refresh_from_db()
        self.assertEqual(rollover_obligation.status, PayoutObligation.Status.CONFIRMED)
        self.assertEqual(rollover_obligation.paid_amount, Decimal('100000.00'))
        self.assertIsNone(rollover_obligation.capital_withdrawal_id)

    def test_procurement_profitability_report_separates_rolled_capital(self):
        ctx = build_tenant()
        procurement = _seed_uzs_received_procurement(ctx)
        _sell_half(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        execute_payout_decision(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('100000.00'),
            allocations=None,
            from_account_id=ctx['cash_account'].id,
            client_request_id='00000000-0000-0000-0000-000000000024',
        )

        rows = get_procurement_profitability_rows(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        serialized = ProcurementProfitabilitySerializer(rows, many=True).data[0]

        self.assertEqual(serialized['venture_capital_recovered_uzs'], '500000.00')
        self.assertEqual(serialized['venture_capital_rolled_to_pool_uzs'], '100000.00')
        self.assertEqual(serialized['venture_capital_return_available_uzs'], '400000.00')

    def test_allocation_preview_aggregates_duplicates_and_caps_default_rows(self):
        ctx = build_tenant()
        agreement = InvestmentAgreement.objects.create(
            tenant=ctx['business'],
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('1000.00'),
            currency='UZS',
        )
        from apps.partnerships.workspace_support import get_or_create_agreement_capital_account

        get_or_create_agreement_capital_account(tenant_id=ctx['business'].id, agreement=agreement)
        create_agreement_terms_version(
            agreement=agreement,
            payout_policy={
                'minimum_available_amount': Decimal('1.00'),
                'minimum_days_between_payouts': 0,
                'trigger_mode': PayoutPolicy.TriggerMode.ANY,
            },
        )
        AgreementPartner.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            partner=ctx['investor'],
            role='INVESTOR',
            planned_capital_share=Decimal('1000.00'),
            profit_share=Decimal('0.50'),
        )
        first = Procurement.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        PartnerPositionReadModel.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            procurement=first,
            partner=ctx['investor'],
            currency='UZS',
            capital_return_available_uzs=Decimal('100.00'),
            available=Decimal('100.00'),
            computed_at=timezone.now(),
        )
        for index in range(100):
            procurement = Procurement.objects.create(
                tenant=ctx['business'],
                agreement=agreement,
                funding_source=Procurement.FundingSource.PARTNERSHIP,
                opened_at=timezone.now(),
            )
            PartnerPositionReadModel.objects.create(
                tenant=ctx['business'],
                agreement=agreement,
                procurement=procurement,
                partner=ctx['investor'],
                currency='UZS',
                capital_return_available_uzs=Decimal('1.00'),
                available=Decimal('1.00'),
                computed_at=timezone.now(),
            )
        record_owner_contribution(
            tenant_id=ctx['business'].id,
            amount=Decimal('2000.00'),
            currency='UZS',
            to_account_id=ctx['cash_account'].id,
        )

        duplicate = build_payout_decision_preview(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('160.00'),
            allocations=[
                {'procurement_id': first.id, 'partner_id': ctx['investor'].id, 'amount_uzs': Decimal('80.00')},
                {'procurement_id': first.id, 'partner_id': ctx['investor'].id, 'amount_uzs': Decimal('80.00')},
            ],
            from_account_id=ctx['cash_account'].id,
        )
        self.assertFalse(duplicate['allowed'])
        self.assertIn('exceeds available', ' '.join(duplicate['blocking_reasons']))

        defaulted = build_payout_decision_preview(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('99.40'),
            from_account_id=ctx['cash_account'].id,
        )
        self.assertTrue(defaulted['allowed'], defaulted['blocking_reasons'])
        self.assertEqual(
            sum(Decimal(row['amount_uzs']) for row in defaulted['allocations']),
            Decimal('99.40'),
        )
        for row in defaulted['allocations']:
            self.assertLessEqual(Decimal(row['amount_uzs']), Decimal(row['available_uzs']))

    def test_policy_amendment_preserves_trigger_mode_when_omitted(self):
        ctx = build_tenant()
        agreement = InvestmentAgreement.objects.create(
            tenant=ctx['business'],
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('1000.00'),
            currency='UZS',
        )
        create_agreement_terms_version(
            agreement=agreement,
            payout_policy={
                'minimum_available_amount': Decimal('100.00'),
                'minimum_days_between_payouts': 0,
                'trigger_mode': PayoutPolicy.TriggerMode.ALL,
            },
        )

        amended = create_agreement_terms_version(
            agreement=agreement,
            payout_policy={'minimum_available_amount': Decimal('200.00')},
        )

        self.assertEqual(amended.payout_policy.trigger_mode, PayoutPolicy.TriggerMode.ALL)
        self.assertEqual(amended.payout_policy.minimum_available_amount, Decimal('200.00'))

    def test_trigger_mode_all_uses_group_threshold_and_requires_interval(self):
        ctx = build_tenant()
        agreement = InvestmentAgreement.objects.create(
            tenant=ctx['business'],
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('1200.00'),
            currency='UZS',
        )
        from apps.partnerships.workspace_support import get_or_create_agreement_capital_account
        from apps.partnerships.lifecycle_services import create_agreement_terms_version

        get_or_create_agreement_capital_account(tenant_id=ctx['business'].id, agreement=agreement)
        create_agreement_terms_version(
            agreement=agreement,
            payout_policy={
                'review_interval_days': 30,
                'minimum_available_amount': Decimal('1000.00'),
                'minimum_days_between_payouts': 0,
                'trigger_mode': PayoutPolicy.TriggerMode.ALL,
            },
        )
        AgreementPartner.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            partner=ctx['investor'],
            role='INVESTOR',
            planned_capital_share=Decimal('1200.00'),
            profit_share=Decimal('0.50'),
        )
        first = Procurement.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        second = Procurement.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        for procurement in (first, second):
            PartnerPositionReadModel.objects.create(
                tenant=ctx['business'],
                agreement=agreement,
                procurement=procurement,
                partner=ctx['investor'],
                currency='UZS',
                capital_return_available_uzs=Decimal('600.00'),
                available=Decimal('600.00'),
                computed_at=timezone.now(),
            )
        record_owner_contribution(
            tenant_id=ctx['business'].id,
            amount=Decimal('2000.00'),
            currency='UZS',
            to_account_id=ctx['cash_account'].id,
        )

        blocked = build_payout_decision_preview(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.PAY_OUT,
            amount_uzs=Decimal('1000.00'),
            from_account_id=ctx['cash_account'].id,
        )
        self.assertFalse(blocked['allowed'])
        self.assertTrue(blocked['threshold_ready'])
        self.assertFalse(blocked['interval_ready'])

        agreement.current_terms.__class__.objects.filter(pk=agreement.current_terms_id).update(
            effective_at=timezone.now() - timedelta(days=31),
        )
        allowed = build_payout_decision_preview(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.PAY_OUT,
            amount_uzs=Decimal('1000.00'),
            from_account_id=ctx['cash_account'].id,
        )
        self.assertTrue(allowed['allowed'], allowed['blocking_reasons'])
        self.assertEqual(allowed['eligible_total_uzs'], '1200.00')

    def test_profit_reinvest_orphans_are_blocked_even_for_non_uzs_agreements(self):
        ctx = build_tenant()
        agreement = InvestmentAgreement.objects.create(
            tenant=ctx['business'],
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('100.00'),
            currency='USD',
        )
        AgreementContribution.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            partner=ctx['investor'],
            amount=Decimal('5.00'),
            currency='USD',
            fx_rate=Decimal('12000'),
            date=timezone.now(),
            source=AgreementActionSource.PROFIT_REINVEST,
            confirmation_status=AgreementConfirmationStatus.CONFIRMED,
        )

        self.assertEqual(agreement_profit_reinvestment_residual(agreement), Decimal('-5.00'))
        self.assertTrue(
            any('реинвест' in reason.lower() for reason in agreement_close_blocking_reasons(agreement=agreement))
        )

    def test_rollover_into_non_base_currency_pool_creates_cost_basis_lot(self):
        ctx = build_tenant()
        upsert_exchange_rate(
            tenant_id=ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='e23 rollover test',
        )
        agreement = InvestmentAgreement.objects.create(
            tenant=ctx['business'],
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio=Decimal('0.50'),
            planned_budget=Decimal('10.00'),
            currency='USD',
        )
        from apps.partnerships.workspace_support import get_or_create_agreement_capital_account
        from apps.partnerships.lifecycle_services import create_agreement_terms_version

        get_or_create_agreement_capital_account(tenant_id=ctx['business'].id, agreement=agreement)
        create_agreement_terms_version(
            agreement=agreement,
            payout_policy={
                'minimum_available_amount': Decimal('1.00'),
                'minimum_days_between_payouts': 0,
                'trigger_mode': PayoutPolicy.TriggerMode.ANY,
            },
        )
        AgreementPartner.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            partner=ctx['investor'],
            role='INVESTOR',
            planned_capital_share=Decimal('10.00'),
            profit_share=Decimal('0.50'),
        )
        procurement = Procurement.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            opened_at=timezone.now(),
        )
        PartnerPositionReadModel.objects.create(
            tenant=ctx['business'],
            agreement=agreement,
            procurement=procurement,
            partner=ctx['investor'],
            currency='UZS',
            capital_return_available_uzs=Decimal('120000.00'),
            available=Decimal('120000.00'),
            computed_at=timezone.now(),
        )
        record_owner_contribution(
            tenant_id=ctx['business'].id,
            amount=Decimal('120000.00'),
            currency='UZS',
            to_account_id=ctx['cash_account'].id,
        )

        execute_payout_decision(
            agreement=agreement,
            decision_type=PayoutDecision.DecisionType.ROLL_OVER_CAPITAL,
            amount_uzs=Decimal('120000.00'),
            allocations=None,
            from_account_id=ctx['cash_account'].id,
            client_request_id='00000000-0000-0000-0000-000000000123',
        )

        rollover = CapitalRollover.objects.get(agreement=agreement, procurement=procurement)
        self.assertEqual(rollover.currency, 'UZS')
        self.assertEqual(rollover.amount, Decimal('120000.00'))
        from apps.partnerships.workspace_common import _agreement_available_by_partner

        self.assertEqual(
            _agreement_available_by_partner(agreement)[ctx['investor'].id]['USD'],
            Decimal('10.000000'),
        )
        self.assertEqual(rollover.amount_uzs, Decimal('120000.00'))

        pool = AgreementCurrencyPool.objects.get(agreement=agreement, currency='UZS').cash_account
        pool.refresh_from_db()
        self.assertEqual(pool.balance, Decimal('120000.00'))
        lot = CurrencyConversionLot.objects.get(agreement=agreement, currency='UZS')
        self.assertEqual(lot.base_currency, 'USD')
        self.assertEqual(lot.amount_remaining, Decimal('120000.000000'))
        self.assertEqual(lot.base_cost_remaining, Decimal('10.000000'))


class CapitalRolloverApiGateTests(APITestCase):
    def test_direct_recovered_capital_return_requires_group_decision(self):
        ctx = build_tenant()
        procurement = _seed_uzs_received_procurement(ctx)
        _sell_half(ctx)
        self.client.force_authenticate(user=ctx['owner'])

        response = self.client.post(
            f'/api/v1/partnerships/agreements/{procurement.agreement_id}/withdrawals/',
            {
                'partner_id': ctx['investor'].id,
                'procurement_id': procurement.id,
                'from_account_id': ctx['cash_account'].id,
                'amount': '100000.00',
                'currency': 'UZS',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('group decision endpoint', str(response.data))

        obligation = PayoutObligation.objects.create(
            tenant=ctx['business'],
            agreement=procurement.agreement,
            procurement=procurement,
            recipient=ctx['investor'],
            kind=PayoutObligation.Kind.CAPITAL_RETURN,
            amount=Decimal('100000.00'),
            currency='UZS',
            due_at=timezone.now(),
        )
        with_obligation = self.client.post(
            f'/api/v1/partnerships/agreements/{procurement.agreement_id}/withdrawals/',
            {
                'partner_id': ctx['investor'].id,
                'procurement_id': procurement.id,
                'from_account_id': ctx['cash_account'].id,
                'amount': '100000.00',
                'currency': 'UZS',
                'payout_obligation_id': obligation.id,
            },
            format='json',
        )
        self.assertEqual(with_obligation.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('group decision endpoint', str(with_obligation.data))
