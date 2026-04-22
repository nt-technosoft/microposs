from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import CashEntry, JournalEntry
from apps.core.models import BusinessInvestorRelation, Partner
from apps.partnerships.models import PartnerLedgerEntry, Procurement

from ._helpers import build_tenant, seed_received_procurement


class PartnershipsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

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

        pay_items_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/pay-items/',
            {
                'reason': 'Pay draft items',
            },
            format='json',
        )
        self.assertEqual(pay_items_response.status_code, status.HTTP_200_OK)

        pay_expenses_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/pay-expenses/',
            {
                'reason': 'Pay draft expenses',
            },
            format='json',
        )
        self.assertEqual(pay_expenses_response.status_code, status.HTTP_200_OK)

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

        receipt_journal = JournalEntry.objects.filter(
            operation_type='receipt',
            operation_id=procurement_id,
        )
        self.assertEqual(receipt_journal.count(), 1)

    def test_owner_can_open_minimal_partnership_procurement_without_supplier_or_items(self):
        self.auth_owner()

        response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'procurement_type': Procurement.Type.PARTNERSHIP,
                'notes': 'Draft-only procurement',
                'contract': {
                    'mudaraba_ratio': '0.571429',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.4',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
                            'profit_share': '0.6',
                        },
                    ],
                },
                'items': [],
                'expenses': [],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], Procurement.Status.OPEN)
        self.assertIsNone(response.data['supplier'])
        self.assertEqual(response.data['items'], [])
        self.assertEqual(response.data['expenses'], [])
        self.assertEqual(response.data['contract']['planned_budget'], '15000.00')

    def test_owner_can_update_open_procurement_after_opening_it_empty(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'procurement_type': Procurement.Type.PARTNERSHIP,
                'notes': 'Draft-only procurement',
                'contract': {
                    'mudaraba_ratio': '0.571429',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.4',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
                            'profit_share': '0.6',
                        },
                    ],
                },
                'items': [],
                'expenses': [],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        procurement_id = create_response.data['id']

        update_response = self.client.put(
            f'/api/v1/partnerships/procurements/{procurement_id}/',
            {
                'procurement_type': Procurement.Type.PARTNERSHIP,
                'supplier_id': self.ctx['supplier'].id,
                'notes': 'Now filled with actual lines',
                'contract': {
                    'mudaraba_ratio': '0.571429',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.4',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
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
            },
            format='json',
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['supplier'], self.ctx['supplier'].id)
        self.assertEqual(update_response.data['notes'], 'Now filled with actual lines')
        self.assertEqual(len(update_response.data['items']), 1)
        self.assertEqual(len(update_response.data['expenses']), 1)

    def test_owner_can_exchange_procurement_balance_inside_procurement(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'procurement_type': Procurement.Type.PARTNERSHIP,
                'notes': 'Exchange in procurement',
                'contract': {
                    'mudaraba_ratio': '0.571429',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.4',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
                            'profit_share': '0.6',
                        },
                    ],
                },
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        procurement_id = create_response.data['id']

        contribution_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['investor'].id,
                'amount': '1000.00',
                'currency': 'USD',
                'fx_rate': '12000',
            },
            format='json',
        )
        self.assertEqual(contribution_response.status_code, status.HTTP_201_CREATED)

        exchange_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/balance-exchanges/',
            {
                'from_currency': 'USD',
                'from_amount': '100.00',
                'to_currency': 'UZS',
                'rate': '12000',
                'notes': 'Exchange for customs',
            },
            format='json',
        )
        self.assertEqual(exchange_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(exchange_response.data['from_currency'], 'USD')
        self.assertEqual(exchange_response.data['to_currency'], 'UZS')
        self.assertEqual(exchange_response.data['to_amount'], '1200000.00')

        detail_response = self.client.get(f'/api/v1/partnerships/procurements/{procurement_id}/')
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data['balance']['balances']['USD'], '900.00')
        self.assertEqual(detail_response.data['balance']['balances']['UZS'], '1200000.00')
        self.assertEqual(len(detail_response.data['balance']['exchanges']), 1)
        self.assertEqual(len(detail_response.data['balance']['contributions']), 1)
        self.assertEqual(len(detail_response.data['balance']['participant_totals']), 2)
        self.assertEqual(
            detail_response.data['balance']['participant_totals'][0]['actual_capital_share'],
            '1.000000',
        )
        self.assertEqual(
            {item['kind'] for item in detail_response.data['balance']['history']},
            {'CONTRIBUTION', 'EXCHANGE'},
        )

    def test_owner_cannot_change_contract_after_balance_activity(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'procurement_type': Procurement.Type.PARTNERSHIP,
                'notes': 'Draft-only procurement',
                'contract': {
                    'mudaraba_ratio': '0.571429',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.4',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
                            'profit_share': '0.6',
                        },
                    ],
                },
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        procurement_id = create_response.data['id']

        contribution_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['investor'].id,
                'amount': '100.00',
                'currency': 'USD',
                'fx_rate': '12000',
            },
            format='json',
        )
        self.assertEqual(contribution_response.status_code, status.HTTP_201_CREATED)

        update_response = self.client.put(
            f'/api/v1/partnerships/procurements/{procurement_id}/',
            {
                'procurement_type': Procurement.Type.MUSHARAKA,
                'notes': 'Try to mutate contract after money movement',
                'contract': {
                    'mudaraba_ratio': '1',
                    'planned_budget': '15000.00',
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': self.ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': '10500.00',
                            'profit_share': '0.700000',
                        },
                        {
                            'partner_id': self.ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': '4500.00',
                            'profit_share': '0.300000',
                        },
                    ],
                },
                'items': [],
                'expenses': [],
            },
            format='json',
        )

        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Нельзя менять тип или договор', str(update_response.data))

    def test_owner_can_list_core_partners_for_contract_builder(self):
        self.auth_owner()

        response = self.client.get('/api/v1/core/partners/?is_active=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 2)
        self.assertSetEqual(
            {row['role'] for row in rows},
            {'INVESTOR', 'OPERATOR'},
        )

    def test_unrelated_investors_are_hidden_from_contract_builder(self):
        self.auth_owner()
        user = self.ctx['investor'].user.__class__.objects.create_user(
            username='unrelated_investor',
            password='x',
        )
        Partner.objects.create(
            tenant=self.ctx['business'],
            role=Partner.Role.INVESTOR,
            display_name='Hidden investor',
            user=user,
            is_active=True,
        )

        response = self.client.get('/api/v1/core/partners/?role=INVESTOR&is_active=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual([row['id'] for row in rows], [self.ctx['investor'].id])

    def test_owner_invites_and_new_investor_registers_from_link(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/core/investor-invites/',
            {
                'email': 'new-investor@example.com',
                'display_name': 'New Investor',
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        token = create_response.data['token']

        self.client.credentials()
        preview_response = self.client.get(f'/api/v1/core/investor-invites/{token}/preview/')
        self.assertEqual(preview_response.status_code, status.HTTP_200_OK)
        self.assertEqual(preview_response.data['business_name'], self.ctx['business'].name)

        register_response = self.client.post(
            f'/api/v1/core/investor-invites/{token}/register/',
            {
                'username': 'new_investor',
                'password': 'Investor123!',
                'display_name': 'New Investor',
                'email': 'new-investor@example.com',
            },
            format='json',
        )
        self.assertEqual(register_response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', register_response.data)
        self.assertTrue(BusinessInvestorRelation.objects.filter(
            tenant=self.ctx['business'],
            partner__user__username='new_investor',
            status=BusinessInvestorRelation.Status.ACTIVE,
        ).exists())

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

        self.ctx['cash_account'].balance = Decimal('200.00')
        self.ctx['cash_account'].save(update_fields=['balance', 'updated_at'])

        response = self.client.post(
            '/api/v1/partnerships/dividends/',
            {
                'partner_id': self.ctx['investor'].id,
                'procurement_id': procurement.id,
                'amount': '50.00',
                'currency': 'UZS',
                'paid_from_account_id': self.ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['amount'], '50.00')
        self.assertEqual(CashEntry.objects.filter(source_ref_type='dividend_payment').count(), 1)
        self.assertEqual(JournalEntry.objects.filter(operation_id=response.data['id']).count(), 1)
