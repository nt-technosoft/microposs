from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import CashAccount
from apps.sales.models import SalePayment
from apps.sales.services import close_pos_session, create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class ReconciliationViewTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def test_operational_reconciliation_exposes_healthy_operational_status(self):
        seed_received_procurement(self.ctx)
        session = open_session(self.ctx)

        cash_sale = create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': self.ctx['cash_account'].id,
            }],
        )

        create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
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

        close_pos_session(
            session=session,
            closed_by_id=self.ctx['cashier'].id,
            actual_cash=Decimal('240000.00'),
        )

        self.auth_owner()
        response = self.client.get('/api/v1/core/excel/reconciliation/latest/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['overall_status'], 'ok')
        checks = {item['code']: item for item in response.data['checks']}

        self.assertEqual(checks['sales_settlement']['status'], 'ok')
        self.assertEqual(checks['receivable_ledger']['status'], 'ok')
        self.assertEqual(checks['cash_accounts_vs_entries']['status'], 'ok')
        self.assertEqual(checks['closed_sessions_expected_cash']['status'], 'ok')
        self.assertEqual(checks['closed_sessions_cash_difference']['status'], 'ok')
        self.assertEqual(checks['journal_balance']['status'], 'ok')
        self.assertEqual(checks['sales_journal_revenue']['status'], 'ok')
        self.assertEqual(checks['sales_journal_cogs']['status'], 'ok')
        self.assertEqual(checks['sales_journal_cogs']['mismatch_count'], 0)

    def test_operational_reconciliation_treats_nonzero_cash_difference_as_warning(self):
        seed_received_procurement(self.ctx)
        session = open_session(self.ctx)

        create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': self.ctx['cash_account'].id,
            }],
        )

        close_pos_session(
            session=session,
            closed_by_id=self.ctx['cashier'].id,
            actual_cash=Decimal('250000.00'),
        )

        self.auth_owner()
        response = self.client.get('/api/v1/core/excel/reconciliation/latest/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['overall_status'], 'warning')
        checks = {item['code']: item for item in response.data['checks']}
        self.assertEqual(checks['closed_sessions_cash_difference']['status'], 'ok')
        self.assertEqual(checks['closed_sessions_nonzero_difference']['status'], 'warning')
        self.assertEqual(checks['closed_sessions_nonzero_difference']['mismatch_count'], 1)
        self.assertEqual(
            Decimal(checks['closed_sessions_nonzero_difference']['actual_amount']),
            Decimal('10000.00'),
        )
        self.assertEqual(checks['closed_sessions_nonzero_difference']['sample_refs'], [f'session:{session.id}'])

    def test_operational_reconciliation_flags_cash_account_structural_mismatch(self):
        seed_received_procurement(self.ctx)
        session = open_session(self.ctx)

        create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': self.ctx['cash_account'].id,
            }],
        )

        close_pos_session(
            session=session,
            closed_by_id=self.ctx['cashier'].id,
            actual_cash=Decimal('240000.00'),
        )

        cash_account = CashAccount.objects.get(id=self.ctx['cash_account'].id)
        cash_account.balance = Decimal('0.00')
        cash_account.save(update_fields=['balance'])

        self.auth_owner()
        response = self.client.get('/api/v1/core/excel/reconciliation/latest/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['overall_status'], 'mismatch')
        checks = {item['code']: item for item in response.data['checks']}
        self.assertEqual(checks['cash_accounts_vs_entries']['status'], 'mismatch')
        self.assertEqual(checks['cash_accounts_vs_entries']['mismatch_count'], 1)
        self.assertEqual(
            Decimal(checks['cash_accounts_vs_entries']['delta_amount']),
            Decimal('-240000.00'),
        )
        self.assertEqual(
            checks['cash_accounts_vs_entries']['sample_refs'],
            [f'cash_account:{cash_account.id}'],
        )
