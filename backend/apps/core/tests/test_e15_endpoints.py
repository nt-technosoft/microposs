"""
E15 Phase 4 — REST endpoints for inter-partner advances.

GET  /api/v1/partnerships/agreements/{id}/advances/        — list advances
POST /api/v1/partnerships/agreements/{id}/settle-advance/   — settle one (CASH/FROM_PROFIT)
"""

from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import CapitalAdvance, ProcurementReceiveBatch

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


class CapitalAdvanceEndpointTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))
        procurement = _build_funded(
            self.ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(self.ctx, procurement, share_basis='AGREED', allocations=(Decimal('66'), Decimal('34')))
        self.agreement_id = procurement.agreement_id
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
        self.advance = CapitalAdvance.objects.get(batch=batch)

    def test_list_advances(self):
        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/advances/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['outstanding_balance'], '4.00')
        self.assertEqual(resp.data[0]['status'], 'OUTSTANDING')

    def test_settle_advance_cash(self):
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-advance/',
            {'advance_id': self.advance.id, 'amount': '4.00', 'source': 'CASH'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'SETTLED')
        self.assertEqual(resp.data['outstanding_balance'], '0.00')

    def test_settle_overpayment_rejected(self):
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-advance/',
            {'advance_id': self.advance.id, 'amount': '99.00', 'source': 'CASH'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profit_summary_lists_payable_rows(self):
        from apps.partnerships.agreement_services import append_ledger_entry, get_or_create_ledger
        from apps.partnerships.models import PartnerLedgerEntry

        # No accrued profit yet → empty payable list.
        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/profit-summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

        # Accrue profit for the investor on the agreement's procurement.
        procurement_id = ProcurementReceiveBatch.objects.get(pk=self.advance.batch_id).procurement_id
        ledger = get_or_create_ledger(
            procurement_id=procurement_id, partner_id=self.advance.debtor_id,
            tenant_id=self.ctx['business'].id)
        append_ledger_entry(ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=Decimal('25'), currency='UZS')

        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/profit-summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['partner_id'], self.advance.debtor_id)
        self.assertEqual(resp.data[0]['pending'], '25.00')
