from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class SaleExplanationApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        cls.procurement, _ = seed_received_procurement(cls.ctx)
        cls.session = open_session(cls.ctx)
        cls.sale = create_sale(
            tenant_id=cls.ctx['business'].id,
            pos_session_id=cls.session.id,
            location_id=cls.ctx['store'].id,
            sold_by_id=cls.ctx['cashier'].id,
            customer_id=cls.ctx['customer'].id,
            lines=[{
                'product_variant_id': cls.ctx['variant'].id,
                'quantity': 2,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[
                {
                    'amount': Decimal('200000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CASH,
                    'account_id': cls.ctx['cash_account'].id,
                },
                {
                    'amount': Decimal('280000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CREDIT,
                },
            ],
        )

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=self.ctx['owner'])

    def auth_cashier(self) -> None:
        self.client.force_authenticate(user=self.ctx['cashier'])

    def test_owner_can_view_sale_explanation_chain(self):
        self.auth_owner()

        response = self.client.get(f'/api/v1/sales/sales/{self.sale.id}/explanation/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['sale']['id'], self.sale.id)
        self.assertEqual(
            response.data['sale']['payment_methods'],
            [SalePayment.Method.CASH, SalePayment.Method.CREDIT],
        )
        self.assertEqual(len(response.data['payments']), 2)
        self.assertEqual(len(response.data['cash_entries']), 1)
        self.assertEqual(len(response.data['receivable_entries']), 1)
        self.assertEqual(len(response.data['journal_entries']), 3)
        self.assertEqual(len(response.data['realization_entries']), 2)
        self.assertEqual(len(response.data['lines']), 1)

        line = response.data['lines'][0]
        self.assertEqual(line['procurement']['id'], self.procurement.id)
        self.assertEqual(line['lot']['id'], self.sale.lines.get().lot_id)
        self.assertEqual(
            {item['role'] for item in line['partner_split']},
            {'INVESTOR', 'OPERATOR'},
        )

        journal_accounts = {
            journal_line['account_code']
            for journal in response.data['journal_entries']
            for journal_line in journal['lines']
        }
        self.assertSetEqual(journal_accounts, {'1000', '1200', '4000', '5000', '1100'})

    def test_cashier_cannot_view_sale_explanation_chain(self):
        self.auth_cashier()

        response = self.client.get(f'/api/v1/sales/sales/{self.sale.id}/explanation/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
