"""
E15 Phase 3 — auto-settle FROM_PROFIT advances from accrued profit (the toggle).

When an advance is marked repayment_mode=FROM_PROFIT, the partner's accrued
profit closes the debt first (oldest first), the remainder stays theirs.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.services import record_owner_contribution
from apps.partnerships.advances import auto_settle_advances_from_profit
from apps.partnerships.agreement_services import append_ledger_entry, get_or_create_ledger
from apps.partnerships.models import (
    CapitalAdvance,
    PartnerLedgerEntry,
    ProcurementReceiveBatch,
)

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


class AutoSettleFromProfitTests(TestCase):
    def test_accrued_profit_closes_from_profit_advance_first(self):
        ctx = build_tenant()
        biz = ctx['business'].id
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, share_basis='AGREED',
                 allocations=(Decimal('66'), Decimal('34')), repayment_mode='FROM_PROFIT')
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
        adv = CapitalAdvance.objects.get(batch=batch)
        self.assertEqual(adv.repayment_mode, CapitalAdvance.RepaymentMode.FROM_PROFIT)
        self.assertEqual(adv.outstanding_balance, Decimal('4.00'))

        # Debtor (investor) accrues 10 of profit; operating cash funded.
        ledger = get_or_create_ledger(procurement_id=procurement.id, partner_id=adv.debtor_id, tenant_id=biz)
        append_ledger_entry(ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=Decimal('10'), currency='UZS')
        record_owner_contribution(tenant_id=biz, amount=Decimal('500'), currency='UZS',
                                  to_account_id=ctx['cash_account'].id)

        settled = auto_settle_advances_from_profit(
            tenant_id=biz, agreement_id=procurement.agreement_id, partner_id=adv.debtor_id,
            from_account_id=ctx['cash_account'].id)

        self.assertEqual(settled, Decimal('4.00'))
        adv.refresh_from_db()
        self.assertEqual(adv.status, CapitalAdvance.Status.SETTLED)
        self.assertEqual(adv.outstanding_balance, Decimal('0.00'))

    def test_partial_profit_partially_settles(self):
        ctx = build_tenant()
        biz = ctx['business'].id
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, share_basis='AGREED',
                 allocations=(Decimal('66'), Decimal('34')), repayment_mode='FROM_PROFIT')
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
        adv = CapitalAdvance.objects.get(batch=batch)

        ledger = get_or_create_ledger(procurement_id=procurement.id, partner_id=adv.debtor_id, tenant_id=biz)
        append_ledger_entry(ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=Decimal('1.50'), currency='UZS')
        record_owner_contribution(tenant_id=biz, amount=Decimal('500'), currency='UZS',
                                  to_account_id=ctx['cash_account'].id)

        settled = auto_settle_advances_from_profit(
            tenant_id=biz, agreement_id=procurement.agreement_id, partner_id=adv.debtor_id,
            from_account_id=ctx['cash_account'].id)

        self.assertEqual(settled, Decimal('1.50'))
        adv.refresh_from_db()
        self.assertEqual(adv.status, CapitalAdvance.Status.PARTIAL)
        self.assertEqual(adv.outstanding_balance, Decimal('2.50'))
