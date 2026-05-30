"""
E11 — Partnership capital pool reconciliation (Phase 2).

Contributions move real cash into the agreement's capital pool (a real
CashAccount of kind AGREEMENT_CAPITAL). Three modes:
  - investor external  → cash-IN to pool, DR 1300 / CR 3100 (investor equity)
  - operator external  → cash-IN to pool, DR 1300 / CR 3000 (owner equity)
  - business turnover  → transfer operating cash → pool, DR 1300 / CR 1000

Reconciliation invariant: pool.balance == Σ contributions − Σ pool outflows.
After Phase 2 there are no pool outflows yet, so pool.balance == Σ contributions.
"""

from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, JournalEntry, JournalLine
from apps.finance.services import get_account_balance, record_owner_contribution
from apps.partnerships.models import (
    AgreementContribution,
    InvestmentAgreement,
    Procurement,
)
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action

from ._helpers import build_tenant


def _build_partnership_agreement(ctx, *, currency='UZS', mudaraba_ratio=Decimal('0.5')):
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
            'mudaraba_ratio': mudaraba_ratio,
            'planned_budget': Decimal('200'),
            'currency': currency,
            'partners': [
                {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                 'planned_capital_share': Decimal('136'), 'profit_share': Decimal('0.34')},
                {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                 'planned_capital_share': Decimal('64'), 'profit_share': Decimal('0.66')},
            ],
        }},
    )
    return procurement


def _pool(procurement):
    agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
    return CashAccount.objects.get(pk=agreement.capital_account_id)


class CapitalPoolProvisioningTests(TestCase):
    def test_agreement_creation_provisions_capital_pool(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx, currency='UZS')

        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        self.assertIsNotNone(agreement.capital_account_id)
        pool = agreement.capital_account
        self.assertEqual(pool.kind, CashAccount.Kind.AGREEMENT_CAPITAL)
        self.assertEqual(pool.currency, 'UZS')
        self.assertEqual(pool.balance, Decimal('0.00'))
        self.assertEqual(pool.linked_account.code, '1300')


class CapitalContributionReconciliationTests(TestCase):
    def test_investor_external_contribution_funds_pool_and_credits_investor_equity(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx)
        operating_before = CashAccount.objects.get(pk=ctx['cash_account'].id).balance

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['investor'].id,
                'amount': Decimal('140'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }},
        )

        pool = _pool(procurement)
        self.assertEqual(pool.balance, Decimal('140.00'))
        # External money — operating cash is untouched.
        self.assertEqual(
            CashAccount.objects.get(pk=ctx['cash_account'].id).balance,
            operating_before,
        )
        # Role-correct equity: investor capital (mudaraba) = 3100.
        self.assertEqual(get_account_balance(ctx['business'].id, '3100'), Decimal('140.00'))
        self.assertEqual(get_account_balance(ctx['business'].id, '1300'), Decimal('140.00'))

    def test_operator_external_contribution_credits_owner_equity(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx)

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['operator'].id,
                'amount': Decimal('60'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }},
        )

        pool = _pool(procurement)
        self.assertEqual(pool.balance, Decimal('60.00'))
        # Operator capital → owner equity (3000), NOT investor capital (3100).
        self.assertEqual(get_account_balance(ctx['business'].id, '3000'), Decimal('60.00'))
        self.assertEqual(get_account_balance(ctx['business'].id, '3100'), Decimal('0.00'))

    def test_operator_turnover_contribution_moves_cash_from_operating_to_pool(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx)
        # Fund the operating cash account first (owner injects 500).
        record_owner_contribution(
            tenant_id=ctx['business'].id,
            amount=Decimal('500'),
            currency='UZS',
            to_account_id=ctx['cash_account'].id,
        )
        operating_before = CashAccount.objects.get(pk=ctx['cash_account'].id).balance

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['operator'].id,
                'amount': Decimal('60'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'mode': 'BUSINESS_FROM_TURNOVER',
                'from_cash_account_id': ctx['cash_account'].id,
            }},
        )

        pool = _pool(procurement)
        self.assertEqual(pool.balance, Decimal('60.00'))
        # Turnover relocates money: operating cash drops by the contribution.
        self.assertEqual(
            CashAccount.objects.get(pk=ctx['cash_account'].id).balance,
            operating_before - Decimal('60.00'),
        )
        # Pure relocation: no new equity recognised (asset ↔ asset).
        self.assertEqual(get_account_balance(ctx['business'].id, '3100'), Decimal('0.00'))

    def test_pool_balance_reconciles_with_sum_of_contributions(self):
        ctx = build_tenant()
        procurement = _build_partnership_agreement(ctx)
        for partner_id, amount in (
            (ctx['investor'].id, Decimal('140')),
            (ctx['operator'].id, Decimal('60')),
        ):
            dispatch_workspace_action(
                tenant_id=ctx['business'].id,
                procurement=procurement,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {
                    'partner_id': partner_id,
                    'amount': amount,
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                }},
            )

        pool = _pool(procurement)
        agreement = InvestmentAgreement.objects.get(pk=procurement.agreement_id)
        contributed = sum(
            (c.amount for c in agreement.contributions.all()),
            Decimal('0'),
        )
        self.assertEqual(pool.balance, contributed)
        self.assertEqual(pool.balance, Decimal('200.00'))
        # Every journal entry is balanced.
        for entry in JournalEntry.objects.filter(tenant_id=ctx['business'].id):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(
                sum((l.debit for l in lines), Decimal('0')),
                sum((l.credit for l in lines), Decimal('0')),
            )
