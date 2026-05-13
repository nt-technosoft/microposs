"""
Wave 6 — History/analytics API tests for E02 (product↔supplier).
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.services import upsert_product_supplier_link
from apps.partnerships.models import Procurement
from apps.partnerships.services import (
    add_contribution,
    open_procurement,
    pay_procurement_items,
    receive_procurement,
)

from ._helpers import build_tenant


def _receive_procurement(ctx, qty=10, unit_price='100'):
    total = Decimal(qty) * Decimal(unit_price)
    proc = open_procurement(
        tenant_id=ctx['business'].id,
        procurement_type=Procurement.Type.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
        items=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal(qty),
            'unit_purchase_price': Decimal(unit_price),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
        }],
    )
    add_contribution(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        partner_id=ctx['operator'].id,
        amount=total, currency='UZS', fx_rate=Decimal('1'),
    )
    pay_procurement_items(tenant_id=ctx['business'].id, procurement_id=proc.id)
    receive_procurement(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        destination_warehouse_id=ctx['storage'].id,
        terms_payload={'type': 'PREPAID', 'total_amount_due': str(total)},
    )


class ProductSuppliersApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_lists_suppliers_for_product(self):
        self.auth()
        _receive_procurement(self.ctx, qty=10, unit_price='100')
        product = self.ctx['variant'].product
        res = self.client.get(f'/api/v1/catalog/products/{product.id}/suppliers/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        item = res.data[0]
        self.assertEqual(item['supplier_id'], self.ctx['supplier'].id)
        self.assertEqual(item['total_procurements_count'], 1)


class PreferredProductSortingTests(APITestCase):
    """Products list with ?supplier_id=X&order=preferred surfaces linked products first."""

    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_linked_product_is_first(self):
        self.auth()
        # Create a second product (un-linked to supplier)
        from apps.catalog.services import create_product_with_variants
        unlinked = create_product_with_variants(
            tenant_id=self.ctx['business'].id,
            name='Unlinked Product',
            category_id=None,
            base_price='50.00',
            pricing_mode='EDITABLE',
            variant_data=None,
        )
        # Link the original variant to supplier via a receipt
        _receive_procurement(self.ctx, qty=5, unit_price='100')

        res = self.client.get(
            f'/api/v1/catalog/products/?supplier_id={self.ctx["supplier"].id}&order=preferred'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data['results'] if 'results' in res.data else res.data
        # The product whose variant has supplier link comes first
        product_names = [it['name'] for it in items]
        self.assertEqual(product_names[0], self.ctx['variant'].product.name)


class SupplierProductsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_lists_products_for_supplier(self):
        self.auth()
        _receive_procurement(self.ctx, qty=10, unit_price='100')
        _receive_procurement(self.ctx, qty=5, unit_price='120')
        res = self.client.get(f'/api/v1/suppliers/suppliers/{self.ctx["supplier"].id}/products/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)  # same variant aggregated
        item = res.data[0]
        self.assertEqual(item['product_variant_id'], self.ctx['variant'].id)
        self.assertEqual(item['total_procurements_count'], 2)
        self.assertEqual(item['total_received_quantity'], '15.000')
        # last_* reflects newest receipt
        self.assertEqual(item['last_unit_price'], '120.000000')
