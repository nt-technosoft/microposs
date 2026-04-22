from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.inventory.models import Warehouse
from apps.sales.models import PosSession

from ._helpers import build_tenant


class PosSessionApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_cashier(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_cashier',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_cashier_can_open_session_and_see_cash_preview(self):
        self.auth_cashier()

        response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['store'].id,
                'opening_cash': '125000.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], PosSession.SessionStatus.OPEN)
        self.assertEqual(response.data['opening_cash'], '125000.00')
        self.assertEqual(response.data['cash_sales_total'], '0.00')
        self.assertEqual(response.data['sales_count'], 0)

    def test_cannot_open_second_session_for_same_location(self):
        self.auth_cashier()

        first_response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['store'].id,
                'opening_cash': '0.00',
            },
            format='json',
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['store'].id,
                'opening_cash': '50000.00',
            },
            format='json',
        )

        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            second_response.data['detail'],
            'На этой точке уже есть открытая смена.',
        )

    def test_cannot_open_session_for_storage_location(self):
        self.auth_cashier()

        response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['storage'].id,
                'opening_cash': '0.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['detail'],
            'Смену можно открыть только на магазине.',
        )

    def test_cannot_open_second_session_for_same_user(self):
        self.auth_cashier()
        second_store = Warehouse.objects.create(
            tenant=self.ctx['business'],
            name='Second Store',
            kind=Warehouse.WarehouseKind.SHOP,
            is_active=True,
        )

        first_response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['store'].id,
                'opening_cash': '0.00',
            },
            format='json',
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': second_store.id,
                'opening_cash': '50000.00',
            },
            format='json',
        )

        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            second_response.data['detail'],
            'У вас уже есть открытая смена.',
        )

    def test_cannot_close_already_closed_session(self):
        self.auth_cashier()

        open_response = self.client.post(
            '/api/v1/sales/sessions/open/',
            {
                'location_id': self.ctx['store'].id,
                'opening_cash': '100000.00',
            },
            format='json',
        )
        self.assertEqual(open_response.status_code, status.HTTP_201_CREATED)
        session_id = open_response.data['id']

        close_response = self.client.post(
            f'/api/v1/sales/sessions/{session_id}/close/',
            {'actual_cash': '100000.00'},
            format='json',
        )
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)

        second_close = self.client.post(
            f'/api/v1/sales/sessions/{session_id}/close/',
            {'actual_cash': '100000.00'},
            format='json',
        )
        self.assertEqual(second_close.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            second_close.data['detail'],
            'Можно закрыть только открытую смену.',
        )

        session = PosSession.objects.get(pk=session_id)
        self.assertEqual(session.actual_cash, Decimal('100000.00'))
        self.assertEqual(session.cash_difference, Decimal('0.00'))
