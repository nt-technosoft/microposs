from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import PartnerLedgerEntry
from apps.partnerships.services import get_partner_aggregate
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class PartnerLedgerAggregateTests(TestCase):
    def test_partner_aggregate_uses_new_ledger_model(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['storage'].id,
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

        investor = get_partner_aggregate(ctx['investor'].id, ctx['business'].id)
        operator = get_partner_aggregate(ctx['operator'].id, ctx['business'].id)

        investor_capital_in = sum(
            (
                contribution.amount
                for contribution in procurement.balance.contributions.filter(
                    partner_id=ctx['investor'].id,
                )
            ),
            Decimal('0.00'),
        )
        operator_capital_in = sum(
            (
                contribution.amount
                for contribution in procurement.balance.contributions.filter(
                    partner_id=ctx['operator'].id,
                )
            ),
            Decimal('0.00'),
        )

        line_snapshot = sale.lines.get().profit_distribution_snapshot
        investor_profit = Decimal(str(line_snapshot[str(ctx['investor'].id)]))
        operator_profit = Decimal(str(line_snapshot[str(ctx['operator'].id)]))

        self.assertEqual(investor['capital_in'], investor_capital_in)
        self.assertEqual(operator['capital_in'], operator_capital_in)
        self.assertEqual(investor['capital_out'], Decimal('0.00'))
        self.assertEqual(operator['capital_out'], Decimal('0.00'))

        self.assertEqual(investor['profit_accrued'], investor_profit)
        self.assertEqual(operator['profit_accrued'], operator_profit)
        self.assertEqual(investor['profit_reversed'], Decimal('0.00'))
        self.assertEqual(operator['profit_reversed'], Decimal('0.00'))
        self.assertEqual(investor['losses_incurred'], Decimal('0.00'))
        self.assertEqual(operator['losses_incurred'], Decimal('0.00'))
        self.assertEqual(investor['dividends_paid'], Decimal('0.00'))
        self.assertEqual(operator['dividends_paid'], Decimal('0.00'))

        self.assertEqual(investor['profit_pending_payout'], investor_profit)
        self.assertEqual(operator['profit_pending_payout'], operator_profit)
        self.assertGreater(investor['profit_pending_payout'], Decimal('0'))
        self.assertGreater(operator['profit_pending_payout'], Decimal('0'))

        investor_entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__partner_id=ctx['investor'].id,
                ledger__tenant_id=ctx['business'].id,
            )
        )
        operator_entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__partner_id=ctx['operator'].id,
                ledger__tenant_id=ctx['business'].id,
            )
        )
        self.assertEqual(
            sum(
                (
                    entry.amount
                    for entry in investor_entries
                    if entry.entry_type == PartnerLedgerEntry.EntryType.PROFIT_ACCRUED
                ),
                Decimal('0.00'),
            ),
            investor_profit,
        )
        self.assertEqual(
            sum(
                (
                    entry.amount
                    for entry in operator_entries
                    if entry.entry_type == PartnerLedgerEntry.EntryType.PROFIT_ACCRUED
                ),
                Decimal('0.00'),
            ),
            operator_profit,
        )

        self.assertEqual(
            investor['profit_accrued'] + operator['profit_accrued'],
            (sale.total_amount - sale.total_cogs).quantize(Decimal('0.01')),
        )
        self.assertEqual(
            investor['capital_in'] + operator['capital_in'],
            procurement.contract.planned_budget,
        )
