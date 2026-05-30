from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.fx_rates import upsert_exchange_rate
from apps.finance.models import CashEntry, ExchangeRate, JournalEntry, JournalLine, Payment
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
            'funding_source': 'PARTNERSHIP',
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
        upsert_exchange_rate(
            tenant_id=self.ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='test fixture',
        )

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            self.procurement_payload(),
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        procurement_id = create_response.data['id']
        agreement_id = create_response.data['documents']['source']['investment_agreement_id']
        self.assertEqual(create_response.data['status'], Procurement.Status.OPEN)

        contribution_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['investor'].id,
                'amount': '385.00',
                'currency': 'USD',
                'fx_rate': '12000',
                'cash_account_id': self.ctx['cash_account'].id,
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
                'cash_account_id': self.ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(second_contribution.status_code, status.HTTP_201_CREATED)

        allocation_response = self.client.post(
            f'/api/v1/partnerships/agreements/{agreement_id}/allocations/',
            {
                'procurement_id': procurement_id,
                'allocations': [
                    {'partner_id': self.ctx['investor'].id, 'amount': '385.00', 'currency': 'USD', 'fx_rate': '12000'},
                    {'partner_id': self.ctx['operator'].id, 'amount': '165.00', 'currency': 'USD', 'fx_rate': '12000'},
                ],
            },
            format='json',
        )
        self.assertEqual(allocation_response.status_code, status.HTTP_201_CREATED)

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

        receive_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/receive/',
            {'destination_warehouse_id': self.ctx['storage'].id},
            format='json',
        )
        self.assertEqual(receive_response.status_code, status.HTTP_200_OK)
        self.assertEqual(receive_response.data['status'], Procurement.Status.RECEIVED)
        self.assertEqual(len(receive_response.data['documents']['items']), 1)
        self.assertEqual(len(receive_response.data['documents']['receive_batches']), 1)

        # E11: partnership inventory is funded out of the capital pool, so the
        # receive books a CAPITAL_POOL payment (DR 1100 / CR 1300), not a
        # legacy 'receipt' journal that re-credited investor equity.
        pool_payment = Payment.objects.get(
            tenant_id=self.ctx['business'].id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=procurement_id,
        )
        inventory_debit = JournalLine.objects.filter(
            journal_entry=pool_payment.journal_entry,
            account__code='1100',
        ).first()
        self.assertIsNotNone(inventory_debit)
        self.assertGreater(inventory_debit.debit, Decimal('0'))

    def test_owner_can_open_minimal_partnership_procurement_without_supplier_or_items(self):
        self.auth_owner()

        response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': 'PARTNERSHIP',
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
        self.assertIsNone(response.data['documents']['source']['supplier_id'])
        self.assertEqual(response.data['documents']['items'], [])
        self.assertEqual(response.data['documents']['expenses'], [])
        self.assertEqual(response.data['documents']['investment']['planned_budget'], '15000.00')

    def test_owner_can_create_agreement_and_allocate_to_linked_procurement(self):
        self.auth_owner()
        upsert_exchange_rate(
            tenant_id=self.ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='test fixture',
        )

        agreement_response = self.client.post(
            '/api/v1/partnerships/agreements/',
            {
                'planned_budget': '200.00',
                'currency': 'USD',
                'mudaraba_ratio': '0.571429',
                'partners': [
                    {
                        'partner_id': self.ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': '140.00',
                        'profit_share': '0.4',
                    },
                    {
                        'partner_id': self.ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': '60.00',
                        'profit_share': '0.6',
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(agreement_response.status_code, status.HTTP_201_CREATED)
        agreement_id = agreement_response.data['id']

        for partner_id, amount in (
            (self.ctx['investor'].id, '140.00'),
            (self.ctx['operator'].id, '60.00'),
        ):
            contribution = self.client.post(
                f'/api/v1/partnerships/agreements/{agreement_id}/contributions/',
                {
                    'partner_id': partner_id,
                    'amount': amount,
                    'currency': 'USD',
                    'fx_rate': '12000',
                },
                format='json',
            )
            self.assertEqual(contribution.status_code, status.HTTP_201_CREATED)

        procurement_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': 'PARTNERSHIP',
                'supplier_id': self.ctx['supplier'].id,
                'agreement_id': agreement_id,
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': '10',
                    'unit_purchase_price': '10.00',
                    'currency': 'USD',
                    'fx_rate': '12000',
                }],
            },
            format='json',
        )
        self.assertEqual(procurement_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(procurement_response.data['documents']['source']['investment_agreement_id'], agreement_id)
        procurement_id = procurement_response.data['id']

        preview = self.client.get(
            f'/api/v1/partnerships/agreements/{agreement_id}/allocation-preview/',
            {'procurement_id': procurement_id},
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertEqual(preview.data['required'], {'USD': '100.00'})

        allocation = self.client.post(
            f'/api/v1/partnerships/agreements/{agreement_id}/allocations/',
            {
                'procurement_id': procurement_id,
                'allocations': [
                    {
                        'partner_id': row['partner_id'],
                        'amount': row['amount'],
                        'currency': row['currency'],
                        'fx_rate': '12000',
                    }
                    for row in preview.data['suggestions']
                    if Decimal(str(row['amount'])) > 0
                ],
            },
            format='json',
        )
        self.assertEqual(allocation.status_code, status.HTTP_201_CREATED)

        detail = self.client.get(f'/api/v1/partnerships/agreements/{agreement_id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail.data['procurements']), 1)
        available = {
            row['partner_id']: row['available_amount']
            for row in detail.data['participant_totals']
        }
        self.assertEqual(available[self.ctx['investor'].id], '70.00')
        self.assertEqual(available[self.ctx['operator'].id], '30.00')

    def test_owner_can_update_open_procurement_after_opening_it_empty(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': 'PARTNERSHIP',
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
                'funding_source': 'PARTNERSHIP',
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
        self.assertEqual(update_response.data['documents']['source']['supplier_id'], self.ctx['supplier'].id)
        self.assertEqual(update_response.data['documents']['procurement']['notes'], 'Now filled with actual lines')
        self.assertEqual(len(update_response.data['documents']['items']), 1)
        self.assertEqual(len(update_response.data['documents']['expenses']), 1)

    # legacy: superseded by E07 workspace dispatch — balance_exchanges not part of E07 contract
    # def test_owner_can_exchange_procurement_balance_inside_procurement(self): ...

    def test_owner_cannot_change_contract_after_balance_activity(self):
        self.auth_owner()

        create_response = self.client.post(
            '/api/v1/partnerships/procurements/',
            {
                'funding_source': 'PARTNERSHIP',
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
        agreement_id = create_response.data['documents']['source']['investment_agreement_id']

        contribution_response = self.client.post(
            f'/api/v1/partnerships/procurements/{procurement_id}/contributions/',
            {
                'partner_id': self.ctx['investor'].id,
                'amount': '100.00',
                'currency': 'USD',
                'fx_rate': '12000',
                'cash_account_id': self.ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(contribution_response.status_code, status.HTTP_201_CREATED)

        allocation_response = self.client.post(
            f'/api/v1/partnerships/agreements/{agreement_id}/allocations/',
            {
                'procurement_id': procurement_id,
                'allocations': [{'partner_id': self.ctx['investor'].id, 'amount': '100.00', 'currency': 'USD', 'fx_rate': '12000'}],
            },
            format='json',
        )
        self.assertEqual(allocation_response.status_code, status.HTTP_201_CREATED)

        update_response = self.client.put(
            f'/api/v1/partnerships/procurements/{procurement_id}/',
            {
                'funding_source': 'PARTNERSHIP',
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
        self.assertIn('capital activity', str(update_response.data))

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
        self.assertEqual(len(response.data['investment']['partners']), 2)
        self.assertGreater(len(response.data['investment']['contributions']), 0)

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
        self.assertEqual(JournalEntry.objects.filter(operation_id=response.data['id'], operation_type='payment').count(), 1)
