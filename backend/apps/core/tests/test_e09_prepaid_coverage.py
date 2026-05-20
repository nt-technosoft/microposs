"""
E09 Wave A — Slice 8: Multi-payment + PREPAID receive coverage constraint.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount
from apps.partnerships.models import Procurement
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)

from ._helpers import build_tenant


def _build_prepaid_procurement(ctx, *, total_amount='10000'):
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_SETTLEMENT',
        payload={'payload': {'type': 'PREPAID', 'total_amount_due': total_amount,
                             'currency_of_obligation': 'UZS'}},
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {'items': [
            {
                'product_variant_id': ctx['variant'].id,
                'quantity': 5, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            },
            {
                'product_variant_id': ctx['variant'].id,
                'quantity': 5, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            },
        ]}},
    )
    proc.refresh_from_db()
    return proc


def _pay(ctx, proc, amount):
    CashAccount.objects.filter(pk=ctx['cash_account'].pk).update(balance=Decimal('100000'))
    dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=proc,
        action='PAY_COSTS',
        payload={'payload': {'cash_account_id': ctx['cash_account'].id,
                             'amount': str(amount), 'currency': 'UZS'}},
    )
    proc.refresh_from_db()


class PrepaidCoverageTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_prepaid_full_receive_after_full_payment_ok(self):
        """Paid 100% → receive 100% items succeeds."""
        proc = _build_prepaid_procurement(self.ctx)
        _pay(self.ctx, proc, '10000')
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )
        self.assertIsNotNone(batch.pk)
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.RECEIVED)

    def test_prepaid_full_receive_with_partial_payment_rejected(self):
        """Paid 50% → attempt to receive all 10 items → ValueError."""
        proc = _build_prepaid_procurement(self.ctx)
        _pay(self.ctx, proc, '5000')
        with self.assertRaises(ValueError, msg='Receiving beyond paid amount should fail'):
            receive_workspace_batch(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={'warehouse_id': self.ctx['store'].id},
            )

    def test_prepaid_partial_receive_with_partial_payment_ok(self):
        """Paid 5000 UZS → can receive exactly 5 items (5000 cost) — OK."""
        proc = _build_prepaid_procurement(self.ctx)
        items = list(proc.items.order_by('id'))
        _pay(self.ctx, proc, '5000')
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'item_ids': [items[0].id],
            },
        )
        self.assertIsNotNone(batch.pk)
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.PARTIALLY_RECEIVED)

    def test_deferred_receive_without_payment_ok(self):
        """DEFERRED + receive without upfront payment is allowed (pay-later model)."""
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'DEFERRED', 'total_amount_due': '5000',
                                 'currency_of_obligation': 'UZS',
                                 'deadline_date': '2027-01-01'}},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id, procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 5, 'unit_purchase_price': '1000',
                'currency': 'UZS', 'fx_rate': '1',
            }]}},
        )
        proc.refresh_from_db()
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )
        self.assertIsNotNone(batch.pk)
