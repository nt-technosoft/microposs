import pytest

pytestmark = pytest.mark.skip(reason='Legacy — rewritten in PR-9 (bootstrap_demo + new tests).')

"""Financial integrity and outbox coverage tests for critical operations."""

from decimal import Decimal

from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import ProductVariant
from apps.core.models import OutboxEvent
from apps.customers.models import Customer
from apps.finance.models import JournalEntry
from apps.inventory.models import Warehouse, Lot
from apps.sales.models import PosSession, Sale
from apps.suppliers.models import Supplier


class FinancialIntegrityTests(APITestCase):
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

    def test_receipt_and_sale_create_journal_and_outbox(self):
        self.auth_owner()

        variant = ProductVariant.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(variant)
        location = Warehouse.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(location)
        session = PosSession.objects.filter(
            status=PosSession.SessionStatus.OPEN,
        ).order_by('-opened_at').first()
        self.assertIsNotNone(session)
        tenant_id = session.tenant_id

        receipt_response = self.client.post('/api/v1/inventory/receipts/', {
            'receipt_type': 'BUSINESS_OWNED',
            'date': '2026-04-14T08:00:00Z',
            'destination_id': location.id,
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 2,
                'cost_per_unit': '47000.00',
            }],
            'notes': 'Financial integrity test receipt',
        }, format='json')
        self.assertEqual(receipt_response.status_code, status.HTTP_201_CREATED)
        receipt_id = receipt_response.data['id']

        confirm_response = self.client.post(
            f'/api/v1/inventory/receipts/{receipt_id}/confirm/',
            {},
            format='json',
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=tenant_id,
            operation_type='receipt',
            operation_id=receipt_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=tenant_id,
            event_type='receipt.confirmed',
        ).exists())

        lot = Lot.objects.filter(
            receipt_id=receipt_id,
            quantity_remaining__gte=1,
            is_active=True,
        ).order_by('-id').first()
        self.assertIsNotNone(lot)

        customer = Customer.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(customer)

        sale_response = self.client.post('/api/v1/sales/sales/', {
            'pos_session_id': session.id,
            'payment_method': 'cash',
            'customer_id': customer.id,
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 1,
                'unit_price': '65000.00',
                'lot_id': lot.id,
            }],
            'notes': 'Financial integrity test sale',
        }, format='json')
        self.assertEqual(sale_response.status_code, status.HTTP_201_CREATED)
        sale_id = sale_response.data['id']

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=tenant_id,
            operation_type='sale',
            operation_id=sale_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=tenant_id,
            event_type='sale.completed',
        ).exists())

    def test_return_payments_writeoff_create_journal_and_outbox(self):
        self.auth_owner()

        sale = Sale.objects.filter(status=Sale.SaleStatus.COMPLETED).order_by('id').first()
        self.assertIsNotNone(sale)
        line = sale.lines.order_by('id').first()
        self.assertIsNotNone(line)

        return_response = self.client.post(f'/api/v1/sales/sales/{sale.id}/return/', {
            'lines': [{
                'sale_line_id': line.id,
                'quantity': 1,
                'condition': 'good',
            }],
            'notes': 'Integrity return',
        }, format='json')
        self.assertEqual(return_response.status_code, status.HTTP_201_CREATED)
        return_id = return_response.data['id']

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=sale.tenant_id,
            operation_type='return',
            operation_id=return_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=sale.tenant_id,
            event_type='sale.returned',
        ).exists())

        customer = Customer.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(customer)
        customer.outstanding_balance = Decimal('120000.00')
        customer.save(update_fields=['outstanding_balance', 'updated_at'])

        customer_payment_response = self.client.post(
            f'/api/v1/customers/customers/{customer.id}/pay/',
            {
                'amount': '50000.00',
                'payment_method': 'cash',
                'notes': 'Debt repayment',
            },
            format='json',
        )
        self.assertEqual(customer_payment_response.status_code, status.HTTP_201_CREATED)
        customer_payment_id = customer_payment_response.data['id']

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=sale.tenant_id,
            operation_type='debt_payment',
            operation_id=customer_payment_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=sale.tenant_id,
            event_type='customer.payment',
        ).exists())

        supplier = Supplier.objects.filter(is_active=True).order_by('id').first()
        self.assertIsNotNone(supplier)
        supplier.outstanding_balance = Decimal('90000.00')
        supplier.save(update_fields=['outstanding_balance', 'updated_at'])

        supplier_payment_response = self.client.post(
            f'/api/v1/suppliers/suppliers/{supplier.id}/pay/',
            {
                'amount': '40000.00',
                'payment_method': 'cash',
                'notes': 'Supplier settlement',
            },
            format='json',
        )
        self.assertEqual(supplier_payment_response.status_code, status.HTTP_201_CREATED)
        supplier_payment_id = supplier_payment_response.data['id']

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=sale.tenant_id,
            operation_type='payment',
            operation_id=supplier_payment_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=sale.tenant_id,
            event_type='supplier.payment',
        ).exists())

        lot = Lot.objects.filter(
            tenant_id=sale.tenant_id,
            quantity_remaining__gte=1,
            is_active=True,
        ).order_by('id').first()
        self.assertIsNotNone(lot)

        writeoff_response = self.client.post('/api/v1/risk/events/writeoff/', {
            'lot_id': lot.id,
            'quantity': 1,
            'reason': 'Integrity writeoff',
            'negligence': False,
        }, format='json')
        self.assertEqual(writeoff_response.status_code, status.HTTP_201_CREATED)
        risk_event_id = writeoff_response.data['id']

        self.assertTrue(JournalEntry.objects.filter(
            tenant_id=sale.tenant_id,
            operation_type='writeoff',
            operation_id=risk_event_id,
        ).exists())
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=sale.tenant_id,
            event_type='risk.writeoff',
        ).exists())
