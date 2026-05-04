from io import StringIO

from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.management.commands.bootstrap_deploy_baseline import (
    BASELINE_PROCUREMENT_NOTES,
    BASELINE_SALE_NOTES,
)
from apps.core.models import BusinessInvestorRelation, Partner
from apps.investors.models import Investor
from apps.partnerships.models import Procurement
from apps.sales.models import Sale


class BootstrapDeployBaselineTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        out = StringIO()
        call_command('bootstrap_deploy_baseline', '--confirm-production-bootstrap', stdout=out)
        call_command('bootstrap_deploy_baseline', '--confirm-production-bootstrap', stdout=out)

    def auth_investor(self):
        response = self.client.post('/api/v1/auth/token/', {
            'username': 'investor',
            'password': 'Investor123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_baseline_links_investor_to_business_and_owner_surfaces(self):
        investor_partner = Partner.objects.get(
            role=Partner.Role.INVESTOR,
            user__username='investor',
        )
        self.assertTrue(
            BusinessInvestorRelation.objects.filter(
                tenant=investor_partner.tenant,
                partner=investor_partner,
                status=BusinessInvestorRelation.Status.ACTIVE,
            ).exists()
        )
        self.assertTrue(
            Investor.objects.filter(
                tenant=investor_partner.tenant,
                user__username='investor',
                is_active=True,
            ).exists()
        )

    def test_baseline_seeds_single_demo_procurement_and_sale(self):
        self.assertEqual(
            Procurement.objects.filter(notes=BASELINE_PROCUREMENT_NOTES).count(),
            1,
        )
        self.assertEqual(
            Sale.objects.filter(notes=BASELINE_SALE_NOTES).count(),
            1,
        )

    def test_investor_dashboard_is_not_empty_after_bootstrap(self):
        self.auth_investor()

        dashboard = self.client.get('/api/v1/investors/dashboard/')
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertNotEqual(dashboard.data['capital_net'], '0.00')
        self.assertNotEqual(dashboard.data['profit_pending_payout'], '0.00')

        procurements = self.client.get('/api/v1/investors/procurements/')
        self.assertEqual(procurements.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(procurements.data), 1)
