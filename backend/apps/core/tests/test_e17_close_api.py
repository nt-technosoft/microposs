"""E17 Phase 5a — REST close endpoints for procurement venture & agreement.

The backend close services are the single source of gate truth; these endpoints
expose them (close + close-preview) so the UI only displays blocking reasons.
"""

import uuid
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import InvestmentAgreement, Procurement

from ._helpers import build_tenant, open_session, seed_received_procurement
from .test_e17_close import _final_settle, _pay_out_everything, _sell


class ProcurementCloseApiTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.client.force_authenticate(user=self.ctx['owner'])

    def _url(self, procurement, suffix):
        return f'/api/v1/partnerships/procurements/{procurement.id}/{suffix}/'

    def _closeable(self):
        procurement, _ = seed_received_procurement(self.ctx)
        session = open_session(self.ctx)
        _sell(self.ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(self.ctx, procurement)
        _pay_out_everything(self.ctx, procurement)
        return procurement

    def test_close_preview_blocked_then_ok(self):
        procurement, _ = seed_received_procurement(self.ctx)
        session = open_session(self.ctx)
        _sell(self.ctx, session, quantity=50, unit_price='240000.00')  # no FINAL yet
        resp = self.client.get(self._url(procurement, 'close-preview'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['closeable'])
        self.assertTrue(resp.data['blocking_reasons'])

    def test_close_ok(self):
        procurement = self._closeable()
        resp = self.client.post(self._url(procurement, 'close'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        procurement.refresh_from_db()
        self.assertEqual(procurement.status, Procurement.Status.CLOSED)

    def test_close_blocked_returns_400_with_reasons(self):
        procurement, _ = seed_received_procurement(self.ctx)
        session = open_session(self.ctx)
        _sell(self.ctx, session, quantity=50, unit_price='240000.00')  # no FINAL → not closeable
        resp = self.client.post(self._url(procurement, 'close'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(resp.data['blocking_reasons'])
        procurement.refresh_from_db()
        self.assertNotEqual(procurement.status, Procurement.Status.CLOSED)

    def test_close_idempotent(self):
        procurement = self._closeable()
        rid = str(uuid.uuid4())
        first = self.client.post(self._url(procurement, 'close'), {'client_request_id': rid}, format='json')
        second = self.client.post(self._url(procurement, 'close'), {'client_request_id': rid}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)


class AgreementCloseApiTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.client.force_authenticate(user=self.ctx['owner'])

    def _url(self, agreement_id, suffix):
        return f'/api/v1/partnerships/agreements/{agreement_id}/{suffix}/'

    def _fully_closed_procurement(self):
        procurement, _ = seed_received_procurement(self.ctx)
        session = open_session(self.ctx)
        _sell(self.ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(self.ctx, procurement)
        _pay_out_everything(self.ctx, procurement)
        self.client.post(self._procurement_close(procurement), {}, format='json')
        return procurement

    def _procurement_close(self, procurement):
        return f'/api/v1/partnerships/procurements/{procurement.id}/close/'

    def test_close_blocked_until_procurements_closed(self):
        procurement, _ = seed_received_procurement(self.ctx)
        resp = self.client.post(self._url(procurement.agreement_id, 'close'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(resp.data['blocking_reasons'])

    def test_close_ok_after_procurement_closed(self):
        procurement = self._fully_closed_procurement()
        preview = self.client.get(self._url(procurement.agreement_id, 'close-preview'))
        self.assertTrue(preview.data['closeable'], preview.data)
        resp = self.client.post(self._url(procurement.agreement_id, 'close'), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], InvestmentAgreement.Status.CLOSED)

    def test_close_idempotent(self):
        procurement = self._fully_closed_procurement()
        rid = str(uuid.uuid4())
        first = self.client.post(self._url(procurement.agreement_id, 'close'), {'client_request_id': rid}, format='json')
        second = self.client.post(self._url(procurement.agreement_id, 'close'), {'client_request_id': rid}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['status'], InvestmentAgreement.Status.CLOSED)
