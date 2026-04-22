from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Business, BusinessInvestorRelation, Partner

from ._helpers import build_tenant


class TenantContextRegressionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

        cls.foreign_owner = User.objects.create_user(username='foreign_owner', password='x')
        cls.foreign_investor_user = User.objects.create_user(username='foreign_investor', password='x')
        cls.foreign_business = Business.objects.create(
            owner=cls.foreign_owner,
            name='Foreign Tenant',
            currency='UZS',
            is_active=True,
        )
        cls.foreign_investor = Partner.objects.create(
            tenant=cls.foreign_business,
            role=Partner.Role.INVESTOR,
            display_name='Foreign Investor',
            user=cls.foreign_investor_user,
            is_active=True,
        )
        BusinessInvestorRelation.objects.create(
            tenant=cls.foreign_business,
            partner=cls.foreign_investor,
            status=BusinessInvestorRelation.Status.ACTIVE,
            source=BusinessInvestorRelation.Source.MANUAL,
            created_by=cls.foreign_owner,
        )

    def test_owner_foreign_header_is_clamped_to_owned_tenant_on_auth_me(self):
        self.client.force_authenticate(user=self.ctx['owner'])

        response = self.client.get(
            '/api/v1/auth/me/',
            HTTP_X_TENANT_ID=str(self.foreign_business.id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'owner')
        self.assertEqual(response.data['active_tenant_id'], self.ctx['business'].id)
        self.assertEqual(response.data['tenant_name'], self.ctx['business'].name)

    def test_owner_foreign_header_does_not_leak_foreign_investor_rows(self):
        self.client.force_authenticate(user=self.ctx['owner'])

        response = self.client.get(
            '/api/v1/core/partners/?role=INVESTOR&is_active=true',
            HTTP_X_TENANT_ID=str(self.foreign_business.id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual([row['id'] for row in rows], [self.ctx['investor'].id])

    def test_linked_investor_foreign_header_is_clamped_on_auth_me(self):
        self.client.force_authenticate(user=self.ctx['investor'].user)

        response = self.client.get(
            '/api/v1/auth/me/',
            HTTP_X_TENANT_ID=str(self.foreign_business.id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'investor')
        self.assertEqual(response.data['active_tenant_id'], self.ctx['business'].id)
        self.assertEqual(response.data['tenant_name'], self.ctx['business'].name)

    def test_linked_investor_foreign_header_cannot_switch_dashboard_scope(self):
        self.client.force_authenticate(user=self.ctx['investor'].user)

        response = self.client.get(
            '/api/v1/investors/dashboard/',
            HTTP_X_TENANT_ID=str(self.foreign_business.id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['partner_id'], self.ctx['investor'].id)
