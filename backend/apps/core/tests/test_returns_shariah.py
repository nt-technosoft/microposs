from decimal import Decimal

from django.test import TestCase

from apps.inventory.models import Lot, StockDisposal
from apps.partnerships.models import PartnerLedgerEntry
from apps.sales.models import Return, SalePayment
from apps.sales.services import create_sale, process_return

from ._helpers import build_tenant, open_session, seed_received_procurement


class ReturnsShariahTests(TestCase):
    def test_restock_return_reverses_profit_and_restores_stock(self):
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
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        process_return(
            sale=sale,
            return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.RESTOCK,
            reason=Return.Reason.CLIENT_REFUSE,
            processed_by_id=ctx['cashier'].id,
            tenant_id=ctx['business'].id,
        )

        lot.refresh_from_db()
        reversed_entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__procurement_id=procurement.id,
                entry_type=PartnerLedgerEntry.EntryType.PROFIT_REVERSED,
            ).order_by('ledger__partner_id')
        )

        self.assertEqual(lot.stocks.get(warehouse=ctx['storage']).quantity_remaining, 46)
        self.assertTrue(lot.is_active)

        sale_line = sale.lines.get()
        qty_ratio = Decimal('1') / Decimal(sale_line.quantity)
        expected_reversed = {
            ctx['investor'].id: (
                Decimal(str(sale_line.profit_distribution_snapshot[str(ctx['investor'].id)]))
                * qty_ratio
            ).quantize(Decimal('0.01')),
            ctx['operator'].id: (
                Decimal(str(sale_line.profit_distribution_snapshot[str(ctx['operator'].id)]))
                * qty_ratio
            ).quantize(Decimal('0.01')),
        }
        actual_reversed = {entry.ledger.partner_id: entry.amount for entry in reversed_entries}
        self.assertEqual(actual_reversed, expected_reversed)

    def test_dispose_return_records_loss_by_capital_share(self):
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
            payments=[{
                'amount': Decimal('1200000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
            }],
        )

        process_return(
            sale=sale,
            return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.DISPOSE,
            reason=Return.Reason.DEFECT,
            processed_by_id=ctx['cashier'].id,
            tenant_id=ctx['business'].id,
        )

        lot.refresh_from_db()
        disposal = StockDisposal.objects.get(return_ref__sale=sale)
        loss_entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__procurement_id=procurement.id,
                entry_type=PartnerLedgerEntry.EntryType.LOSS_INCURRED,
            ).order_by('ledger__partner_id')
        )

        self.assertEqual(lot.stocks.get(warehouse=ctx['storage']).quantity_remaining, 45)
        self.assertEqual(lot.quantity_initial, 49)
        self.assertEqual(disposal.reason, StockDisposal.Reason.DAMAGED_RETURN)

        sale_line = sale.lines.get()
        expected_loss_amount = (sale_line.unit_landed_cost * Decimal('1')).quantize(Decimal('0.01'))
        self.assertEqual(disposal.loss_amount, expected_loss_amount)

        partners = {
            item['role']: item
            for item in lot.contract_snapshot['partners']
        }
        expected_losses = {
            ctx['investor'].id: (
                expected_loss_amount
                * Decimal(str(partners['INVESTOR']['capital_share']))
            ).quantize(Decimal('0.01')),
            ctx['operator'].id: (
                expected_loss_amount
                * Decimal(str(partners['OPERATOR']['capital_share']))
            ).quantize(Decimal('0.01')),
        }
        actual_losses = {entry.ledger.partner_id: entry.amount for entry in loss_entries}
        self.assertEqual(actual_losses, expected_losses)
        self.assertEqual(sum(actual_losses.values()), expected_loss_amount)
