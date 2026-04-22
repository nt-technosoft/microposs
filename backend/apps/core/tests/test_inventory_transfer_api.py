from rest_framework import status
from rest_framework.test import APITestCase

from ._helpers import build_tenant, seed_received_procurement


class InventoryTransferApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        _, cls.lot = seed_received_procurement(cls.ctx)

    def auth_owner(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_owner',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_transfer_rejects_same_source_and_destination(self):
        self.auth_owner()

        response = self.client.post(
            '/api/v1/inventory/stock/transfer/',
            {
                'lot_id': self.lot.id,
                'from_warehouse_id': self.ctx['storage'].id,
                'to_warehouse_id': self.ctx['storage'].id,
                'quantity': 1,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['to_warehouse_id'][0],
            'Склад назначения должен отличаться от склада отправления.',
        )
