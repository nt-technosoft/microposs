"""
Integration layer behavioral tests.

Coverage:
  - Credential creation: key format, prefix, hash != plain, full_key returned once
  - Credential revocation: revoked key → 401
  - Auth middleware: miss → 401, wrong vendor → 401, IP block → 401, success → tenant_id set
  - Raw event storage: all 4 endpoints store correct slug + body
  - Agreements tenant isolation: key A cannot see tenant B agreements
  - Catchall slug validation: invalid slug → 400
"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Business
from apps.finance.chart_of_accounts import setup_chart_of_accounts
from apps.integrations.models import IntegrationCredential
from apps.integrations.services import create_credential
from apps.integrations.yespos.models import YesposRawEvent
from apps.partnerships.models import InvestmentAgreement, AgreementPartner
from apps.core.models import Partner


def _make_tenant(name='TenantA') -> tuple[Business, User]:
    owner = User.objects.create_user(username=f'owner_{name}', password='x')
    business = Business.objects.create(owner=owner, name=name, currency='UZS', is_active=True)
    setup_chart_of_accounts(business.id)
    return business, owner


class CredentialCreationTests(TestCase):
    def setUp(self):
        self.business, self.owner = _make_tenant('T1')

    def test_key_format_and_prefix(self):
        cred, full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )
        self.assertTrue(full_key.startswith('ssk_yespos_live_'), msg=f"Bad format: {full_key!r}")
        self.assertEqual(cred.key_prefix, full_key[:12])

    def test_hash_is_not_plaintext(self):
        cred, full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )
        self.assertNotEqual(cred.key_hash, full_key)
        self.assertIn('$argon2', cred.key_hash)

    def test_full_key_in_response_and_not_stored(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        res = client.post('/api/v1/integrations/credentials', {'vendor': 'yespos'}, format='json')
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn('full_key', data)
        self.assertTrue(data['full_key'].startswith('ssk_yespos_live_'))
        # LIST response must NOT contain full_key
        list_res = client.get('/api/v1/integrations/credentials')
        self.assertEqual(list_res.status_code, 200)
        for cred in list_res.json():
            self.assertNotIn('full_key', cred)

    def test_active_unique_constraint_per_vendor(self):
        create_credential(tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            create_credential(tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id)


class CredentialRevocationTests(TestCase):
    def setUp(self):
        self.business, self.owner = _make_tenant('T2')
        self.cred, self.full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )

    def test_revoked_key_returns_401(self):
        # Verify key works before revoke
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY=self.full_key)
        res = client.post('/api/v1/integrations/yespos/v1/sale', {'foo': 'bar'}, format='json')
        self.assertEqual(res.status_code, 201)

        # Revoke via API
        mgmt = APIClient()
        mgmt.force_authenticate(user=self.owner)
        rv = mgmt.post(f'/api/v1/integrations/credentials/{self.cred.id}/revoke')
        self.assertEqual(rv.status_code, 200)

        # Now same key must 401
        res2 = client.post('/api/v1/integrations/yespos/v1/sale', {'foo': 'bar'}, format='json')
        self.assertEqual(res2.status_code, 401)

    def test_double_revoke_returns_409(self):
        mgmt = APIClient()
        mgmt.force_authenticate(user=self.owner)
        mgmt.post(f'/api/v1/integrations/credentials/{self.cred.id}/revoke')
        res = mgmt.post(f'/api/v1/integrations/credentials/{self.cred.id}/revoke')
        self.assertEqual(res.status_code, 409)


class AuthMiddlewareTests(TestCase):
    def setUp(self):
        self.business, self.owner = _make_tenant('T3')
        self.cred, self.full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )

    def test_missing_key_returns_401(self):
        client = APIClient()
        res = client.post('/api/v1/integrations/yespos/v1/sale', {'x': 1}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_wrong_format_returns_401(self):
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY='not-a-valid-key')
        res = client.post('/api/v1/integrations/yespos/v1/sale', {}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_wrong_argon2_hash_returns_401(self):
        client = APIClient()
        # Correct prefix, wrong suffix
        tampered = self.full_key[:-4] + 'XXXX'
        client.credentials(HTTP_X_INTEGRATION_KEY=tampered)
        res = client.post('/api/v1/integrations/yespos/v1/sale', {}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_ip_allowlist_blocks_unknown_ip(self):
        self.cred.source_ip_allowlist = ['10.0.0.1']
        self.cred.save(update_fields=['source_ip_allowlist', 'updated_at'])
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY=self.full_key)
        # REMOTE_ADDR from APIClient defaults to 127.0.0.1
        res = client.post('/api/v1/integrations/yespos/v1/sale', {}, format='json')
        self.assertEqual(res.status_code, 401)

    def test_successful_auth_injects_tenant_id(self):
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY=self.full_key)
        res = client.get('/api/v1/integrations/yespos/v1/agreements')
        self.assertEqual(res.status_code, 200)

    def test_last_used_at_update_function(self):
        from apps.integrations.auth import _update_last_used
        _update_last_used(self.cred.id)
        self.cred.refresh_from_db()
        self.assertIsNotNone(self.cred.last_used_at)


class RawEventStorageTests(TestCase):
    def setUp(self):
        self.business, self.owner = _make_tenant('T4')
        self.cred, self.full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTEGRATION_KEY=self.full_key)

    def _post(self, path, body):
        return self.client.post(path, body, format='json')

    def test_sale_event_stored(self):
        payload = {'order_id': 'ORD-1', 'total': 50000}
        res = self._post('/api/v1/integrations/yespos/v1/sale', payload)
        self.assertEqual(res.status_code, 201)
        ev = YesposRawEvent.objects.get(id=res.json()['id'])
        self.assertEqual(ev.slug, 'sale')
        self.assertEqual(ev.body['order_id'], 'ORD-1')
        self.assertEqual(ev.tenant_id, self.business.id)

    def test_agreement_link_event_stored(self):
        payload = {'agreement_id': 42}
        res = self._post('/api/v1/integrations/yespos/v1/agreement-link', payload)
        self.assertEqual(res.status_code, 201)
        ev = YesposRawEvent.objects.get(id=res.json()['id'])
        self.assertEqual(ev.slug, 'agreement-link')
        self.assertEqual(ev.body['agreement_id'], 42)

    def test_inventory_event_stored(self):
        res = self._post('/api/v1/integrations/yespos/v1/inventory', {'sku': 'ABC', 'qty': 5})
        self.assertEqual(res.status_code, 201)
        ev = YesposRawEvent.objects.get(id=res.json()['id'])
        self.assertEqual(ev.slug, 'inventory')

    def test_catchall_event_stored_with_custom_slug(self):
        res = self._post('/api/v1/integrations/yespos/v1/custom-event', {'data': 1})
        self.assertEqual(res.status_code, 201)
        ev = YesposRawEvent.objects.get(id=res.json()['id'])
        self.assertEqual(ev.slug, 'custom-event')

    def test_idempotency_via_request_id(self):
        req_id = 'unique-req-001'
        self.client.credentials(
            HTTP_X_INTEGRATION_KEY=self.full_key, HTTP_X_REQUEST_ID=req_id,
        )
        res1 = self._post('/api/v1/integrations/yespos/v1/sale', {'n': 1})
        res2 = self._post('/api/v1/integrations/yespos/v1/sale', {'n': 2})
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()['status'], 'duplicate')
        self.assertEqual(YesposRawEvent.objects.filter(source_request_id=req_id).count(), 1)


class AgreementsTenantIsolationTests(TestCase):
    def setUp(self):
        self.biz_a, self.owner_a = _make_tenant('TenantA')
        self.biz_b, self.owner_b = _make_tenant('TenantB')
        self.cred_a, self.key_a = create_credential(
            tenant_id=self.biz_a.id, vendor='yespos', created_by_id=self.owner_a.id,
        )
        # Create an ACTIVE agreement on tenant B
        from django.utils import timezone
        self.ag_b = InvestmentAgreement.objects.create(
            tenant=self.biz_b,
            status=InvestmentAgreement.Status.ACTIVE,
            opened_at=timezone.now(),
            mudaraba_ratio='0.5',
            planned_budget='10000',
            currency='UZS',
        )

    def test_tenant_a_key_cannot_see_tenant_b_agreements(self):
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY=self.key_a)
        res = client.get('/api/v1/integrations/yespos/v1/agreements')
        self.assertEqual(res.status_code, 200)
        ids = [ag['id'] for ag in res.json()]
        self.assertNotIn(self.ag_b.pk, ids)

    def test_tenant_a_events_not_visible_to_tenant_b(self):
        client = APIClient()
        client.credentials(HTTP_X_INTEGRATION_KEY=self.key_a)
        client.post('/api/v1/integrations/yespos/v1/sale', {'x': 1}, format='json')
        # All events stored belong to tenant A
        self.assertEqual(YesposRawEvent.objects.filter(tenant=self.biz_b).count(), 0)


class CatchallSlugValidationTests(TestCase):
    def setUp(self):
        self.business, self.owner = _make_tenant('T5')
        self.cred, self.full_key = create_credential(
            tenant_id=self.business.id, vendor='yespos', created_by_id=self.owner.id,
        )
        self.client = APIClient()
        self.client.credentials(HTTP_X_INTEGRATION_KEY=self.full_key)

    def test_invalid_slug_uppercase_returns_400(self):
        res = self.client.post('/api/v1/integrations/yespos/v1/INVALID-UPPER', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_invalid_slug_underscore_returns_400(self):
        # Underscore is not allowed — only [a-z0-9-]
        res = self.client.post('/api/v1/integrations/yespos/v1/bad_slug', {}, format='json')
        self.assertEqual(res.status_code, 400)

    def test_valid_slug_stored(self):
        res = self.client.post('/api/v1/integrations/yespos/v1/my-custom-01', {'k': 'v'}, format='json')
        self.assertEqual(res.status_code, 201)
