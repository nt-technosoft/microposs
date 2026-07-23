"""E18 Phase 8 — property-based conservation test (T-8.2).

Generates ≥12 distinct operation sequences. After every step verifies:
  1. venture_conservation residual == 0 per pocket × UZS (exact Decimal zero)
  2. FX imbalances within ε=0.01
  3. materialized read-model == canonical == legacy (tag-driven)

Operations covered: sell (profit/loss/at-cost), return (restock/dispose),
constructive settlement, final settlement, dividend, debt repayment, writeoff.
"""
from decimal import Decimal

from django.test import TestCase

from apps.partnerships.agreement_services import pay_dividend as _pay_dividend_service
from apps.partnerships.models import (
    InvestmentAgreement,
    PartnerPositionReadModel,
    ProcurementVentureSettlement,
)
from apps.partnerships.read_models import (
    canonical_partner_position_rows,
    legacy_partner_position_rows,
)
from apps.partnerships.venture import (
    create_venture_settlement,
    procurement_venture_positions,
    repay_partner_venture_debt,
    venture_conservation,
)
from apps.risk.services import create_writeoff
from apps.sales.models import PosSession, Return, SalePayment
from apps.sales.services import create_sale, process_return

from ._helpers import build_tenant, open_session, seed_received_procurement

_EPS = Decimal('0.01')
_ZERO = Decimal('0')
_POCKETS = ('capital', 'proceeds', 'distribution')

# Default seed: qty=50, unit_usd=10, customs_usd=50, fx=12,000 UZS/USD
# landed cost per unit = (50×10 + 50) / 50 × 12,000 = 11 × 12,000 = 132,000 UZS
_PROFIT_PRICE = Decimal('240000.00')   # 108,000 UZS above cost
_LOSS_PRICE = Decimal('100000.00')     # 32,000 UZS below cost
_AT_COST = Decimal('132000.00')        # exact break-even

_CONSTRUCTIVE = ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE
_FINAL = ProcurementVentureSettlement.SettlementType.FINAL


class _Runner:
    """
    Stateful helper for one scenario: wraps all financial operations and
    exposes check() to assert both conservation and read-model freshness.
    """

    def __init__(self, test_case, ctx, procurement, lot):
        self.tc = test_case
        self.ctx = ctx
        self.procurement = procurement
        self.lot = lot
        self.agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)

    # ------------------------------------------------------------------
    # Invariant checks
    # ------------------------------------------------------------------

    def _check_conservation(self, label: str) -> None:
        report = venture_conservation(procurement=self.procurement)
        for pocket in _POCKETS:
            resid = report.residual(pocket, 'UZS')
            self.tc.assertEqual(
                resid, _ZERO,
                msg=f'[{label}] pocket={pocket}/UZS resid={resid}; '
                    f'breakdown={report.breakdown(_ZERO)}',
            )
        self.tc.assertTrue(
            report.is_balanced(_EPS),
            msg=f'[{label}] FX imbalances: {report.imbalances(_EPS)}',
        )

    def check(self, label: str) -> None:
        """Assert conservation + read-model freshness after the last step."""
        self._check_conservation(label)
        canonical = dict(canonical_partner_position_rows(self.agreement))
        self.tc.assertEqual(
            canonical,
            dict(legacy_partner_position_rows(self.agreement)),
            msg=f'[{label}] canonical != legacy',
        )
        rm = {
            row.identity_key: row.money_payload
            for row in PartnerPositionReadModel.objects.filter(agreement=self.agreement)
        }
        self.tc.assertEqual(rm, canonical, msg=f'[{label}] read_model != canonical')

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _session(self):
        """Reuse the open session or create one (which transfers stock to store)."""
        return (
            PosSession.objects.filter(
                tenant=self.ctx['business'],
                location=self.ctx['store'],
                status=PosSession.SessionStatus.OPEN,
            ).first()
            or open_session(self.ctx)
        )

    def sell(self, quantity: int, unit_price: Decimal):
        total = unit_price * quantity
        return create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=self._session().id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=self.ctx['customer'].id,
            lines=[{'product_variant_id': self.ctx['variant'].id,
                    'quantity': quantity, 'unit_price': unit_price}],
            payments=[{'amount': total, 'currency': 'UZS', 'fx_rate': Decimal('1'),
                       'method': SalePayment.Method.CASH,
                       'account_id': self.ctx['cash_account'].id}],
        )

    def return_sale(self, sale, quantity: int, resolution: Return.Resolution) -> None:
        line = sale.lines.first()
        process_return(
            sale=sale,
            return_lines=[{'sale_line_id': line.id, 'quantity': quantity}],
            resolution=resolution,
            reason=Return.Reason.CLIENT_REFUSE,
            processed_by_id=self.ctx['cashier'].id,
            tenant_id=self.ctx['business'].id,
        )

    def settle(self, kind=_CONSTRUCTIVE) -> None:
        create_venture_settlement(
            tenant_id=self.ctx['business'].id,
            procurement_id=self.procurement.id,
            settlement_type=kind,
        )

    def dividend(self) -> None:
        """Pay the full currently available investor dividend (no-op if none)."""
        positions = procurement_venture_positions(procurement=self.procurement)
        avail = positions.get(self.ctx['investor'].id, {}).get('provisional_profit_available_uzs', _ZERO)
        if avail > _ZERO:
            _pay_dividend_service(
                partner_id=self.ctx['investor'].id,
                procurement_id=self.procurement.id,
                amount=avail,
                currency='UZS',
                from_account_id=self.ctx['cash_account'].id,
                tenant_id=self.ctx['business'].id,
            )

    def repay_debt(self) -> None:
        """Repay investor's full negative position (no-op if none)."""
        positions = procurement_venture_positions(procurement=self.procurement)
        neg = positions.get(self.ctx['investor'].id, {}).get('negative_position_uzs', _ZERO)
        if neg > _ZERO:
            repay_partner_venture_debt(
                tenant_id=self.ctx['business'].id,
                procurement_id=self.procurement.id,
                partner_id=self.ctx['investor'].id,
                amount=neg,
                currency='UZS',
                paid_to_account_id=self.ctx['cash_account'].id,
            )

    def writeoff(self, quantity: int) -> None:
        """Write off units from the store (requires prior sell/open_session)."""
        create_writeoff(
            tenant_id=self.ctx['business'].id,
            lot_id=self.lot.id,
            warehouse_id=self.ctx['store'].id,
            quantity=quantity,
            reason='Negligence',
            responsible_user_id=self.ctx['owner'].id,
            negligence=True,
        )


