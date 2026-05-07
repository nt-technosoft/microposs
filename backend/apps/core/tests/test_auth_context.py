"""Auth context regression tests."""

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase


class AuthContextTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('reset_workflow_demo')

    def test_linked_investor_gets_investor_role_and_active_tenant(self):
        self.client.force_authenticate(user=User.objects.get(username='investor'))
        response = self.client.get('/api/v1/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'investor')
        self.assertIsNotNone(response.data['active_tenant_id'])
        self.assertEqual(response.data['tenant_name'], 'MicroPOS Workflow')
        self.assertEqual(response.data['locale'], 'ru')

    def test_user_can_update_locale_preference(self):
        self.client.force_authenticate(user=User.objects.get(username='owner'))

        response = self.client.patch('/api/v1/auth/preferences/', {'locale': 'uz'}, format='json')
        me_response = self.client.get('/api/v1/auth/me/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['locale'], 'uz')
        self.assertEqual(me_response.data['locale'], 'uz')

    def test_invalid_locale_is_rejected(self):
        self.client.force_authenticate(user=User.objects.get(username='owner'))

        response = self.client.patch('/api/v1/auth/preferences/', {'locale': 'de'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'unsupported_locale')
