"""
E14 — reversal & pool invariant.

Reversing a partnership receive batch is only reachable while the batch is fully
unsold (existing sales block it). In that state the whole funding event unwinds,
so the inter-partner advance is cancelled and any prior cash settlement refunded.
Advances never break the pool reconciliation invariant.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.services import get_account_balance
from apps.finance.models import CashAccount, Payment
from apps.partnerships.advances import settle_capital_advance
from apps.partnerships.models import (
    CapitalAdvance,
    CapitalAdvanceSettlement,
    InvestmentAgreement,
    ProcurementReceiveBatch,
)
from apps.partnerships.workspace import reverse_workspace_receive_batch

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


def _make_advance(ctx):
    procurement = _build_funded(
        ctx, planned=(Decimal('70'), Decimal('30')),
        profit=(Decimal('0.35'), Decimal('0.65')),
        contributions=(Decimal('66'), Decimal('34')),
    )
    _receive(ctx, procurement, share_basis='AGREED', allocations=(Decimal('66'), Decimal('34')))
    batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
    return procurement, batch, CapitalAdvance.objects.get(batch=batch)


class ReversalCancelsAdvanceTests(TestCase):
    def test_reverse_unsold_batch_cancels_advance(self):
        ctx = build_tenant()
        _, batch, adv = _make_advance(ctx)
        reverse_workspace_receive_batch(tenant_id=ctx['business'].id, batch_id=batch.id)
        adv.refresh_from_db()
        self.assertEqual(adv.status, CapitalAdvance.Status.CANCELLED)

    def test_reverse_after_cash_settlement_refunds_equity(self):
        ctx = build_tenant()
        biz = ctx['business'].id
        _, batch, adv = _make_advance(ctx)
        settle_capital_advance(
            tenant_id=biz, advance_id=adv.id,
            amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.CASH,
        )
        # After settlement equity was trued to agreed (70/30).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('70.00'))

        reverse_workspace_receive_batch(tenant_id=biz, batch_id=batch.id)
        adv.refresh_from_db()
        self.assertEqual(adv.status, CapitalAdvance.Status.CANCELLED)
        # Settlement refunded → equity back to the actual contributions (66/34).
        self.assertEqual(get_account_balance(biz, '3100'), Decimal('66.00'))
        self.assertEqual(get_account_balance(biz, '3000'), Decimal('34.00'))


class PoolInvariantTests(TestCase):
    def test_advance_does_not_break_pool_reconciliation(self):
        ctx = build_tenant()
        procurement, _, _ = _make_advance(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        pool = CashAccount.objects.get(pk=agreement.capital_account_id)

        contributed = sum((c.amount for c in agreement.contributions.all()), Decimal('0'))
        pool_out = sum(
            (p.amount for p in Payment.objects.filter(
                tenant_id=ctx['business'].id, source_type=Payment.SourceType.CAPITAL_POOL)),
            Decimal('0'),
        )
        # pool == Σ contributions − Σ pool payments, unaffected by the advance.
        self.assertEqual(pool.balance, contributed - pool_out)
