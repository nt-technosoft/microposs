from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import Procurement
from apps.sales.models import SalePayment
from apps.finance.models import ExchangeRate
from apps.partnerships.formulas import calculate_profit_distribution
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class ProfitabilityReportsTests(APITestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.procurement, self.lot = seed_received_procurement(self.ctx)
        ExchangeRate.objects.update_or_create(
            tenant=self.ctx['business'],
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            defaults={
                'rate': Decimal('12000.000000'),
                'source': ExchangeRate.Source.MANUAL,
                'is_manual': True,
                'notes': 'Profitability report test rate',
                'raw_payload': {},
            },
        )
        self.session = open_session(self.ctx)
        self.sale = create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=self.session.id,
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
        self.sale_line = self.sale.lines.get()

    def auth_owner(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_owner'))

    def auth_cashier(self) -> None:
        self.client.force_authenticate(user=User.objects.get(username='t_cashier'))

    def test_sales_profitability_endpoint_returns_consistent_sale_metrics(self):
        self.auth_owner()
        today = timezone.localdate().isoformat()

        response = self.client.get(
            '/api/v1/finance/sales-profitability/',
            {'date_from': today, 'date_to': today},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        row = response.data[0]
        gross_profit = (self.sale.total_amount - self.sale.total_cogs).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(self.sale_line.profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )

        self.assertEqual(row['sale_id'], self.sale.id)
        self.assertEqual(row['location_id'], self.ctx['store'].id)
        self.assertEqual(row['customer_id'], self.ctx['customer'].id)
        self.assertEqual(row['payment_methods'], [SalePayment.Method.CASH])
        self.assertEqual(Decimal(row['revenue']), self.sale.total_amount)
        self.assertEqual(Decimal(row['cogs']), self.sale.total_cogs)
        self.assertEqual(Decimal(row['gross_profit']), gross_profit)
        self.assertEqual(Decimal(row['investor_profit']), investor_profit)
        self.assertEqual(
            Decimal(row['business_profit']),
            (gross_profit - investor_profit).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(row['margin_percent']),
            ((gross_profit / self.sale.total_amount) * Decimal('100')).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(row['markup_percent']),
            ((gross_profit / self.sale.total_cogs) * Decimal('100')).quantize(Decimal('0.01')),
        )

    def test_sales_profitability_endpoint_returns_usd_display_without_changing_functional_values(self):
        self.auth_owner()
        today = timezone.localdate().isoformat()

        response = self.client.get(
            '/api/v1/finance/sales-profitability/',
            {'date_from': today, 'date_to': today, 'report_currency': 'USD'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        row = response.data[0]
        self.assertEqual(Decimal(row['revenue']), self.sale.total_amount)
        self.assertEqual(row['display']['currency'], 'USD')
        self.assertEqual(Decimal(row['display']['amounts']['revenue']), Decimal('100.00'))

    def test_product_profitability_endpoint_includes_remaining_projection(self):
        self.auth_owner()

        response = self.client.get('/api/v1/finance/product-profitability/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        row = response.data[0]
        remaining_quantity = sum(stock.quantity_remaining for stock in self.lot.stocks.all())
        remaining_cost = (
            Decimal(str(self.lot.landed_cost_per_unit))
            * Decimal(str(remaining_quantity))
        ).quantize(Decimal('0.01'))
        projected_revenue = (
            Decimal(str(self.ctx['variant'].effective_price))
            * Decimal(str(remaining_quantity))
        ).quantize(Decimal('0.01'))
        projected_distribution = calculate_profit_distribution(
            lot=self.lot,
            unit_price=Decimal(str(self.ctx['variant'].effective_price)),
            quantity=remaining_quantity,
            unit_landed_cost=Decimal(str(self.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = Decimal(
            str(projected_distribution[str(self.ctx['investor'].id)]),
        )
        gross_profit = (self.sale.total_amount - self.sale.total_cogs).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(self.sale_line.profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )

        self.assertEqual(row['product_variant_id'], self.ctx['variant'].id)
        self.assertEqual(row['quantity_sold'], 5)
        self.assertEqual(row['remaining_quantity'], remaining_quantity)
        self.assertEqual(Decimal(row['revenue']), self.sale.total_amount)
        self.assertEqual(Decimal(row['cogs']), self.sale.total_cogs)
        self.assertEqual(Decimal(row['gross_profit']), gross_profit)
        self.assertEqual(Decimal(row['investor_profit']), investor_profit)
        self.assertEqual(Decimal(row['remaining_landed_cost']), remaining_cost)
        self.assertEqual(Decimal(row['projected_revenue']), projected_revenue)
        self.assertEqual(
            Decimal(row['projected_gross_profit']),
            (projected_revenue - remaining_cost).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(row['projected_investor_profit']),
            projected_investor_profit,
        )

    def test_sale_detail_endpoint_exposes_profitability_breakdown(self):
        self.auth_cashier()

        response = self.client.get(f'/api/v1/sales/sales/{self.sale.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        gross_profit = (self.sale.total_amount - self.sale.total_cogs).quantize(Decimal('0.01'))
        purchase_cost = (
            self.sale_line.unit_purchase_price * self.sale_line.quantity
        ).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(self.sale_line.profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )

        self.assertEqual(Decimal(response.data['purchase_cost']), purchase_cost)
        self.assertEqual(Decimal(response.data['landed_cost']), self.sale.total_cogs)
        self.assertEqual(Decimal(response.data['gross_profit']), gross_profit)
        self.assertEqual(Decimal(response.data['investor_profit']), investor_profit)
        self.assertEqual(
            Decimal(response.data['business_profit']),
            (gross_profit - investor_profit).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(response.data['margin_percent']),
            ((gross_profit / self.sale.total_amount) * Decimal('100')).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(response.data['markup_percent']),
            ((gross_profit / self.sale.total_cogs) * Decimal('100')).quantize(Decimal('0.01')),
        )

    def test_procurement_profitability_endpoint_groups_realized_and_projected_metrics(self):
        self.auth_owner()

        response = self.client.get('/api/v1/finance/procurement-profitability/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        row = response.data[0]
        remaining_quantity = sum(stock.quantity_remaining for stock in self.lot.stocks.all())
        remaining_cost = (
            Decimal(str(self.lot.landed_cost_per_unit))
            * Decimal(str(remaining_quantity))
        ).quantize(Decimal('0.01'))
        projected_revenue = (
            Decimal(str(self.ctx['variant'].effective_price))
            * Decimal(str(remaining_quantity))
        ).quantize(Decimal('0.01'))
        projected_distribution = calculate_profit_distribution(
            lot=self.lot,
            unit_price=Decimal(str(self.ctx['variant'].effective_price)),
            quantity=remaining_quantity,
            unit_landed_cost=Decimal(str(self.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = Decimal(
            str(projected_distribution[str(self.ctx['investor'].id)]),
        )
        gross_profit = (self.sale.total_amount - self.sale.total_cogs).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(self.sale_line.profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )

        self.assertEqual(row['procurement_id'], self.procurement.id)
        self.assertEqual(row['procurement_type'], Procurement.Type.PARTNERSHIP)
        self.assertEqual(row['status'], Procurement.Status.RECEIVED)
        self.assertEqual(row['item_count'], 1)
        self.assertEqual(row['quantity_sold'], 5)
        self.assertEqual(row['remaining_quantity'], remaining_quantity)
        self.assertEqual(Decimal(row['revenue']), self.sale.total_amount)
        self.assertEqual(Decimal(row['cogs']), self.sale.total_cogs)
        self.assertEqual(Decimal(row['gross_profit']), gross_profit)
        self.assertEqual(Decimal(row['investor_profit']), investor_profit)
        self.assertEqual(Decimal(row['remaining_landed_cost']), remaining_cost)
        self.assertEqual(Decimal(row['projected_revenue']), projected_revenue)
        self.assertEqual(
            Decimal(row['projected_gross_profit']),
            (projected_revenue - remaining_cost).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            Decimal(row['projected_investor_profit']),
            projected_investor_profit,
        )

    def test_procurement_profitability_detail_endpoint_exposes_item_level_breakdown(self):
        self.auth_owner()

        response = self.client.get(f'/api/v1/finance/procurement-profitability/{self.procurement.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.data
        procurement_row = payload['procurement']
        self.assertEqual(procurement_row['procurement_id'], self.procurement.id)
        self.assertEqual(len(payload['items']), 1)

        item_row = payload['items'][0]
        remaining_quantity = sum(stock.quantity_remaining for stock in self.lot.stocks.all())
        projected_distribution = calculate_profit_distribution(
            lot=self.lot,
            unit_price=Decimal(str(self.ctx['variant'].effective_price)),
            quantity=remaining_quantity,
            unit_landed_cost=Decimal(str(self.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = Decimal(
            str(projected_distribution[str(self.ctx['investor'].id)]),
        )
        gross_profit = (self.sale.total_amount - self.sale.total_cogs).quantize(Decimal('0.01'))
        investor_profit = Decimal(
            str(self.sale_line.profit_distribution_snapshot[str(self.ctx['investor'].id)]),
        )

        self.assertEqual(item_row['procurement_item_id'], self.procurement.items.get().id)
        self.assertEqual(item_row['product_variant_id'], self.ctx['variant'].id)
        self.assertEqual(item_row['purchased_quantity'], 50)
        self.assertEqual(item_row['sold_quantity'], 5)
        self.assertEqual(item_row['remaining_quantity'], remaining_quantity)
        self.assertEqual(Decimal(item_row['revenue']), self.sale.total_amount)
        self.assertEqual(Decimal(item_row['cogs']), self.sale.total_cogs)
        self.assertEqual(Decimal(item_row['gross_profit']), gross_profit)
        self.assertEqual(Decimal(item_row['investor_profit']), investor_profit)
        self.assertEqual(
            Decimal(item_row['projected_investor_profit']),
            projected_investor_profit,
        )

    def test_procurement_profitability_detail_defaults_to_contract_currency_display(self):
        self.auth_owner()

        response = self.client.get(f'/api/v1/finance/procurement-profitability/{self.procurement.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.data
        self.assertEqual(payload['report_currency']['currency'], 'USD')
        self.assertEqual(payload['procurement']['display']['currency'], 'USD')
        self.assertEqual(
            Decimal(payload['procurement']['display']['amounts']['revenue']),
            (self.sale.total_amount / Decimal('12000')).quantize(Decimal('0.01')),
        )
