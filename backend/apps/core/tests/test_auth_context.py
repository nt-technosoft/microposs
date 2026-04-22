"""Auth context regression tests."""

from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase


class AuthContextTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('reset_workflow_demo')

    def test_unlinked_investor_keeps_investor_role_without_active_tenant(self):
        token_response = self.client.post('/api/v1/auth/token/', {
            'username': 'investor',
            'password': 'Investor123!',
        }, format='json')
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_response.data['access']}")
        response = self.client.get('/api/v1/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'investor')
        self.assertIsNone(response.data['active_tenant_id'])
