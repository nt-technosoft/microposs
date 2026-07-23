"""
E09 Wave A — Slice 5: Cancel procurement action tests.
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import Procurement
from apps.partnerships.workspace import (
    cancel_workspace_procurement,
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)
from apps.finance.models import CashAccount

from ._helpers import build_tenant


def _build_open_procurement(ctx):
    return create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )


def _add_payment(ctx, proc):
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
    return proc


class CancelProcurementTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_cancel_open_without_payments_succeeds(self):
        """OPEN procurement with no payments or batches → cancel OK."""
        proc = _build_open_procurement(self.ctx)
        result = cancel_workspace_procurement(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={},
        )
        self.assertEqual(result.status, Procurement.Status.CANCELLED)

    def test_cancel_draft_procurement_via_dispatch_succeeds(self):
        """CANCEL action via dispatch_workspace_action works."""
        proc = _build_open_procurement(self.ctx)
        result = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='CANCEL_PROCUREMENT',
            payload={'payload': {'reason': 'test cancel'}},
        )
        self.assertEqual(result.status, Procurement.Status.CANCELLED)

    def test_cancel_open_with_payment_rejected(self):
        """OPEN procurement with existing Payment → cancel raises ValueError."""
        proc = _build_open_procurement(self.ctx)
        proc = _add_payment(self.ctx, proc)
        with self.assertRaises(ValueError, msg='Cancelling paid procurement should fail'):
            cancel_workspace_procurement(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={},
            )

    def test_cancel_open_with_receive_rejected(self):
        """OPEN procurement with existing ReceiveBatch → cancel raises ValueError."""
        proc = _build_open_procurement(self.ctx)
        proc = _add_payment(self.ctx, proc)
        receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )
        proc.refresh_from_db()
        with self.assertRaises(ValueError, msg='Cancelling received procurement should fail'):
            cancel_workspace_procurement(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={},
            )

    def test_cancel_received_procurement_rejected(self):
        """RECEIVED procurement → always rejected."""
        proc = _build_open_procurement(self.ctx)
        proc = _add_payment(self.ctx, proc)
        receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.RECEIVED)
        with self.assertRaises(ValueError):
            cancel_workspace_procurement(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={},
            )
