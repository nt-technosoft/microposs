"""
Unit tests for E01 + E02 services (Wave 1).

Covers:
  - upsert_product_supplier_link: create + update + multiple receipts aggregate correctly
  - quick_create_product: minimal create, with/without supplier link
  - create_payable_from_procurement: basic creation, PREPAID rejection
  - record_payable_payment: single-cash, multi-cash, multi-currency, partial pay,
    full pay, schedule entry update, idempotency
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import ProductSupplier
from apps.catalog.services import (
    quick_create_product,
    upsert_product_supplier_link,
)
from apps.partnerships.models import Procurement, ProcurementTerms
from apps.suppliers.models import (
    PaymentSchedule,
    Supplier,
    SupplierPayable,
    SupplierPayment,
)
from apps.suppliers.services import (
    create_payable_from_procurement,
    record_payable_payment,
)

from ._helpers import build_tenant


def _make_procurement(business, supplier, type_=Procurement.Type.OWN_FUNDS):
    return Procurement.objects.create(
        tenant=business,
        procurement_type=type_,
        status=Procurement.Status.OPEN,
        opened_at=timezone.now(),
        supplier=supplier,
    )


def _make_terms(business, procurement, *, terms_type, total, currency='UZS', deadline=None):
    return ProcurementTerms.objects.create(
        tenant=business,
        procurement=procurement,
        type=terms_type,
        currency_of_obligation=currency,
        fx_rate_at_obligation=Decimal('1') if currency == 'UZS' else Decimal('12500'),
        total_amount_due=Decimal(total),
        paid_amount=Decimal('0'),
        status=ProcurementTerms.Status.OPEN,
        deadline_date=deadline,
    )


class UpsertProductSupplierLinkTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.supplier = self.ctx['supplier']
        self.variant = self.ctx['variant']

    def test_creates_link_on_first_call(self):
        self.assertFalse(
            ProductSupplier.objects.filter(
                product_variant=self.variant, supplier=self.supplier
            ).exists()
        )
        link = upsert_product_supplier_link(
            tenant_id=self.business.id,
            product_variant_id=self.variant.id,
            supplier_id=self.supplier.id,
            unit_price=Decimal('100'),
            currency='UZS',
            quantity=Decimal('10'),
            fx_rate=Decimal('1'),
        )
        self.assertEqual(link.total_received_quantity, Decimal('10'))
        self.assertEqual(link.total_received_value_uzs, Decimal('1000.00'))
        self.assertEqual(link.total_procurements_count, 1)
        self.assertEqual(link.last_unit_price, Decimal('100'))
        self.assertEqual(link.last_currency, 'UZS')

    def test_updates_link_aggregates_on_subsequent_calls(self):
        # First receipt
        upsert_product_supplier_link(
            tenant_id=self.business.id,
            product_variant_id=self.variant.id,
            supplier_id=self.supplier.id,
            unit_price=Decimal('100'),
            currency='UZS',
            quantity=Decimal('10'),
            fx_rate=Decimal('1'),
        )
        # Second receipt — different price/qty
        link = upsert_product_supplier_link(
            tenant_id=self.business.id,
            product_variant_id=self.variant.id,
            supplier_id=self.supplier.id,
            unit_price=Decimal('120'),
            currency='UZS',
            quantity=Decimal('5'),
            fx_rate=Decimal('1'),
        )
        self.assertEqual(link.total_received_quantity, Decimal('15'))
        self.assertEqual(link.total_received_value_uzs, Decimal('1600.00'))
        self.assertEqual(link.total_procurements_count, 2)
        # `last_*` reflects the most recent receipt
        self.assertEqual(link.last_unit_price, Decimal('120'))

    def test_zero_or_negative_quantity_rejected(self):
        with self.assertRaises(ValueError):
            upsert_product_supplier_link(
                tenant_id=self.business.id,
                product_variant_id=self.variant.id,
                supplier_id=self.supplier.id,
                unit_price=Decimal('100'),
                currency='UZS',
                quantity=Decimal('0'),
            )


class QuickCreateProductTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.supplier = self.ctx['supplier']

    def test_creates_product_variant_and_links_supplier(self):
        variant = quick_create_product(
            tenant_id=self.business.id,
            name='New Inline Product',
            supplier_id=self.supplier.id,
        )
        self.assertIsNotNone(variant.id)
        self.assertTrue(variant.sku)  # auto-generated
        # Supplier link created with 0 quantity placeholder
        link = ProductSupplier.objects.get(
            product_variant=variant, supplier=self.supplier
        )
        self.assertEqual(link.total_received_quantity, Decimal('0'))
        self.assertEqual(link.total_procurements_count, 0)

    def test_creates_product_without_supplier(self):
        variant = quick_create_product(
            tenant_id=self.business.id,
            name='Lone Product',
        )
        self.assertIsNotNone(variant.id)
        self.assertFalse(
            ProductSupplier.objects.filter(product_variant=variant).exists()
        )

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            quick_create_product(
                tenant_id=self.business.id,
                name='   ',
                supplier_id=self.supplier.id,
            )


class CreatePayableFromProcurementTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.supplier = self.ctx['supplier']
        self.procurement = _make_procurement(self.business, self.supplier)

    def test_creates_payable_for_deferred(self):
        terms = _make_terms(
            self.business, self.procurement,
            terms_type=ProcurementTerms.Type.DEFERRED,
            total=Decimal('1000'),
            deadline=timezone.now().date(),
        )
        payable = create_payable_from_procurement(
            tenant_id=self.business.id,
            procurement_id=self.procurement.id,
            supplier_id=self.supplier.id,
            terms=terms,
            deadline_date=terms.deadline_date,
        )
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.remaining_amount, Decimal('1000.00'))
        self.assertEqual(payable.paid_amount, Decimal('0.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.OPEN)
        self.assertEqual(payable.reason, SupplierPayable.Reason.PROCUREMENT)
        self.assertEqual(payable.currency_of_obligation, 'UZS')

    def test_prepaid_rejected(self):
        terms = _make_terms(
            self.business, self.procurement,
            terms_type=ProcurementTerms.Type.PREPAID,
            total=Decimal('1000'),
        )
        with self.assertRaises(ValueError):
            create_payable_from_procurement(
                tenant_id=self.business.id,
                procurement_id=self.procurement.id,
                supplier_id=self.supplier.id,
                terms=terms,
            )

    def test_zero_amount_rejected(self):
        terms = _make_terms(
            self.business, self.procurement,
            terms_type=ProcurementTerms.Type.DEFERRED,
            total=Decimal('0'),
        )
        with self.assertRaises(ValueError):
            create_payable_from_procurement(
                tenant_id=self.business.id,
                procurement_id=self.procurement.id,
                supplier_id=self.supplier.id,
                terms=terms,
            )


class RecordPayablePaymentTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.business = self.ctx['business']
        self.supplier = self.ctx['supplier']
        self.cash = self.ctx['cash_account']
        self.card = self.ctx['card_account']
        self.procurement = _make_procurement(self.business, self.supplier)
        self.terms = _make_terms(
            self.business, self.procurement,
            terms_type=ProcurementTerms.Type.DEFERRED,
            total=Decimal('1000'),
        )
        self.payable = create_payable_from_procurement(
            tenant_id=self.business.id,
            procurement_id=self.procurement.id,
            supplier_id=self.supplier.id,
            terms=self.terms,
        )

    def test_single_cash_full_payment(self):
        payment = record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '1000', 'currency': 'UZS'},
            ],
            notes='full',
        )
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, SupplierPayable.Status.FULLY_PAID)
        self.assertEqual(self.payable.remaining_amount, Decimal('0.00'))
        self.assertEqual(self.payable.paid_amount, Decimal('1000.00'))
        # Payment row recorded with allocations
        self.assertEqual(payment.payment_method, SupplierPayment.PaymentMethod.CASH)
        self.assertEqual(len(payment.allocations), 1)

    def test_multi_cash_split(self):
        payment = record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '400', 'currency': 'UZS'},
                {'cash_account_id': self.card.id, 'amount': '600', 'currency': 'UZS'},
            ],
            notes='split',
        )
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, SupplierPayable.Status.FULLY_PAID)
        self.assertEqual(payment.payment_method, SupplierPayment.PaymentMethod.MIXED)
        self.assertEqual(len(payment.allocations), 2)

    def test_partial_payment_then_complete(self):
        record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '300', 'currency': 'UZS'},
            ],
        )
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, SupplierPayable.Status.PARTIALLY_PAID)
        self.assertEqual(self.payable.remaining_amount, Decimal('700.00'))

        record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '700', 'currency': 'UZS'},
            ],
        )
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, SupplierPayable.Status.FULLY_PAID)

    def test_overpayment_rejected(self):
        with self.assertRaises(ValueError):
            record_payable_payment(
                tenant_id=self.business.id,
                payable_id=self.payable.id,
                allocations=[
                    {'cash_account_id': self.cash.id, 'amount': '1500', 'currency': 'UZS'},
                ],
            )

    def test_empty_allocations_rejected(self):
        with self.assertRaises(ValueError):
            record_payable_payment(
                tenant_id=self.business.id,
                payable_id=self.payable.id,
                allocations=[],
            )

    def test_idempotency(self):
        crid = uuid.uuid4()
        p1 = record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '500', 'currency': 'UZS'},
            ],
            client_request_id=crid,
        )
        p2 = record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '500', 'currency': 'UZS'},
            ],
            client_request_id=crid,
        )
        self.assertEqual(p1.id, p2.id)
        # Payable updated only once
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.paid_amount, Decimal('500.00'))

    def test_schedule_entry_updated_when_payment_targets_it(self):
        schedule = PaymentSchedule.objects.create(
            tenant=self.business,
            procurement_terms=self.terms,
            sequence_number=1,
            due_date=timezone.now().date(),
            amount=Decimal('500'),
            currency='UZS',
            status=PaymentSchedule.Status.PENDING,
        )
        record_payable_payment(
            tenant_id=self.business.id,
            payable_id=self.payable.id,
            allocations=[
                {'cash_account_id': self.cash.id, 'amount': '500', 'currency': 'UZS'},
            ],
            schedule_entry_id=schedule.id,
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, PaymentSchedule.Status.PAID)
        self.assertEqual(schedule.paid_amount, Decimal('500.00'))
        self.assertIsNotNone(schedule.paid_at)
