from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import PartnerLedgerEntry, Procurement

from ._helpers import build_tenant, seed_received_procurement


class PartnershipsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self) -> None:
        response = self.client.post('/api/v1/auth/token/', {
            'username': 't_owner',
            'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def procurement_payload(self) -> dict:
        return {
            'procurement_type': Procurement.Type.PARTNERSHIP,
            'supplier_id': self.ctx['supplier'].id,
            'notes': 'API bridge procurement',
            'contract': {
                'mudaraba_ratio': '0.571429',
                'planned_budget': '550.00',
                'currency': 'USD',
                'partners': [
                    {
                        'partner_id': self.ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': '385.00',
                        'profit_share': '0.4',
                    },
                    {
                        'partner_id': self.ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': '165.00',
                        'profit_share': '0.6',
                    },
                ],
            },
            'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '50',
                'unit_purchase_price': '10.00',
                'currency': 'USD',
                'fx_rate': '12000',
            }],
            'expenses': [{
                'expense_type': 'CUSTOMS',
                'amount': '50.00',
                'currency': 'USD',
                'fx_rate': '12000',
            }],
        }

    def test_owner_can_create_and_receive_procurement_via_api(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            self.procurement_payload(),
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        procurement_id = create_response.data['id']
        self.assertEqual(create_response.data['status'], Procurement.Status.OPEN)

        contribution_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['investor'].id,
                'amount': '385.00',
                'currency': 'USD',
                'fx_rate': '12000',
            },
            format='json',
        )
        self.assertEqual(contribution_response.status_code, status.HTTP_201_CREATED)

        withdrawal_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/withdrawals/',
            {
                'amount': '385.00',
                'currency': 'USD',
                'fx_rate': '12000',
                'reason': 'Supplier payment part 1',
            },
            format='json',
        )
        self.assertEqual(withdrawal_response.status_code, status.HTTP_201_CREATED)

        second_contribution = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['operator'].id,
                'amount': '165.00',
                'currency': 'USD',
                'fx_rate': '12000',
            },
            format='json',
        )
        self.assertEqual(second_contribution.status_code, status.HTTP_201_CREATED)

        second_withdrawal = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/withdrawals/',
            {
                'amount': '165.00',
                'currency': 'USD',
                'fx_rate': '12000',
                'reason': 'Supplier payment part 2',
            },
            format='json',
        )
        self.assertEqual(second_withdrawal.status_code, status.HTTP_201_CREATED)

        expense_withdrawal = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/withdrawals/',
            {
                'amount': '0.00',
                'currency': 'USD',
                'fx_rate': '12000',
                'reason': 'noop',
            },
            format='json',
        )
        self.assertEqual(expense_withdrawal.status_code, status.HTTP_400_BAD_REQUEST)

        procurement_detail = self.client.get(f'/api/v1/partnerships/procurements/{procurement_id}/')
        self.assertEqual(procurement_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(procurement_detail.data['balance']['balances'], {'USD': '0.00'})

        receive_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/receive/',
            {'destination_warehouse_id': self.ctx['storage'].id},
            format='json',
        )
        self.assertEqual(receive_response.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_response.data['status'], Procurement.Status.RECEIVED)
        self.assertEqual(receive_response.data['items_count'], 1)

    def test_owner_can_view_procurement_ledger(self):
        self.auth_owner()
        procurement, _ = seed_received_procurement(self.ctx)

        response = self.client.get(f'/api/v1/partnerships/procurements/{procurement.id}/ledger/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['partners']), 2)
        entry_types = {
            entry['entry_type']
            for partner in response.data['partners']
            for entry in partner['entries']
        }
        self.assertSetEqual(entry_types, {PartnerLedgerEntry.EntryType.CAPITAL_IN})

    def test_owner_can_create_dividend_payment_via_api(self):
        self.auth_owner()
        procurement, _ = seed_received_procurement(self.ctx)

        PartnerLedgerEntry.objects.create(
            tenant_id=self.ctx['business'].id,
            ledger_id=procurement.partner_ledgers.get(partner=self.ctx['investor']).id,
            date=procurement.received_at,
            amount=Decimal('100.00'),
            currency='UZS',
            entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
            source_ref='test:profit',
        )

        response = self.client.post(
            '/api/v1/partnerships/dividends/',
            {
                'partner_id': self.ctx['investor'].id,
                'procurement_id': procurement.id,
                'amount': '50.00',
                'currency': 'UZS',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], '50.00')
