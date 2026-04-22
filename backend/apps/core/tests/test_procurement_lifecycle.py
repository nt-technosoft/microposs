from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import ExchangeRate
from apps.inventory.models import LotStock
from apps.partnerships.models import Procurement, ProcurementBalance
from apps.partnerships.services import (
    add_contribution,
    open_procurement,
    pay_procurement_expenses,
    pay_procurement_items,
    receive_procurement,
    update_open_procurement,
)

from ._helpers import build_tenant, seed_received_procurement


class ProcurementLifecycleTests(TestCase):
    def test_receive_procurement_creates_lot_stock_and_contract_snapshot(self):
        ctx = build_tenant()

        procurement, lot = seed_received_procurement(ctx)
        balance = ProcurementBalance.objects.get(procurement=procurement)
        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])

        self.assertEqual(procurement.status, Procurement.Status.RECEIVED)
        self.assertIn('USD', balance.balances)
        self.assertTrue(
            all(
                Decimal(str(value)) == Decimal('0')
                for value in balance.balances.values()
            )
        )

        self.assertEqual(lot.quantity_initial, 50)
        self.assertEqual(stock.quantity_remaining, lot.quantity_initial)

        item = procurement.items.get()
        all_items = list(procurement.items.all())
        total_expenses_uzs = sum(
            (
                (
                    Decimal(str(expense.amount)) * Decimal(str(expense.fx_rate))
                ).quantize(Decimal('0.01'))
                for expense in procurement.expenses.all()
            ),
            Decimal('0.00'),
        )
        item_value_uzs = (
            Decimal(str(item.quantity))
            * Decimal(str(item.unit_purchase_price))
            * Decimal(str(item.fx_rate))
        ).quantize(Decimal('0.01'))
        total_value_uzs = sum(
            (
                (
                    Decimal(str(proc_item.quantity))
                    * Decimal(str(proc_item.unit_purchase_price))
                    * Decimal(str(proc_item.fx_rate))
                ).quantize(Decimal('0.01'))
                for proc_item in all_items
            ),
            Decimal('0.00'),
        )
        item_unit_price_uzs = (
            Decimal(str(item.unit_purchase_price))
            * Decimal(str(item.fx_rate))
        ).quantize(Decimal('0.01'))
        allocated_expense_uzs = (
            total_expenses_uzs * (item_value_uzs / total_value_uzs)
        ).quantize(Decimal('0.01'))
        expected_landed_cost = (
            item_unit_price_uzs + (allocated_expense_uzs / int(item.quantity))
        ).quantize(Decimal('0.01'))

        self.assertEqual(lot.unit_purchase_price, item_unit_price_uzs)
        self.assertEqual(lot.landed_cost_per_unit, expected_landed_cost)

        self.assertIn('mudaraba_ratio', lot.contract_snapshot)
        self.assertGreaterEqual(
            Decimal(str(lot.contract_snapshot['mudaraba_ratio'])),
            Decimal('0'),
        )
        self.assertLessEqual(
            Decimal(str(lot.contract_snapshot['mudaraba_ratio'])),
            Decimal('1'),
        )

        partners = {
            item['role']: item
            for item in lot.contract_snapshot['partners']
        }
        self.assertSetEqual(set(partners.keys()), {'INVESTOR', 'OPERATOR'})
        self.assertEqual(int(partners['INVESTOR']['partner_id']), ctx['investor'].id)
        self.assertEqual(int(partners['OPERATOR']['partner_id']), ctx['operator'].id)
        self.assertEqual(
            sum(
                Decimal(str(item['capital_share']))
                for item in partners.values()
            ).quantize(Decimal('0.0001')),
            Decimal('1.0000'),
        )
        self.assertEqual(
            sum(
                Decimal(str(item['profit_share']))
                for item in partners.values()
            ).quantize(Decimal('0.000001')),
            Decimal('1.000000'),
        )

    def test_receive_procurement_rejects_non_zero_balance(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('100'),
                'currency': 'USD',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('70'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('30'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'USD',
                'fx_rate': Decimal('12000'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('70'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )

        with self.assertRaisesMessage(ValueError, 'Есть неоплаченные черновики'):
            receive_procurement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                destination_warehouse_id=ctx['storage'].id,
            )

    def test_receive_procurement_respects_expense_allocation_method(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('30'),
                    'unit_purchase_price': Decimal('20'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
            expenses=[
                {
                    'expense_type': 'CUSTOMS',
                    'amount': Decimal('70'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'allocation_method': 'BY_VALUE',
                },
                {
                    'expense_type': 'LOGISTICS',
                    'amount': Decimal('40'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'allocation_method': 'BY_QUANTITY',
                },
            ],
        )

        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('810'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )

        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        pay_procurement_expenses(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
        )

        lots = list(procurement.items.order_by('id').prefetch_related('lots'))
        first_lot = lots[0].lots.get()
        second_lot = lots[1].lots.get()

        self.assertEqual(first_lot.landed_cost_per_unit, Decimal('12.00'))
        self.assertEqual(second_lot.landed_cost_per_unit, Decimal('23.00'))

    def test_receive_procurement_auto_returns_surplus_by_planned_capital(self):
        ctx = build_tenant()
        ExchangeRate.objects.create(
            tenant=ctx['business'],
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Auto surplus USD rate',
            raw_payload={},
        )
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('100'),
                'currency': 'USD',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('70'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('30'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'USD',
                'fx_rate': Decimal('12000'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('80'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('40'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
        )

        balance = ProcurementBalance.objects.get(procurement=procurement)
        lot = procurement.items.get().lots.get()
        partners = {item['role']: item for item in lot.contract_snapshot['partners']}

        self.assertEqual(balance.balances, {'USD': '0.00'})
        self.assertEqual(Decimal(partners['INVESTOR']['capital_share']), Decimal('0.700000'))
        self.assertEqual(Decimal(partners['OPERATOR']['capital_share']), Decimal('0.300000'))
        self.assertEqual(Decimal(partners['INVESTOR']['profit_share']), Decimal('0.400000'))
        self.assertEqual(Decimal(partners['OPERATOR']['profit_share']), Decimal('0.600000'))

    def test_landed_cost_recalculates_if_new_items_are_added_after_expense_payment(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('100'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
            }],
        )

        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('300'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )

        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        pay_procurement_expenses(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        update_open_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            expenses=[],
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
        )

        lots = list(procurement.items.order_by('id').prefetch_related('lots'))
        first_lot = lots[0].lots.get()
        second_lot = lots[1].lots.get()

        self.assertEqual(first_lot.landed_cost_per_unit, Decimal('15.00'))
        self.assertEqual(second_lot.landed_cost_per_unit, Decimal('15.00'))

    def test_receive_procurement_normalizes_mixed_currency_contributions_to_contract_currency(self):
        ctx = build_tenant()
        rate_date = timezone.localdate()
        ExchangeRate.objects.create(
            tenant=ctx['business'],
            base_currency='USD',
            quote_currency='UZS',
            rate_date=rate_date,
            rate=Decimal('12000.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Mixed currency contract valuation',
            raw_payload={},
        )

        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('1000'),
                'currency': 'USD',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('700'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('300'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('70'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'USD',
                'fx_rate': Decimal('12000'),
            }],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('3600000'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('700'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('3600000'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        pay_procurement_expenses(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
        )

        lot = procurement.items.get().lots.get()
        partners = {item['role']: item for item in lot.contract_snapshot['partners']}

        self.assertEqual(lot.contract_snapshot['contract_currency'], 'USD')
        self.assertEqual(
            Decimal(str(partners['INVESTOR']['capital_amount_contract_currency'])),
            Decimal('700.00'),
        )
        self.assertEqual(
            Decimal(str(partners['OPERATOR']['capital_amount_contract_currency'])),
            Decimal('300.00'),
        )
        self.assertEqual(Decimal(partners['INVESTOR']['capital_share']), Decimal('0.700000'))
        self.assertEqual(Decimal(partners['OPERATOR']['capital_share']), Decimal('0.300000'))
