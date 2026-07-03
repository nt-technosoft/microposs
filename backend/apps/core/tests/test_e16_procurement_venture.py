from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.partnerships.models import ProcurementSaleRealization, ProcurementVentureSettlement
from apps.partnerships.agreement_services import pay_dividend
from apps.partnerships.venture import create_venture_settlement, procurement_venture_positions
from apps.partnerships.workspace_support import add_agreement_withdrawal
from apps.finance.services import get_procurement_profitability_rows
from apps.finance.models import Account, CashAccount, ExchangeRate
from apps.finance.fx_rates import upsert_exchange_rate
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class ProcurementVentureRealizationTests(TestCase):
    def test_sale_creates_partner_realization_buckets(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        self.assertEqual(sale.total_amount, Decimal('1200000.00'))
        self.assertEqual(sale.total_cogs, Decimal('660000.00'))

        rows = {
            row.partner_id: row
            for row in ProcurementSaleRealization.objects.filter(
                procurement=procurement,
                sale_line=sale.lines.get(),
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
            )
        }
        self.assertEqual(set(rows), {ctx['investor'].id, ctx['operator'].id})

        investor = rows[ctx['investor'].id]
        operator = rows[ctx['operator'].id]

        self.assertEqual(investor.capital_recovered_uzs, Decimal('462000.00'))
        self.assertEqual(operator.capital_recovered_uzs, Decimal('198000.00'))
        self.assertEqual(investor.provisional_profit_uzs, Decimal('216000.00'))
        self.assertEqual(operator.provisional_profit_uzs, Decimal('324000.00'))
        self.assertEqual(investor.loss_uzs, Decimal('0.00'))
        self.assertEqual(operator.loss_uzs, Decimal('0.00'))
        self.assertEqual(investor.sale_proceeds_currency, 'UZS')
        self.assertEqual(investor.sale_proceeds_amount, Decimal('1200000.00'))
        self.assertEqual(investor.cost_basis_currency, 'USD')
        self.assertEqual(investor.cost_basis_amount, Decimal('55.00'))
        self.assertEqual(investor.cost_basis_at_sale_uzs, Decimal('660000.00'))
        self.assertEqual(investor.fx_gain_loss_uzs, Decimal('0.00'))
        self.assertEqual(investor.capital_recovered_currency, 'USD')
        self.assertEqual(investor.capital_recovered_amount, Decimal('38.50'))
        self.assertEqual(investor.profit_currency, 'UZS')
        self.assertEqual(investor.profit_amount, Decimal('216000.00'))

        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['capital_return_available_uzs'],
            Decimal('462000.00'),
        )
        self.assertEqual(
            positions[ctx['operator'].id]['provisional_profit_uzs'],
            Decimal('324000.00'),
        )
        self.assertEqual(
            positions[ctx['operator'].id]['provisional_profit_available_uzs'],
            Decimal('0'),
        )

    def test_sale_below_cost_records_loss_by_capital_share(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('100000.00'),
            }],
            payments=[{
                'amount': Decimal('500000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        rows = {
            row.partner_id: row
            for row in ProcurementSaleRealization.objects.filter(
                procurement=procurement,
                sale_line=sale.lines.get(),
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
            )
        }

        self.assertEqual(rows[ctx['investor'].id].capital_recovered_uzs, Decimal('350000.00'))
        self.assertEqual(rows[ctx['operator'].id].capital_recovered_uzs, Decimal('150000.00'))
        self.assertEqual(rows[ctx['investor'].id].loss_uzs, Decimal('112000.00'))
        self.assertEqual(rows[ctx['operator'].id].loss_uzs, Decimal('48000.00'))
        self.assertEqual(rows[ctx['investor'].id].provisional_profit_uzs, Decimal('0.00'))
        self.assertEqual(rows[ctx['operator'].id].provisional_profit_uzs, Decimal('0.00'))

    def test_later_loss_is_netted_before_profit_becomes_available(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )
        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('100000.00'),
            }],
            payments=[{
                'amount': Decimal('500000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_uzs'],
            Decimal('152000.00'),
        )
        self.assertEqual(
            positions[ctx['operator'].id]['provisional_profit_uzs'],
            Decimal('228000.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_available_uzs'],
            Decimal('0'),
        )

        settlement = create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        self.assertEqual(
            settlement.partner_positions[str(ctx['investor'].id)]['provisional_profit_available_uzs'],
            '152000.00',
        )

        with self.assertRaises(ValueError):
            pay_dividend(
                partner_id=ctx['investor'].id,
                procurement_id=procurement.id,
                amount=Decimal('200000.00'),
                currency='UZS',
                from_account_id=ctx['cash_account'].id,
                tenant_id=ctx['business'].id,
            )

    def test_final_settlement_true_ups_capital_and_loss_from_net_venture_result(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('180000.00'),
            }],
            payments=[{
                'amount': Decimal('900000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )
        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('72000.00'),
            }],
            payments=[{
                'amount': Decimal('360000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        interim = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            interim[ctx['investor'].id]['capital_return_available_uzs'],
            Decimal('672000.00'),
        )
        self.assertEqual(
            interim[ctx['investor'].id]['loss_uzs'],
            Decimal('168000.00'),
        )

        settlement = create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
        )
        investor = settlement.partner_positions[str(ctx['investor'].id)]
        operator = settlement.partner_positions[str(ctx['operator'].id)]

        self.assertEqual(investor['capital_recovered_uzs'], '840000.00')
        self.assertEqual(operator['capital_recovered_uzs'], '360000.00')
        self.assertEqual(investor['loss_uzs'], '0.00')
        self.assertEqual(operator['loss_uzs'], '0.00')
        self.assertEqual(investor['provisional_profit_available_uzs'], '24000.00')
        self.assertEqual(operator['provisional_profit_available_uzs'], '36000.00')
        self.assertEqual(investor['negative_position_uzs'], '0.00')
        self.assertEqual(operator['negative_position_uzs'], '0.00')
        self.assertEqual(settlement.totals['capital_return_available_uzs'], '1200000.00')
        self.assertEqual(settlement.totals['provisional_profit_available_uzs'], '60000.00')

    def test_cross_currency_sale_separates_fx_capital_gain_from_trading_profit(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)
        upsert_exchange_rate(
            tenant_id=ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=session.opened_at.date(),
            rate=Decimal('13000.00'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='E16 cross-currency sale rate',
        )

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 10,
                'unit_price': Decimal('180000.00'),
            }],
            payments=[{
                'amount': Decimal('1800000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        rows = {
            row.partner_id: row
            for row in ProcurementSaleRealization.objects.filter(
                procurement=procurement,
                sale_line=sale.lines.get(),
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
            )
        }
        investor_row = rows[ctx['investor'].id]
        operator_row = rows[ctx['operator'].id]
        self.assertEqual(investor_row.cost_basis_amount, Decimal('100.00'))
        self.assertEqual(investor_row.cost_basis_uzs, Decimal('1200000.00'))
        self.assertEqual(investor_row.cost_basis_at_sale_uzs, Decimal('1300000.00'))
        self.assertEqual(investor_row.fx_gain_loss_uzs, Decimal('70000.00'))
        self.assertEqual(operator_row.fx_gain_loss_uzs, Decimal('30000.00'))

        settlement = create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
        )
        investor = settlement.partner_positions[str(ctx['investor'].id)]
        operator = settlement.partner_positions[str(ctx['operator'].id)]

        self.assertEqual(investor['capital_recovered_uzs'], '910000.00')
        self.assertEqual(operator['capital_recovered_uzs'], '390000.00')
        self.assertEqual(investor['provisional_profit_available_uzs'], '200000.00')
        self.assertEqual(operator['provisional_profit_available_uzs'], '300000.00')
        self.assertEqual(investor['loss_uzs'], '0.00')
        self.assertEqual(operator['loss_uzs'], '0.00')
        self.assertEqual(settlement.totals['capital_return_available_uzs'], '1300000.00')
        self.assertEqual(settlement.totals['provisional_profit_available_uzs'], '500000.00')
        self.assertEqual(
            Decimal(investor['capital_return_available_uzs'])
            + Decimal(operator['capital_return_available_uzs'])
            + Decimal(investor['provisional_profit_available_uzs'])
            + Decimal(operator['provisional_profit_available_uzs']),
            Decimal('1800000.00'),
        )

    def test_final_settlement_requires_no_active_lots(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        with self.assertRaises(ValueError):
            create_venture_settlement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
            )

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 50,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('12000000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        settlement = create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
        )
        self.assertEqual(settlement.settlement_type, ProcurementVentureSettlement.SettlementType.FINAL)
        self.assertEqual(settlement.totals['capital_recovered_uzs'], '6600000.00')

    def test_recovered_capital_can_be_returned_from_operating_cash_for_procurement(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        cash_before = CashAccount.objects.get(pk=ctx['cash_account'].id).balance
        add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=procurement.agreement_id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('100000.00'),
            currency='UZS',
            from_account_id=ctx['cash_account'].id,
        )

        self.assertEqual(
            CashAccount.objects.get(pk=ctx['cash_account'].id).balance,
            cash_before - Decimal('100000.00'),
        )
        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['capital_return_available_uzs'],
            Decimal('362000.00'),
        )

        with self.assertRaises(ValueError):
            add_agreement_withdrawal(
                tenant_id=ctx['business'].id,
                agreement_id=procurement.agreement_id,
                procurement_id=procurement.id,
                partner_id=ctx['investor'].id,
                amount=Decimal('999999.00'),
                currency='UZS',
                from_account_id=ctx['cash_account'].id,
            )


class ProcurementVentureApiTests(APITestCase):
    def test_venture_summary_flags_suspicious_usd_cost_fx(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        procurement.items.update(fx_rate=Decimal('1'))

        self.client.force_authenticate(user=ctx['owner'])
        response = self.client.get(f'/api/v1/partnerships/procurements/{procurement.id}/venture-summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['audit_warnings'][0]['code'], 'SUSPICIOUS_USD_COST_FX')

    def test_venture_summary_exposes_returned_and_available_capital(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )
        add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=procurement.agreement_id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('100000.00'),
            currency='UZS',
            from_account_id=ctx['cash_account'].id,
        )

        self.client.force_authenticate(user=ctx['owner'])
        response = self.client.get(f'/api/v1/partnerships/procurements/{procurement.id}/venture-summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        investor_row = next(
            row for row in response.data['positions']
            if row['partner_id'] == ctx['investor'].id
        )
        self.assertEqual(investor_row['capital_recovered_uzs'], '462000.00')
        self.assertEqual(investor_row['capital_returned_uzs'], '100000.00')
        self.assertEqual(investor_row['capital_return_available_uzs'], '362000.00')
        self.assertEqual(response.data['totals']['capital_returned_uzs'], '100000.00')

    def test_recovered_capital_can_be_returned_in_usd_with_explicit_fx_rate(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        usd_account = CashAccount.objects.create(
            tenant=ctx['business'],
            name='USD Cash',
            currency='USD',
            balance=Decimal('100.00'),
            kind=CashAccount.Kind.CASH,
            linked_account=Account.objects.get(tenant=ctx['business'], code='1000'),
        )

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        add_agreement_withdrawal(
            tenant_id=ctx['business'].id,
            agreement_id=procurement.agreement_id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('10.00'),
            currency='USD',
            fx_rate=Decimal('12000.00'),
            from_account_id=usd_account.id,
        )

        usd_account.refresh_from_db()
        self.assertEqual(usd_account.balance, Decimal('90.00'))
        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['capital_return_available_uzs'],
            Decimal('342000.00'),
        )

    def test_payout_preview_allows_capital_return_and_blocks_unavailable_profit(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        self.client.force_authenticate(user=ctx['owner'])
        allowed = self.client.post(
            f'/api/v1/partnerships/agreements/{procurement.agreement_id}/payout-preview/',
            {
                'partner_id': ctx['investor'].id,
                'procurement_id': procurement.id,
                'payout_type': 'CAPITAL_RETURN',
                'amount': '100000.00',
                'currency': 'UZS',
                'from_account_id': ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertTrue(allowed.data['allowed'])
        self.assertEqual(allowed.data['available_uzs'], '462000.00')

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('100000.00'),
            }],
            payments=[{
                'amount': Decimal('500000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )
        blocked = self.client.post(
            f'/api/v1/partnerships/agreements/{procurement.agreement_id}/payout-preview/',
            {
                'partner_id': ctx['investor'].id,
                'procurement_id': procurement.id,
                'payout_type': 'PROFIT',
                'amount': '200000.00',
                'currency': 'UZS',
                'from_account_id': ctx['cash_account'].id,
            },
            format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_200_OK)
        self.assertFalse(blocked.data['allowed'])
        self.assertIn('Доступно только 0.00 UZS.', blocked.data['blocking_reasons'])

    def test_payout_preview_blocks_when_partner_has_negative_position(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )
        create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        pay_dividend(
            partner_id=ctx['investor'].id,
            procurement_id=procurement.id,
            amount=Decimal('216000.00'),
            currency='UZS',
            from_account_id=ctx['cash_account'].id,
            tenant_id=ctx['business'].id,
        )
        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('100000.00'),
            }],
            payments=[{
                'amount': Decimal('500000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        self.client.force_authenticate(user=ctx['owner'])
        response = self.client.post(
            f'/api/v1/partnerships/agreements/{procurement.agreement_id}/payout-preview/',
            {
                'partner_id': ctx['investor'].id,
                'procurement_id': procurement.id,
                'payout_type': 'CAPITAL_RETURN',
                'amount': '1000.00',
                'currency': 'UZS',
                'from_account_id': ctx['cash_account'].id,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['allowed'])
        self.assertIn('Есть отрицательная позиция партнёра; сначала погасите её.', response.data['blocking_reasons'])

    def test_procurement_profitability_rows_expose_e16_buckets(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        rows = get_procurement_profitability_rows(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['venture_capital_recovered_uzs'], Decimal('660000.00'))
        self.assertEqual(rows[0]['venture_capital_return_available_uzs'], Decimal('660000.00'))
        self.assertEqual(rows[0]['venture_provisional_profit_available_uzs'], Decimal('0.00'))
