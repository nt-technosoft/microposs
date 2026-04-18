from decimal import Decimal

from django.test import TestCase

from apps.inventory.models import LotStock
from apps.partnerships.models import Procurement, ProcurementBalance
from apps.partnerships.services import open_procurement, add_contribution, receive_procurement

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

        with self.assertRaisesMessage(ValueError, 'Cannot receive: balance is non-zero'):
            receive_procurement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                destination_warehouse_id=ctx['storage'].id,
            )
