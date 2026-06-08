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
from apps.partnerships.models import CapitalAdvanceSettlement

from ._helpers import build_tenant
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
            source=CapitalAdvanceSettlement.Source.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('0.00'))

    def test_partial_then_full(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('1.50'),
            source=CapitalAdvanceSettlement.Source.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('2.50'))
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('2.50'),
            source=CapitalAdvanceSettlement.Source.CASH,
        )
        self.assertEqual(_owed(ctx, agreement), Decimal('0.00'))

    def test_overpayment_rejected(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('5.00'),
                source=CapitalAdvanceSettlement.Source.CASH,
            )

    def test_nonpositive_rejected(self):
        ctx = build_tenant()
        agreement = _make_shortfall(ctx).agreement
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('0'),
                source=CapitalAdvanceSettlement.Source.CASH,
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
            source=CapitalAdvanceSettlement.Source.CASH,
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
                source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
                from_account_id=ctx['cash_account'].id,
            )
