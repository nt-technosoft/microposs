from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from apps.inventory.models import Lot
from apps.partnerships.models import (
    Procurement,
    ProcurementBalance,
    ProcurementExpense,
    ProcurementItem,
    ProcurementTerms,
)
from apps.suppliers.models import SupplierPayable
from apps.partnerships.workspace import (
    build_workspace_payload,
    create_workspace,
    dispatch_workspace_action,
)

from ._helpers import build_tenant


class ProcurementWorkspaceContractTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def test_own_funds_cost_payment_and_receive_use_target_contracts(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.LOGISTICS,
                    'amount': '250',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1250',
            }},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id}},
        )
        self.assertEqual(
            set(procurement.items.values_list('lifecycle_state', flat=True)),
            {ProcurementItem.LifecycleState.READY_FOR_RECEIVE},
        )
        self.assertEqual(
            set(procurement.expenses.values_list('lifecycle_state', flat=True)),
            {ProcurementExpense.LifecycleState.READY_FOR_RECEIVE},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        procurement.refresh_from_db()
        self.assertEqual(procurement.status, Procurement.Status.RECEIVED)
        self.assertEqual(Lot.objects.filter(procurement_item__procurement=procurement).count(), 1)
        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['flow']['current_step'], 'history')
        self.assertEqual(
            [step['key'] for step in payload['flow']['steps']],
            [
                'purchase_intent',
                'supplier_settlement',
                'funding',
                'payment_obligation',
                'goods_receipt',
                'history',
            ],
        )
        self.assertEqual(payload['documents']['source']['funding_source'], Procurement.FundingSource.OWN_FUNDS)
        self.assertEqual(payload['summaries']['receive_batches_count'], 1)

    def test_quick_investment_agreement_switches_workspace_to_partnership(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='CREATE_INVESTMENT_AGREEMENT',
            payload={'payload': {
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('1000'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': self.ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('700'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': self.ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('300'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            }},
        )

        procurement.refresh_from_db()
        payload = build_workspace_payload(procurement)
        self.assertEqual(procurement.funding_source, Procurement.FundingSource.PARTNERSHIP)
        self.assertIsNotNone(procurement.agreement_id)
        self.assertEqual(payload['documents']['source']['funding_source'], Procurement.FundingSource.PARTNERSHIP)
        self.assertEqual(payload['flow']['current_step'], 'purchase_intent')

    def test_partnership_agreement_moves_to_capital_step_before_allocation_exists(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='CREATE_INVESTMENT_AGREEMENT',
            payload={'payload': {
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('1000'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': self.ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('700'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': self.ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('300'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            }},
        )

        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['flow']['current_step'], 'payment_obligation')
        self.assertNotIn(
            'PARTNERSHIP requires ProcurementBalance capital pool.',
            [row['message'] for row in payload['policy']['blocked_reasons']],
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': self.ctx['investor'].id,
                'cash_account_id': self.cash.id,
                'amount': '1000',
                'currency': 'UZS',
                'fx_rate': '1',
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {
                'allocations': [{
                    'partner_id': self.ctx['investor'].id,
                    'amount': '1000',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )

        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['flow']['current_step'], 'goods_receipt')
        self.assertTrue(payload['readiness']['capital_ready']['ok'])

    def test_split_item_action_keeps_expense_scope_for_partial_receive(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        item = procurement.items.get()
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_EXPENSES',
            payload={'payload': {
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.LOGISTICS,
                    'amount': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                    'target_item_ids': [item.id],
                }],
            }},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='SPLIT_ITEM',
            payload={'payload': {'item_id': item.id, 'quantity': '4'}},
        )

        quantities = sorted(procurement.items.values_list('quantity', flat=True))
        payload = build_workspace_payload(procurement)
        expense_targets = sorted(payload['documents']['expenses'][0]['target_item_ids'])
        self.assertEqual([str(value) for value in quantities], ['4.000', '6.000'])
        self.assertEqual(expense_targets, sorted(procurement.items.values_list('id', flat=True)))
        self.assertIn('SPLIT_ITEM', payload['policy']['allowed_actions'])

    def test_own_funds_zero_legacy_balance_does_not_block_workspace(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        ProcurementBalance.objects.create(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            balances={'USD': '0.00'},
        )

        payload = build_workspace_payload(procurement)

        self.assertNotIn(
            'OWN_FUNDS must not use ProcurementBalance.',
            [row['message'] for row in payload['policy']['blocked_reasons']],
        )

    def test_partial_settlement_requires_payment_and_creates_remainder_payable(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'PARTIAL',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
                'deadline_date': '2026-06-01',
            }},
        )

        with self.assertRaisesMessage(ValueError, 'PARTIAL settlement requires an upfront payment before receive.'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='RECEIVE_BATCH',
                payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
            )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {
                'cash_account_id': self.cash.id,
                'amount': '300',
                'currency': 'UZS',
            }},
        )

        terms = ProcurementTerms.objects.get(procurement=procurement)
        self.assertEqual(terms.paid_amount, Decimal('300.00'))
        self.assertEqual(terms.status, ProcurementTerms.Status.PARTIALLY_PAID)

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        payable = SupplierPayable.objects.get(procurement=procurement)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.paid_amount, Decimal('300.00'))
        self.assertEqual(payable.remaining_amount, Decimal('700.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.PARTIALLY_PAID)

    def test_deferred_settlement_receives_without_upfront_payment_and_creates_payable(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '5',
                    'unit_purchase_price': '200',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'DEFERRED',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
                'deadline_date': '2026-06-15',
            }},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        payable = SupplierPayable.objects.get(procurement=procurement)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.remaining_amount, Decimal('1000.00'))
        self.assertEqual(payable.deadline_date.isoformat(), '2026-06-15')
        self.assertEqual(build_workspace_payload(procurement)['flow']['current_step'], 'history')

    def test_installment_settlement_requires_schedule_before_receive(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '5',
                    'unit_purchase_price': '200',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'INSTALLMENT',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            }},
        )

        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['flow']['current_step'], 'supplier_settlement')
        self.assertIn('GENERATE_INSTALLMENT_SCHEDULE', payload['policy']['allowed_actions'])
        with self.assertRaisesMessage(ValueError, 'INSTALLMENT settlement requires payment schedule.'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='RECEIVE_BATCH',
                payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
            )

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='GENERATE_INSTALLMENT_SCHEDULE',
            payload={'payload': {
                'installments_count': 2,
                'first_due_date': '2026-06-01',
                'interval': 'MONTHLY',
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        terms = ProcurementTerms.objects.get(procurement=procurement)
        self.assertEqual(terms.schedule_entries.count(), 2)
        payable = SupplierPayable.objects.get(procurement=procurement)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))


class ProcurementWorkspaceFacadeApiTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.client.force_authenticate(user=self.ctx['owner'])
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def test_legacy_procurement_endpoint_is_workspace_facade(self):
        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': Procurement.FundingSource.OWN_FUNDS,
                'supplier_id': self.ctx['supplier'].id,
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
                'terms': {
                    'type': 'PREPAID',
                    'currency_of_obligation': 'UZS',
                    'total_amount_due': '1000',
                },
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        procurement_id = create_response.data['id']
        self.assertEqual(
            create_response.data['documents']['source']['funding_source'],
            Procurement.FundingSource.OWN_FUNDS,
        )

        pay_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/pay-items/',
            {'cash_account_id': self.cash.id},
            format='json',
        )
        self.assertEqual(pay_response.status_code, 200)
        self.assertEqual(
            pay_response.data['documents']['items'][0]['lifecycle_state'],
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        )

        receive_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/receive/',
            {'destination_warehouse_id': self.ctx['storage'].id},
            format='json',
        )
        self.assertEqual(receive_response.status_code, 200)
        self.assertEqual(receive_response.data['status'], Procurement.Status.RECEIVED)
