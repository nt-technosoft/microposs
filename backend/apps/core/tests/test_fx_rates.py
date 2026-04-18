from datetime import date
from decimal import Decimal

from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Business
from apps.finance.models import ExchangeRate, Expense


class FxRateApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('bootstrap_demo')
        cls.tenant = Business.objects.order_by('id').first()
        assert cls.tenant is not None

    def _auth_owner(self) -> None:
        token_response = self.client.post('/api/v1/auth/token/', {
            'username': 'owner',
            'password': 'Owner123!',
        }, format='json')
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access = token_response.data.get('access')
        self.assertTrue(access)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_owner_can_create_manual_rate_and_read_latest(self):
        self._auth_owner()

        create_response = self.client.post('/api/v1/finance/fx-rates/manual/', {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
            'rate_date': '2026-04-16',
            'rate': '12650.000000',
            'notes': 'Manual market close rate',
        }, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['base_currency'], 'USD')
        self.assertEqual(create_response.data['quote_currency'], 'UZS')
        self.assertEqual(create_response.data['source'], 'MANUAL')
        self.assertTrue(create_response.data['is_manual'])

        latest_response = self.client.get('/api/v1/finance/fx-rates/latest/', {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
            'on_date': '2026-04-16',
        })
        self.assertEqual(latest_response.status_code, status.HTTP_200_OK)
        self.assertEqual(latest_response.data['rate'], '12650.000000')

    def test_expense_uses_stored_rate_when_fx_not_passed(self):
        self._auth_owner()

        ExchangeRate.objects.create(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=date(2026, 4, 15),
            rate=Decimal('12500.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Test manual rate',
            raw_payload={},
        )

        response = self.client.post('/api/v1/finance/expenses/', {
            'title': 'USD expense from history rate',
            'category': 'ops',
            'payment_method': 'cash',
            'operation_currency': 'USD',
            'operation_amount': '10.00',
            'occurred_at': '2026-04-15T10:30:00Z',
            'notes': 'FX resolver smoke',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        expense = Expense.objects.get(pk=response.data['id'])
        self.assertEqual(expense.fx_rate_snapshot, Decimal('12500.000000'))
        self.assertEqual(expense.functional_amount_uzs, Decimal('125000.00'))
