"""
E14/E17 — partner net-capital settlement (participant ↔ agreement pool).

`settle_partner_capital` settles a partner's net capital shortfall vs the pool:
CASH (the partner contributes the owed capital into the pool) or FROM_PROFIT
(their undistributed venture profit is reinvested as capital). The agreed-vs-
actual gap is read from the net position, not a CapitalAdvance entity (E17).
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.advances import partner_capital_positions, settle_partner_capital
from apps.partnerships.models import (
    AgreementContribution,
    CapitalSettlementSource,
    PartnerLedgerEntry,
    ProcurementVentureSettlement,
)
from apps.partnerships.venture import create_venture_settlement, procurement_venture_positions, venture_conservation
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session
from .test_e14_capital_advances import _build_funded, _receive


def _make_shortfall(ctx):
    """Path-2 receive where the investor under-funds 66 vs agreed 70 → the
    investor's net position owes the pool 4 (operator over-contributed 4)."""
    procurement = _build_funded(
        ctx, planned=(Decimal('70'), Decimal('30')),
        profit=(Decimal('0.35'), Decimal('0.65')),
        contributions=(Decimal('66'), Decimal('34')),
    )
    _receive(ctx, procurement, share_basis='AGREED',
             allocations=(Decimal('66'), Decimal('34')))
    return procurement


def _owed(ctx, agreement, partner_key='investor'):
    return partner_capital_positions(agreement)[ctx[partner_key].id]['owed']


class CashSettlementTests(TestCase):
    def test_full_cash_settlement_clears_owed(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        self.assertEqual(_owed(ctx, agreement), Decimal('4.00'))
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('4.00'),
            source=CapitalSettlementSource.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('0.00'))

    def test_partial_then_full(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('1.50'),
            source=CapitalSettlementSource.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('2.50'))
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('2.50'),
            source=CapitalSettlementSource.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('0.00'))

    def test_overpayment_rejected(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('5.00'),
                source=CapitalSettlementSource.CASH,
            )

    def test_nonpositive_rejected(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('0'),
                source=CapitalSettlementSource.CASH,
            )


class CashSettlementGLTests(TestCase):
    def test_full_settlement_trues_equity_to_agreed_and_lands_in_pool(self):
        from apps.finance.services import get_account_balance
        from apps.finance.models import CashAccount, JournalEntry, JournalLine

        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        biz = ctx['business'].id
        pool = CashAccount.objects.get(pk=agreement.capital_account_id)
        pool_before = pool.balance

        # Pre-settlement equity reflects ACTUAL contributions (investor 66, operator 34).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('66.00'))
        self.assertEqual(get_account_balance(biz, '3000'), Decimal('34.00'))

        settle_partner_capital(
            tenant_id=biz, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('4.00'),
            source=CapitalSettlementSource.CASH,
        )

        # The debtor's capital completes (66 -> 70); the creditor is untouched
        # (still 34 — recovers its over-contribution via a separate withdrawal).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('70.00'))
        self.assertEqual(get_account_balance(biz, '3000'), Decimal('34.00'))
        # The settlement cash lands in the pool (available capital).
        self.assertEqual(CashAccount.objects.get(pk=pool.id).balance, pool_before + Decimal('4.00'))
        # Every journal entry stays balanced.
        for entry in JournalEntry.objects.filter(tenant_id=biz):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(sum((line.debit for line in lines), Decimal('0')),
                             sum((line.credit for line in lines), Decimal('0')))


class FromProfitSettlementTests(TestCase):
    def test_from_profit_rejected_when_no_undistributed_profit(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        # No settled venture profit → undistributed profit is 0 → cannot settle
        # the shortfall from profit.
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('4.00'),
                source=CapitalSettlementSource.FROM_PROFIT,
                from_account_id=ctx['cash_account'].id,
            )


def _build_shortfall_with_profit(ctx):
    """Investor under-contributes (owes 4); sell all 10 units at 15 UZS each
    (profit = 50 UZS) then FINAL-settle → investor has owed=4 and
    provisional_profit_available_uzs > 4. Returns procurement."""
    procurement = _make_shortfall(ctx)   # 10 units × 10 UZS, investor 66/34
    session = open_session(ctx)
    create_sale(
        tenant_id=ctx['business'].id,
        pos_session_id=session.id,
        location_id=ctx['store'].id,
        sold_by_id=ctx['cashier'].id,
        customer_id=ctx['customer'].id,
        lines=[{'product_variant_id': ctx['variant'].id, 'quantity': 10, 'unit_price': Decimal('15')}],
        payments=[{
            'amount': Decimal('150'), 'currency': 'UZS', 'fx_rate': Decimal('1'),
            'method': SalePayment.Method.CASH, 'account_id': ctx['cash_account'].id,
        }],
    )
    create_venture_settlement(
        tenant_id=ctx['business'].id, procurement_id=procurement.id,
        settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
    )
    return procurement


