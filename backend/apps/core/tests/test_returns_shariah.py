from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase

from apps.finance.models import CashEntry, JournalEntry
from apps.inventory.models import Lot, StockDisposal, StockMovement
from apps.partnerships.models import ProcurementSaleRealization
from apps.partnerships.venture import procurement_venture_positions
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

        process_return(
            sale=sale,
            return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.RESTOCK,
            reason=Return.Reason.CLIENT_REFUSE,
            processed_by_id=ctx['cashier'].id,
            tenant_id=ctx['business'].id,
        )

        lot.refresh_from_db()

        self.assertEqual(lot.stocks.get(warehouse=ctx['store']).quantity_remaining, 46)
        self.assertTrue(lot.is_active)

        sale_line = sale.lines.get()
        reversal_rows = ProcurementSaleRealization.objects.filter(
            sale_line=sale_line,
            event_type=ProcurementSaleRealization.EventType.REVERSAL,
        )
        self.assertEqual(reversal_rows.count(), 2)
        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['capital_recovered_uzs'],
            Decimal('369600.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_uzs'],
            Decimal('172800.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_available_uzs'],
            Decimal('0'),
        )

    def test_dispose_return_records_loss_by_capital_share(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
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
                'account_id': ctx['cash_account'].id,
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

        self.assertEqual(lot.stocks.get(warehouse=ctx['store']).quantity_remaining, 45)
        self.assertEqual(lot.quantity_initial, 49)
        self.assertEqual(disposal.reason, StockDisposal.Reason.DAMAGED_RETURN)

        sale_line = sale.lines.get()
        expected_loss_amount = (sale_line.unit_landed_cost * Decimal('1')).quantize(Decimal('0.01'))
        self.assertEqual(disposal.loss_amount, expected_loss_amount)

        # E17: the disposed-return loss is recorded as a venture realization
        # reversal (loss by capital share), not a legacy LOSS_INCURRED ledger row.
        disposed_loss = ProcurementSaleRealization.objects.filter(
            sale_line=sale_line,
            event_type=ProcurementSaleRealization.EventType.REVERSAL,
        ).aggregate(total=Sum('loss_uzs'))['total'] or Decimal('0')
        self.assertEqual(disposed_loss, expected_loss_amount)

        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['investor'].id]['capital_recovered_uzs'],
            Decimal('369600.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['loss_uzs'],
            Decimal('92400.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_uzs'],
            Decimal('120000.00'),
        )
        self.assertEqual(
            positions[ctx['investor'].id]['provisional_profit_available_uzs'],
            Decimal('0'),
        )

    def test_cash_return_without_customer_updates_stock_cash_journal_and_status(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=None,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        return_doc = process_return(
            sale=sale,
            return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.RESTOCK,
            reason=Return.Reason.CLIENT_REFUSE,
            processed_by_id=ctx['cashier'].id,
            tenant_id=ctx['business'].id,
            refund_payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        sale.refresh_from_db()
        self.assertEqual(sale.status, sale.SaleStatus.RETURNED)
        self.assertEqual(sale.payments.filter(role=SalePayment.Role.REFUND).count(), 1)
        self.assertEqual(
            CashEntry.objects.filter(source_ref_type='refund', direction=CashEntry.Direction.OUT).count(),
            1,
        )
        self.assertTrue(
            StockMovement.objects.filter(
                movement_type=StockMovement.MovementType.RETURN,
                reference_type='return',
                reference_id=return_doc.pk,
            ).exists()
        )
        self.assertGreaterEqual(
            JournalEntry.objects.filter(operation_type=JournalEntry.OperationType.RETURN).count(),
            2,
        )
