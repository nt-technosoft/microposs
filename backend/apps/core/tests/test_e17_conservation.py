"""E17 Phase 4 — conservation invariant matrix (safety-critical).

Each pocket (capital / proceeds / distribution) must net to ~0 INDEPENDENTLY and
PER CURRENCY across the full scenario matrix. Functional UZS residuals are exact
zero (Decimal); native-currency legs tolerate sub-cent FX-division rounding only.
The matrix CONFIRMS the derived identities; it does not define them.
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import ExchangeRate
from apps.finance.fx_rates import upsert_exchange_rate
from apps.partnerships.agreement_services import pay_dividend
from apps.partnerships.models import ProcurementSaleRealization, ProcurementVentureSettlement
from apps.partnerships.venture import create_venture_settlement, venture_conservation
from apps.partnerships.workspace_support import add_agreement_withdrawal
from apps.risk.services import create_writeoff
from apps.sales.models import Return, SalePayment
from apps.sales.services import create_sale, process_return

from ._helpers import build_tenant, open_session, seed_received_procurement

_EPS = Decimal('0.01')


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


def _set_sale_fx(ctx, session, rate):
    upsert_exchange_rate(
        tenant_id=ctx['business'].id, base_currency='USD', quote_currency='UZS',
        rate_date=session.opened_at.date(), rate=Decimal(rate),
        source=ExchangeRate.Source.MANUAL, is_manual=True, notes='conservation matrix',
    )


class ConservationMixin:
    def assert_balanced(self, procurement, *, msg=''):
        report = venture_conservation(procurement=procurement)
        # Functional UZS pockets must be EXACTLY zero.
        for pocket in ConservationReportPockets:
            resid = report.residual(pocket, 'UZS')
            self.assertEqual(
                resid, Decimal('0.00'),
                msg=f'{msg} pocket {pocket}/UZS residual={resid} '
                    f'breakdown={report.breakdown(Decimal("0"))}',
            )
        # Every pocket/currency (incl native) within FX-division epsilon.
        self.assertTrue(
            report.is_balanced(_EPS),
            msg=f'{msg} imbalances={report.imbalances(_EPS)}',
        )


ConservationReportPockets = ('capital', 'proceeds', 'distribution')


class ConservationMatrixTests(ConservationMixin, TestCase):
    def test_profit_partial_sale(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        self.assert_balanced(procurement, msg='profit')

    def test_loss_below_cost(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='100000.00')
        self.assert_balanced(procurement, msg='loss')

    def test_mixed_profit_then_loss(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        _sell(ctx, session, quantity=5, unit_price='100000.00')
        self.assert_balanced(procurement, msg='mixed')

    def test_cross_currency_fx_up(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)
        _set_sale_fx(ctx, session, '13000.00')
        _sell(ctx, session, quantity=10, unit_price='180000.00')
        self.assert_balanced(procurement, msg='fx_up')

    def test_cross_currency_fx_down(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)
        _set_sale_fx(ctx, session, '11000.00')
        _sell(ctx, session, quantity=10, unit_price='180000.00')
        self.assert_balanced(procurement, msg='fx_down')

    def test_partner_liability_writeoff(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        create_writeoff(
            tenant_id=ctx['business'].id, lot_id=lot.id, warehouse_id=ctx['store'].id,
            quantity=2, reason='Negligence', responsible_user_id=ctx['owner'].id, negligence=True,
        )
        self.assert_balanced(procurement, msg='partner_liability')

    def test_partner_liability_cross_currency(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)
        _set_sale_fx(ctx, session, '13000.00')
        _sell(ctx, session, quantity=5, unit_price='180000.00')
        create_writeoff(
            tenant_id=ctx['business'].id, lot_id=lot.id, warehouse_id=ctx['store'].id,
            quantity=2, reason='Negligence', responsible_user_id=ctx['owner'].id, negligence=True,
        )
        self.assert_balanced(procurement, msg='partner_liability_fx')

    def test_return_restock(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = _sell(ctx, session, quantity=5, unit_price='240000.00')
        process_return(
            sale=sale, return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.RESTOCK, reason=Return.Reason.CLIENT_REFUSE,
            processed_by_id=ctx['cashier'].id, tenant_id=ctx['business'].id,
        )
        self.assert_balanced(procurement, msg='return_restock')

    def test_return_dispose(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = _sell(ctx, session, quantity=5, unit_price='240000.00')
        process_return(
            sale=sale, return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.DISPOSE, reason=Return.Reason.DEFECT,
            processed_by_id=ctx['cashier'].id, tenant_id=ctx['business'].id,
        )
        self.assert_balanced(procurement, msg='return_dispose')

    def test_full_sale_then_final_settlement(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        create_venture_settlement(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
        )
        self.assert_balanced(procurement, msg='final_settlement')


class ConservationLifecycleTests(ConservationMixin, TestCase):
    def test_repeated_return_submit_is_idempotent(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = _sell(ctx, session, quantity=5, unit_price='240000.00')
        rid = uuid.uuid4()
        kwargs = dict(
            sale=sale, return_lines=[{'sale_line_id': sale.lines.get().id, 'quantity': 1}],
            resolution=Return.Resolution.DISPOSE, reason=Return.Reason.DEFECT,
            processed_by_id=ctx['cashier'].id, tenant_id=ctx['business'].id,
            client_request_id=rid,
        )
        first = process_return(**kwargs)
        second = process_return(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Return.objects.filter(tenant_id=ctx['business'].id, sale=sale).count(), 1,
        )
        # Exactly one set of REVERSAL events; conservation still nets to zero.
        self.assertEqual(
            ProcurementSaleRealization.objects.filter(
                procurement=procurement,
                event_type=ProcurementSaleRealization.EventType.REVERSAL,
            ).count(),
            2,  # one per partner, single return
        )
        self.assert_balanced(procurement, msg='idempotent_return')

    def test_over_withdrawal_then_loss_keeps_conservation(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        create_venture_settlement(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        # Investor withdraws profit, then a later loss creates a negative position.
        pay_dividend(
            partner_id=ctx['investor'].id, procurement_id=procurement.id,
            amount=Decimal('216000.00'), currency='UZS',
            from_account_id=ctx['cash_account'].id, tenant_id=ctx['business'].id,
        )
        _sell(ctx, session, quantity=5, unit_price='100000.00')
        from apps.partnerships.venture import procurement_venture_positions
        positions = procurement_venture_positions(procurement=procurement)
        self.assertGreater(positions[ctx['investor'].id]['negative_position_uzs'], Decimal('0'))
        # Payouts/negative positions do not break value conservation.
        self.assert_balanced(procurement, msg='over_withdrawal')


class ConservationTamperTests(ConservationMixin, TestCase):
    def test_final_settlement_blocked_on_injected_discrepancy(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')  # fully sold → FINAL allowed

        row = ProcurementSaleRealization.objects.filter(
            procurement=procurement,
            event_type=ProcurementSaleRealization.EventType.REALIZATION,
        ).first()
        ProcurementSaleRealization.objects.filter(pk=row.pk).update(
            capital_recovered_uzs=row.capital_recovered_uzs + Decimal('5000.00'),
        )
        with self.assertRaises(ValueError) as cm:
            create_venture_settlement(
                tenant_id=ctx['business'].id, procurement_id=procurement.id,
                settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
            )
        self.assertIn('Conservation invariant violated', str(cm.exception))


    def test_injected_discrepancy_breaks_capital_pocket(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        self.assert_balanced(procurement, msg='pre-tamper')

        # Inject phantom recovered capital with no matching cost/proceeds.
        row = ProcurementSaleRealization.objects.filter(
            procurement=procurement,
            event_type=ProcurementSaleRealization.EventType.REALIZATION,
        ).first()
        ProcurementSaleRealization.objects.filter(pk=row.pk).update(
            capital_recovered_uzs=row.capital_recovered_uzs + Decimal('5000.00'),
        )

        report = venture_conservation(procurement=procurement)
        self.assertFalse(report.is_balanced(_EPS))
        broken = {pocket for pocket, _ccy, _resid in report.imbalances(_EPS)}
        self.assertIn('capital', broken)
