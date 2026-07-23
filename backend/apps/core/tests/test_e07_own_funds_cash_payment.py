from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashEntry, JournalEntry, Payment
from apps.partnerships.models import Procurement, ProcurementExpense, ProcurementItem
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
)

from ._helpers import build_tenant


class OwnFundsCashPaymentTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def test_pay_items_from_cash_account_without_procurement_balance_topup(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '10',
                'unit_purchase_price': '100',
                'currency': 'UZS',
                'fx_rate': '1',
            }]}},
        )
        item = procurement.items.get()

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id, 'item_ids': [item.id]}},
        )

        item = ProcurementItem.objects.get(procurement=procurement)
        self.assertEqual(item.lifecycle_state, ProcurementItem.LifecycleState.READY_FOR_RECEIVE)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal('4000.00'))

        cash_entry = CashEntry.objects.get(
            source_ref_type='finance_payment',
        )
        self.assertEqual(cash_entry.direction, CashEntry.Direction.OUT)
        self.assertEqual(cash_entry.amount, Decimal('1000.00'))

        payment = Payment.objects.get(target_type=Payment.TargetType.PROCUREMENT_COST, target_id=procurement.id)
        journal = JournalEntry.objects.get(operation_type='procurement_payment', operation_id=payment.id)
        lines = {
            line.account.code: (line.debit, line.credit)
            for line in journal.lines.select_related('account')
        }
        self.assertEqual(lines['1100'], (Decimal('1000.00'), Decimal('0.00')))
        self.assertEqual(lines['1000'], (Decimal('0.00'), Decimal('1000.00')))

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
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )
        self.assertFalse(
            JournalEntry.objects.filter(
                operation_type='receipt',
            ).exists()
        )

    def test_pay_expenses_from_cash_account(self):
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
                    'quantity': '1',
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
        expense = procurement.expenses.get()

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id, 'expense_ids': [expense.id]}},
        )

        expense = ProcurementExpense.objects.get(procurement=procurement)
        self.assertEqual(expense.lifecycle_state, ProcurementExpense.LifecycleState.READY_FOR_RECEIVE)
        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal('4750.00'))

    def test_cash_account_must_have_enough_money(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '100',
                'unit_purchase_price': '100',
                'currency': 'UZS',
                'fx_rate': '1',
            }]}},
        )

        with self.assertRaisesMessage(ValueError, 'Insufficient cash'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='PAY_COSTS',
                payload={'payload': {'cash_account_id': self.cash.id}},
            )
