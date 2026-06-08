"""
E14/E17 — reversal & pool invariant.

Reversing a partnership receive batch is only reachable while the batch is fully
unsold (existing sales block it). The agreed-vs-actual gap is no longer reified
as a CapitalAdvance, so there is nothing to cancel: reversing the batch drops its
deployment, the net capital positions recompute, and the pool reconciliation
invariant holds throughout.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, Payment
from apps.partnerships.advances import partner_capital_positions
from apps.partnerships.models import (
    CapitalAdvance,
    InvestmentAgreement,
    ProcurementReceiveBatch,
)
from apps.partnerships.workspace import reverse_workspace_receive_batch

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


def _make_shortfall(ctx):
    procurement = _build_funded(
        ctx, planned=(Decimal('70'), Decimal('30')),
        profit=(Decimal('0.35'), Decimal('0.65')),
        contributions=(Decimal('66'), Decimal('34')),
    )
    _receive(ctx, procurement, share_basis='AGREED', allocations=(Decimal('66'), Decimal('34')))
    batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
    return procurement, batch


class ReversalTests(TestCase):
    def test_reverse_unsold_batch_drops_deployment_and_positions(self):
        ctx = build_tenant()
        procurement, batch = _make_shortfall(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)

        # Before reversal: investor deployed 70, owes the pool 4.
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['investor'].id]['deployed'], Decimal('70.00'))
        self.assertEqual(pos[ctx['investor'].id]['owed'], Decimal('4.00'))

        reverse_workspace_receive_batch(tenant_id=ctx['business'].id, batch_id=batch.id)

        # No advance ever existed, so nothing to cancel.
        self.assertEqual(CapitalAdvance.objects.filter(batch=batch).count(), 0)
        # Deployment is gone → no outstanding shortfall.
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['investor'].id]['deployed'], Decimal('0.00'))
        self.assertEqual(pos[ctx['operator'].id]['deployed'], Decimal('0.00'))
        self.assertEqual(pos[ctx['investor'].id]['owed'], Decimal('0.00'))
        self.assertEqual(pos[ctx['operator'].id]['owed'], Decimal('0.00'))


class PoolInvariantTests(TestCase):
    def test_shortfall_does_not_break_pool_reconciliation(self):
        ctx = build_tenant()
        procurement, _ = _make_shortfall(ctx)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        pool = CashAccount.objects.get(pk=agreement.capital_account_id)

        contributed = sum((c.amount for c in agreement.contributions.all()), Decimal('0'))
        pool_out = sum(
            (p.amount for p in Payment.objects.filter(
                tenant_id=ctx['business'].id, source_type=Payment.SourceType.CAPITAL_POOL)),
            Decimal('0'),
        )
        # pool == Σ contributions − Σ pool payments, unaffected by the gap.
        self.assertEqual(pool.balance, contributed - pool_out)
