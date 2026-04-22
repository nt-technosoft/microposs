from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from ._helpers import build_tenant, open_session, seed_received_procurement


class SalesLocationApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        seed_received_procurement(cls.ctx)
        cls.session = open_session(cls.ctx)

    def auth_cashier(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_cashier',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_sale_rejects_location_mismatch_with_open_session(self):
        self.auth_cashier()

        response = self.client.post(
            '/api/v1/sales/sales/',
            {
                'pos_session_id': self.session.id,
                'location_id': self.ctx['storage'].id,
                'lines': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': 1,
                    'unit_price': '240000.00',
                }],
                'payments': [{
                    'amount': '240000.00',
                    'currency': 'UZS',
                    'fx_rate': str(Decimal('1')),
                    'method': 'CARD',
                }],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['detail'],
            'Продажа должна оформляться из точки открытой смены.',
        )
