"""
E14 — Contributed-vs-agreed capital reconciliation (inter-partner advances).

Path 2 (share_basis='AGREED') pins the agreed capital/profit shares on the
immutable batch snapshot even when actual contributions differ, and records the
per-partner funding gap as a CapitalAdvance (debtor owes, creditor covered).
Path 1 (share_basis='FACTUAL', the backward-compatible default) is unchanged:
shares follow actual cash, no advances.
"""

from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import (
    CapitalAdvance,
    InvestmentAgreement,
    Procurement,
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
)
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


def _build_funded(ctx, *, planned, profit, contributions, required_units=10, unit_price=10,
                  reconciliation_mode='AGREED', repayment_mode='LUMP'):
    """Agreement (planned capital + profit shares) funded by `contributions`,
    items worth required_units*unit_price, capital allocated to the procurement.
    The reconciliation path is fixed on the agreement at creation (E14)."""
    procurement = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
        supplier_id=ctx['supplier'].id,
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=procurement,
        action='CREATE_INVESTMENT_AGREEMENT',
        payload={'payload': {
            'mudaraba_ratio': Decimal('0.5'),
            'planned_budget': Decimal(str(required_units * unit_price)),
            'currency': 'UZS',
            'reconciliation_mode': reconciliation_mode,
            'default_advance_repayment_mode': repayment_mode,
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': planned[0], 'profit_share': profit[0]},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': planned[1], 'profit_share': profit[1]},
            ],
        }},
    )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=procurement, action='UPDATE_ITEMS',
        payload={'payload': {'items': [{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal(str(required_units)),
            'unit_purchase_price': Decimal(str(unit_price)),
            'currency': 'UZS', 'fx_rate': Decimal('1'),
        }]}},
    )
    for partner_id, amount in (
        (ctx['investor'].id, contributions[0]),
        (ctx['operator'].id, contributions[1]),
    ):
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {'partner_id': partner_id, 'amount': amount,
                                 'currency': 'UZS', 'fx_rate': Decimal('1')}},
        )
    procurement = dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=procurement, action='ALLOCATE_CAPITAL',
        payload={'payload': {'allocations': [
            {'partner_id': ctx['investor'].id, 'amount': contributions[0], 'currency': 'UZS'},
            {'partner_id': ctx['operator'].id, 'amount': contributions[1], 'currency': 'UZS'},
        ]}},
    )
    return procurement


def _receive(ctx, procurement, *, share_basis='AGREED', allocations, repayment_mode='LUMP'):
    # E14: share_basis/repayment_mode now come from the agreement (set at creation),
    # not the receive payload. These kwargs are kept for caller compatibility but the
    # receive no longer chooses the path — it reflects the agreement's reconciliation_mode.
    item = procurement.items.get()
    return dispatch_workspace_action(
        tenant_id=ctx['business'].id, procurement=procurement, action='RECEIVE_BATCH',
        payload={'payload': {
            'warehouse_id': ctx['storage'].id,
            'item_ids': [item.id],
            'capital_allocations': [
                {'partner_id': ctx['investor'].id, 'amount': allocations[0]},
                {'partner_id': ctx['operator'].id, 'amount': allocations[1]},
            ],
        }},
    )


class Path2AgreedTests(TestCase):
    def test_agreed_pins_shares_and_creates_advance(self):
        ctx = build_tenant()
        # Agreed 70/30 capital, 40/60 profit. Investor under-funds (66 vs 70).
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, share_basis='AGREED',
                 allocations=(Decimal('66'), Decimal('34')))

        batch = ProcurementReceiveBatch.objects.get(procurement=procurement)
        inv_alloc = ProcurementReceiveBatchCapitalAllocation.objects.get(
            batch=batch, partner_id=ctx['investor'].id)
        op_alloc = ProcurementReceiveBatchCapitalAllocation.objects.get(
            batch=batch, partner_id=ctx['operator'].id)

        # Shares pinned to AGREED, not to actual cash.
        self.assertEqual(inv_alloc.capital_share, Decimal('0.700000'))
        self.assertEqual(op_alloc.capital_share, Decimal('0.300000'))
        self.assertEqual(inv_alloc.profit_share, Decimal('0.350000'))
        self.assertEqual(op_alloc.profit_share, Decimal('0.650000'))
        # amount_contract_currency keeps ACTUAL cash (honest pool accounting).
        self.assertEqual(inv_alloc.amount_contract_currency, Decimal('66.00'))
        self.assertEqual(op_alloc.amount_contract_currency, Decimal('34.00'))

        # One advance: investor (under by 4) owes operator (over by 4).
        advances = list(CapitalAdvance.objects.filter(batch=batch))
        self.assertEqual(len(advances), 1)
        adv = advances[0]
        self.assertEqual(adv.debtor_id, ctx['investor'].id)
        self.assertEqual(adv.creditor_id, ctx['operator'].id)
        self.assertEqual(adv.principal, Decimal('4.00'))
        self.assertEqual(adv.outstanding_balance, Decimal('4.00'))
        self.assertEqual(adv.status, CapitalAdvance.Status.OUTSTANDING)
        self.assertEqual(adv.repayment_mode, CapitalAdvance.RepaymentMode.LUMP)

    def test_perfect_funding_creates_no_advance(self):
        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('70'), Decimal('30')),
        )
        _receive(ctx, procurement, share_basis='AGREED',
                 allocations=(Decimal('70'), Decimal('30')))
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement)
        self.assertEqual(CapitalAdvance.objects.filter(batch=batch).count(), 0)


class Path1FactualUnchangedTests(TestCase):
    def test_factual_default_derives_shares_and_makes_no_advance(self):
        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
            reconciliation_mode='FACTUAL',
        )
        _receive(ctx, procurement, allocations=(Decimal('66'), Decimal('34')))
        batch = ProcurementReceiveBatch.objects.get(procurement=procurement)
        inv_alloc = ProcurementReceiveBatchCapitalAllocation.objects.get(
            batch=batch, partner_id=ctx['investor'].id)
        # Shares follow ACTUAL cash (66/34 → 0.66/0.34), no advance.
        self.assertEqual(inv_alloc.capital_share, Decimal('0.660000'))
        self.assertEqual(CapitalAdvance.objects.filter(batch=batch).count(), 0)
