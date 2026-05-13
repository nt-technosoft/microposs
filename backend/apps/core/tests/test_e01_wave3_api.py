"""
Wave 3 — API tests for E01.

Covers:
  - GET /api/v1/suppliers/payables/ listing + filters
  - POST /api/v1/suppliers/payables/{id}/pay/ multi-cash payment
  - apply_terms_amendment service + payable.deadline sync
  - mark_overdue_payment_schedules Celery task
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.analytics.tasks import mark_overdue_payment_schedules
from apps.catalog.models import ProductSupplier
from apps.partnerships.models import Procurement, ProcurementTerms, ProcurementTermsAmendment
from apps.partnerships.services import (
    add_contribution,
    apply_terms_amendment,
    open_procurement,
    pay_procurement_items,
    receive_procurement,
)
from apps.suppliers.models import PaymentSchedule, SupplierPayable, SupplierPayment

from ._helpers import build_tenant


def _seed_deferred_procurement(ctx, *, qty=10, unit_price='100', deadline=None):
    """OWN_FUNDS procurement → receive with DEFERRED terms → returns (procurement, payable, terms)."""
    deadline = deadline or (timezone.now().date() + timedelta(days=30))
    total = Decimal(qty) * Decimal(unit_price)
    proc = open_procurement(
        tenant_id=ctx['business'].id,
        procurement_type=Procurement.Type.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
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
    pay_procurement_items(tenant_id=ctx['business'].id, procurement_id=proc.id)
    receive_procurement(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        destination_warehouse_id=ctx['storage'].id,
        terms_payload={
            'type': 'DEFERRED',
            'currency_of_obligation': 'UZS',
            'total_amount_due': str(total),
            'deadline_date': deadline,
        },
    )
    payable = SupplierPayable.objects.get(procurement=proc)
    terms = ProcurementTerms.objects.get(procurement=proc)
    return proc, payable, terms


class SupplierPayablesApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_list_returns_open_payables(self):
        self.auth_owner()
        _seed_deferred_procurement(self.ctx)
        res = self.client.get('/api/v1/suppliers/payables/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['status'], 'OPEN')

    def test_filter_by_supplier(self):
        self.auth_owner()
        _, payable, _ = _seed_deferred_procurement(self.ctx)
        res = self.client.get(
            f'/api/v1/suppliers/payables/?supplier={payable.supplier_id}'
        )
        items = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(items), 1)
        # Filter with non-matching supplier returns empty
        res = self.client.get('/api/v1/suppliers/payables/?supplier=99999')
        items = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(items), 0)

    def test_filter_burning_in(self):
        self.auth_owner()
        # Create one near-deadline + one far-deadline
        _seed_deferred_procurement(self.ctx, qty=5, deadline=timezone.now().date() + timedelta(days=3))
        _seed_deferred_procurement(self.ctx, qty=7, deadline=timezone.now().date() + timedelta(days=30))
        res = self.client.get('/api/v1/suppliers/payables/?burning_in=7')
        items = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(items), 1)


class ProcurementTermsDraftApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_draft_terms_persist_and_receive_creates_partial_payable(self):
        self.auth_owner()
        total = Decimal('1000')
        res = self.client.post(
            '/api/v1/partnerships/procurements/',
            data={
                'procurement_type': Procurement.Type.OWN_FUNDS,
                'supplier_id': self.ctx['supplier'].id,
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
                'terms': {
                    'type': 'PARTIAL',
                    'currency_of_obligation': 'UZS',
                    'total_amount_due': str(total),
                    'paid_amount': '400',
                },
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['terms']['type'], 'PARTIAL')
        self.assertEqual(Decimal(res.data['terms']['paid_amount']), Decimal('400.00'))

        procurement_id = res.data['id']
        add_contribution(
            tenant_id=self.ctx['business'].id,
            procurement_id=procurement_id,
            partner_id=self.ctx['operator'].id,
            amount=total,
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=self.ctx['business'].id,
            procurement_id=procurement_id,
        )

        receive_res = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/receive/',
            data={'destination_warehouse_id': self.ctx['storage'].id},
            format='json',
        )
        self.assertEqual(receive_res.status_code, status.HTTP_200_OK)

        payable = SupplierPayable.objects.get(procurement_id=procurement_id)
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.paid_amount, Decimal('400.00'))
        self.assertEqual(payable.remaining_amount, Decimal('600.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.PARTIALLY_PAID)


class SupplierPayablePayApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def setUp(self):
        self.proc, self.payable, self.terms = _seed_deferred_procurement(self.ctx)

    def test_pay_single_cash_full(self):
        self.auth_owner()
        res = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data={
                'allocations': [
                    {'cash_account_id': self.ctx['cash_account'].id,
                     'amount': '1000', 'currency': 'UZS'},
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.status, SupplierPayable.Status.FULLY_PAID)
        self.assertEqual(self.payable.remaining_amount, Decimal('0.00'))

    def test_pay_multi_cash_split(self):
        self.auth_owner()
        res = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data={
                'allocations': [
                    {'cash_account_id': self.ctx['cash_account'].id,
                     'amount': '400', 'currency': 'UZS'},
                    {'cash_account_id': self.ctx['card_account'].id,
                     'amount': '600', 'currency': 'UZS'},
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Payment recorded as MIXED
        payment_id = res.data['id']
        payment = SupplierPayment.objects.get(pk=payment_id)
        self.assertEqual(payment.payment_method, SupplierPayment.PaymentMethod.MIXED)
        self.assertEqual(len(payment.allocations), 2)

    def test_pay_overpayment_rejected(self):
        self.auth_owner()
        res = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data={
                'allocations': [
                    {'cash_account_id': self.ctx['cash_account'].id,
                     'amount': '1500', 'currency': 'UZS'},
                ],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pay_empty_allocations_rejected(self):
        self.auth_owner()
        res = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data={'allocations': []},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pay_idempotency(self):
        self.auth_owner()
        crid = str(uuid.uuid4())
        payload = {
            'allocations': [
                {'cash_account_id': self.ctx['cash_account'].id,
                 'amount': '500', 'currency': 'UZS'},
            ],
            'client_request_id': crid,
        }
        r1 = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data=payload, format='json',
        )
        r2 = self.client.post(
            f'/api/v1/suppliers/payables/{self.payable.id}/pay/',
            data=payload, format='json',
        )
        self.assertEqual(r1.data['id'], r2.data['id'])
        # Payable updated only once
        self.payable.refresh_from_db()
        self.assertEqual(self.payable.paid_amount, Decimal('500.00'))


class TermsAmendmentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self):
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_amend_deadline_propagates_to_payable(self):
        proc, payable, terms = _seed_deferred_procurement(self.ctx)
        new_deadline = timezone.now().date() + timedelta(days=60)

        amendment = apply_terms_amendment(
            tenant_id=self.ctx['business'].id,
            terms_id=terms.id,
            new_fields={'deadline_date': new_deadline},
            reason='Supplier agreed to extend',
        )

        terms.refresh_from_db()
        self.assertEqual(terms.deadline_date, new_deadline)

        payable.refresh_from_db()
        self.assertEqual(payable.deadline_date, new_deadline)

        # Amendment row captures before/after snapshot
        self.assertEqual(amendment.reason, 'Supplier agreed to extend')
        self.assertIn('before', amendment.change_payload)
        self.assertIn('after', amendment.change_payload)
        self.assertNotEqual(
            amendment.change_payload['before']['deadline_date'],
            amendment.change_payload['after']['deadline_date'],
        )

    def test_amend_rejects_unknown_fields(self):
        _, _, terms = _seed_deferred_procurement(self.ctx)
        with self.assertRaises(ValueError):
            apply_terms_amendment(
                tenant_id=self.ctx['business'].id,
                terms_id=terms.id,
                new_fields={'type': 'INSTALLMENT'},  # not amendable
            )

    def test_terms_amendments_endpoint_returns_history(self):
        self.auth_owner()
        proc, _, terms = _seed_deferred_procurement(self.ctx)
        apply_terms_amendment(
            tenant_id=self.ctx['business'].id,
            terms_id=terms.id,
            new_fields={'deadline_date': timezone.now().date() + timedelta(days=45)},
            reason='Supplier confirmed new date',
            user_id=User.objects.get(username='t_owner').id,
        )

        res = self.client.get(
            f'/api/v1/partnerships/procurements/{proc.id}/terms/amendments/',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['reason'], 'Supplier confirmed new date')
        self.assertIn('after', res.data[0]['change_payload'])


class OverdueBeatTaskTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def _seed_installment(self, due_dates):
        """Return a procurement with INSTALLMENT terms whose schedule entries
        have the given due_dates (in order)."""
        total = Decimal('1000')
        proc = open_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
            items=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('100'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            partner_id=self.ctx['operator'].id,
            amount=total, currency='UZS', fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=self.ctx['business'].id, procurement_id=proc.id,
        )
        receive_procurement(
            tenant_id=self.ctx['business'].id,
            procurement_id=proc.id,
            destination_warehouse_id=self.ctx['storage'].id,
            terms_payload={
                'type': 'INSTALLMENT',
                'currency_of_obligation': 'UZS',
                'total_amount_due': str(total),
            },
            schedule_payload=[
                {'sequence_number': i + 1, 'due_date': d,
                 'amount': str(total / len(due_dates))}
                for i, d in enumerate(due_dates)
            ],
        )
        return proc

    def test_marks_only_past_due_pending_as_overdue(self):
        today = timezone.now().date()
        # 2 past-due + 1 future
        self._seed_installment([
            today - timedelta(days=10),
            today - timedelta(days=1),
            today + timedelta(days=10),
        ])

        updated = mark_overdue_payment_schedules()
        self.assertEqual(updated, 2)

        statuses = list(
            PaymentSchedule.objects.order_by('due_date').values_list('status', flat=True)
        )
        self.assertEqual(statuses, ['OVERDUE', 'OVERDUE', 'PENDING'])

    def test_overdue_task_is_registered_in_celery_beat_schedule(self):
        task = settings.CELERY_BEAT_SCHEDULE['analytics.mark-overdue-payment-schedules']
        self.assertEqual(task['task'], 'apps.analytics.tasks.mark_overdue_payment_schedules')