class FromProfitHonestMechanismTests(TestCase):
    """E18 Phase 1 — characterising (failing before fix):
    FROM_PROFIT must write PROFIT_TO_CAPITAL + source=PROFIT_REINVEST; must
    never write DIVIDEND_PAID or a generic-source contribution. G4 oracle."""

    def test_honest_events_not_fake_dividend(self):
        ctx = build_tenant()
        procurement = _build_shortfall_with_profit(ctx)
        agreement = procurement.agreement

        # Pre-condition: investor owes 4, has > 4 UZS profit available.
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['investor'].id]['owed'], Decimal('4.00'))
        vpos = procurement_venture_positions(procurement=procurement)
        self.assertGreater(
            Decimal(str(vpos[ctx['investor'].id]['provisional_profit_available_uzs'])),
            Decimal('4.00'),
        )

        settle_partner_capital(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('4.00'),
            source=CapitalSettlementSource.FROM_PROFIT,
            from_account_id=ctx['cash_account'].id,
        )

        # 1. Honest ledger entry: PROFIT_TO_CAPITAL present, DIVIDEND_PAID absent.
        investor_entries = PartnerLedgerEntry.objects.filter(
            ledger__procurement=procurement,
            ledger__partner_id=ctx['investor'].id,
        )
        entry_types = set(investor_entries.values_list('entry_type', flat=True))
        self.assertIn('PROFIT_TO_CAPITAL', entry_types, 'PROFIT_TO_CAPITAL entry missing')
        self.assertNotIn('DIVIDEND_PAID', entry_types, 'Fake DIVIDEND_PAID entry must not exist')

        # 2. Honest contribution: source=PROFIT_REINVEST present, generic absent.
        contribs = AgreementContribution.objects.filter(
            agreement=agreement, partner_id=ctx['investor'].id,
        )
        sources = set(contribs.values_list('source', flat=True))
        self.assertIn('PROFIT_REINVEST', sources, 'PROFIT_REINVEST contribution missing')
        # Only the initial BUSINESS_RECORDED contribution (the original 66) should
        # exist with generic source — NOT a second generic one from this settlement.
        generic_count = contribs.filter(source='BUSINESS_RECORDED').count()
        self.assertEqual(generic_count, 1, 'Settlement must not add a generic BUSINESS_RECORDED contribution')

        # 3. Venture bucket: profit_to_capital_uzs grows, dividends_paid_uzs unchanged.
        vpos_after = procurement_venture_positions(procurement=procurement)
        iv_after = vpos_after[ctx['investor'].id]
        self.assertGreater(
            Decimal(str(iv_after['profit_to_capital_uzs'])),
            Decimal('0.00'),
            'profit_to_capital_uzs must grow',
        )
        self.assertEqual(
            Decimal(str(iv_after['dividends_paid_uzs'])),
            Decimal('0.00'),
            'dividends_paid_uzs must not grow on FROM_PROFIT path',
        )

        # 4. Net position cleared.
        pos_after = partner_capital_positions(agreement)
        self.assertEqual(pos_after[ctx['investor'].id]['owed'], Decimal('0.00'))

        # 5. GL balanced (numbers/accounts unchanged from E17 design).
        from apps.finance.models import JournalEntry, JournalLine
        for entry in JournalEntry.objects.filter(
            tenant_id=ctx['business'].id, operation_type='advance_settle',
        ):
            lines = list(JournalLine.objects.filter(journal_entry=entry))
            self.assertEqual(
                sum(ln.debit for ln in lines),
                sum(ln.credit for ln in lines),
            )

        # 6. Conservation residual = exact 0 on all functional UZS pockets.
        report = venture_conservation(procurement=procurement)
        for pocket in ('capital', 'proceeds', 'distribution'):
            self.assertEqual(
                report.residual(pocket, 'UZS'), Decimal('0.00'),
                msg=f'pocket {pocket}/UZS residual ≠ 0: {report.breakdown()}',
            )


class ProfitReinvestmentResidualTests(TestCase):
    """E18 Phase 1 / variant A — agreement_profit_reinvestment_residual checks that
    PLR.PROFIT_TO_CAPITAL sums == AgreementContribution.PROFIT_REINVEST sums.
    Two tests: positive (honest path → 0) and negative (orphan record → ≠0, close blocked)."""

    def test_positive_honest_path_residual_is_zero(self):
        from apps.partnerships.agreement_services import agreement_profit_reinvestment_residual
        ctx = build_tenant()
        procurement = _build_shortfall_with_profit(ctx)
        agreement = procurement.agreement

        settle_partner_capital(
            tenant_id=ctx['business'].id,
            agreement_id=agreement.id,
            partner_id=ctx['investor'].id,
            amount=Decimal('4.00'),
            source=CapitalSettlementSource.FROM_PROFIT,
            from_account_id=ctx['cash_account'].id,
        )

        residual = agreement_profit_reinvestment_residual(agreement)
        self.assertEqual(residual, Decimal('0.00'), 'Honest FROM_PROFIT path must reconcile to 0')

    def test_negative_orphan_contribution_detected_and_blocks_close(self):
        """Inject an orphan PROFIT_REINVEST contribution (no matching PLR entry) →
        residual ≠ 0 → agreement_close_blocking_reasons returns a reason."""
        from apps.partnerships.agreement_services import (
            agreement_close_blocking_reasons,
            agreement_profit_reinvestment_residual,
        )
        from apps.partnerships.models import AgreementActionSource, AgreementConfirmationStatus
        ctx = build_tenant()
        procurement = _build_shortfall_with_profit(ctx)
        agreement = procurement.agreement

        # Inject an orphan contribution with PROFIT_REINVEST but NO matching PLR entry.
        AgreementContribution.objects.create(
            tenant_id=ctx['business'].id,
            agreement=agreement,
            partner_id=ctx['investor'].id,
            amount=Decimal('4.00'),
            currency='UZS',
            fx_rate=Decimal('1'),
            date=agreement.opened_at,
            source=AgreementActionSource.PROFIT_REINVEST,
            confirmation_status=AgreementConfirmationStatus.CONFIRMED,
            notes='orphan — no PLR counterpart',
        )

        residual = agreement_profit_reinvestment_residual(agreement)
        self.assertNotEqual(residual, Decimal('0.00'), 'Orphan contribution must produce non-zero residual')

        # The close gate must surface a blocking reason.
        reasons = agreement_close_blocking_reasons(agreement=agreement)
        self.assertTrue(
            any('реинвестирование' in r.lower() or 'reinvest' in r.lower() for r in reasons),
            f'Close gate must block on profit_reinvestment residual; got: {reasons}',
        )
