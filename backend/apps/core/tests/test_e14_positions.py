"""
E14 (participant↔pool) — net capital positions derived from snapshots.

partner_capital_positions(agreement) nets each partner's agreed-vs-actual
capital across all receives, minus settlements. net > 0 → owes the pool;
net < 0 → pool owes them (over-contributed, withdrawable).
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.advances import (
    partner_capital_positions,
    settle_capital_advance,
    settle_partner_capital,
)
from apps.partnerships.models import (
    CapitalAdvance,
    CapitalAdvanceSettlement,
    InvestmentAgreement,
    ProcurementReceiveBatch,
)

from ._helpers import build_tenant
from .test_e14_capital_advances import _build_funded, _receive


class PartnerCapitalPositionsTests(TestCase):
    def test_net_positions_from_snapshot(self):
        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)

        pos = partner_capital_positions(agreement)
        inv = pos[ctx['investor'].id]
        op = pos[ctx['operator'].id]
        # Investor: agreed 70, actual 66 → owes the pool 4.
        self.assertEqual(inv['agreed'], Decimal('70.00'))
        self.assertEqual(inv['actual'], Decimal('66.00'))
        self.assertEqual(inv['net'], Decimal('4.00'))
        # Operator: agreed 30, actual 34 → pool owes them 4 (over-contributed).
        self.assertEqual(op['net'], Decimal('-4.00'))

    def test_settlement_reduces_net(self):
        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement, is_reversal=False)
        adv = CapitalAdvance.objects.get(batch=batch)

        settle_capital_advance(
            tenant_id=ctx['business'].id, advance_id=adv.id,
            amount=Decimal('4.00'), source=CapitalAdvanceSettlement.Source.CASH)

        pos = partner_capital_positions(agreement)
        # Investor's debt is now fully settled → net 0.
        self.assertEqual(pos[ctx['investor'].id]['net'], Decimal('0.00'))


class SettlePartnerCapitalTests(TestCase):
    def _setup(self, ctx):
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        return InvestmentAgreement.objects.get(pk=procurement.agreement_id)

    def test_cash_settlement_clears_net(self):
        ctx = build_tenant()
        agreement = self._setup(ctx)
        settle_partner_capital(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['investor'].id, amount=Decimal('4.00'),
            source=CapitalAdvanceSettlement.Source.CASH)
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['investor'].id]['net'], Decimal('0.00'))

    def test_overpayment_rejected(self):
        ctx = build_tenant()
        agreement = self._setup(ctx)
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['investor'].id, amount=Decimal('99.00'),
                source=CapitalAdvanceSettlement.Source.CASH)

    def test_creditor_has_no_debt(self):
        ctx = build_tenant()
        agreement = self._setup(ctx)
        # Operator over-contributed (net < 0) → cannot "settle" (nothing owed).
        with self.assertRaises(ValueError):
            settle_partner_capital(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['operator'].id, amount=Decimal('1.00'),
                source=CapitalAdvanceSettlement.Source.CASH)
