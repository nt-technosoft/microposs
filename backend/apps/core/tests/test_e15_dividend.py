"""
E15 Phase 2 — profit distribution (dividend) is physical with correct GL.

A dividend must move real cash from a source account (sales proceeds in
operating cash) and book DR 3200 (retained earnings) / CR cash — not the old
ledger-only / counterpart-2100 placeholder. Bounded by the partner's pending
profit.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, JournalEntry, JournalLine
from apps.finance.services import get_account_balance, record_owner_contribution
from apps.partnerships.agreement_services import (
    append_ledger_entry,
    get_or_create_ledger,
    pay_dividend,
)
from apps.partnerships.models import PartnerLedgerEntry

from ._helpers import build_tenant
from .test_e11_capital_pool_reconciliation import _build_partnership_agreement


def _accrue_profit(ctx, procurement, partner_id, amount):
    ledger = get_or_create_ledger(
        procurement_id=procurement.id, partner_id=partner_id, tenant_id=ctx['business'].id)
    append_ledger_entry(
        ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
        amount=amount, currency='UZS')


class DividendPhysicalTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.biz = self.ctx['business'].id
        self.procurement = _build_partnership_agreement(self.ctx, currency='UZS')
        # Sales proceeds live in operating cash.
        record_owner_contribution(
            tenant_id=self.biz, amount=Decimal('500'), currency='UZS',
            to_account_id=self.ctx['cash_account'].id)
        _accrue_profit(self.ctx, self.procurement, self.ctx['investor'].id, Decimal('100'))

    def test_dividend_moves_cash_and_books_retained_earnings(self):
        cash_before = CashAccount.objects.get(pk=self.ctx['cash_account'].id).balance
        re_before = get_account_balance(self.biz, '3200')

        pay_dividend(
            partner_id=self.ctx['investor'].id, procurement_id=self.procurement.id,
            amount=Decimal('100'), currency='UZS',
            from_account_id=self.ctx['cash_account'].id, tenant_id=self.biz)

        self.assertEqual(
            CashAccount.objects.get(pk=self.ctx['cash_account'].id).balance,
            cash_before - Decimal('100.00'))
        # Retained earnings debited by the distribution.
        self.assertEqual(get_account_balance(self.biz, '3200'), re_before - Decimal('100.00'))
        self.assertTrue(PartnerLedgerEntry.objects.filter(
            ledger__procurement_id=self.procurement.id,
            ledger__partner_id=self.ctx['investor'].id,
            entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID).exists())
        for entry in JournalEntry.objects.filter(tenant_id=self.biz):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(sum((l.debit for l in lines), Decimal('0')),
                             sum((l.credit for l in lines), Decimal('0')))

    def test_dividend_cannot_exceed_pending_profit(self):
        with self.assertRaises(ValueError):
            pay_dividend(
                partner_id=self.ctx['investor'].id, procurement_id=self.procurement.id,
                amount=Decimal('150'), currency='UZS',
                from_account_id=self.ctx['cash_account'].id, tenant_id=self.biz)

    def test_dividend_requires_source_account(self):
        with self.assertRaises(ValueError):
            pay_dividend(
                partner_id=self.ctx['investor'].id, procurement_id=self.procurement.id,
                amount=Decimal('50'), currency='UZS',
                from_account_id=None, tenant_id=self.biz)
