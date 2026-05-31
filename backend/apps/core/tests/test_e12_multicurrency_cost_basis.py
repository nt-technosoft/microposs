"""
E12 — Multi-currency capital pool, FIFO cost-basis (Phase 1/2 foundation).

Shares stay in the base (accounting) currency; the pool may hold other
currencies via real conversion. Each conversion is a FIFO lot carrying its
base-currency cost. Spending the held currency consumes lots oldest-first; the
base-currency cost (conversion rate, NOT receive-day market rate) is returned.

Invariants verified with real conversions (not hand-mocked rows):
  - Σ lot.amount_remaining (a currency) == that currency pool's CashAccount.balance
  - Σ lot.base_cost_remaining == base currency physically moved into conversions
  - FIFO spend draws oldest lots first, at their own rates
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount
from apps.partnerships.models import (
    CurrencyConversionLot,
    InvestmentAgreement,
    Procurement,
)
from apps.partnerships.multicurrency import (
    convert_agreement_pool,
    pool_currency_balance,
    spend_pool_cost_basis,
)
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


def _usd_agreement_with_base_capital(ctx, base_usd):
    """USD agreement; investor contributes `base_usd` into the base (USD) pool."""
    procurement = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='CREATE_INVESTMENT_AGREEMENT',
        payload={'payload': {
            'mudaraba_ratio': Decimal('0.5'),
            'planned_budget': Decimal(str(base_usd)),
            'currency': 'USD',
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': Decimal('136'), 'profit_share': Decimal('0.34')},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': Decimal('64'), 'profit_share': Decimal('0.66')},
            ],
        }},
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=procurement,
        action='RECORD_CAPITAL_CONTRIBUTION',
        payload={'payload': {
            'partner_id': ctx['investor'].id,
            'amount': Decimal(str(base_usd)),
            'currency': 'USD',
            'fx_rate': Decimal('12000'),
        }},
    )
    return InvestmentAgreement.objects.get(pk=procurement.agreement_id)


class CurrencyConversionTests(TestCase):
    def test_convert_moves_real_cash_and_records_cost_basis_lot(self):
        ctx = build_tenant()
        ag = _usd_agreement_with_base_capital(ctx, base_usd='1000')

        convert_agreement_pool(
            tenant_id=ctx['business'].id, agreement_id=ag.id,
            to_currency='UZS', from_amount=Decimal('800'), rate=Decimal('12000'),
        )

        # Base USD pool dropped by 800; a UZS sub-pool appeared with 9.6M.
        ag.refresh_from_db()
        base_pool = CashAccount.objects.get(pk=ag.capital_account_id)
        self.assertEqual(base_pool.balance, Decimal('200.00'))
        uzs_pool = CashAccount.objects.get(
            tenant_id=ctx['business'].id, kind=CashAccount.Kind.AGREEMENT_CAPITAL, currency='UZS',
        )
        self.assertEqual(uzs_pool.balance, Decimal('9600000.00'))

        # Lot carries the base-currency cost ($800).
        lot = CurrencyConversionLot.objects.get(agreement=ag, currency='UZS')
        self.assertEqual(lot.amount_remaining, Decimal('9600000.000000'))
        self.assertEqual(lot.base_cost_remaining, Decimal('800.000000'))
        # Reconciliation: held UZS across lots == physical UZS pool balance.
        self.assertEqual(
            pool_currency_balance(tenant_id=ctx['business'].id, agreement_id=ag.id, currency='UZS'),
            uzs_pool.balance,
        )


class FifoCostBasisTests(TestCase):
    def _three_lots(self, ctx):
        """$1000 @12000 + $1000 @12500 + $1000 @13000 → 37.5M UZS, base $3000."""
        ag = _usd_agreement_with_base_capital(ctx, base_usd='3000')
        for rate in ('12000', '12500', '13000'):
            convert_agreement_pool(
                tenant_id=ctx['business'].id, agreement_id=ag.id,
                to_currency='UZS', from_amount=Decimal('1000'), rate=Decimal(rate),
            )
        return ag

    def test_fifo_spend_spans_lots_at_their_own_rates(self):
        ctx = build_tenant()
        ag = self._three_lots(ctx)

        # Spend 15M UZS: 12M from L1@12000 ($1000) + 3M from L2@12500 ($240) = $1240.
        base_cost = spend_pool_cost_basis(
            tenant_id=ctx['business'].id, agreement_id=ag.id,
            currency='UZS', amount=Decimal('15000000'),
        )
        self.assertEqual(base_cost, Decimal('1240'))

        lots = list(CurrencyConversionLot.objects.filter(agreement=ag).order_by('converted_at', 'id'))
        self.assertEqual(lots[0].amount_remaining, Decimal('0.000000'))            # L1 drained
        self.assertEqual(lots[1].amount_remaining, Decimal('9500000.000000'))      # L2 partial
        self.assertEqual(lots[1].base_cost_remaining, Decimal('760.000000'))       # $1000 - $240
        self.assertEqual(lots[2].amount_remaining, Decimal('13000000.000000'))     # L3 untouched

        # Cost basis conserved: spent + remaining == original $3000.
        remaining_base = sum(
            (Decimal(str(l.base_cost_remaining)) for l in lots), Decimal('0'),
        )
        self.assertEqual(base_cost + remaining_base, Decimal('3000'))

    def test_second_spend_continues_fifo_from_where_first_stopped(self):
        ctx = build_tenant()
        ag = self._three_lots(ctx)
        spend_pool_cost_basis(tenant_id=ctx['business'].id, agreement_id=ag.id,
                              currency='UZS', amount=Decimal('15000000'))
        # Next 10M: 9.5M from L2@12500 ($760) + 0.5M from L3@13000 ($38.46…).
        base_cost = spend_pool_cost_basis(tenant_id=ctx['business'].id, agreement_id=ag.id,
                                          currency='UZS', amount=Decimal('10000000'))
        expected = Decimal('760') + (Decimal('500000') * Decimal('1000') / Decimal('13000000'))
        self.assertEqual(base_cost, expected)

    def test_insufficient_currency_raises(self):
        ctx = build_tenant()
        ag = self._three_lots(ctx)
        with self.assertRaises(ValueError):
            spend_pool_cost_basis(tenant_id=ctx['business'].id, agreement_id=ag.id,
                                  currency='UZS', amount=Decimal('40000000'))

    def test_cost_basis_not_prematurely_rounded(self):
        """Base cost keeps full precision (no 0.01 quantization in the math)."""
        ctx = build_tenant()
        ag = self._three_lots(ctx)
        # Spend an amount that yields a non-2dp base cost.
        base_cost = spend_pool_cost_basis(tenant_id=ctx['business'].id, agreement_id=ag.id,
                                          currency='UZS', amount=Decimal('12345678'))
        # 12M @12000 = $1000; remainder 345678 UZS @12500 = 345678/12500 = 27.65424
        expected = Decimal('1000') + (Decimal('345678') * Decimal('1000') / Decimal('12500000'))
        self.assertEqual(base_cost, expected)
        self.assertNotEqual(base_cost, base_cost.quantize(Decimal('0.01')))
