from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import ExchangeRate
from apps.core.models import Partner
from apps.inventory.models import LotStock
from apps.partnerships.models import (
    AgreementAllocation,
    InvestmentAgreement,
    Procurement,
    ProcurementBalance,
    ProcurementExpenseTarget,
)
from apps.partnerships.services import (
    add_contribution,
    add_agreement_contribution,
    allocate_agreement_to_procurement,
    create_investment_agreement,
    get_agreement_allocation_preview,
    get_procurement_receive_plan,
    open_procurement,
    pay_procurement_expenses,
    pay_procurement_items,
    receive_procurement,
    split_procurement_item,
    update_procurement_expense_targets,
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

        with self.assertRaisesMessage(ValueError, 'ещё нет оплаченных товаров'):
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

    def test_receive_procurement_can_receive_selected_paid_items_once(self):
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
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
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

        first_item, second_item = list(procurement.items.order_by('id'))
        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[first_item.id],
        )

        procurement.refresh_from_db()
        first_item.refresh_from_db()
        second_item.refresh_from_db()

        self.assertEqual(procurement.status, Procurement.Status.PARTIALLY_RECEIVED)
        self.assertEqual(first_item.status, first_item.Status.RECEIVED)
        self.assertEqual(second_item.status, second_item.Status.PAID)
        self.assertEqual(first_item.lots.count(), 1)
        self.assertEqual(second_item.lots.count(), 0)
        self.assertEqual(procurement.receive_batches.count(), 1)
        first_batch = procurement.receive_batches.first()
        self.assertEqual(first_batch.items_count, 1)
        self.assertEqual(first_batch.lines.count(), 1)

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[second_item.id],
        )

        procurement.refresh_from_db()
        first_item.refresh_from_db()
        second_item.refresh_from_db()

        self.assertEqual(procurement.status, Procurement.Status.RECEIVED)
        self.assertEqual(first_item.lots.count(), 1)
        self.assertEqual(second_item.lots.count(), 1)
        self.assertEqual(procurement.receive_batches.count(), 2)

    def test_partial_receive_allows_targeted_expense_for_remaining_batch(self):
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
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('320'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        first_item, second_item = list(procurement.items.order_by('id'))
        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[first_item.id],
        )
        procurement.refresh_from_db()
        self.assertEqual(procurement.status, Procurement.Status.PARTIALLY_RECEIVED)

        update_open_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('20'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
                'target_item_ids': [second_item.id],
            }],
        )
        pay_procurement_expenses(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[second_item.id],
        )

        procurement.refresh_from_db()
        second_item.refresh_from_db()
        second_lot = second_item.lots.get()
        self.assertEqual(procurement.status, Procurement.Status.RECEIVED)
        self.assertEqual(second_lot.landed_cost_per_unit, Decimal('11.00'))
        self.assertEqual(procurement.receive_batches.count(), 2)

    def test_pay_procurement_items_can_pay_selected_draft_items(self):
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
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('300'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        first_item, second_item = list(procurement.items.order_by('id'))

        paid = pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            item_ids=[first_item.id],
        )
        first_item.refresh_from_db()
        second_item.refresh_from_db()
        balance = ProcurementBalance.objects.get(procurement=procurement)

        self.assertEqual([item.id for item in paid], [first_item.id])
        self.assertEqual(first_item.status, first_item.Status.PAID)
        self.assertEqual(second_item.status, second_item.Status.DRAFT)
        self.assertEqual(balance.balances, {'UZS': '200.00'})

    def test_paid_expense_targets_can_be_fixed_before_partial_receive(self):
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
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('30'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('330'),
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
        first_item, second_item = list(procurement.items.order_by('id'))
        expense = procurement.expenses.get()

        with self.assertRaisesMessage(ValueError, 'Для частичного оприходования'):
            receive_procurement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                destination_warehouse_id=ctx['storage'].id,
                item_ids=[first_item.id],
            )

        updated_expense = update_procurement_expense_targets(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            expense_id=expense.id,
            target_item_ids=[first_item.id],
        )
        self.assertEqual(list(updated_expense.targets.values_list('item_id', flat=True)), [first_item.id])

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[first_item.id],
        )
        expense.refresh_from_db()
        procurement.refresh_from_db()
        second_item.refresh_from_db()

        self.assertEqual(procurement.status, Procurement.Status.PARTIALLY_RECEIVED)
        self.assertEqual(expense.status, expense.Status.RECEIVED)
        self.assertEqual(second_item.status, second_item.Status.PAID)
        with self.assertRaisesMessage(ValueError, 'Cannot edit targets'):
            update_procurement_expense_targets(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                expense_id=expense.id,
                target_item_ids=[second_item.id],
            )

    def test_update_open_procurement_keeps_draft_ids_and_expense_targets(self):
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
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('30'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
            }],
        )
        first_item, second_item = list(procurement.items.order_by('id'))
        expense = procurement.expenses.get()

        update_open_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[
                {
                    'id': first_item.id,
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('11'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
                {
                    'id': second_item.id,
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('20'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
            expenses=[{
                'id': expense.id,
                'expense_type': 'CUSTOMS',
                'amount': Decimal('35'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
                'target_item_ids': [second_item.id],
            }],
        )

        first_item.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual(first_item.quantity, Decimal('11.000'))
        self.assertEqual(expense.amount, Decimal('35.00'))
        self.assertEqual(list(expense.targets.values_list('item_id', flat=True)), [second_item.id])

    def test_update_open_procurement_can_save_same_expense_target_repeatedly(self):
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
                'amount': Decimal('30'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
            }],
        )
        item = procurement.items.get()
        expense = procurement.expenses.get()

        payload = {
            'tenant_id': ctx['business'].id,
            'procurement_id': procurement.id,
            'procurement_type': Procurement.Type.OWN_FUNDS,
            'supplier_id': ctx['supplier'].id,
            'items': [{
                'id': item.id,
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
            'expenses': [{
                'id': expense.id,
                'expense_type': 'CUSTOMS',
                'amount': Decimal('30'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
                'target_item_ids': [item.id],
            }],
        }

        update_open_procurement(**payload)
        update_open_procurement(**payload)

        expense.refresh_from_db()
        self.assertEqual(list(expense.targets.values_list('item_id', flat=True)), [item.id])
        self.assertEqual(
            ProcurementExpenseTarget.all_objects.filter(expense=expense, item=item).count(),
            1,
        )

    def test_update_procurement_expense_targets_is_idempotent_after_soft_delete(self):
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
                'amount': Decimal('30'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'allocation_method': 'BY_QUANTITY',
            }],
        )
        item = procurement.items.get()
        expense = procurement.expenses.get()

        update_procurement_expense_targets(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            expense_id=expense.id,
            target_item_ids=[item.id],
        )
        update_procurement_expense_targets(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            expense_id=expense.id,
            target_item_ids=[],
        )
        update_procurement_expense_targets(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            expense_id=expense.id,
            target_item_ids=[item.id],
        )

        expense.refresh_from_db()
        self.assertEqual(list(expense.targets.values_list('item_id', flat=True)), [item.id])
        self.assertEqual(
            ProcurementExpenseTarget.all_objects.filter(expense=expense, item=item).count(),
            1,
        )

    def test_split_procurement_item_keeps_paid_status_and_total_quantity(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('100'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('1000'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        item = procurement.items.get()

        first_part, second_part = split_procurement_item(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            item_id=item.id,
            quantity=Decimal('30'),
        )

        first_part.refresh_from_db()
        second_part.refresh_from_db()
        self.assertEqual(first_part.quantity, Decimal('30'))
        self.assertEqual(second_part.quantity, Decimal('70'))
        self.assertEqual(first_part.status, first_part.Status.PAID)
        self.assertEqual(second_part.status, second_part.Status.PAID)

    def test_partial_receive_keeps_balance_for_draft_future_items(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.6'),
                'planned_budget': Decimal('150'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('100'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('50'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('100'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('50'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        paid_item = procurement.items.get()

        update_open_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.6'),
                'planned_budget': Decimal('150'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('100'),
                        'profit_share': Decimal('0.4'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('50'),
                        'profit_share': Decimal('0.6'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('5'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[paid_item.id],
            capital_allocations=[
                {'partner_id': ctx['investor'].id, 'amount': Decimal('66.67')},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('33.33')},
            ],
        )

        procurement.refresh_from_db()
        balance = ProcurementBalance.objects.get(procurement=procurement)
        self.assertEqual(procurement.status, Procurement.Status.PARTIALLY_RECEIVED)
        self.assertEqual(balance.balances, {'UZS': '50.00'})

    def test_partial_receive_uses_batch_level_capital_snapshots(self):
        from apps.partnerships.formulas import calculate_profit_distribution

        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.5'),
                'planned_budget': Decimal('200'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('70'),
                        'profit_share': Decimal('0.35'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('30'),
                        'profit_share': Decimal('0.65'),
                    },
                ],
            },
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
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                },
            ],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('160'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('40'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        first_item, second_item = list(procurement.items.order_by('id'))

        with self.assertRaisesMessage(ValueError, 'укажите доли капитала партии'):
            receive_procurement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                destination_warehouse_id=ctx['storage'].id,
                item_ids=[first_item.id],
            )

        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[first_item.id],
            capital_allocations=[
                {'partner_id': ctx['investor'].id, 'amount': Decimal('70')},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('30')},
            ],
        )
        receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
            item_ids=[second_item.id],
            capital_allocations=[
                {'partner_id': ctx['investor'].id, 'amount': Decimal('90')},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('10')},
            ],
        )

        first_lot = first_item.lots.get()
        second_lot = second_item.lots.get()
        first_partners = {
            row['role']: row for row in first_lot.contract_snapshot['partners']
        }
        second_partners = {
            row['role']: row for row in second_lot.contract_snapshot['partners']
        }

        self.assertEqual(Decimal(first_partners['INVESTOR']['capital_share']), Decimal('0.700000'))
        self.assertEqual(Decimal(second_partners['INVESTOR']['capital_share']), Decimal('0.900000'))
        self.assertEqual(Decimal(first_partners['INVESTOR']['profit_share']), Decimal('0.350000'))
        self.assertEqual(Decimal(second_partners['INVESTOR']['profit_share']), Decimal('0.450000'))

        first_distribution = calculate_profit_distribution(
            lot=first_lot,
            unit_price=Decimal('20'),
            quantity=10,
            unit_landed_cost=Decimal('10'),
        )
        second_distribution = calculate_profit_distribution(
            lot=second_lot,
            unit_price=Decimal('20'),
            quantity=10,
            unit_landed_cost=Decimal('10'),
        )

        self.assertEqual(Decimal(first_distribution[str(ctx['investor'].id)]), Decimal('35.00'))
        self.assertEqual(Decimal(first_distribution[str(ctx['operator'].id)]), Decimal('65.00'))
        self.assertEqual(Decimal(second_distribution[str(ctx['investor'].id)]), Decimal('45.00'))
        self.assertEqual(Decimal(second_distribution[str(ctx['operator'].id)]), Decimal('55.00'))

    def test_receive_rejects_batch_allocation_above_available_capital(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.5'),
                'planned_budget': Decimal('100'),
                'currency': 'UZS',
                'partners': [
                    {
                        'partner_id': ctx['investor'].id,
                        'role': 'INVESTOR',
                        'planned_capital_share': Decimal('50'),
                        'profit_share': Decimal('0.25'),
                    },
                    {
                        'partner_id': ctx['operator'].id,
                        'role': 'OPERATOR',
                        'planned_capital_share': Decimal('50'),
                        'profit_share': Decimal('0.75'),
                    },
                ],
            },
            items=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('10'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('80'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('120'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        item = procurement.items.get()

        with self.assertRaisesMessage(ValueError, 'Недостаточно капитала'):
            receive_procurement(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                destination_warehouse_id=ctx['storage'].id,
                item_ids=[item.id],
                capital_allocations=[
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('100')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('0')},
                ],
            )

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

    def test_add_contribution_rejects_partner_outside_procurement_contract(self):
        ctx = build_tenant()
        outsider = Partner.objects.create(
            tenant=ctx['business'],
            role=Partner.Role.INVESTOR,
            display_name='Outsider',
            is_active=True,
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

        with self.assertRaisesMessage(ValueError, 'Selected partner is not part of this procurement contract.'):
            add_contribution(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                partner_id=outsider.id,
                amount=Decimal('70'),
                currency='USD',
                fx_rate=Decimal('12000'),
            )

    def test_agreement_flow_allocates_multiple_procurements_and_targets_expenses(self):
        ctx = build_tenant()
        agreement = create_investment_agreement(
            tenant_id=ctx['business'].id,
            planned_budget=Decimal('200'),
            currency='USD',
            mudaraba_ratio=Decimal('0.571429'),
            supplier_id=ctx['supplier'].id,
            partners=[
                {
                    'partner_id': ctx['investor'].id,
                    'role': 'INVESTOR',
                    'planned_capital_share': Decimal('140'),
                    'profit_share': Decimal('0.4'),
                },
                {
                    'partner_id': ctx['operator'].id,
                    'role': 'OPERATOR',
                    'planned_capital_share': Decimal('60'),
                    'profit_share': Decimal('0.6'),
                },
            ],
        )
        add_agreement_contribution(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('150'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )
        add_agreement_contribution(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('50'),
            currency='USD',
            fx_rate=Decimal('12000'),
        )

        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            agreement_id=agreement.id,
            items=[
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'USD',
                    'fx_rate': Decimal('12000'),
                },
                {
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('5'),
                    'currency': 'USD',
                    'fx_rate': Decimal('12000'),
                },
            ],
        )

        preview = get_agreement_allocation_preview(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            procurement_id=procurement.id,
        )
        self.assertEqual(preview['required'], {'USD': '150.00'})
        allocate_agreement_to_procurement(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            procurement_id=procurement.id,
            allocations=[
                {
                    'partner_id': row['partner_id'],
                    'amount': row['amount'],
                    'currency': row['currency'],
                    'fx_rate': Decimal('12000'),
                }
                for row in preview['suggestions']
                if Decimal(str(row['amount'])) > 0
            ],
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )

        first_item = procurement.items.order_by('id').first()
        update_open_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            agreement_id=agreement.id,
            items=[],
            expenses=[{
                'expense_type': 'CUSTOMS',
                'amount': Decimal('20'),
                'currency': 'USD',
                'fx_rate': Decimal('12000'),
                'allocation_method': 'BY_QUANTITY',
                'target_item_ids': [first_item.id],
            }],
        )
        allocate_agreement_to_procurement(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            procurement_id=procurement.id,
            allocations=[
                {
                    'partner_id': ctx['investor'].id,
                    'amount': Decimal('20'),
                    'currency': 'USD',
                    'fx_rate': Decimal('12000'),
                },
                {
                    'partner_id': ctx['operator'].id,
                    'amount': Decimal('5'),
                    'currency': 'USD',
                    'fx_rate': Decimal('12000'),
                },
            ],
        )
        pay_procurement_expenses(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        ExchangeRate.objects.create(
            tenant=ctx['business'],
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Agreement surplus return rate',
            raw_payload={},
        )

        received = receive_procurement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            destination_warehouse_id=ctx['storage'].id,
        )
        agreement.refresh_from_db()
        balance = ProcurementBalance.objects.get(procurement=received)
        lots = [item.lots.get() for item in received.items.order_by('id')]

        self.assertEqual(received.status, Procurement.Status.RECEIVED)
        self.assertEqual(balance.balances, {'USD': '0.00'})
        self.assertEqual(agreement.balances, {'USD': '30.00'})
        self.assertEqual(lots[0].landed_cost_per_unit, Decimal('144000.00'))
        self.assertEqual(lots[1].landed_cost_per_unit, Decimal('60000.00'))
        returned = sum(
            (
                allocation.amount
                for allocation in AgreementAllocation.objects.filter(
                    agreement=agreement,
                    procurement=received,
                    direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
                )
            ),
            Decimal('0.00'),
        )
        self.assertEqual(returned, Decimal('5.00'))

    def test_partnership_receive_plan_is_blocked_when_batch_preview_missing(self):
        ctx = build_tenant()
        procurement = open_procurement(
            tenant_id=ctx['business'].id,
            procurement_type=Procurement.Type.PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
            contract={
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('100'),
                'currency': 'UZS',
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
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }],
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('70'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        add_contribution(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            partner_id=ctx['operator'].id,
            amount=Decimal('30'),
            currency='UZS',
            fx_rate=Decimal('1'),
        )
        pay_procurement_items(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
        )
        item = procurement.items.get()

        with patch('apps.partnerships.services._batch_capital_preview', return_value=None):
            plan = get_procurement_receive_plan(
                tenant_id=ctx['business'].id,
                procurement_id=procurement.id,
                item_ids=[item.id],
            )

        self.assertEqual(plan['status'], 'BLOCKED')
        self.assertEqual(plan['batch_capital_preview']['status'], 'BLOCKED')
        self.assertIn('Не удалось сформировать доли партии', plan['message'])
