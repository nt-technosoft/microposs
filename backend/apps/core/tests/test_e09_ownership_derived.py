"""
E09 follow-up — goods_ownership is derived from settlement type, not a user choice.

After removal of MIXED:
  * Procurement.goods_ownership @property follows terms.type (ON_SALE → CONSIGNED, else OWNED).
  * Switching settlement type cascades the denormalized goods_ownership on draft items.
  * MIXED is no longer a legal combination.
"""

from django.test import SimpleTestCase, TestCase

from apps.partnerships.models import Procurement, ProcurementItem, ProcurementTerms
from apps.partnerships.policies import (
    LEGAL_COMBINATIONS,
    validate_procurement_combination,
)
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
)

from ._helpers import build_tenant

OWN_FUNDS = Procurement.FundingSource.OWN_FUNDS
PARTNERSHIP = Procurement.FundingSource.PARTNERSHIP
OWNED = Procurement.GoodsOwnership.OWNED
CONSIGNED = Procurement.GoodsOwnership.CONSIGNED
PREPAID = ProcurementTerms.Type.PREPAID
ON_SALE = ProcurementTerms.Type.ON_SALE


class NoMixedInLegalCombinationsTests(SimpleTestCase):
    def test_no_mixed_value_in_enum(self):
        self.assertFalse(hasattr(Procurement.GoodsOwnership, 'MIXED'))

    def test_legal_combinations_has_exactly_eight_points(self):
        self.assertEqual(len(LEGAL_COMBINATIONS), 8)

    def test_all_legal_combinations_use_owned_or_consigned(self):
        for _funding, _timing, ownership in LEGAL_COMBINATIONS:
            self.assertIn(ownership, (OWNED, CONSIGNED))


class OwnershipCascadeTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.tenant_id = self.ctx['business'].id

    def _proc(self):
        return create_workspace(tenant_id=self.tenant_id, funding_source=OWN_FUNDS)

    def _add_item(self, proc):
        dispatch_workspace_action(
            tenant_id=self.tenant_id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': 2, 'unit_purchase_price': '1000',
                    'currency': 'UZS', 'fx_rate': '1',
                }],
            }},
        )

    def test_empty_procurement_defaults_to_owned(self):
        proc = self._proc()
        self.assertEqual(proc.goods_ownership, OWNED)

    def test_prepaid_terms_yield_owned_items(self):
        proc = self._proc()
        self._add_item(proc)
        dispatch_workspace_action(
            tenant_id=self.tenant_id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': PREPAID}},
        )
        proc.refresh_from_db()
        self.assertEqual(proc.goods_ownership, OWNED)
        self.assertTrue(all(
            i.goods_ownership == OWNED for i in proc.items.all()
        ))

    def _attach_supplier(self, proc):
        return dispatch_workspace_action(
            tenant_id=self.tenant_id, procurement=proc,
            action='UPDATE_SOURCE',
            payload={'payload': {'supplier_id': self.ctx['supplier'].id}},
        )

    def test_on_sale_cascades_consigned_onto_existing_items(self):
        proc = self._proc()
        self._add_item(proc)
        proc = self._attach_supplier(proc)
        proc = dispatch_workspace_action(
            tenant_id=self.tenant_id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': ON_SALE}},
        )
        self.assertEqual(proc.goods_ownership, CONSIGNED)
        self.assertTrue(all(
            i.goods_ownership == CONSIGNED for i in proc.items.all()
        ))

    def test_switching_back_from_on_sale_restores_owned(self):
        proc = self._proc()
        self._add_item(proc)
        proc = self._attach_supplier(proc)
        proc = dispatch_workspace_action(
            tenant_id=self.tenant_id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': ON_SALE}},
        )
        proc = dispatch_workspace_action(
            tenant_id=self.tenant_id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': PREPAID}},
        )
        self.assertEqual(proc.goods_ownership, OWNED)
        self.assertTrue(all(
            i.goods_ownership == OWNED for i in proc.items.all()
        ))
