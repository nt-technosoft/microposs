from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import PartnerLedgerEntry

from ._helpers import build_tenant, seed_received_procurement


class InvestorBridgeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        cls.procurement, _ = seed_received_procurement(cls.ctx)
        ledger = cls.procurement.partner_ledgers.get(partner=cls.ctx['investor'])
        PartnerLedgerEntry.objects.create(
            tenant_id=cls.ctx['business'].id,
            ledger=ledger,
            date=cls.procurement.received_at,
            amount=Decimal('150.00'),
            currency='UZS',
            entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
            source_ref='test:profit',
        )

    def auth_investor(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_investor',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_investor_dashboard_and_procurements_are_available(self):
        self.auth_investor()

        dashboard = self.client.get('/api/v1/investors/dashboard/')
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.data['partner_id'], self.ctx['investor'].id)
        self.assertEqual(dashboard.data['profit_pending_payout'], '150.00')

        procurements = self.client.get('/api/v1/investors/procurements/')
        self.assertEqual(procurements.status_code, status.HTTP_200_OK)
        self.assertEqual(len(procurements.data), 1)
        self.assertEqual(procurements.data[0]['id'], self.procurement.id)

        detail = self.client.get(f'/api/v1/investors/procurements/{self.procurement.id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['id'], self.procurement.id)
        self.assertEqual(detail.data['investor_aggregate']['profit_pending_payout'], '150.00')
        self.assertEqual(len(detail.data['investor_ledger']['entries']), 2)
