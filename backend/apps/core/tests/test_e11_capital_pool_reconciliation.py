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
from django.utils import timezone

from apps.finance.fx_rates import upsert_exchange_rate
from apps.finance.models import (
    CashAccount,
    ExchangeRate,
    JournalEntry,
    JournalLine,
    Payment,
)
from apps.finance.services import get_account_balance, record_owner_contribution
from apps.partnerships.models import (
    AgreementContribution,
    InvestmentAgreement,
    Procurement,
)
from apps.suppliers.models import SupplierPayable
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

    def test_usd_contribution_keeps_pool_in_usd_but_books_gl_in_functional_uzs(self):
        ctx = build_tenant()
        upsert_exchange_rate(
            tenant_id=ctx['business'].id,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=timezone.localdate(),
            rate=Decimal('12000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='test fixture',
        )
        procurement = _build_partnership_agreement(ctx, currency='USD')

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECORD_CAPITAL_CONTRIBUTION',
            payload={'payload': {
                'partner_id': ctx['investor'].id,
                'amount': Decimal('595'),
                'currency': 'USD',
                'fx_rate': Decimal('12000'),
            }},
        )

        pool = _pool(procurement)
        # Cash subledger stays in the agreement (transaction) currency.
        self.assertEqual(pool.currency, 'USD')
        self.assertEqual(pool.balance, Decimal('595.00'))
        # GL is functional UZS everywhere: 595 USD × 12000 = 7 140 000 UZS.
        functional = Decimal('595') * Decimal('12000')
        self.assertEqual(get_account_balance(ctx['business'].id, '1300'), functional)
        self.assertEqual(get_account_balance(ctx['business'].id, '3100'), functional)

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


class CapitalPoolPaymentReconciliationTests(TestCase):
    """Phase 3: partnership supplier cost is settled from the pool, not from
    operating cash and not by re-crediting investor equity at receive."""

    def _build_funded_partnership(self, ctx):
        procurement = _build_partnership_agreement(ctx, currency='UZS')
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': Decimal('20'),
                'unit_purchase_price': Decimal('10'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
            }]}},
        )
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
        procurement = dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='ALLOCATE_CAPITAL',
            payload={'payload': {'allocations': [
                {'partner_id': ctx['investor'].id, 'amount': Decimal('140'), 'currency': 'UZS'},
                {'partner_id': ctx['operator'].id, 'amount': Decimal('60'), 'currency': 'UZS'},
            ]}},
        )
        return procurement

    def test_receive_draws_inventory_cost_from_pool(self):
        ctx = build_tenant()
        procurement = self._build_funded_partnership(ctx)
        item = procurement.items.get()

        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': ctx['storage'].id,
                'item_ids': [item.id],
                'capital_allocations': [
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('140')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('60')},
                ],
            }},
        )

        pool = _pool(procurement)
        # Inventory cost (20 × 10 = 200) is drawn out of the pool.
        self.assertEqual(pool.balance, Decimal('0.00'))
        # The draw is a CAPITAL_POOL payment, not operating cash.
        pool_payment = Payment.objects.get(
            tenant_id=ctx['business'].id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            target_type=Payment.TargetType.PROCUREMENT_COST,
        )
        self.assertEqual(pool_payment.amount, Decimal('200.00'))
        self.assertEqual(pool_payment.source_id, pool.pk)
        # Partnership procurements never leave a supplier payable — the pool settles it.
        self.assertFalse(
            SupplierPayable.objects.filter(tenant_id=ctx['business'].id, procurement=procurement).exists()
        )

    def test_pool_reconciles_and_equity_not_double_counted_after_receive(self):
        ctx = build_tenant()
        procurement = self._build_funded_partnership(ctx)
        item = procurement.items.get()
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=procurement,
            action='RECEIVE_BATCH',
            payload={'payload': {
                'warehouse_id': ctx['storage'].id,
                'item_ids': [item.id],
                'capital_allocations': [
                    {'partner_id': ctx['investor'].id, 'amount': Decimal('140')},
                    {'partner_id': ctx['operator'].id, 'amount': Decimal('60')},
                ],
            }},
        )

        pool = _pool(procurement)
        contributed = sum(
            (c.amount for c in InvestmentAgreement.objects.get(pk=procurement.agreement_id).contributions.all()),
            Decimal('0'),
        )
        pool_out = sum(
            (p.amount for p in Payment.objects.filter(
                tenant_id=ctx['business'].id,
                source_type=Payment.SourceType.CAPITAL_POOL,
            )),
            Decimal('0'),
        )
        # Reconciliation invariant: pool == Σ contributions − Σ pool payments.
        self.assertEqual(pool.balance, contributed - pool_out)

        # Equity is recognised once (at contribution), not re-credited at receive.
        self.assertEqual(get_account_balance(ctx['business'].id, '3100'), Decimal('140.00'))
        self.assertEqual(get_account_balance(ctx['business'].id, '3000'), Decimal('60.00'))
        # Inventory landed on the books; pool GL nets to zero.
        self.assertEqual(get_account_balance(ctx['business'].id, '1100'), Decimal('200.00'))
        self.assertEqual(get_account_balance(ctx['business'].id, '1300'), Decimal('0.00'))
        # All journals balanced.
        for entry in JournalEntry.objects.filter(tenant_id=ctx['business'].id):
            lines = JournalLine.objects.filter(journal_entry=entry)
            self.assertEqual(
                sum((l.debit for l in lines), Decimal('0')),
                sum((l.credit for l in lines), Decimal('0')),
            )
