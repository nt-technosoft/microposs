from decimal import Decimal

from django.test import TestCase

from apps.sales.services import calculate_profit_distribution

from ._helpers import build_tenant, seed_received_procurement


class MusharakaMudarabaFormulaTests(TestCase):
    def test_calculate_profit_distribution_respects_contract_formula(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        unit_price = Decimal('240000.00')
        unit_landed_cost = Decimal('132000.00')
        quantity = 5
        gross = (unit_price - unit_landed_cost) * quantity

        distribution = calculate_profit_distribution(
            lot=lot,
            unit_price=unit_price,
            quantity=quantity,
            unit_landed_cost=unit_landed_cost,
        )

        partners = {
            item['role']: item
            for item in lot.contract_snapshot['partners']
        }
        investor_capital_share = Decimal(str(partners['INVESTOR']['capital_share']))
        investor_expected = (
            gross * investor_capital_share * Decimal(str(lot.contract_snapshot['mudaraba_ratio']))
        ).quantize(Decimal('0.01'))

        investor_actual = Decimal(distribution[str(ctx['investor'].id)])
        operator_actual = Decimal(distribution[str(ctx['operator'].id)])

        self.assertSetEqual(
            set(distribution.keys()),
            {str(ctx['investor'].id), str(ctx['operator'].id)},
        )
        self.assertEqual(investor_actual, investor_expected)
        self.assertEqual(
            investor_actual + operator_actual,
            gross.quantize(Decimal('0.01')),
        )
        self.assertGreater(operator_actual, investor_actual)
        self.assertEqual(
            (investor_actual / gross).quantize(Decimal('0.0001')),
            Decimal(str(partners['INVESTOR']['profit_share'])).quantize(Decimal('0.0001')),
        )
        self.assertEqual(
            (operator_actual / gross).quantize(Decimal('0.0001')),
            Decimal(str(partners['OPERATOR']['profit_share'])).quantize(Decimal('0.0001')),
        )

    def test_calculate_profit_distribution_returns_empty_for_non_positive_profit(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        distribution = calculate_profit_distribution(
            lot=lot,
            unit_price=Decimal('132000.00'),
            quantity=5,
            unit_landed_cost=Decimal('132000.00'),
        )

        self.assertEqual(distribution, {})
