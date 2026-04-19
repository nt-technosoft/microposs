from rest_framework import status
from rest_framework.test import APITestCase

from ._helpers import build_tenant


class FinanceBridgeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_owner',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_owner_can_manage_cash_accounts_and_owner_contribution(self):
        self.auth_owner()

        create_account = self.client.post(
            '/api/v1/finance/cash-accounts/',
            {
                'name': 'Bridge Cash',
                'currency': 'UZS',
                'kind': 'cash',
            },
            format='json',
        )
        self.assertEqual(create_account.status_code, status.HTTP_201_CREATED)
        account_id = create_account.data['id']

        accounts = self.client.get('/api/v1/finance/cash-accounts/')
        self.assertEqual(accounts.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(accounts.data['count'], 1)

        contribution = self.client.post(
            '/api/v1/finance/owner-contributions/',
            {
                'amount': '100000.00',
                'currency': 'UZS',
                'to_account_id': account_id,
            },
            format='json',
        )
        self.assertEqual(contribution.status_code, status.HTTP_201_CREATED)
        self.assertEqual(contribution.data['amount'], '100000.00')

        entries = self.client.get('/api/v1/finance/cash-entries/')
        self.assertEqual(entries.status_code, status.HTTP_200_OK)
        self.assertEqual(entries.data['count'], 1)
        self.assertEqual(entries.data['results'][0]['direction'], 'IN')

    def test_owner_can_create_currency_exchange(self):
        self.auth_owner()

        from_account = self.client.post(
            '/api/v1/finance/cash-accounts/',
            {'name': 'UZS Cash', 'currency': 'UZS', 'kind': 'cash'},
            format='json',
        )
        to_account = self.client.post(
            '/api/v1/finance/cash-accounts/',
            {'name': 'USD Cash', 'currency': 'USD', 'kind': 'cash'},
            format='json',
        )
        self.assertEqual(from_account.status_code, status.HTTP_201_CREATED)
        self.assertEqual(to_account.status_code, status.HTTP_201_CREATED)

        contribution = self.client.post(
            '/api/v1/finance/owner-contributions/',
            {
                'amount': '120000.00',
                'currency': 'UZS',
                'to_account_id': from_account.data['id'],
            },
            format='json',
        )
        self.assertEqual(contribution.status_code, status.HTTP_201_CREATED)

        exchange = self.client.post(
            '/api/v1/finance/currency-exchanges/',
            {
                'from_account_id': from_account.data['id'],
                'to_account_id': to_account.data['id'],
                'from_amount': '120000.00',
                'rate': '0.000083',
            },
            format='json',
        )
        self.assertEqual(exchange.status_code, status.HTTP_201_CREATED)
        self.assertEqual(exchange.data['from_currency'], 'UZS')
        self.assertEqual(exchange.data['to_currency'], 'USD')
