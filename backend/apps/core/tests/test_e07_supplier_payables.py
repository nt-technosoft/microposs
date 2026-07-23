from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import JournalEntry, Payment
from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action
from apps.suppliers.models import SupplierPayable
from apps.suppliers.models import PaymentSchedule

from ._helpers import build_tenant


class SupplierPayableWorkspaceTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def _deferred_procurement(self):
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
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': ProcurementTerms.Type.DEFERRED,
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
                'deadline_date': timezone.localdate(),
            }},
        )
        return procurement

    def test_deferred_receive_creates_payable_and_supplier_balance(self):
        procurement = self._deferred_procurement()

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        payable = SupplierPayable.objects.get(procurement=procurement)
        self.assertEqual(payable.settlement_id, procurement.terms.id)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.remaining_amount, Decimal('1000.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.OPEN)

        self.ctx['supplier'].refresh_from_db()
        self.assertEqual(self.ctx['supplier'].outstanding_balance, Decimal('1000.00'))

        journal = JournalEntry.objects.get(operation_type='receipt', operation_id=procurement.receive_batches.get().id)
        lines = {
            line.account.code: (line.debit, line.credit)
            for line in journal.lines.select_related('account')
        }
        self.assertEqual(lines['1100'], (Decimal('1000.00'), Decimal('0.00')))
        self.assertEqual(lines['2000'], (Decimal('0.00'), Decimal('1000.00')))

    def test_pay_supplier_payable_posts_generic_payment_cash_and_journal(self):
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self._deferred_procurement(),
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )
        payable = SupplierPayable.objects.get(procurement=procurement)

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_SUPPLIER_PAYABLE',
            payload={'payload': {
                'payable_id': payable.id,
                'cash_account_id': self.cash.id,
                'amount': '1000',
                'currency': 'UZS',
            }},
        )

        payable.refresh_from_db()
        self.assertEqual(payable.status, SupplierPayable.Status.FULLY_PAID)
        self.assertEqual(payable.remaining_amount, Decimal('0.00'))

        self.cash.refresh_from_db()
        self.assertEqual(self.cash.balance, Decimal('4000.00'))
        self.ctx['supplier'].refresh_from_db()
        self.assertEqual(self.ctx['supplier'].outstanding_balance, Decimal('0.00'))

        payment = Payment.objects.get(
            target_type=Payment.TargetType.SUPPLIER_PAYABLE,
            target_id=payable.id,
        )
        self.assertEqual(payment.amount, Decimal('1000.00'))
        journal = payment.journal_entry
        lines = {
            line.account.code: (line.debit, line.credit)
            for line in journal.lines.select_related('account')
        }
        self.assertEqual(lines['2000'], (Decimal('1000.00'), Decimal('0.00')))
        self.assertEqual(lines['1000'], (Decimal('0.00'), Decimal('1000.00')))

    def test_installment_schedule_can_be_generated_before_receive(self):
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
                'quantity': '3',
                'unit_purchase_price': '100',
                'currency': 'UZS',
                'fx_rate': '1',
            }]}},
        )
        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': ProcurementTerms.Type.INSTALLMENT,
                'currency_of_obligation': 'UZS',
                'total_amount_due': '300',
            }},
        )
        with self.assertRaisesMessage(ValueError, 'INSTALLMENT settlement requires payment schedule.'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=procurement,
                action='RECEIVE_BATCH',
                payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
            )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='GENERATE_INSTALLMENT_SCHEDULE',
            payload={'payload': {
                'installments_count': 3,
                'first_due_date': '2026-06-01',
                'interval': 'MONTHLY',
            }},
        )

        rows = list(PaymentSchedule.objects.filter(procurement_terms=procurement.terms).order_by('sequence_number'))
        self.assertEqual([row.amount for row in rows], [
            Decimal('100.00'),
            Decimal('100.00'),
            Decimal('100.00'),
        ])
        self.assertEqual([row.due_date.isoformat() for row in rows], [
            '2026-06-01',
            '2026-07-01',
            '2026-08-01',
        ])

        payload = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )
        payable = SupplierPayable.objects.get(procurement=payload)
        self.assertEqual(payable.status, SupplierPayable.Status.OPEN)
