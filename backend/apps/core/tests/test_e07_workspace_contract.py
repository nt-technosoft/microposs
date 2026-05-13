from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from apps.inventory.models import Lot
from apps.partnerships.models import Procurement, ProcurementExpense, ProcurementItem
from apps.partnerships.workspace import (
    build_workspace_payload,
    create_workspace,
    dispatch_workspace_action,
)

from ._helpers import build_tenant


class ProcurementWorkspaceContractTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def test_own_funds_cost_payment_and_receive_use_target_contracts(self):
        procurement = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
                'expenses': [{
                    'expense_type': ProcurementExpense.ExpenseType.LOGISTICS,
                    'amount': '250',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'allocation_method': ProcurementExpense.AllocationMethod.BY_VALUE,
                }],
            }},
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'PREPAID',
                'currency_of_obligation': 'UZS',
                'total_amount_due': '1250',
            }},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='PAY_COSTS',
            payload={'payload': {'cash_account_id': self.cash.id}},
        )
        self.assertEqual(
            set(procurement.items.values_list('lifecycle_state', flat=True)),
            {ProcurementItem.LifecycleState.READY_FOR_RECEIVE},
        )
        self.assertEqual(
            set(procurement.expenses.values_list('lifecycle_state', flat=True)),
            {ProcurementExpense.LifecycleState.READY_FOR_RECEIVE},
        )

        procurement = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )

        procurement.refresh_from_db()
        self.assertEqual(procurement.status, Procurement.Status.RECEIVED)
        self.assertEqual(Lot.objects.filter(procurement_item__procurement=procurement).count(), 1)
        payload = build_workspace_payload(procurement)
        self.assertEqual(payload['flow']['current_step'], 'history')
        self.assertEqual(
            [step['key'] for step in payload['flow']['steps']],
            [
                'purchase_intent',
                'supplier_settlement',
                'funding',
                'payment_obligation',
                'goods_receipt',
                'history',
            ],
        )
        self.assertEqual(payload['documents']['source']['funding_source'], Procurement.FundingSource.OWN_FUNDS)
        self.assertEqual(payload['summaries']['receive_batches_count'], 1)


class ProcurementWorkspaceFacadeApiTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.client.force_authenticate(user=self.ctx['owner'])
        self.cash = self.ctx['cash_account']
        self.cash.balance = Decimal('5000.00')
        self.cash.save(update_fields=['balance', 'updated_at'])

    def test_legacy_procurement_endpoint_is_workspace_facade(self):
        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': Procurement.FundingSource.OWN_FUNDS,
                'supplier_id': self.ctx['supplier'].id,
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '100',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
                'terms': {
                    'type': 'PREPAID',
                    'currency_of_obligation': 'UZS',
                    'total_amount_due': '1000',
                },
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        procurement_id = create_response.data['id']
        self.assertEqual(
            create_response.data['documents']['source']['funding_source'],
            Procurement.FundingSource.OWN_FUNDS,
        )

        pay_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/pay-items/',
            {'cash_account_id': self.cash.id},
            format='json',
        )
        self.assertEqual(pay_response.status_code, 200)
        self.assertEqual(
            pay_response.data['documents']['items'][0]['lifecycle_state'],
            ProcurementItem.LifecycleState.READY_FOR_RECEIVE,
        )

        receive_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/receive/',
            {'destination_warehouse_id': self.ctx['storage'].id},
            format='json',
        )
        self.assertEqual(receive_response.status_code, 200)
        self.assertEqual(receive_response.data['status'], Procurement.Status.RECEIVED)
