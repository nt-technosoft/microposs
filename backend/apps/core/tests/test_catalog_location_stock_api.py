from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.sales.services import open_pos_session

from ._helpers import build_tenant, seed_received_procurement


class CatalogLocationStockApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        cls.procurement, cls.lot = seed_received_procurement(cls.ctx, qty=12)

    def auth_cashier(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_cashier',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_product_list_exposes_location_and_total_stock_separately(self):
        self.auth_cashier()

        response = self.client.get(
            '/api/v1/catalog/products/',
            {'location_id': self.ctx['store'].id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        row = next(item for item in rows if item['id'] == self.ctx['product'].id)
        self.assertEqual(row['total_stock'], 0)
        self.assertEqual(row['stock_at_location'], 0)
        self.assertEqual(row['total_stock_all_locations'], 12)
        self.assertEqual(row['availability_state'], 'warehouse_only')
        self.assertEqual(len(row['stock_by_location']), 1)
        self.assertEqual(row['stock_by_location'][0]['warehouse_id'], self.ctx['storage'].id)

    def test_product_detail_exposes_location_breakdown(self):
        self.auth_cashier()

        response = self.client.get(
            f'/api/v1/catalog/products/{self.ctx["product"].id}/',
            {'location_id': self.ctx['store'].id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stock_at_location'], 0)
        self.assertEqual(response.data['total_stock_all_locations'], 12)
        self.assertEqual(response.data['availability_state'], 'warehouse_only')
        self.assertEqual(response.data['variants'][0]['stock_at_location'], 0)
        self.assertEqual(response.data['variants'][0]['total_stock_all_locations'], 12)

    def test_sale_fails_when_stock_exists_only_in_storage(self):
        self.auth_cashier()
        session = open_pos_session(
            tenant_id=self.ctx['business'].id,
            location_id=self.ctx['store'].id,
            opened_by_id=self.ctx['cashier'].id,
            opening_cash=Decimal('0'),
        )

        response = self.client.post(
            '/api/v1/sales/sales/',
            {
                'pos_session_id': session.id,
                'lines': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': 1,
                    'unit_price': '240000.00',
                }],
                'payments': [{
                    'amount': '240000.00',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'method': 'CARD',
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'].code, 'insufficient_stock')
