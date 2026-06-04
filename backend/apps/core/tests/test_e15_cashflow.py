"""
E15 Phase 6 — partner outflows surface in the cash-flow summary.

Dividends (operating cash) + capital returns (pool) feed
CashFlowSummary.cash_out_investor_payments, no longer stubbed to zero.
Advances never appear as profit (they are obligations, not P&L).
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.analytics.tasks import aggregate_daily_pnl
from apps.finance.models import CashFlowSummary
from apps.finance.services import record_owner_contribution
from apps.partnerships.agreement_services import (
    append_ledger_entry,
    get_or_create_ledger,
    pay_dividend,
)
from apps.partnerships.models import PartnerLedgerEntry
from apps.partnerships.workspace import dispatch_workspace_action
from apps.partnerships.workspace_support import add_agreement_withdrawal

from ._helpers import build_tenant
from .test_e11_capital_pool_reconciliation import _build_partnership_agreement


class CashFlowInvestorOutflowTests(TestCase):
    def test_dividend_and_capital_return_feed_investor_outflow(self):
        ctx = build_tenant()
        biz = ctx['business'].id
        procurement = _build_partnership_agreement(ctx, currency='UZS')

        # Fund the pool (so a capital return has cash to draw).
        for partner_id, amount in ((ctx['investor'].id, Decimal('140')), (ctx['operator'].id, Decimal('60'))):
            dispatch_workspace_action(
                tenant_id=biz, procurement=procurement, action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {'partner_id': partner_id, 'amount': amount,
                                     'currency': 'UZS', 'fx_rate': Decimal('1')}},
            )

        # Accrue profit for the investor + fund operating cash for the dividend.
        ledger = get_or_create_ledger(procurement_id=procurement.id, partner_id=ctx['investor'].id, tenant_id=biz)
        append_ledger_entry(ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.PROFIT_ACCRUED,
                            amount=Decimal('50'), currency='UZS')
        record_owner_contribution(tenant_id=biz, amount=Decimal('500'), currency='UZS',
                                  to_account_id=ctx['cash_account'].id)

        # Dividend (operating cash) 50 + capital return (pool) 40 = 90 out to partners.
        pay_dividend(partner_id=ctx['investor'].id, procurement_id=procurement.id,
                     amount=Decimal('50'), currency='UZS',
                     from_account_id=ctx['cash_account'].id, tenant_id=biz)
        add_agreement_withdrawal(tenant_id=biz, agreement_id=procurement.agreement_id,
                                 partner_id=ctx['investor'].id, amount=Decimal('40'), currency='UZS')

        aggregate_daily_pnl(biz)

        cfs = CashFlowSummary.objects.get(tenant_id=biz, date=timezone.localdate())
        self.assertEqual(cfs.cash_out_investor_payments, Decimal('90.00'))
