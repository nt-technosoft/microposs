"""Iteration 2 hardening tests: AP lifecycle, Expense, reconciliation endpoint."""

from __future__ import annotations

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Business, ExcelImportBatch, ExcelImportRow, OutboxEvent
from apps.finance.models import Expense, JournalEntry
from apps.inventory.models import Warehouse
from apps.suppliers.models import Supplier
from apps.catalog.models import ProductVariant


class BackendHardeningIteration2Tests(APITestCase):
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

    def test_supplier_credit_receipt_increases_payable_in_domain_service(self):
        self._auth_owner()

        supplier = Supplier.objects.filter(tenant=self.tenant, is_active=True).order_by('id').first()
        variant = ProductVariant.objects.filter(tenant=self.tenant, is_active=True).order_by('id').first()
        destination = Warehouse.objects.filter(tenant=self.tenant, is_active=True).order_by('id').first()
        self.assertIsNotNone(supplier)
        self.assertIsNotNone(variant)
        self.assertIsNotNone(destination)

        starting_balance = supplier.outstanding_balance

        create_response = self.client.post('/api/v1/inventory/receipts/', {
            'receipt_type': 'SUPPLIER_PURCHASE',
            'date': '2026-04-15T09:30:00Z',
            'destination_id': destination.id,
            'supplier_id': supplier.id,
            'payable_terms': {'type': 'credit', 'term': '30 KUN'},
            'lines': [{
                'product_variant_id': variant.id,
                'quantity': 3,
                'cost_per_unit': '10000.00',
            }],
            'notes': 'AP lifecycle test',
        }, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        receipt_id = create_response.data['id']

        confirm_response = self.client.post(
            f'/api/v1/inventory/receipts/{receipt_id}/confirm/',
            {},
            format='json',
        )
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        supplier.refresh_from_db()
        self.assertEqual(
            supplier.outstanding_balance,
            starting_balance + Decimal('30000.00'),
        )

        receipt_entry = JournalEntry.objects.filter(
            tenant=self.tenant,
            operation_type='receipt',
            operation_id=receipt_id,
        ).first()
        self.assertIsNotNone(receipt_entry)
        assert receipt_entry is not None
        self.assertEqual(receipt_entry.date.isoformat(), '2026-04-15T09:30:00+00:00')
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=self.tenant.id,
            event_type='supplier.payable_accrued',
        ).exists())

    def test_expense_endpoint_creates_first_class_domain_record_and_journal(self):
        self._auth_owner()

        payload = {
            'title': 'Delivery expense',
            'category': 'logistics',
            'payment_method': 'cash',
            'operation_currency': 'USD',
            'operation_amount': '10.00',
            'fx_rate_snapshot': '12600.00',
            'functional_amount_uzs': '126000.00',
            'occurred_at': '2026-04-15T11:00:00Z',
            'notes': 'Courier payment',
        }
        response = self.client.post('/api/v1/finance/expenses/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        expense_id = response.data['id']

        expense = Expense.objects.get(pk=expense_id)
        self.assertEqual(expense.operation_currency, 'USD')
        self.assertEqual(expense.functional_amount_uzs, Decimal('126000.00'))
        self.assertEqual(expense.occurred_at.isoformat(), '2026-04-15T11:00:00+00:00')

        expense_entry = JournalEntry.objects.filter(
            tenant=self.tenant,
            operation_type='payment',
            operation_id=expense_id,
        ).first()
        self.assertIsNotNone(expense_entry)
        assert expense_entry is not None
        self.assertEqual(expense_entry.date.isoformat(), '2026-04-15T11:00:00+00:00')
        self.assertTrue(OutboxEvent.objects.filter(
            tenant_id=self.tenant.id,
            event_type='expense.recorded',
        ).exists())

    def test_owner_can_fetch_latest_reconciliation_summary(self):
        self._auth_owner()

        batch = ExcelImportBatch.objects.create(
            tenant=self.tenant,
            source_kind='json',
            source_ref='unit-test',
            mode=ExcelImportBatch.Mode.RECONCILE,
            status=ExcelImportBatch.Status.COMPLETED,
            totals={
                'computed': {'gross_profit_uzs': '10000.00'},
                'expected': {'gross_profit_uzs': '9000.00'},
                'deltas': {'gross_profit_uzs': '1000.00'},
            },
        )
        ExcelImportRow.objects.create(
            tenant=self.tenant,
            batch=batch,
            source_sheet='SOTUV',
            source_row_id='10',
            row_fingerprint='abc',
            raw_payload={},
            status=ExcelImportRow.Status.FAILED,
            parse_errors=['Sample mapping error'],
            failure_category=ExcelImportRow.FailureCategory.MAPPING,
        )

        response = self.client.get('/api/v1/core/excel/reconciliation/latest/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['batch_id'], batch.id)
        self.assertIn('computed', response.data)
        self.assertEqual(response.data['gap_summary'].get('mapping'), 1)


class PilotSnapshotSliceTests(TestCase):
    def test_slice_keeps_recent_rows_and_malumotlar(self):
        from apps.core.management.commands.excel_align_pilot import _slice_transaction_period

        snapshot = {
            'sheets': {
                'MALUMOTLAR': [{'_row_id': '2', 'MAHSULOTLAR': 'Demo'}],
                'SOTUV': [
                    {'_row_id': '2', 'SOTUV SANASI': '2026-04-01', 'MAHSULOT': 'A'},
                    {'_row_id': '3', 'SOTUV SANASI': '2026-04-14', 'MAHSULOT': 'B'},
                ],
            },
            'opening_balances': {},
            'expected': {},
        }
        sliced = _slice_transaction_period(snapshot, days=7)
        self.assertEqual(len(sliced['sheets']['MALUMOTLAR']), 1)
        self.assertEqual(len(sliced['sheets']['SOTUV']), 1)
        self.assertEqual(sliced['sheets']['SOTUV'][0]['MAHSULOT'], 'B')