class PropertyConservationTests(TestCase):
    """
    Property: for every sequence of financial operations, both conservation
    invariants and read-model freshness hold after each individual step.

    Each test method is one distinct scenario; they share no state.
    """

    def _runner(self) -> _Runner:
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        return _Runner(self, ctx, procurement, lot)

    # --- single-operation baseline ---

    def test_s01_profit_partial_sell(self):
        r = self._runner()
        r.sell(5, _PROFIT_PRICE)
        r.check('s01:sell_profit')

    def test_s02_loss_partial_sell(self):
        r = self._runner()
        r.sell(5, _LOSS_PRICE)
        r.check('s02:sell_loss')

    def test_s03_at_cost_sell(self):
        r = self._runner()
        r.sell(5, _AT_COST)
        r.check('s03:at_cost')

    # --- return variants ---

    def test_s04_profit_then_restock_return(self):
        r = self._runner()
        s = r.sell(10, _PROFIT_PRICE)
        r.check('s04:sell')
        r.return_sale(s, 3, Return.Resolution.RESTOCK)
        r.check('s04:restock')

    def test_s05_profit_then_dispose_return(self):
        r = self._runner()
        s = r.sell(10, _PROFIT_PRICE)
        r.check('s05:sell')
        r.return_sale(s, 3, Return.Resolution.DISPOSE)
        r.check('s05:dispose')

    # --- settlement path ---

    def test_s06_profit_constructive_settle(self):
        r = self._runner()
        r.sell(10, _PROFIT_PRICE)
        r.check('s06:sell')
        r.settle()
        r.check('s06:settle')

    def test_s07_profit_settle_dividend(self):
        r = self._runner()
        r.sell(10, _PROFIT_PRICE)
        r.check('s07:sell')
        r.settle()
        r.check('s07:settle')
        r.dividend()
        r.check('s07:dividend')

    # --- over-withdrawal + debt repayment ---

    def test_s08_dividend_then_loss_then_repay(self):
        """Investor over-draws profit, subsequent loss creates negative position."""
        r = self._runner()
        r.sell(10, _PROFIT_PRICE)
        r.check('s08:sell_profit')
        r.settle()
        r.check('s08:settle')
        r.dividend()
        r.check('s08:dividend')
        r.sell(15, _LOSS_PRICE)
        r.check('s08:sell_loss')
        r.repay_debt()
        r.check('s08:repay')

    # --- multi-price sequences ---

    def test_s09_three_price_points_in_sequence(self):
        r = self._runner()
        r.sell(5, _PROFIT_PRICE)
        r.check('s09:profit')
        r.sell(5, _LOSS_PRICE)
        r.check('s09:loss')
        r.sell(5, _AT_COST)
        r.check('s09:at_cost')

    def test_s10_loss_first_then_profit(self):
        r = self._runner()
        r.sell(5, _LOSS_PRICE)
        r.check('s10:loss_first')
        r.sell(5, _PROFIT_PRICE)
        r.check('s10:profit_second')

    # --- writeoff ---

    def test_s11_sell_then_writeoff(self):
        r = self._runner()
        r.sell(5, _PROFIT_PRICE)
        r.check('s11:sell')
        r.writeoff(3)
        r.check('s11:writeoff')

    # --- full liquidation + final settlement ---

    def test_s12_full_sell_final_settlement(self):
        r = self._runner()
        r.sell(50, _PROFIT_PRICE)
        r.check('s12:full_sell')
        r.settle(_FINAL)
        r.check('s12:final')

    # --- mixed return types ---

    def test_s13_two_sales_two_return_types(self):
        r = self._runner()
        s1 = r.sell(10, _PROFIT_PRICE)
        r.check('s13:sell1')
        s2 = r.sell(10, _PROFIT_PRICE)
        r.check('s13:sell2')
        r.return_sale(s1, 2, Return.Resolution.RESTOCK)
        r.check('s13:restock')
        r.return_sale(s2, 2, Return.Resolution.DISPOSE)
        r.check('s13:dispose')

    # --- loss path with settle + repay ---

    def test_s14_loss_settle_repay(self):
        r = self._runner()
        r.sell(10, _LOSS_PRICE)
        r.check('s14:sell_loss')
        r.settle()
        r.check('s14:settle')
        r.repay_debt()
        r.check('s14:repay')

    # --- interleaved: return + writeoff + loss ---

    def test_s15_interleaved_return_writeoff_loss(self):
        r = self._runner()
        s = r.sell(15, _PROFIT_PRICE)
        r.check('s15:sell_profit')
        r.return_sale(s, 3, Return.Resolution.RESTOCK)
        r.check('s15:restock')
        r.writeoff(2)
        r.check('s15:writeoff')
        r.sell(10, _LOSS_PRICE)
        r.check('s15:sell_loss')
