"""Products/category template and sales pricing-mode behavior tests."""

from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Product, ProductVariant
from apps.customers.models import Customer
from apps.inventory.models import Warehouse, Lot
from apps.sales.models import PosSession, SaleLine


class ProductsPricingFlowTests(APITestCase):
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

    def auth_owner(self) -> None:
        token = self.token_for('owner', 'Owner123!')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def create_receipt_and_lot(self, variant_id: int) -> Lot:
        destination = Warehouse.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(destination)

        receipt_response = self.client.post('/api/v1/inventory/receipts/', {
            'receipt_type': 'BUSINESS_OWNED',
            'date': (timezone.now() - timedelta(minutes=1)).isoformat(),
            'destination_id': destination.id,
            'lines': [{
                'product_variant_id': variant_id,
                'quantity': 4,
                'cost_per_unit': '49000.00',
            }],
            'notes': 'Pricing matrix test receipt',
        }, format='json')
        self.assertEqual(receipt_response.status_code, status.HTTP_201_CREATED)

        receipt_id = receipt_response.data['id']
        confirm_response = self.client.post(
            f'/api/v1/inventory/receipts/{receipt_id}/confirm/',
            {},
            format='json',
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        lot = (
            Lot.objects
            .filter(receipt_id=receipt_id, is_active=True, quantity_remaining__gt=0)
            .order_by('id')
            .first()
        )
        self.assertIsNotNone(lot)
        return lot

    def create_product(self, *, name: str, pricing_mode: str, base_price: str = '70000.00') -> ProductVariant:
        response = self.client.post('/api/v1/catalog/products/', {
            'name': name,
            'base_price': base_price,
            'pricing_mode': pricing_mode,
            'description': 'pricing mode test product',
            'characteristics': [],
            'variants': [],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        product_id = response.data['id']
        variant = ProductVariant.objects.filter(product_id=product_id, is_active=True).order_by('id').first()
        self.assertIsNotNone(variant)
        return variant

    def create_sale_line(self, *, variant: ProductVariant, lot: Lot, unit_price: str) -> tuple[int, dict]:
        session = PosSession.objects.filter(status=PosSession.SessionStatus.OPEN).order_by('-opened_at').first()
        self.assertIsNotNone(session)
        customer = Customer.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(customer)

        response = self.client.post('/api/v1/sales/sales/', {
            'pos_session_id': session.id,
            'payment_method': 'cash',
            'customer_id': customer.id,
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 1,
                'unit_price': unit_price,
                'lot_id': lot.id,
            }],
            'notes': 'Pricing matrix sale',
        }, format='json')
        return response.status_code, response.data

    def test_fixed_locked_rejects_changed_price(self):
        self.auth_owner()
        variant = self.create_product(
            name=f'Fixed Product {timezone.now().timestamp()}',
            pricing_mode='FIXED',
            base_price='65000.00',
        )
        lot = self.create_receipt_and_lot(variant.id)

        status_code, payload = self.create_sale_line(
            variant=variant,
            lot=lot,
            unit_price='64000.00',
        )
        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Fixed price product', str(payload.get('detail')))

    def test_ask_each_sale_requires_positive_price(self):
        self.auth_owner()
        variant = self.create_product(
            name=f'Ask Product {timezone.now().timestamp()}',
            pricing_mode='ALWAYS_ASK',
            base_price='0.00',
        )
        lot = self.create_receipt_and_lot(variant.id)

        status_code, payload = self.create_sale_line(
            variant=variant,
            lot=lot,
            unit_price='0.00',
        )
        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Unit price', str(payload.get('detail')))

    def test_discount_reason_defaults_to_torg_when_price_changed(self):
        self.auth_owner()
        variant = self.create_product(
            name=f'Editable Product {timezone.now().timestamp()}',
            pricing_mode='EDITABLE',
            base_price='70000.00',
        )
        lot = self.create_receipt_and_lot(variant.id)

        status_code, payload = self.create_sale_line(
            variant=variant,
            lot=lot,
            unit_price='68000.00',
        )
        self.assertEqual(status_code, status.HTTP_201_CREATED)

        sale_id = payload['id']
        sale_line = SaleLine.objects.filter(sale_id=sale_id).order_by('id').first()
        self.assertIsNotNone(sale_line)
        self.assertTrue(sale_line.price_changed)
        self.assertIsNotNone(sale_line.discount_reason)
        self.assertEqual(sale_line.discount_reason.name, 'Торг')

    def test_category_template_characteristics_applies_to_new_and_existing(self):
        self.auth_owner()

        category_response = self.client.post('/api/v1/catalog/categories/', {
            'name': f'Category Tpl {timezone.now().timestamp()}',
            'default_pricing_mode': 'ALWAYS_ASK',
            'sort_order': 1,
        }, format='json')
        self.assertEqual(category_response.status_code, status.HTTP_201_CREATED)
        category_id = category_response.data['id']

        template_response = self.client.put(
            f'/api/v1/catalog/categories/{category_id}/characteristics/',
            [
                {'name': 'Материал', 'default_value': 'Кожа', 'sort_order': 0},
                {'name': 'Сезон', 'default_value': 'Лето', 'sort_order': 1},
            ],
            format='json',
        )
        self.assertEqual(template_response.status_code, status.HTTP_200_OK)

        product_response = self.client.post('/api/v1/catalog/products/', {
            'name': f'Category Product {timezone.now().timestamp()}',
            'category_id': category_id,
            'base_price': '70000.00',
            'description': 'category template test',
            'characteristics': [],
            'variants': [],
        }, format='json')
        self.assertEqual(product_response.status_code, status.HTTP_201_CREATED)

        created_product = Product.objects.get(pk=product_response.data['id'])
        self.assertEqual(created_product.pricing_mode, 'ALWAYS_ASK')
        self.assertTrue(created_product.characteristics.filter(name='Материал', value='Кожа').exists())

        update_template_response = self.client.put(
            f'/api/v1/catalog/categories/{category_id}/characteristics/',
            [
                {'name': 'Материал', 'default_value': 'Эко-кожа', 'sort_order': 0},
            ],
            format='json',
        )
        self.assertEqual(update_template_response.status_code, status.HTTP_200_OK)

        apply_response = self.client.post(
            f'/api/v1/catalog/categories/{category_id}/apply-settings/',
            {
                'apply_to_existing': True,
                'apply_pricing_mode': False,
                'apply_characteristics': True,
            },
            format='json',
        )
        self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(apply_response.data.get('updated_count', 0), 1)

        created_product.refresh_from_db()
        self.assertTrue(created_product.characteristics.filter(name='Материал', value='Эко-кожа').exists())
