"""
E09 Wave A — Slice 2: per-item goods_ownership refactor tests.

Tests cover:
  * Mixed procurement: 5 OWNED + 5 CONSIGNED items → correct Lot.is_owned per item
  * MIXED combination accepted by validator (OWN_FUNDS × PREPAID × MIXED)
  * PARTNERSHIP × PREPAID × MIXED rejected
  * OWN_FUNDS × ON_SALE × MIXED rejected
  * Procurement.goods_ownership @property returns OWNED / CONSIGNED / MIXED correctly
"""

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.policies import (
    LEGAL_COMBINATIONS,
    validate_procurement_combination,
)
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    receive_workspace_batch,
)
from apps.inventory.models import Lot

from ._helpers import build_tenant

OWN_FUNDS = Procurement.FundingSource.OWN_FUNDS
PARTNERSHIP = Procurement.FundingSource.PARTNERSHIP
OWNED = Procurement.GoodsOwnership.OWNED
CONSIGNED = Procurement.GoodsOwnership.CONSIGNED
MIXED = Procurement.GoodsOwnership.MIXED
PREPAID = ProcurementTerms.Type.PREPAID
ON_SALE = ProcurementTerms.Type.ON_SALE


class MixedCombinationValidatorTests(SimpleTestCase):
    """Validator checks for MIXED ownership (pure logic, no DB)."""

    def test_mixed_procurement_legal(self):
        validate_procurement_combination(OWN_FUNDS, PREPAID, MIXED)

    def test_mixed_partnership_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(PARTNERSHIP, PREPAID, MIXED)

    def test_mixed_on_sale_rejected(self):
        with self.assertRaises(ValueError):
            validate_procurement_combination(OWN_FUNDS, ON_SALE, MIXED)

    def test_mixed_combinations_in_legal_set(self):
        from apps.partnerships.policies import AT_RECEIPT, PARTIAL, DEFERRED, INSTALLMENT
        for timing in (PREPAID, AT_RECEIPT, PARTIAL, DEFERRED, INSTALLMENT):
            with self.subTest(timing=timing):
                self.assertIn((OWN_FUNDS, timing, MIXED), LEGAL_COMBINATIONS)


class ProcurementOwnershipPropertyTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def _make_procurement(self):
        return create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=OWN_FUNDS,
        )

    def test_procurement_ownership_property_empty_returns_owned(self):
        proc = self._make_procurement()
        self.assertEqual(proc.goods_ownership, OWNED)

    def test_procurement_ownership_property_owned_only(self):
        proc = self._make_procurement()
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [
                    {'product_variant_id': self.ctx['variant'].id,
                     'quantity': 10, 'unit_purchase_price': '1000',
                     'currency': 'UZS', 'fx_rate': '1', 'goods_ownership': 'OWNED'},
                ],
            }},
        )
        proc.refresh_from_db()
        self.assertEqual(proc.goods_ownership, OWNED)

    def test_procurement_ownership_property_mixed(self):
        proc = self._make_procurement()
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [
                    {'product_variant_id': self.ctx['variant'].id,
                     'quantity': 5, 'unit_purchase_price': '1000',
                     'currency': 'UZS', 'fx_rate': '1', 'goods_ownership': 'OWNED'},
                    {'product_variant_id': self.ctx['variant'].id,
                     'quantity': 5, 'unit_purchase_price': '800',
                     'currency': 'UZS', 'fx_rate': '1', 'goods_ownership': 'CONSIGNED'},
                ],
            }},
        )
        proc.refresh_from_db()
        self.assertEqual(proc.goods_ownership, MIXED)


class PerItemOwnershipLotCreationTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_per_item_ownership_lot_creation(self):
        """5 OWNED + 5 CONSIGNED items → 5 Lots is_owned=True, 5 is_owned=False."""
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=OWN_FUNDS,
        )
        # Set PREPAID terms (MIXED × OWN_FUNDS × PREPAID is legal)
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'PREPAID',
                'total_amount_due': '9000',
                'currency_of_obligation': 'UZS',
                'fx_rate_at_obligation': '1',
            }},
        )
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [
                    {'product_variant_id': self.ctx['variant'].id,
                     'quantity': i, 'unit_purchase_price': '1000',
                     'currency': 'UZS', 'fx_rate': '1',
                     'goods_ownership': 'OWNED' if i <= 5 else 'CONSIGNED'}
                    for i in range(1, 11)
                ],
            }},
        )

        # Pay so items move to READY_FOR_RECEIVE (PREPAID requirement)
        from apps.finance.models import CashAccount
        CashAccount.objects.filter(pk=self.ctx['cash_account'].pk).update(
            balance=Decimal('100000'),
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='PAY_COSTS',
            payload={'payload': {
                'cash_account_id': self.ctx['cash_account'].id,
                'amount': '9000',
                'currency': 'UZS',
            }},
        )
        proc.refresh_from_db()

        receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )

        owned_count = Lot.objects.filter(
            procurement_item__procurement=proc, is_owned=True,
        ).count()
        consigned_count = Lot.objects.filter(
            procurement_item__procurement=proc, is_owned=False,
        ).count()
        self.assertEqual(owned_count, 5, f'Expected 5 OWNED Lots, got {owned_count}')
        self.assertEqual(consigned_count, 5, f'Expected 5 CONSIGNED Lots, got {consigned_count}')
