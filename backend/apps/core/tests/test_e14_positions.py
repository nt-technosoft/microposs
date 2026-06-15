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
    settle_partner_capital,
)
from apps.partnerships.models import (
    CapitalAdvanceSettlement,
    InvestmentAgreement,
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
        # Investor: deployed 70, paid-in 66 → owes the pool 4.
        self.assertEqual(inv['deployed'], Decimal('70.00'))
        self.assertEqual(inv['paid_in'], Decimal('66.00'))
        self.assertEqual(inv['net'], Decimal('4.00'))
        self.assertEqual(inv['owed'], Decimal('4.00'))
        # Operator over-contributed (net -4); but the surplus is tied up in
        # inventory until the investor tops up, so withdrawable is 0 for now.
        self.assertEqual(op['net'], Decimal('-4.00'))
        self.assertEqual(op['withdrawable'], Decimal('0.00'))

class UnifiedSettleEqualsTopUpTests(TestCase):
    def test_plain_contribution_reduces_debt_and_frees_creditor(self):
        """Погасить == Пополнить: a plain contribution by the debtor lowers their
        net automatically, and the creditor's surplus becomes withdrawable once
        the pool has free cash."""
        from apps.partnerships.workspace import dispatch_workspace_action

        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)

        # Before: investor owes 4; operator overpaid but withdrawable 0 (tied up).
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['investor'].id]['owed'], Decimal('4.00'))
        self.assertEqual(pos[ctx['operator'].id]['withdrawable'], Decimal('0.00'))

        # A plain contribution (top-up), NOT the "Погасить" path.
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {'partner_id': ctx['investor'].id, 'amount': Decimal('4'),
                                 'currency': 'UZS', 'fx_rate': Decimal('1')}},
        )

        pos = partner_capital_positions(agreement)
        # Debt cleared by the plain top-up.
        self.assertEqual(pos[ctx['investor'].id]['owed'], Decimal('0.00'))
        # Pool now has 4 free → operator can withdraw their surplus.
        self.assertEqual(pos[ctx['operator'].id]['withdrawable'], Decimal('4.00'))


class PoolWithdrawalGateTests(TestCase):
    """E17 S4 regression: the pool-withdrawal path must validate availability
    against the canonical pool-read (positions.withdrawable), not the legacy
    _agreement_partner_available. Earlier the suite only *read* the position and
    never *called* the withdrawal, so the gate mismatch went unnoticed: a
    creditor whose surplus is genuinely withdrawable was rejected."""

    def _funded_with_free_pool(self, ctx):
        from apps.partnerships.workspace import dispatch_workspace_action

        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        # Debtor tops up → pool gains 4 free cash, operator's surplus is now
        # withdrawable.
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {'partner_id': ctx['investor'].id, 'amount': Decimal('4'),
                                 'currency': 'UZS', 'fx_rate': Decimal('1')}},
        )
        return agreement

    def test_creditor_can_withdraw_surplus_via_pool(self):
        from apps.partnerships.workspace_support import add_agreement_withdrawal

        ctx = build_tenant()
        agreement = self._funded_with_free_pool(ctx)
        pos = partner_capital_positions(agreement)
        withdrawable = pos[ctx['operator'].id]['withdrawable']
        self.assertEqual(withdrawable, Decimal('4.00'))

        # Pool path: procurement_id=None, from_account_id=None. The gate must
        # accept the full withdrawable amount.
        withdrawal = add_agreement_withdrawal(
            tenant_id=ctx['business'].id, agreement_id=agreement.id,
            partner_id=ctx['operator'].id, amount=withdrawable, currency='UZS',
        )
        self.assertEqual(withdrawal.amount, Decimal('4.00'))
        # After the withdrawal the surplus is consumed.
        pos = partner_capital_positions(agreement)
        self.assertEqual(pos[ctx['operator'].id]['withdrawable'], Decimal('0.00'))

    def test_over_withdrawable_pool_return_rejected(self):
        from apps.partnerships.workspace_support import add_agreement_withdrawal

        ctx = build_tenant()
        agreement = self._funded_with_free_pool(ctx)
        with self.assertRaises(ValueError):
            add_agreement_withdrawal(
                tenant_id=ctx['business'].id, agreement_id=agreement.id,
                partner_id=ctx['operator'].id, amount=Decimal('5.00'), currency='UZS',
            )


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
