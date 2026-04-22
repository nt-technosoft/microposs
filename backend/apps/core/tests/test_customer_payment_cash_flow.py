from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import CashEntry, JournalEntry
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class CustomerPaymentCashFlowTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()
        seed_received_procurement(cls.ctx)
        session = open_session(cls.ctx)
        create_sale(
            tenant_id=cls.ctx['business'].id,
            pos_session_id=session.id,
            location_id=cls.ctx['store'].id,
            sold_by_id=cls.ctx['cashier'].id,
            customer_id=cls.ctx['customer'].id,
            lines=[{
                'product_variant_id': cls.ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CREDIT,
            }],
        )

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_owner_customer_payment_creates_cash_entry_and_journal(self):
        self.auth_owner()

        response = self.client.post(
            f"/api/v1/customers/customers/{self.ctx['customer'].id}/pay/",
            {
                'amount': '100000.00',
                'currency': 'UZS',
                'payment_method': 'cash',
                'account_id': self.ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(CashEntry.objects.filter(source_ref_type='customer_payment').count(), 1)
        self.assertEqual(JournalEntry.objects.filter(operation_type='debt_payment').count(), 1)
