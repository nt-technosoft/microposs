"""E17 — Production Lifecycle Readiness tests.

Phase 1 starts with a proof that the legacy ``PartnerLedgerEntry`` profit
source and the E16 venture model disagree on a mixed profit/loss venture. The
test computes both actual values from the running system (never hard-coded
"derived by reading the code" numbers) and asserts the divergence, the
direction of the error (legacy overstates), and that the gap equals the loss
the legacy ledger silently ignores.
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.venture import procurement_venture_positions
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


def _sell(ctx, session, *, quantity, unit_price):
    return create_sale(
        tenant_id=ctx['business'].id,
        pos_session_id=session.id,
        location_id=ctx['store'].id,
        sold_by_id=ctx['cashier'].id,
        customer_id=ctx['customer'].id,
        lines=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': quantity,
            'unit_price': Decimal(unit_price),
        }],
        payments=[{
            'amount': Decimal(unit_price) * Decimal(quantity),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
            'method': SalePayment.Method.CASH,
            'account_id': ctx['cash_account'].id,
        }],
    )


class LegacyLedgerVsVentureProofTests(TestCase):
    """T-1.1 — legacy ledger and venture diverge on a mixed profit/loss venture."""

    def test_legacy_ledger_overstates_distributable_profit_vs_venture(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)

        # Sale 1 above cost (profit), Sale 2 below cost (loss) — same venture,
        # same immutable share profile.
        profit_sale = _sell(ctx, session, quantity=5, unit_price='240000.00')
        loss_sale = _sell(ctx, session, quantity=5, unit_price='100000.00')

        partner_ids = [ctx['investor'].id, ctx['operator'].id]

        # Legacy algorithm, reconstructed faithfully from the per-line
        # profit_distribution_snapshot (still stored on each SaleLine): the old
        # PROFIT_ACCRUED ledger summed each line's gross profit split by
        # profit_share, but ONLY on profitable lines (gross_line_profit > 0) and
        # never recorded the below-cost line's loss. This is exactly what the
        # legacy investor dashboards / reports distributed.
        legacy = {pid: Decimal('0') for pid in partner_ids}
        for line in (profit_sale.lines.get(), loss_sale.lines.get()):
            if Decimal(str(line.gross_profit)) <= 0:
                continue
            for pid_str, amount in (line.profit_distribution_snapshot or {}).items():
                pid = int(pid_str)
                if pid in legacy:
                    legacy[pid] += Decimal(str(amount))

        # Target source of truth: venture net entitlement.
        venture_positions = procurement_venture_positions(procurement=procurement)
        venture = {
            pid: Decimal(str(venture_positions[pid]['provisional_profit_uzs']))
            for pid in partner_ids
        }

        legacy_total = sum(legacy.values(), Decimal('0'))
        venture_total = sum(venture.values(), Decimal('0'))

        # 1) The two sources genuinely disagree per partner — two truths.
        for pid in partner_ids:
            self.assertNotEqual(
                legacy[pid], venture[pid],
                msg=f'partner {pid}: legacy {legacy[pid]} == venture {venture[pid]} '
                    f'(expected divergence)',
            )

        # 2) The legacy ledger OVERSTATES distributable profit: a below-cost
        #    sale writes no LOSS_INCURRED into the partnership ledger, so the
        #    loss is invisible to the legacy profit number. This invites
        #    over-withdrawal of profit the venture never earned.
        self.assertGreater(legacy_total, venture_total)
        for pid in partner_ids:
            self.assertGreater(legacy[pid], venture[pid])

        # 3) The overstatement equals exactly the loss the legacy ledger
        #    ignored — derived from the loss sale's own facts, not assumed.
        loss_line = loss_sale.lines.get()
        ignored_loss = (
            Decimal(str(loss_line.unit_landed_cost)) - Decimal(str(loss_line.unit_price))
        ) * Decimal(str(loss_line.quantity))
        self.assertGreater(ignored_loss, Decimal('0'))
        self.assertEqual(legacy_total - venture_total, ignored_loss)
