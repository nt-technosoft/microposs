import pytest

pytestmark = pytest.mark.skip(reason='Legacy — rewritten in PR-9 (bootstrap_demo + new tests).')

"""Tests for Excel alignment import pipeline."""

from __future__ import annotations

import json
import tempfile

from django.core.management import call_command
from django.test import TestCase

from apps.core.models import Business, ExcelImportBatch, ExcelImportRow
from apps.customers.models import CustomerPayment
from apps.inventory.models import Receipt
from apps.sales.models import Sale
from apps.suppliers.models import SupplierPayment


def _make_snapshot() -> dict:
    return {
        "sheets": {
            "MALUMOTLAR": [
                {
                    "_row_id": "2",
                    "TRADE CREDITOR": "SUP1",
                    "MIJOZLAR": "CLIENT A",
                    "MAHSULOTLAR": "PRODUCT A",
                    "OMBOR": "ASOSIY",
                    "__COL_3": "https://drive.google.com/file/d/testphoto/view",
                    "POSTING": "✅",
                }
            ],
            "SOTIB OLISH": [
                {
                    "_row_id": "2",
                    "SANA": "2026-04-10",
                    "ISM": "SUP1",
                    "MAHSULOT": "PRODUCT A",
                    "SONI": "10",
                    "MAHSULOT NARXI": "10000",
                    "PUL BIRLIGI": "SOM",
                    "KURS": "1",
                    "TO'LOV MUDDATI": "30 KUN",
                    "POSTED": "✅",
                }
            ],
            "STOCK TRANSFER": [],
            "SOTUV": [
                {
                    "_row_id": "2",
                    "SOTUV SANASI": "2026-04-11",
                    "MIJOZ": "CLIENT A",
                    "MAHSULOT": "PRODUCT A",
                    "JAMI DONA": "2",
                    "SOTUV NARXI": "15000",
                    "VALYUTA": "SOM",
                    "KURS": "1",
                    "OMBOR": "ASOSIY",
                    "TO'LOV MUDDATI": "NAQD",
                    "POSTED": "✅",
                }
            ],
            "TUSHUM": [
                {
                    "_row_id": "2",
                    "SANA": "2026-04-12",
                    "MIJOZ": "CLIENT A",
                    "MIQDOR": "5000",
                    "VALYUTA": "SOM",
                    "KURS": "1",
                    "TO'LOV TURI": "NAQD",
                    "POSTED": "✅",
                }
            ],
            "XARAJAT": [
                {
                    "_row_id": "2",
                    "SANA": "2026-04-13",
                    "CREDITOR": "SUP1",
                    "TO'LOV TURI": "NAQD",
                    "MIQDOR": "3000",
                    "VALYUTA": "SOM",
                    "KURS": "1",
                    "QAYERDAN TO'LOV QILINDI": "KASSA SOM",
                    "POSTED": "✅",
                }
            ],
            "PUL AYRIBOSHLASH": [
                {
                    "_row_id": "2",
                    "SANA": "2026-04-14",
                    "KIRIM": "KASSA DOLLAR",
                    "KIRIM MIQDORI": "100",
                    "CHIQIM": "KASSA SOM",
                    "CHIQIM MIQDORI": "1200000",
                    "VALYUTA (CHIQUVCHI)": "SOM",
                    "KURS": "12000",
                    "POSTED": "✅",
                }
            ],
        },
        "opening_balances": {
            "customers": [{"name": "CLIENT A", "amount": "1000"}],
            "suppliers": [{"name": "SUP1", "amount": "2000"}],
        },
        "expected": {},
    }


class ExcelAlignmentImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('bootstrap_demo')
        cls.tenant = Business.objects.order_by('id').first()
        assert cls.tenant is not None

    def _run_command(self, mode: str) -> ExcelImportBatch:
        payload = _make_snapshot()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            json.dump(payload, tf, ensure_ascii=False)
            temp_path = tf.name

        call_command(
            'excel_align_import',
            '--tenant-id', str(self.tenant.id),
            '--mode', mode,
            '--source-file', temp_path,
        )
        return ExcelImportBatch.objects.order_by('-id').first()

    def test_dry_run_stages_rows(self):
        batch = self._run_command('dry-run')
        self.assertEqual(batch.status, ExcelImportBatch.Status.COMPLETED)
        self.assertGreater(
            ExcelImportRow.objects.filter(batch=batch).count(),
            0,
        )

    def test_load_transactions_applies_core_operations(self):
        batch = self._run_command('load-transactions')
        self.assertEqual(batch.status, ExcelImportBatch.Status.COMPLETED)

        self.assertTrue(Receipt.objects.filter(
            tenant=self.tenant,
            notes__icontains='Excel import',
            status=Receipt.ReceiptStatus.CONFIRMED,
        ).exists())
        self.assertTrue(Sale.objects.filter(
            tenant=self.tenant,
            notes__icontains='Excel import',
            status=Sale.SaleStatus.COMPLETED,
        ).exists())
        self.assertTrue(CustomerPayment.objects.filter(
            tenant=self.tenant,
            notes__icontains='Excel import',
        ).exists())
        self.assertTrue(SupplierPayment.objects.filter(
            tenant=self.tenant,
            notes__icontains='Excel import',
        ).exists())

        applied = ExcelImportRow.objects.filter(
            batch=batch,
            status=ExcelImportRow.Status.APPLIED,
        ).count()
        self.assertGreater(applied, 0)

    def test_reconcile_mode_builds_metrics(self):
        batch = self._run_command('reconcile')
        self.assertEqual(batch.status, ExcelImportBatch.Status.COMPLETED)
        self.assertIn('computed', batch.totals)
        self.assertIn('gross_profit_uzs', batch.totals['computed'])
