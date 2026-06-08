"""
E15/E17 — REST endpoints for partner net-capital reconciliation.

GET  /api/v1/partnerships/agreements/{id}/capital-positions/      — net positions
POST /api/v1/partnerships/agreements/{id}/settle-partner-capital/ — settle a shortfall
GET  /api/v1/partnerships/agreements/{id}/profit-summary/         — payable venture profit
"""

from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


class PartnerCapitalEndpointTests(APITestCase):
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
        self.investor_id = self.ctx['investor'].id

    def test_capital_positions_and_settle_partner(self):
        # Net position: investor under-contributed 4 (owes pool), operator -4.
        resp = self.client.get(f'/api/v1/partnerships/agreements/{self.agreement_id}/capital-positions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_partner = {r['partner_id']: r for r in resp.data}
        self.assertEqual(by_partner[self.investor_id]['net'], '4.00')

        # Settle the debtor's shortfall per-partner.
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-partner-capital/',
            {'partner_id': self.investor_id, 'amount': '4.00', 'source': 'CASH'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_partner = {r['partner_id']: r for r in resp.data}
        self.assertEqual(by_partner[self.investor_id]['net'], '0.00')

    def test_settle_partner_overpayment_rejected(self):
        resp = self.client.post(
            f'/api/v1/partnerships/agreements/{self.agreement_id}/settle-partner-capital/',
            {'partner_id': self.investor_id, 'amount': '99.00', 'source': 'CASH'},
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
