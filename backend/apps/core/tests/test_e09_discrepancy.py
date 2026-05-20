"""
E09 Wave A — Slice 3: Discrepancy fields on ReceiveBatchLine tests.

Tests cover:
  * ACCEPT_AS_SHORTFALL closes item (qty_planned updated to received)
  * MISSING_EXPECTED_LATER keeps item open → procurement PARTIALLY_RECEIVED
  * discrepancy_reason required when qty_received < qty_planned
  * qty_received > qty_planned always rejected
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import (
    Procurement,
    ProcurementItem,
    ProcurementReceiveBatchLine,
    ProcurementTerms,
)
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)
from apps.finance.models import CashAccount

from ._helpers import build_tenant


def _build_prepaid_procurement(ctx, *, qty=100):
    """OWN_FUNDS PREPAID procurement with `qty` items, payment done."""
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    total = str(qty * 1000)
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_SETTLEMENT',
        payload={'payload': {
            'type': 'PREPAID', 'total_amount_due': total,
            'currency_of_obligation': 'UZS',
        }},
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {'items': [{
            'product_variant_id': ctx['variant'].id,
            'quantity': qty, 'unit_purchase_price': '1000',
            'currency': 'UZS', 'fx_rate': '1',
        }]}},
    )
    CashAccount.objects.filter(pk=ctx['cash_account'].pk).update(
        balance=Decimal(total) * 2,
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='PAY_COSTS',
        payload={'payload': {
            'cash_account_id': ctx['cash_account'].id,
            'amount': total, 'currency': 'UZS',
        }},
    )
    proc.refresh_from_db()
    return proc


class DiscrepancyAcceptShortfallTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_discrepancy_accept_shortfall_closes_item(self):
        """qty_planned=100, received=98, ACCEPT_AS_SHORTFALL → item RECEIVED with qty=98."""
        proc = _build_prepaid_procurement(self.ctx, qty=100)
        item = proc.items.first()
        receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'item_discrepancies': {
                    str(item.id): {
                        'qty_received': '98',
                        'discrepancy_reason': 'ACCEPT_AS_SHORTFALL',
                    },
                },
            },
        )
        item.refresh_from_db()
        self.assertEqual(item.lifecycle_state, ProcurementItem.LifecycleState.RECEIVED)
        self.assertEqual(item.quantity, Decimal('98'))

        line = ProcurementReceiveBatchLine.objects.get(item=item)
        self.assertEqual(line.quantity_planned, Decimal('100'))
        self.assertEqual(line.quantity_received, Decimal('98'))
        self.assertEqual(line.discrepancy_reason, ProcurementReceiveBatchLine.DiscrepancyReason.ACCEPT_AS_SHORTFALL)


class DiscrepancyMissingLaterTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_discrepancy_missing_later_keeps_open(self):
        """qty_planned=100, received=98, MISSING_EXPECTED_LATER → item stays open, procurement PARTIALLY_RECEIVED."""
        proc = _build_prepaid_procurement(self.ctx, qty=100)
        item = proc.items.first()
        receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'item_discrepancies': {
                    str(item.id): {
                        'qty_received': '98',
                        'discrepancy_reason': 'MISSING_EXPECTED_LATER',
                    },
                },
            },
        )
        item.refresh_from_db()
        proc.refresh_from_db()
        # Item should NOT be marked RECEIVED
        self.assertNotEqual(item.lifecycle_state, ProcurementItem.LifecycleState.RECEIVED)
        # Procurement remains PARTIALLY_RECEIVED (waiting for more)
        self.assertEqual(proc.status, Procurement.Status.PARTIALLY_RECEIVED)

        line = ProcurementReceiveBatchLine.objects.get(item=item)
        self.assertEqual(line.quantity_received, Decimal('98'))
        self.assertEqual(line.discrepancy_reason, ProcurementReceiveBatchLine.DiscrepancyReason.MISSING_EXPECTED_LATER)


class DiscrepancyValidationTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_discrepancy_without_reason_rejected(self):
        """qty_received < qty_planned without reason → ValueError."""
        proc = _build_prepaid_procurement(self.ctx, qty=100)
        item = proc.items.first()
        with self.assertRaises(ValueError, msg='Missing reason should be rejected'):
            receive_workspace_batch(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={
                    'warehouse_id': self.ctx['store'].id,
                    'item_discrepancies': {
                        str(item.id): {'qty_received': '90'},
                    },
                },
            )

    def test_discrepancy_over_received_rejected(self):
        """qty_received > qty_planned → ValueError."""
        proc = _build_prepaid_procurement(self.ctx, qty=100)
        item = proc.items.first()
        with self.assertRaises(ValueError, msg='Over-receive should be rejected'):
            receive_workspace_batch(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={
                    'warehouse_id': self.ctx['store'].id,
                    'item_discrepancies': {
                        str(item.id): {
                            'qty_received': '101',
                            'discrepancy_reason': 'NONE',
                        },
                    },
                },
            )
