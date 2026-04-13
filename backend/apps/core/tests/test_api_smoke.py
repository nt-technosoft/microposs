"""Backend smoke tests for critical API flows."""

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import ProductVariant
from apps.customers.models import Customer
from apps.inventory.models import Location, Lot
from apps.sales.models import PosSession


class ApiSmokeTests(APITestCase):
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
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token_for(username, password)}')

    def test_auth_me_returns_role_and_tenant_context(self):
        self.auth('owner', 'Owner123!')
        owner_me = self.client.get('/api/v1/auth/me/')
        self.assertEqual(owner_me.status_code, status.HTTP_200_OK)
        self.assertEqual(owner_me.data['role'], 'owner')
        self.assertIsNotNone(owner_me.data['active_tenant_id'])

        self.auth('investor', 'Investor123!')
        investor_me = self.client.get('/api/v1/auth/me/')
        self.assertEqual(investor_me.status_code, status.HTTP_200_OK)
        self.assertEqual(investor_me.data['role'], 'investor')
        self.assertIsNotNone(investor_me.data['active_tenant_id'])

    def test_owner_read_endpoints_smoke(self):
        self.auth('owner', 'Owner123!')

        endpoints = [
            '/api/v1/catalog/products/',
            '/api/v1/inventory/receipts/',
            '/api/v1/sales/sessions/?status=open',
            '/api/v1/sales/sales/',
            '/api/v1/finance/daily-summaries/',
            '/api/v1/finance/cash-flow/',
            '/api/v1/customers/customers/',
            '/api/v1/suppliers/suppliers/',
        ]

        for path in endpoints:
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_200_OK, path)
            self.assertIn('results', response.data, path)

    def test_critical_write_flow_product_receipt_confirm_sale(self):
        self.auth('owner', 'Owner123!')

        product_response = self.client.post('/api/v1/catalog/products/', {
            'name': f'Smoke Product {timezone.now().timestamp()}',
            'base_price': '71000.00',
            'pricing_mode': 'DEFAULT_EDITABLE',
            'description': 'Created by smoke test',
            'characteristics': [],
            'variants': [],
        }, format='json')
        self.assertEqual(product_response.status_code, status.HTTP_201_CREATED)

        variant = ProductVariant.objects.filter(is_active=True).order_by('-id').first()
        self.assertIsNotNone(variant)

        destination = Location.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(destination)

        receipt_response = self.client.post('/api/v1/inventory/receipts/', {
            'receipt_type': 'BUSINESS_OWNED',
            'date': (timezone.now() - timedelta(minutes=1)).isoformat(),
            'destination_id': destination.id,
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 2,
                'cost_per_unit': '49000.00',
            }],
            'notes': 'Smoke receipt',
        }, format='json')
        self.assertEqual(receipt_response.status_code, status.HTTP_201_CREATED)

        receipt_id = receipt_response.data['id']
        confirm_response = self.client.post(f'/api/v1/inventory/receipts/{receipt_id}/confirm/', {}, format='json')
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        session = PosSession.objects.filter(status=PosSession.SessionStatus.OPEN).order_by('-opened_at').first()
        self.assertIsNotNone(session)

        customer = Customer.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(customer)

        sale_lot = (
            Lot.objects
            .filter(product_variant=variant, is_active=True, quantity_remaining__gte=1)
            .order_by('-id')
            .first()
        )
        self.assertIsNotNone(sale_lot)

        sale_response = self.client.post('/api/v1/sales/sales/', {
            'pos_session_id': session.id,
            'payment_method': 'cash',
            'customer_id': customer.id,
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 1,
                'unit_price': str(Decimal('71000.00')),
                'lot_id': sale_lot.id,
            }],
            'notes': 'Smoke sale',
        }, format='json')
        self.assertEqual(sale_response.status_code, status.HTTP_201_CREATED)
