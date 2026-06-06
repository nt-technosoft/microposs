from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import AgreementAllocation, PartnerLedgerEntry
from apps.partnerships.agreement_services import get_partner_aggregate
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

        investor = get_partner_aggregate(ctx['investor'].id, ctx['business'].id)
        operator = get_partner_aggregate(ctx['operator'].id, ctx['business'].id)

        investor_capital_in = sum(
            (
                allocation.amount
                for allocation in AgreementAllocation.objects.filter(
                    procurement=procurement,
                    partner_id=ctx['investor'].id,
                    direction=AgreementAllocation.Direction.TO_PROCUREMENT,
                )
            ),
            Decimal('0.00'),
        )
        operator_capital_in = sum(
            (
                allocation.amount
                for allocation in AgreementAllocation.objects.filter(
                    procurement=procurement,
                    partner_id=ctx['operator'].id,
                    direction=AgreementAllocation.Direction.TO_PROCUREMENT,
                )
            ),
            Decimal('0.00'),
        )

        line_snapshot = sale.lines.get().profit_distribution_snapshot
        investor_profit = Decimal(str(line_snapshot[str(ctx['investor'].id)]))
        operator_profit = Decimal(str(line_snapshot[str(ctx['operator'].id)]))

        self.assertEqual(investor['by_currency']['USD']['capital_in'], investor_capital_in)
        self.assertEqual(operator['by_currency']['USD']['capital_in'], operator_capital_in)
        self.assertEqual(investor['by_currency']['USD']['capital_out'], Decimal('0.00'))
        self.assertEqual(operator['by_currency']['USD']['capital_out'], Decimal('0.00'))

        self.assertEqual(investor['profit_accrued'], investor_profit)
        self.assertEqual(operator['profit_accrued'], operator_profit)
        self.assertEqual(investor['profit_reversed'], Decimal('0.00'))
        self.assertEqual(operator['profit_reversed'], Decimal('0.00'))
        self.assertEqual(investor['losses_incurred'], Decimal('0.00'))
        self.assertEqual(operator['losses_incurred'], Decimal('0.00'))
        self.assertEqual(investor['dividends_paid'], Decimal('0.00'))
        self.assertEqual(operator['dividends_paid'], Decimal('0.00'))

        # E17: venture profit is not payable before a venture settlement.
        self.assertEqual(investor['profit_pending_payout'], Decimal('0.00'))
        self.assertEqual(operator['profit_pending_payout'], Decimal('0.00'))

        # E17 T-1.5/T-1.6: the PartnerLedgerEntry profit triad is no longer
        # written; the ledger holds only physical events (capital/dividends).
        triad = {
            PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
            PartnerLedgerEntry.EntryType.PROFIT_REVERSED,
            PartnerLedgerEntry.EntryType.LOSS_INCURRED,
        }
        self.assertFalse(
            PartnerLedgerEntry.objects.filter(
                ledger__tenant_id=ctx['business'].id,
                entry_type__in=triad,
            ).exists()
        )

        self.assertEqual(
            investor['profit_accrued'] + operator['profit_accrued'],
            (sale.total_amount - sale.total_cogs).quantize(Decimal('0.01')),
        )
        agreement = procurement.agreement_allocations.first().agreement
        self.assertEqual(
            investor['by_currency']['USD']['capital_in'] + operator['by_currency']['USD']['capital_in'],
            agreement.planned_budget,
        )
