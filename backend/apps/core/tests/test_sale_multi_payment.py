from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import PartnerLedgerEntry
from apps.sales.models import Sale, SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class SaleMultiPaymentTests(TestCase):
    def test_create_sale_creates_multiple_payments_and_profit_ledger_entries(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
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
            payments=[
                {
                    'amount': Decimal('600000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CASH,
                },
                {
                    'amount': Decimal('600000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CARD,
                },
            ],
            notes='PR-9c multi-payment test',
        )

        sale.refresh_from_db()
        line = sale.lines.get()
        payments = list(sale.payments.order_by('id'))
        entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__procurement_id=procurement.id,
                entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
            ).order_by('ledger__partner_id')
        )

        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.assertEqual(line.lot_id, lot.id)
        self.assertEqual(len(payments), 2)
        self.assertEqual({payments[0].method, payments[1].method}, {
            SalePayment.Method.CASH,
            SalePayment.Method.CARD,
        })

        paid_total = sum(payment.amount for payment in payments)
        self.assertEqual(paid_total, sale.total_amount)
        self.assertEqual(sale.total_amount, line.unit_price * line.quantity)
        self.assertEqual(sale.total_cogs, line.unit_landed_cost * line.quantity)

        snapshot = line.profit_distribution_snapshot
        self.assertSetEqual(
            set(snapshot.keys()),
            {str(ctx['investor'].id), str(ctx['operator'].id)},
        )
        snapshot_total = sum(Decimal(str(value)) for value in snapshot.values())
        self.assertEqual(
            snapshot_total,
            (sale.total_amount - sale.total_cogs).quantize(Decimal('0.01')),
        )

        entry_map = {entry.ledger.partner_id: entry.amount for entry in entries}
        self.assertEqual(len(entry_map), 2)
        self.assertEqual(
            entry_map[ctx['investor'].id],
            Decimal(str(snapshot[str(ctx['investor'].id)])),
        )
        self.assertEqual(
            entry_map[ctx['operator'].id],
            Decimal(str(snapshot[str(ctx['operator'].id)])),
        )

        self.assertEqual(lot.stocks.get(warehouse=ctx['storage']).quantity_remaining, 50 - line.quantity)
