from decimal import Decimal

from django.db import models
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.core.models import Business
from apps.finance.models import Payment
from apps.inventory.models import Lot
from apps.partnerships.models import (
    Procurement,
    ProcurementExpense,
    ProcurementExpenseTarget,
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

    def test_updating_expense_targets_keeps_existing_links(self):
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
                'items': [
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '10',
                        'unit_purchase_price': '100',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '5',
                        'unit_purchase_price': '200',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                ],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '250',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                }],
            }},
        )
        item_ids = list(procurement.items.order_by('id').values_list('id', flat=True))
        expense = procurement.expenses.get()

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_EXPENSES',
            payload={'payload': {'expenses': [{
                'id': expense.id,
                'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                'amount': '250',
                'currency': 'UZS',
                'fx_rate': '1',
                'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                'target_item_ids': [item_ids[0]],
            }]}},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_EXPENSES',
            payload={'payload': {'expenses': [{
                'id': expense.id,
                'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                'amount': '250',
                'currency': 'UZS',
                'fx_rate': '1',
                'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                'target_item_ids': item_ids,
            }]}},
        )

        self.assertEqual(
            set(ProcurementExpenseTarget.objects.filter(expense=expense).values_list('item_id', flat=True)),
            set(item_ids),
        )

    def test_partial_receive_prorates_shared_expense_and_keeps_remainder(self):
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
                'items': [
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                ],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '300',
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
                'total_amount_due': '2300',
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id}},
        )

        first_item, second_item = list(procurement.items.order_by('id'))
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': self.ctx['storage'].id,
                'item_ids': [first_item.id],
            }},
        )

        expense = procurement.expenses.get()
        batch_expense = expense.receive_batch_expenses.get()
        self.assertEqual(batch_expense.allocated_amount_uzs, Decimal('150.00'))
        expense.refresh_from_db()
        self.assertEqual(expense.lifecycle_state, ProcurementExpense.LifecycleState.READY_FOR_RECEIVE)
        payment_status = build_workspace_payload(procurement)['documents']['payment_status']
        self.assertEqual(payment_status['state'], 'paid_full')
        self.assertEqual(payment_status['obligation_amount'], '2300.00')
        self.assertEqual(payment_status['paid_amount'], '2300.00')

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': self.ctx['storage'].id,
                'item_ids': [second_item.id],
            }},
        )

        expense.refresh_from_db()
        self.assertEqual(expense.lifecycle_state, ProcurementExpense.LifecycleState.RECEIVED)
        self.assertEqual(
            expense.receive_batch_expenses.aggregate(total=models.Sum('allocated_amount_uzs'))['total'],
            Decimal('300.00'),
        )

    def test_paid_unreceived_lines_can_be_amended_but_not_cancelled(self):
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
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '300',
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
                'total_amount_due': '1300',
            }},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id}},
        )
        item = procurement.items.get()
        expense = procurement.expenses.get()

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='AMEND_ITEMS',
            payload={'payload': {
                'reason': 'Supplier corrected quantity before delivery.',
                'items': [{
                    'id': item.id,
                    'product_variant_id': item.product_variant_id,
                    'quantity': '12',
                    'unit_purchase_price': '90',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        item.refresh_from_db()
        self.assertEqual(item.lifecycle_state, ProcurementItem.LifecycleState.READY_FOR_RECEIVE)
        self.assertEqual(item.quantity, Decimal('12.000'))
        self.assertEqual(item.unit_purchase_price, Decimal('90.000000'))

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='AMEND_EXPENSES',
            payload={'payload': {
                'reason': 'Customs amount corrected before receipt.',
                'expenses': [{
                    'id': expense.id,
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '350',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                }],
            }},
        )
        expense.refresh_from_db()
        self.assertEqual(expense.lifecycle_state, ProcurementExpense.LifecycleState.READY_FOR_RECEIVE)
        self.assertEqual(expense.amount, Decimal('350.00'))

        payload = build_workspace_payload(procurement)
        payment_status = payload['documents']['payment_status']
        self.assertEqual(payment_status['state'], 'underpaid')
        self.assertEqual(payment_status['obligation_amount'], '1430.00')
        self.assertEqual(payment_status['paid_amount'], '1300.00')
        self.assertEqual(payment_status['remaining_by_currency']['UZS'], '130.00')

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {
                'cash_account_id': self.cash.id,
                'amount': '130',
                'currency': 'UZS',
            }},
        )
        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['documents']['payment_status']['state'], 'paid_full')
        self.assertEqual(
            Payment.objects.filter(
                tenant_id=self.ctx['business'].id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=procurement.id,
            ).count(),
            2,
        )

        with self.assertRaisesMessage(ValueError, 'only DRAFT lines can be removed'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='AMEND_ITEMS',
                payload={'payload': {
                    'reason': 'Try invalid remove.',
                    'items': [{'id': item.id, '_cancel': True}],
                }},
            )

        with self.assertRaisesMessage(ValueError, 'only DRAFT expenses can be removed'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='AMEND_EXPENSES',
                payload={'payload': {
                    'reason': 'Try invalid remove.',
                    'expenses': [{'id': expense.id, '_cancel': True}],
                }},
            )

        self.assertTrue(any(event['kind'] == 'PROCUREMENT_AMENDMENT' for event in payload['history']))

    def test_partially_received_expense_amendment_reallocates_only_remaining_amount(self):
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
                'items': [
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                ],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '300',
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
                'type': 'DEFERRED',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '2300',
                'deadline_date': '2026-06-01',
            }},
        )
        first_item, second_item = list(procurement.items.order_by('id'))
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': self.ctx['storage'].id,
                'item_ids': [first_item.id],
            }},
        )
        expense = procurement.expenses.get()
        self.assertEqual(expense.receive_batch_expenses.get().allocated_amount_uzs, Decimal('150.00'))

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='AMEND_EXPENSES',
            payload={'payload': {
                'reason': 'Customs invoice increased after first batch.',
                'expenses': [{
                    'id': expense.id,
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '500',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                }],
            }},
        )
        expense.refresh_from_db()
        self.assertEqual(expense.lifecycle_state, ProcurementExpense.LifecycleState.READY_FOR_RECEIVE)

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': self.ctx['storage'].id,
                'item_ids': [second_item.id],
            }},
        )
        expense.refresh_from_db()
        allocations = list(expense.receive_batch_expenses.order_by('id').values_list('allocated_amount_uzs', flat=True))
        self.assertEqual(allocations, [Decimal('150.00'), Decimal('350.00')])
        self.assertEqual(sum(allocations, Decimal('0.00')), Decimal('500.00'))

    def test_partially_received_expense_cannot_be_reduced_below_allocated_amount(self):
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
                'items': [
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                    {
                        'product_variant_id': self.ctx['variant'].id,
                        'quantity': '1',
                        'unit_purchase_price': '1000',
                        'currency': 'UZS',
                        'fx_rate': '1',
                    },
                ],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                    'amount': '300',
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
                'type': 'DEFERRED',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '2300',
                'deadline_date': '2026-06-01',
            }},
        )
        first_item = procurement.items.order_by('id').first()
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': self.ctx['storage'].id,
                'item_ids': [first_item.id],
            }},
        )
        expense = procurement.expenses.get()

        with self.assertRaisesMessage(ValueError, 'below already received amount'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='AMEND_EXPENSES',
                payload={'payload': {
                    'reason': 'Invalid decrease.',
                    'expenses': [{
                        'id': expense.id,
                        'expense_type': ProcurementExpense.ExpenseType.CUSTOMS,
                        'amount': '100',
                        'currency': 'UZS',
                        'fx_rate': '1',
                        'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                    }],
                }},
            )

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

    def test_workspace_api_requires_unambiguous_business_context(self):
        Business.objects.create(
            name='Second active business',
            owner=self.ctx['owner'],
            currency='UZS',
            is_active=True,
        )

        response = self.client.post(
            '/api/v1/procurement-workspaces/',
            {'funding_source': Procurement.FundingSource.OWN_FUNDS},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            str(response.data['detail']),
            'Business context is required for procurement workspace operations.',
        )
