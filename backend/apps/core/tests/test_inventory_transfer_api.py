from rest_framework import status
from rest_framework.test import APITestCase

from apps.inventory.models import StockMovement

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

    def test_stock_movements_can_filter_transfers_before_pagination(self):
        self.auth_owner()

        StockMovement.objects.create(
            tenant=self.ctx['business'],
            lot=self.lot,
            movement_type=StockMovement.MovementType.TRANSFER,
            quantity=3,
            from_location=self.ctx['storage'],
            to_location=self.ctx['store'],
            reference_type='transfer',
        )
        for index in range(25):
            StockMovement.objects.create(
                tenant=self.ctx['business'],
                lot=self.lot,
                movement_type=StockMovement.MovementType.SALE,
                quantity=-1,
                from_location=self.ctx['store'],
                reference_type='sale',
                reference_id=index + 1,
            )

        unfiltered = self.client.get('/api/v1/inventory/movements/', {'page': 1})
        filtered = self.client.get(
            '/api/v1/inventory/movements/',
            {'movement_type': 'transfer', 'page': 1, 'page_size': 6},
        )

        self.assertEqual(unfiltered.status_code, status.HTTP_200_OK)
        self.assertTrue(any(
            item['movement_type'] != StockMovement.MovementType.TRANSFER
            for item in unfiltered.data['results']
        ))
        self.assertEqual(filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(filtered.data['count'], 1)
        self.assertEqual(filtered.data['results'][0]['movement_type'], StockMovement.MovementType.TRANSFER)
