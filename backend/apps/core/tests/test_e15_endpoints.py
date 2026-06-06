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

    def test_capital_positions_and_settle_partner(self):
        # Net position: investor under-contributed 4 (owes pool), operator -4.
        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/capital-positions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_partner = {r['partner_id']: r for r in resp.data}
        self.assertEqual(by_partner[self.advance.debtor_id]['net'], '4.00')

        # Settle the debtor's shortfall per-partner.
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-partner-capital/',
            {'partner_id': self.advance.debtor_id, 'amount': '4.00', 'source': 'CASH'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_partner = {r['partner_id']: r for r in resp.data}
        self.assertEqual(by_partner[self.advance.debtor_id]['net'], '0.00')

    def test_settle_partner_overpayment_rejected(self):
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-partner-capital/',
            {'partner_id': self.advance.debtor_id, 'amount': '99.00', 'source': 'CASH'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profit_summary_is_empty_without_settled_venture_profit(self):
        # E17: profit-summary lists payable profit from the venture model, which
        # is unavailable before a venture settlement. With no sales/settlement
        # there is nothing payable. The positive case (payable rows after a
        # constructive/final settlement) is covered by the E16 venture tests;
        # the legacy "manual PROFIT_ACCRUED → payable" path no longer applies.
        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/profit-summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])
