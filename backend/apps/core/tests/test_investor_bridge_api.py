from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class InvestorBridgeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        cls.procurement, _ = seed_received_procurement(cls.ctx)
        session = open_session(cls.ctx)
        # E17: real venture profit via a profitable sale (no manual ledger fake).
        create_sale(
            tenant_id=cls.ctx['business'].id,
            pos_session_id=session.id,
            location_id=cls.ctx['store'].id,
            sold_by_id=cls.ctx['cashier'].id,
            customer_id=cls.ctx['customer'].id,
            lines=[{
                'product_variant_id': cls.ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': cls.ctx['cash_account'].id,
            }],
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
        # E17: venture entitlement is non-zero, but profit is not payable before
        # a venture settlement.
        self.assertNotEqual(dashboard.data['profit_accrued'], '0.00')
        self.assertEqual(dashboard.data['profit_pending_payout'], '0.00')

        procurements = self.client.get('/api/v1/investors/procurements/')
        self.assertEqual(procurements.status_code, status.HTTP_200_OK)
        self.assertEqual(len(procurements.data), 1)
        self.assertEqual(procurements.data[0]['id'], self.procurement.id)

        detail = self.client.get(f'/api/v1/investors/procurements/{self.procurement.id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['id'], self.procurement.id)
        self.assertNotEqual(detail.data['investor_aggregate']['profit_accrued'], '0.00')
        self.assertEqual(detail.data['investor_aggregate']['profit_pending_payout'], '0.00')
        # PartnerLedgerEntry now holds only physical events (capital/dividends).
        self.assertGreaterEqual(len(detail.data['investor_ledger']['entries']), 1)
