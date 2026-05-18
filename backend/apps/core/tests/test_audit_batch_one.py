from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import CashEntry
from apps.partnerships.agreement_services import get_partner_aggregate
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class AuditBatchOneTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ctx = build_tenant()

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def auth_investor(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_investor'))

    def test_fifo_sale_consumes_oldest_lot_first(self):
        first_procurement, first_lot = seed_received_procurement(
            self.ctx,
            qty=5,
            unit_usd=10,
            customs_usd=10,
        )
        second_procurement, second_lot = seed_received_procurement(
            self.ctx,
            qty=10,
            unit_usd=12,
            customs_usd=20,
        )
        session = open_session(self.ctx)

        sale = create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 8,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1920000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': self.ctx['cash_account'].id,
            }],
        )

        lines = list(sale.lines.order_by('id'))
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].lot_id, first_lot.id)
        self.assertEqual(lines[0].quantity, 5)
        self.assertEqual(lines[1].lot_id, second_lot.id)
        self.assertEqual(lines[1].quantity, 3)

        first_lot.refresh_from_db()
        second_lot.refresh_from_db()
        self.assertFalse(first_lot.is_active)
        self.assertTrue(second_lot.is_active)
        self.assertEqual(first_lot.stocks.get(warehouse=self.ctx['store']).quantity_remaining, 0)
        self.assertEqual(second_lot.stocks.get(warehouse=self.ctx['store']).quantity_remaining, 7)

        expected_cogs = (
            lines[0].unit_landed_cost * lines[0].quantity
            + lines[1].unit_landed_cost * lines[1].quantity
        ).quantize(Decimal('0.01'))
        self.assertEqual(sale.total_cogs, expected_cogs)

    def test_owner_reports_and_investor_dashboard_stay_consistent_after_sale(self):
        procurement, lot = seed_received_procurement(self.ctx)
        session = open_session(self.ctx)
        sale = create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': self.ctx['cash_account'].id,
            }],
        )

        gross_profit = (sale.total_amount - sale.total_cogs).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(sale.lines.get().profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )
        operator_aggregate = get_partner_aggregate(
            self.ctx['operator'].id,
            self.ctx['business'].id,
        )

        today = timezone.localdate().isoformat()

        self.auth_owner()

        daily_summary = self.client.get(
            '/api/v1/finance/daily-summaries/',
            {'date_from': today, 'date_to': today},
        )
        self.assertEqual(daily_summary.status_code, status.HTTP_200_OK)
        self.assertEqual(len(daily_summary.data), 1)
        summary_row = daily_summary.data[0]
        self.assertEqual(Decimal(summary_row['total_revenue']), sale.total_amount)
        self.assertEqual(Decimal(summary_row['total_cogs']), sale.total_cogs)
        self.assertEqual(Decimal(summary_row['gross_profit']), gross_profit)
        self.assertEqual(summary_row['total_sales_count'], 1)

        cash_flow = self.client.get(
            '/api/v1/finance/cash-flow/',
            {'date_from': today, 'date_to': today},
        )
        self.assertEqual(cash_flow.status_code, status.HTTP_200_OK)
        self.assertEqual(len(cash_flow.data), 1)
        cash_flow_row = cash_flow.data[0]
        self.assertEqual(Decimal(cash_flow_row['cash_in_sales']), sale.total_amount)
        self.assertEqual(
            Decimal(cash_flow_row['net_cash_flow']),
            sale.total_amount,
        )

        stock_summary = self.client.get(
            '/api/v1/inventory/stock/summary/',
            {'warehouse': self.ctx['store'].id},
        )
        self.assertEqual(stock_summary.status_code, status.HTTP_200_OK)
        variant_row = next(
            row for row in stock_summary.data
            if row['product_variant_id'] == self.ctx['variant'].id
        )
        self.assertEqual(variant_row['total_quantity'], lot.quantity_initial - 5)
        self.assertGreater(Decimal(variant_row['total_landed_cost']), Decimal('0'))

        self.auth_investor()
        investor_dashboard = self.client.get('/api/v1/investors/dashboard/')
        self.assertEqual(investor_dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(investor_dashboard.data['profit_pending_payout']),
            investor_profit,
        )

        operator_profit = Decimal(str(operator_aggregate['profit_pending_payout']))
        self.assertEqual(investor_profit + operator_profit, gross_profit)

    def test_sale_without_explicit_account_binds_to_default_cash_account(self):
        seed_received_procurement(self.ctx)
        session = open_session(self.ctx)

        sale = create_sale(
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
            }],
        )

        payment = sale.payments.get()
        self.assertEqual(payment.account_id, self.ctx['cash_account'].id)

        cash_entry = CashEntry.objects.get(
            tenant=self.ctx['business'],
            source_ref_type='sale_payment',
            source_ref_id=payment.id,
        )
        self.assertEqual(cash_entry.account_id, self.ctx['cash_account'].id)

        self.ctx['cash_account'].refresh_from_db()
        self.assertEqual(self.ctx['cash_account'].balance, Decimal('240000.00'))
