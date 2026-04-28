from django.contrib.auth.models import Group, User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Business, BusinessRegistrationRequest, Partner
from apps.core.permissions import resolve_user_role


class BusinessRegistrationRequestApiTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_user(
            username='platform-admin',
            password='Admin123!',
        )
        self.platform_admin.is_staff = True
        self.platform_admin.is_superuser = True
        self.platform_admin.save(update_fields=['is_staff', 'is_superuser'])

    @staticmethod
    def payload(**overrides):
        payload = {
            'username': 'new-owner',
            'password': 'Owner123!',
            'first_name': 'Ali',
            'last_name': 'Valiyev',
            'phone': '+998901234567',
            'business_name': 'Ali Market',
        }
        payload.update(overrides)
        return payload

    def test_public_request_can_be_created_and_pending_login_is_blocked(self):
        response = self.client.post(
            '/api/v1/core/business-registration-requests/',
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], BusinessRegistrationRequest.Status.PENDING)
        self.assertEqual(
            BusinessRegistrationRequest.objects.get(username='new-owner').business_name,
            'Ali Market',
        )

        login_response = self.client.post('/api/v1/auth/token/', {
            'username': 'new-owner',
            'password': 'Owner123!',
        }, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(login_response.data['detail'], 'Заявка ещё не подтверждена.')

    def test_platform_admin_can_approve_request_and_create_business_owner(self):
        create_response = self.client.post(
            '/api/v1/core/business-registration-requests/',
            self.payload(),
            format='json',
        )
        request_id = create_response.data['id']

        self.client.force_authenticate(user=self.platform_admin)
        approve_response = self.client.post(
            f'/api/v1/core/business-registration-requests/{request_id}/approve/',
            {},
            format='json',
        )

        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data['status'], BusinessRegistrationRequest.Status.APPROVED)

        user = User.objects.get(username='new-owner')
        business = Business.objects.get(name='Ali Market')
        owner_group = Group.objects.get(name='owner')

        self.assertTrue(user.groups.filter(id=owner_group.id).exists())
        self.assertEqual(business.owner_id, user.id)
        self.assertEqual(resolve_user_role(self.platform_admin), 'platform_admin')
        self.assertTrue(
            Partner.objects.filter(
                tenant=business,
                user=user,
                role=Partner.Role.OPERATOR,
                is_active=True,
            ).exists()
        )

        self.client.force_authenticate(user=None)
        login_response = self.client.post('/api/v1/auth/token/', {
            'username': 'new-owner',
            'password': 'Owner123!',
        }, format='json')
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

    def test_regular_owner_cannot_review_requests(self):
        owner_group, _ = Group.objects.get_or_create(name='owner')
        owner_user = User.objects.create_user(
            username='tenant-owner',
            password='Owner123!',
        )
        owner_user.groups.add(owner_group)

        request_record = BusinessRegistrationRequest.objects.create(
            username='pending-owner',
            password_hash='hashed',
            first_name='Bek',
            last_name='Aliyev',
            phone='+998900000000',
            business_name='Pending Shop',
        )

        self.client.force_authenticate(user=owner_user)

        list_response = self.client.get('/api/v1/core/business-registration-requests/')
        approve_response = self.client.post(
            f'/api/v1/core/business-registration-requests/{request_record.id}/approve/',
            {},
            format='json',
        )

        self.assertEqual(list_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(approve_response.status_code, status.HTTP_403_FORBIDDEN)
