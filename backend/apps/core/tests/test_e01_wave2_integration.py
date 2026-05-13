"""
Integration tests for E01 Wave 2 — hooks in receive_procurement().

Verifies that confirming a procurement with `terms_payload`:
  - Creates ProcurementTerms
  - For non-PREPAID, creates SupplierPayable
  - For INSTALLMENT, creates PaymentSchedule rows
  - For each item with a supplier, refreshes ProductSupplier link (E02 hook)
  - Validates supplier presence for non-PREPAID terms (raises ValueError)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import ProductSupplier
from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.services import (
    add_contribution,
    open_procurement,
    pay_procurement_items,
    receive_procurement,
)
from apps.suppliers.models import PaymentSchedule, SupplierPayable

from ._helpers import build_tenant


def _open_own_funds_procurement(ctx, *, with_supplier=True, qty=10, unit_price='100'):
    """Helper: open OWN_FUNDS procurement in UZS, fund + pay items, ready for receive."""
    total = Decimal(qty) * Decimal(unit_price)
    proc = open_procurement(
        tenant_id=ctx['business'].id,
        procurement_type=Procurement.Type.OWN_FUNDS,
        supplier_id=ctx['supplier'].id if with_supplier else None,
        items=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal(qty),
            'unit_purchase_price': Decimal(unit_price),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
        }],
    )
    add_contribution(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        partner_id=ctx['operator'].id,
        amount=total,
        currency='UZS',
        fx_rate=Decimal('1'),
    )
    pay_procurement_items(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
    )
    return proc


class ReceiveWithTermsPrepaidTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_prepaid_terms_created_no_payable(self):
        proc = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            },
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.RECEIVED)
        # Terms created
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.type, ProcurementTerms.Type.PREPAID)
        self.assertEqual(terms.total_amount_due, Decimal('1000.00'))
        # No payable for PREPAID
        self.assertFalse(SupplierPayable.objects.filter(procurement=proc).exists())

    def test_prepaid_without_supplier_allowed(self):
        proc = _open_own_funds_procurement(self.ctx, with_supplier=False)
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            },
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, Procurement.Status.RECEIVED)
        # No supplier link should be created (no supplier on procurement)
        self.assertFalse(ProductSupplier.objects.filter(supplier__isnull=True).exists())


class ReceiveWithTermsDeferredTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_deferred_creates_payable(self):
        proc = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        deadline = (timezone.now().date() + timedelta(days=30))
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'DEFERRED',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
                'deadline_date': deadline,
            },
        )
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.type, ProcurementTerms.Type.DEFERRED)
        self.assertEqual(terms.deadline_date, deadline)
        payable = SupplierPayable.objects.get(procurement=proc)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.remaining_amount, Decimal('1000.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.OPEN)
        self.assertEqual(payable.deadline_date, deadline)

    def test_deferred_without_supplier_rejected(self):
        proc = _open_own_funds_procurement(self.ctx, with_supplier=False, qty=10)
        with self.assertRaises(ValueError) as ctx:
            receive_procurement(
                tenant_id=self.ctx['business'].id,
                procurement_id=proc.id,
                destination_warehouse_id=self.ctx['storage'].id,
                terms_payload={
                    'type': 'DEFERRED',
                    'currency_of_obligation': 'UZS',
                    'total_amount_due': '1000',
                    'deadline_date': timezone.now().date(),
                },
            )
        self.assertIn('Supplier is required', str(ctx.exception))


class ReceiveWithTermsInstallmentTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_installment_creates_payable_and_schedule(self):
        proc = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        today = timezone.now().date()
        schedule = [
            {'sequence_number': 1, 'due_date': today + timedelta(days=30), 'amount': '250'},
            {'sequence_number': 2, 'due_date': today + timedelta(days=60), 'amount': '250'},
            {'sequence_number': 3, 'due_date': today + timedelta(days=90), 'amount': '250'},
            {'sequence_number': 4, 'due_date': today + timedelta(days=120), 'amount': '250'},
        ]
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'INSTALLMENT',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            },
            schedule_payload=schedule,
        )
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.type, ProcurementTerms.Type.INSTALLMENT)
        # Payable created
        payable = SupplierPayable.objects.get(procurement=proc)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        # Schedule: 4 entries
        entries = list(PaymentSchedule.objects.filter(procurement_terms=terms).order_by('sequence_number'))
        self.assertEqual(len(entries), 4)
        self.assertEqual([e.sequence_number for e in entries], [1, 2, 3, 4])
        self.assertEqual(sum(Decimal(str(e.amount)) for e in entries), Decimal('1000'))
        self.assertEqual(entries[0].status, PaymentSchedule.Status.PENDING)


class ReceiveProductSupplierHookTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_product_supplier_link_created_on_receipt(self):
        # No link before receipt
        self.assertFalse(ProductSupplier.objects.filter(
            product_variant=self.ctx['variant'], supplier=self.ctx['supplier']
        ).exists())

        proc = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            },
        )
        link = ProductSupplier.objects.get(
            product_variant=self.ctx['variant'], supplier=self.ctx['supplier']
        )
        self.assertEqual(link.total_received_quantity, Decimal('10.000'))
        self.assertEqual(link.total_procurements_count, 1)
        self.assertEqual(link.last_unit_price, Decimal('100.000000'))

    def test_no_link_when_supplier_is_null(self):
        proc = _open_own_funds_procurement(self.ctx, with_supplier=False, qty=10)
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1000',
            },
        )
        # No link created (supplier was None on procurement)
        self.assertFalse(
            ProductSupplier.objects.filter(product_variant=self.ctx['variant']).exists()
        )

    def test_link_aggregates_across_multiple_procurements(self):
        # First receipt
        p1 = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=p1.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={'type': 'PREPAID', 'total_amount_due': '1000'},
        )
        # Second receipt
        p2 = _open_own_funds_procurement(self.ctx, qty=5, unit_price='120')
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=p2.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={'type': 'PREPAID', 'total_amount_due': '600'},
        )
        link = ProductSupplier.objects.get(
            product_variant=self.ctx['variant'], supplier=self.ctx['supplier']
        )
        self.assertEqual(link.total_received_quantity, Decimal('15.000'))
        self.assertEqual(link.total_procurements_count, 2)
        # last_* reflects the most recent receipt
        self.assertEqual(link.last_unit_price, Decimal('120.000000'))


class ReceiveBackwardCompatTests(TestCase):
    """Existing callers (no terms_payload) must continue to work."""

    def setUp(self):
        self.ctx = build_tenant()

    def test_receive_without_terms_payload_works(self):
        proc = _open_own_funds_procurement(self.ctx, qty=10, unit_price='100')
        result = receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            # No terms_payload — legacy call
        )
        result.refresh_from_db()
        self.assertEqual(result.status, Procurement.Status.RECEIVED)
        # No terms created
        self.assertFalse(ProcurementTerms.objects.filter(procurement=proc).exists())
        # No payable
        self.assertFalse(SupplierPayable.objects.filter(procurement=proc).exists())
        # But supplier link IS upserted (it's an unconditional E02 hook)
        self.assertTrue(
            ProductSupplier.objects.filter(
                product_variant=self.ctx['variant'], supplier=self.ctx['supplier']
            ).exists()
        )
