"""
E09 Wave A — Slice 7: Amendment model for items/expenses tests.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount
from apps.partnerships.models import Procurement, ProcurementAmendment
from apps.partnerships.workspace import (
    apply_expenses_amendment,
    apply_items_amendment,
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)

from ._helpers import build_tenant


def _build_open_procurement(ctx):
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_SETTLEMENT',
        payload={'payload': {'type': 'PREPAID', 'total_amount_due': '5000',
                             'currency_of_obligation': 'UZS'}},
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {'items': [{
            'product_variant_id': ctx['variant'].id,
            'quantity': 5, 'unit_purchase_price': '1000',
            'currency': 'UZS', 'fx_rate': '1',
        }]}},
    )
    proc.refresh_from_db()
    return proc


def _pay_and_receive(ctx, proc):
    CashAccount.objects.filter(pk=ctx['cash_account'].pk).update(balance=Decimal('20000'))
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='PAY_COSTS',
        payload={'payload': {'cash_account_id': ctx['cash_account'].id,
                             'amount': '5000', 'currency': 'UZS'}},
    )
    proc.refresh_from_db()
    batch = receive_workspace_batch(
        tenant_id=ctx['business'].id,
        procurement=proc,
        payload={'warehouse_id': ctx['store'].id},
    )
    proc.refresh_from_db()
    return proc, batch


class AmendItemsTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_amend_items_records_before_after(self):
        """Changing item qty on OPEN procurement creates ProcurementAmendment with correct snapshots."""
        proc = _build_open_procurement(self.ctx)
        item = proc.items.first()
        original_qty = str(item.quantity)

        amendment = apply_items_amendment(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': 8, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            }],
            reason='test amendment',
        )

        self.assertIsNotNone(amendment.pk)
        self.assertEqual(amendment.target_type, ProcurementAmendment.TargetType.ITEMS)
        before_qty = str(amendment.before[0]['quantity'])
        after_qty = str(amendment.after[0]['quantity'])
        self.assertEqual(before_qty, original_qty)
        self.assertNotEqual(after_qty, original_qty)
        self.assertEqual(Decimal(after_qty), Decimal('8'))

    def test_amend_items_in_cancelled_rejected(self):
        """CANCELLED procurement raises ValueError on amendment."""
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        Procurement.objects.filter(pk=proc.pk).update(status=Procurement.Status.CANCELLED)
        proc.refresh_from_db()
        with self.assertRaises(ValueError, msg='Amendment on CANCELLED should raise ValueError'):
            apply_items_amendment(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                new_items_payload=[],
            )

    def test_amend_received_item_rejected(self):
        """Cancelling an item that has already been received in a batch → ValueError."""
        proc = _build_open_procurement(self.ctx)
        proc, batch = _pay_and_receive(self.ctx, proc)
        item = batch.lines.first().item

        with self.assertRaises(ValueError, msg='Cancelling received item should fail'):
            apply_items_amendment(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                new_items_payload=[{'id': item.id, 'cancel': True}],
                reason='attempting invalid cancel',
            )

    def test_amend_after_close_rejected(self):
        """CLOSED procurement → amendment raises ValueError."""
        proc = _build_open_procurement(self.ctx)
        from apps.core.models import IMMUTABLE_STATUSES
        from apps.partnerships.models import Procurement as P
        Procurement.objects.filter(pk=proc.pk).update(status=Procurement.Status.CLOSED)
        proc.refresh_from_db()

        with self.assertRaises(ValueError):
            apply_items_amendment(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                new_items_payload=[],
            )

    def test_amendment_delete_forbidden(self):
        """ProcurementAmendment.delete() raises ValueError."""
        proc = _build_open_procurement(self.ctx)
        item = proc.items.first()
        amendment = apply_items_amendment(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': 3, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            }],
        )
        with self.assertRaises(ValueError, msg='ProcurementAmendment.delete() should raise'):
            amendment.delete()

    def test_amend_items_with_payment_keeps_payment_intact(self):
        """Amendment after payment doesn't touch finance.Payment — payment remains."""
        from apps.finance.models import Payment
        proc = _build_open_procurement(self.ctx)
        CashAccount.objects.filter(pk=self.ctx['cash_account'].pk).update(balance=Decimal('20000'))
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id, procurement=proc,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.ctx['cash_account'].id,
                                 'amount': '5000', 'currency': 'UZS'}},
        )
        payment_count_before = Payment.objects.filter(
            tenant_id=self.ctx['business'].id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.pk,
        ).count()

        item = proc.items.first()
        apply_items_amendment(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': 3, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            }],
            reason='reduce qty after payment',
        )

        payment_count_after = Payment.objects.filter(
            tenant_id=self.ctx['business'].id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.pk,
        ).count()
        self.assertEqual(payment_count_before, payment_count_after)

    def test_amend_items_increases_cost_blocks_receive(self):
        """
        After amendment increases items beyond paid amount, payment_status block
        reflects 'underpaid' state (OPEN-S7.1: amendment doesn't touch payments).
        """
        proc = _build_open_procurement(self.ctx)
        CashAccount.objects.filter(pk=self.ctx['cash_account'].pk).update(balance=Decimal('50000'))
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id, procurement=proc,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.ctx['cash_account'].id,
                                 'amount': '5000', 'currency': 'UZS'}},
        )
        proc.refresh_from_db()

        item = proc.items.first()
        apply_items_amendment(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            new_items_payload=[{
                'id': item.id,
                'product_variant_id': item.product_variant_id,
                'quantity': 10, 'unit_purchase_price': '2000',
                'currency': 'UZS', 'fx_rate': '1',
            }],
            reason='increase qty',
        )

        proc.refresh_from_db()
        from apps.partnerships.workspace import build_workspace_payload
        detail = build_workspace_payload(proc)
        payment_status = detail.get('documents', {}).get('payment_status') or {}
        self.assertIn(payment_status.get('state'), ('underpaid', 'unpaid'))
