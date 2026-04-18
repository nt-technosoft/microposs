"""Role matrix API tests for owner/cashier/warehouse/investor."""

from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import ProductVariant


class RoleMatrixApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('bootstrap_demo')

    def token_for(self, username: str, password: str) -> str:
        response = self.client.post('/api/v1/auth/token/', {
            'username': username,
            'password': password,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = response.data.get('access')
        self.assertTrue(token)
        return token

    def auth(self, username: str, password: str) -> None:
        token = self.token_for(username, password)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def assert_get_status(self, path: str, expected: int) -> None:
        response = self.client.get(path)
        self.assertEqual(response.status_code, expected, path)

    def test_cashier_sales_only_matrix(self):
        self.auth('cashier', 'Cashier123!')

        variant = ProductVariant.objects.select_related('product').first()
        self.assertIsNotNone(variant)
        product_id = variant.product_id

        allowed = [
            '/api/v1/catalog/categories/',
            '/api/v1/catalog/products/',
            f'/api/v1/catalog/products/{product_id}/variants/',
            '/api/v1/sales/sessions/?status=open',
            '/api/v1/sales/sales/',
            '/api/v1/customers/customers/',
        ]
        denied = [
            '/api/v1/inventory/receipts/',
            '/api/v1/inventory/lots/',
            '/api/v1/suppliers/suppliers/',
            '/api/v1/analytics/product-performance/',
            '/api/v1/investors/contracts/',
        ]

        for path in allowed:
            self.assert_get_status(path, status.HTTP_200_OK)
        for path in denied:
            self.assert_get_status(path, status.HTTP_403_FORBIDDEN)

    def test_warehouse_inventory_matrix(self):
        self.auth('warehouse', 'Warehouse123!')

        allowed = [
            '/api/v1/catalog/products/',
            '/api/v1/catalog/variants/',
            '/api/v1/inventory/locations/',
            '/api/v1/inventory/receipts/',
            '/api/v1/inventory/lots/',
            '/api/v1/inventory/stock/summary/',
        ]
        denied = [
            '/api/v1/sales/sales/',
            '/api/v1/customers/customers/',
            '/api/v1/suppliers/suppliers/',
            '/api/v1/analytics/product-performance/',
            '/api/v1/investors/contracts/',
        ]

        for path in allowed:
            self.assert_get_status(path, status.HTTP_200_OK)
        for path in denied:
            self.assert_get_status(path, status.HTTP_403_FORBIDDEN)

    def test_investor_cabinet_matrix(self):
        self.auth('investor', 'Investor123!')

        allowed = [
            '/api/v1/investors/summaries/',
            '/api/v1/investors/profit-records/',
        ]
        denied = [
            '/api/v1/sales/sales/',
            '/api/v1/catalog/products/',
            '/api/v1/inventory/receipts/',
            '/api/v1/customers/customers/',
            '/api/v1/analytics/product-performance/',
        ]

        for path in allowed:
            self.assert_get_status(path, status.HTTP_200_OK)
        for path in denied:
            self.assert_get_status(path, status.HTTP_403_FORBIDDEN)

