"""Auth context regression tests."""

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase


class AuthContextTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('reset_workflow_demo')

    def test_unlinked_investor_keeps_investor_role_without_active_tenant(self):
        self.client.force_authenticate(user=User.objects.get(username='investor'))
        response = self.client.get('/api/v1/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'investor')
        self.assertIsNone(response.data['active_tenant_id'])
