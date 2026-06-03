"""
E14 — CapitalAdvance settlement service.

settle_capital_advance appends an append-only CapitalAdvanceSettlement,
moves real money (CASH) or routes the debtor's undistributed profit
(FROM_PROFIT), and recomputes status. Principal-only; never below zero;
idempotent on client_request_id.

GL/cash-movement assertions are added once the pool-funding helpers are
wired; this module pins the behavioral guards and status machine.
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.partnerships.advances import settle_capital_advance
from apps.partnerships.models import CapitalAdvance, CapitalAdvanceSettlement
from apps.partnerships.models import ProcurementReceiveBatch

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


def _make_advance(ctx, *, repayment_mode='LUMP'):
    """Path-2 receive where investor under-funds 66 vs agreed 70 → advance of 4
    (debtor=investor, creditor=operator)."""
    procurement = _build_funded(
        ctx, planned=(Decimal('70'), Decimal('30')),
        profit=(Decimal('0.35'), Decimal('0.65')),
        contributions=(Decimal('66'), Decimal('34')),
    )
    _receive(ctx, procurement, share_basis='AGREED',
             allocations=(Decimal('66'), Decimal('34')), repayment_mode=repayment_mode)
    batch = ProcurementReceiveBatch.objects.get(procurement=procurement)
    return CapitalAdvance.objects.get(batch=batch)


class CashSettlementTests(TestCase):
    def test_full_cash_settlement_marks_settled(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        settle_capital_advance(
            tenant_id=ctx['business'].id, advance_id=adv.id,
            amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.CASH,
        )
        adv.refresh_from_db()
        self.assertEqual(adv.outstanding_balance, Decimal('0.00'))
        self.assertEqual(adv.status, CapitalAdvance.Status.SETTLED)
        self.assertEqual(adv.settlements.count(), 1)

    def test_partial_then_full(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        settle_capital_advance(
            tenant_id=ctx['business'].id, advance_id=adv.id,
            amount=Decimal('1.50'), source=CapitalAdvanceSettlement.Source.CASH,
        )
        adv.refresh_from_db()
        self.assertEqual(adv.outstanding_balance, Decimal('2.50'))
        self.assertEqual(adv.status, CapitalAdvance.Status.PARTIAL)

        settle_capital_advance(
            tenant_id=ctx['business'].id, advance_id=adv.id,
            amount=Decimal('2.50'), source=CapitalAdvanceSettlement.Source.CASH,
        )
        adv.refresh_from_db()
        self.assertEqual(adv.outstanding_balance, Decimal('0.00'))
        self.assertEqual(adv.status, CapitalAdvance.Status.SETTLED)

    def test_overpayment_rejected(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        with self.assertRaises(ValueError):
            settle_capital_advance(
                tenant_id=ctx['business'].id, advance_id=adv.id,
                amount=Decimal('5.00'), source=CapitalAdvanceSettlement.Source.CASH,
            )

    def test_nonpositive_rejected(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        with self.assertRaises(ValueError):
            settle_capital_advance(
                tenant_id=ctx['business'].id, advance_id=adv.id,
                amount=Decimal('0'), source=CapitalAdvanceSettlement.Source.CASH,
            )

    def test_idempotent_on_client_request_id(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        rid = uuid.uuid4()
        for _ in range(2):
            settle_capital_advance(
                tenant_id=ctx['business'].id, advance_id=adv.id,
                amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.CASH,
                client_request_id=rid,
            )
        adv.refresh_from_db()
        self.assertEqual(adv.settlements.count(), 1)
        self.assertEqual(adv.outstanding_balance, Decimal('0.00'))


class CashSettlementGLTests(TestCase):
    def test_full_settlement_trues_equity_to_agreed_and_pool_net_flat(self):
        from apps.finance.services import get_account_balance
        from apps.partnerships.models import InvestmentAgreement
        from apps.finance.models import CashAccount, JournalEntry, JournalLine

        ctx = build_tenant()
        adv = _make_advance(ctx)
        biz = ctx['business'].id
        agreement = InvestmentAgreement.objects.get(pk=adv.agreement_id)
        pool = CashAccount.objects.get(pk=agreement.capital_account_id)
        pool_before = pool.balance

        # Pre-settlement equity reflects ACTUAL contributions (investor 66, operator 34).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('66.00'))
        self.assertEqual(get_account_balance(biz, '3000'), Decimal('34.00'))

        settle_capital_advance(
            tenant_id=biz, advance_id=adv.id,
            amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.CASH,
        )

        # Equity converges to the AGREED shares (investor 70, operator 30).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('70.00'))
        self.assertEqual(get_account_balance(biz, '3000'), Decimal('30.00'))
        # Pool cash nets flat (debtor in, creditor out).
        self.assertEqual(CashAccount.objects.get(pk=pool.id).balance, pool_before)
        # Every journal entry stays balanced.
        for entry in JournalEntry.objects.filter(tenant_id=biz):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(sum((l.debit for l in lines), Decimal('0')),
                             sum((l.credit for l in lines), Decimal('0')))


class FromProfitSettlementTests(TestCase):
    def test_from_profit_rejected_when_no_undistributed_profit(self):
        ctx = build_tenant()
        adv = _make_advance(ctx)
        # No sales yet → no accrued profit for the debtor → cannot settle from profit.
        with self.assertRaises(ValueError):
            settle_capital_advance(
                tenant_id=ctx['business'].id, advance_id=adv.id,
                amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
                from_account_id=ctx['cash_account'].id,
            )

    def test_from_profit_settles_via_debtor_profit_and_returns_creditor(self):
        from apps.finance.services import get_account_balance, record_owner_contribution
        from apps.finance.models import CashAccount
        from apps.partnerships.agreement_services import append_ledger_entry, get_or_create_ledger
        from apps.partnerships.models import PartnerLedgerEntry, ProcurementReceiveBatch

        ctx = build_tenant()
        biz = ctx['business'].id
        adv = _make_advance(ctx)
        procurement_id = ProcurementReceiveBatch.objects.get(pk=adv.batch_id).procurement_id

        # Debtor (investor) accrues profit; operating cash holds sales proceeds.
        ledger = get_or_create_ledger(procurement_id=procurement_id, partner_id=adv.debtor_id, tenant_id=biz)
        append_ledger_entry(ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=Decimal('10'), currency='UZS')
        record_owner_contribution(tenant_id=biz, amount=Decimal('500'), currency='UZS',
                                  to_account_id=ctx['cash_account'].id)
        cash_before = CashAccount.objects.get(pk=ctx['cash_account'].id).balance
        e_debtor_before = get_account_balance(biz, '3100')
        e_creditor_before = get_account_balance(biz, '3000')

        settle_capital_advance(
            tenant_id=biz, advance_id=adv.id, amount=Decimal('4.00'),
            source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
            from_account_id=ctx['cash_account'].id,
        )

        adv.refresh_from_db()
        self.assertEqual(adv.status, CapitalAdvance.Status.SETTLED)
        # Creditor returned from operating cash.
        self.assertEqual(CashAccount.objects.get(pk=ctx['cash_account'].id).balance,
                         cash_before - Decimal('4.00'))
        # Equity moves toward agreed: debtor capital +4, creditor capital -4.
        self.assertEqual(get_account_balance(biz, '3100'), e_debtor_before + Decimal('4.00'))
        self.assertEqual(get_account_balance(biz, '3000'), e_creditor_before - Decimal('4.00'))
        # Debtor's profit consumed.
        self.assertTrue(PartnerLedgerEntry.objects.filter(
            ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID).exists())
