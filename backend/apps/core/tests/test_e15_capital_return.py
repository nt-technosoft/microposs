"""
E15 Phase 1 — capital return is physical.

Returning capital draws real cash OUT of the agreement pool and books the
equity reduction (DR partner equity / CR 1300). Previously this was ledger-only
and the pool balance silently diverged from the derived `balances`.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, JournalEntry, JournalLine
from apps.finance.services import get_account_balance
from apps.partnerships.models import InvestmentAgreement
from apps.partnerships.workspace import dispatch_workspace_action
from apps.partnerships.workspace_support import add_agreement_withdrawal

from ._helpers import build_tenant
from .test_e11_capital_pool_reconciliation import _build_partnership_agreement, _pool


def _fund(ctx, procurement, investor_amt, operator_amt):
    for partner_id, amount in (
        (ctx['investor'].id, investor_amt),
        (ctx['operator'].id, operator_amt),
    ):
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {'partner_id': partner_id, 'amount': amount,
                                 'currency': 'UZS', 'fx_rate': Decimal('1')}},
        )


class CapitalReturnPhysicalTests(TestCase):
    def test_withdrawal_draws_cash_from_pool_and_reduces_equity(self):
        ctx = build_tenant()
        biz = ctx['business'].id
        procurement = _build_partnership_agreement(ctx, currency='UZS')
        _fund(ctx, procurement, Decimal('140'), Decimal('60'))

        pool = _pool(procurement)
        self.assertEqual(pool.balance, Decimal('200.00'))
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('140.00'))

        add_agreement_withdrawal(
            tenant_id=biz, agreement_id=procurement.agreement_id,
            partner_id=ctx['investor'].id, amount=Decimal('40'), currency='UZS',
        )

        # Pool physically dropped; investor equity reduced.
        self.assertEqual(CashAccount.objects.get(pk=pool.id).balance, Decimal('160.00'))
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('100.00'))
        # All journals balanced.
        for entry in JournalEntry.objects.filter(tenant_id=biz):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(sum((l.debit for l in lines), Decimal('0')),
                             sum((l.credit for l in lines), Decimal('0')))

    def test_cannot_withdraw_more_than_available(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx, currency='UZS')
        _fund(ctx, procurement, Decimal('140'), Decimal('60'))
        with self.assertRaises(ValueError):
            add_agreement_withdrawal(
                tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id,
                partner_id=ctx['investor'].id, amount=Decimal('500'), currency='UZS',
            )

    def test_leftover_capital_return_reconciles_pool(self):
        """Founder's scenario: contribute 200, deploy part, return the leftover —
        pool stays reconciled, nothing changes by magic."""
        ctx = build_tenant()
        biz = ctx['business'].id
        procurement = _build_partnership_agreement(ctx, currency='UZS')
        _fund(ctx, procurement, Decimal('140'), Decimal('60'))
        pool = _pool(procurement)

        # Return the full leftover to both partners.
        add_agreement_withdrawal(
            tenant_id=biz, agreement_id=procurement.agreement_id,
            partner_id=ctx['investor'].id, amount=Decimal('140'), currency='UZS')
        add_agreement_withdrawal(
            tenant_id=biz, agreement_id=procurement.agreement_id,
            partner_id=ctx['operator'].id, amount=Decimal('60'), currency='UZS')

        self.assertEqual(CashAccount.objects.get(pk=pool.id).balance, Decimal('0.00'))
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        # Derived balances and physical pool agree (both zero) — no drift.
        total_available = sum(
            (Decimal(v) for v in agreement.balances.values()), Decimal('0'))
        self.assertEqual(total_available, Decimal('0.00'))
