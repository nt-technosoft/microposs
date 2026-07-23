from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.finance.models import JournalEntry
from apps.sales.models import SalePayment
from apps.partnerships.formulas import calculate_profit_distribution
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class AuditBatchTwoTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def auth_investor(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_investor'))

    # Deleted in E08 Phase 2: the legacy /api/v1/suppliers/suppliers/<id>/pay/
    # endpoint set a free-floating Supplier.outstanding_balance. The field is
    # now a derived @property over SupplierPayable / finance.Payment, so a
    # detached SupplierPayment cannot reduce it. Supplier-payable payments
    # belong on record_payable_payment (covered by test_e07_supplier_payables).

    def test_investor_dashboard_exposes_capital_state_at_cost_basis(self):
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

        sale_line = sale.lines.get()
        investor_meta = next(
            meta for meta in lot.contract_snapshot['partners']
            if int(meta['partner_id']) == self.ctx['investor'].id
        )
        investor_capital_share = Decimal(str(investor_meta['capital_share']))
        remaining_quantity = sum(stock.quantity_remaining for stock in lot.stocks.all())

        expected_sold_cost = (
            Decimal(str(sale_line.unit_landed_cost))
            * Decimal(str(sale_line.quantity))
            * investor_capital_share
        ).quantize(Decimal('0.01'))
        expected_in_stock_cost = (
            Decimal(str(lot.landed_cost_per_unit))
            * Decimal(str(remaining_quantity))
            * investor_capital_share
        ).quantize(Decimal('0.01'))
        expected_sold_revenue = (
            Decimal(str(sale_line.unit_price))
            * Decimal(str(sale_line.quantity))
            * investor_capital_share
        ).quantize(Decimal('0.01'))
        projected_revenue = (
            Decimal(str(self.ctx['variant'].effective_price))
            * Decimal(str(remaining_quantity))
            * investor_capital_share
        ).quantize(Decimal('0.01'))
        projected_distribution = calculate_profit_distribution(
            lot=lot,
            unit_price=Decimal(str(self.ctx['variant'].effective_price)),
            quantity=remaining_quantity,
            unit_landed_cost=Decimal(str(lot.landed_cost_per_unit)),
        )
        expected_projected_partner_profit = Decimal(
            str(projected_distribution[str(self.ctx['investor'].id)]),
        )

        self.auth_investor()

        dashboard = self.client.get('/api/v1/investors/dashboard/')
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['sold_cost_uzs']),
            expected_sold_cost,
        )
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['in_stock_cost_uzs']),
            expected_in_stock_cost,
        )
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['tracked_cost_uzs']),
            expected_sold_cost + expected_in_stock_cost,
        )
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['sold_revenue_uzs']),
            expected_sold_revenue,
        )
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['projected_revenue_uzs']),
            projected_revenue,
        )
        self.assertEqual(
            Decimal(dashboard.data['capital_state']['projected_partner_profit_uzs']),
            expected_projected_partner_profit,
        )

        procurement_detail = self.client.get(
            f'/api/v1/investors/procurements/{procurement.id}/',
        )
        self.assertEqual(procurement_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Decimal(procurement_detail.data['capital_state']['sold_cost_uzs']),
            expected_sold_cost,
        )
        self.assertEqual(
            Decimal(procurement_detail.data['capital_state']['in_stock_cost_uzs']),
            expected_in_stock_cost,
        )
        self.assertEqual(
            Decimal(procurement_detail.data['capital_state']['projected_partner_profit_uzs']),
            expected_projected_partner_profit,
        )
