"""
E09 Wave A — Slice 6: Reverse receive batch action tests.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount
from apps.inventory.models import Lot, LotStock, StockMovement
from apps.partnerships.models import Procurement, ProcurementReceiveBatch
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
    reverse_workspace_receive_batch,
)
from apps.sales.services import create_sale, open_pos_session
from apps.inventory.services import transfer_lot_stock

from ._helpers import build_tenant


def _build_received_procurement(ctx):
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


class ReverseReceiveBatchTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_reverse_receive_creates_inverse_batch(self):
        """Reversing a batch creates an is_reversal=True batch; net stock effect is zero."""
        proc, batch = _build_received_procurement(self.ctx)

        lot_ids = list(batch.lines.values_list('lot_id', flat=True))
        stock_before = (
            LotStock.objects
            .filter(lot_id__in=lot_ids, warehouse_id=self.ctx['store'].id)
            .first()
        )
        qty_before = stock_before.quantity_remaining

        reversal = reverse_workspace_receive_batch(
            tenant_id=self.ctx['business'].id,
            batch_id=batch.id,
            reason='test reversal',
        )

        self.assertTrue(reversal.is_reversal)
        self.assertEqual(reversal.reversed_batch_id, batch.id)
        self.assertEqual(reversal.total_inventory_uzs, -batch.total_inventory_uzs)

        stock_after = LotStock.objects.get(lot_id__in=lot_ids, warehouse_id=self.ctx['store'].id)
        self.assertEqual(stock_after.quantity_remaining, 0)

        reversal_movement = StockMovement.objects.filter(
            reference_type='procurement_receive_batch_reversal',
            reference_id=reversal.id,
        ).first()
        self.assertIsNotNone(reversal_movement)
        self.assertEqual(reversal_movement.quantity, -qty_before)

    def test_reverse_receive_marks_lots_reversed(self):
        """All lots from original batch are marked reversed=True after reversal."""
        proc, batch = _build_received_procurement(self.ctx)
        lot_ids = list(batch.lines.values_list('lot_id', flat=True))

        reverse_workspace_receive_batch(
            tenant_id=self.ctx['business'].id,
            batch_id=batch.id,
        )

        reversed_count = Lot.objects.filter(pk__in=lot_ids, reversed=True).count()
        self.assertEqual(reversed_count, len(lot_ids))

    def test_reverse_receive_changes_procurement_status(self):
        """RECEIVED → OPEN when all batches are reversed (no remaining active batches)."""
        proc, batch = _build_received_procurement(self.ctx)
        self.assertEqual(proc.status, Procurement.Status.RECEIVED)

        reverse_workspace_receive_batch(
            tenant_id=self.ctx['business'].id,
            batch_id=batch.id,
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.OPEN)

    def test_lot_reversed_excluded_from_fifo(self):
        """Reversed lot does not appear in FIFO allocation for sales."""
        from apps.inventory.services import allocate_lot, InsufficientStockError

        proc, batch = _build_received_procurement(self.ctx)
        lot_ids = list(batch.lines.values_list('lot_id', flat=True))

        reverse_workspace_receive_batch(
            tenant_id=self.ctx['business'].id,
            batch_id=batch.id,
        )

        with self.assertRaises(InsufficientStockError):
            allocate_lot(
                tenant_id=self.ctx['business'].id,
                warehouse_id=self.ctx['store'].id,
                product_variant_id=self.ctx['variant'].id,
                quantity=1,
            )

    def test_reverse_already_reversed_batch_rejected(self):
        """Attempting to reverse an already-reversed batch raises ValueError."""
        proc, batch = _build_received_procurement(self.ctx)
        reverse_workspace_receive_batch(
            tenant_id=self.ctx['business'].id,
            batch_id=batch.id,
        )
        with self.assertRaises(ValueError, msg='Double-reversal should raise ValueError'):
            reverse_workspace_receive_batch(
                tenant_id=self.ctx['business'].id,
                batch_id=batch.id,
            )

    def test_reverse_receive_batch_with_sold_lot_rejected(self):
        """STRICT: if any lot from batch has been sold, reversal raises ValueError with lot ID."""
        proc, batch = _build_received_procurement(self.ctx)
        lot_ids = list(batch.lines.values_list('lot_id', flat=True))

        session = open_pos_session(
            tenant_id=self.ctx['business'].id,
            location_id=self.ctx['store'].id,
            opened_by_id=self.ctx['cashier'].id,
            opening_cash=Decimal('0'),
        )
        create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=None,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 1,
                'unit_price': '1500',
            }],
            payments=[{'amount': '1500', 'currency': 'UZS', 'method': 'CASH',
                        'account_id': self.ctx['cash_account'].id}],
        )

        with self.assertRaises(ValueError) as cm:
            reverse_workspace_receive_batch(
                tenant_id=self.ctx['business'].id,
                batch_id=batch.id,
            )
        error_msg = str(cm.exception)
        self.assertIn('sales', error_msg.lower())
        sold_lot_id = str(lot_ids[0])
        self.assertIn(sold_lot_id, error_msg)
