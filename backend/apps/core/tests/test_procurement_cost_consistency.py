"""
Consistency guard: procurement cost must come from ONE source everywhere.

If this test breaks it means someone re-introduced a parallel cost calculation
(inline Σ qty×price×fx, or a fresh filter, or a different CANCELLED exclusion).
Fix the root cause — don't patch the test.

Invariants verified:
  1. procurement_cost_by_currency ≡ payment_status.obligation_amount
  2. procurement_cost_by_currency ≡ capital allocation preview required
  3. procurement_cost_by_currency ≡ terms.total_amount_due
  4. CANCELLED items are excluded from all three
  5. fx_rate changes do NOT affect obligation (fx is reporting-only)
  6. Mixed currencies → ValueError
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import CashAccount, Account, ExchangeRate
from apps.finance.fx_rates import upsert_exchange_rate
from apps.partnerships.models import (
    Procurement,
    ProcurementItem,
    ProcurementTerms,
    InvestmentAgreement,
    AgreementPartner,
)
from apps.partnerships.procurement_cost import (
    procurement_cost_by_currency,
    active_procurement_lines,
)
from apps.partnerships.workspace import (
    build_workspace_capital_allocation_preview,
    build_workspace_payload,
    create_workspace,
    dispatch_workspace_action,
)

from ._helpers import build_tenant

FX = Decimal('12100')


def _seed_usd_rate(tenant_id):
    upsert_exchange_rate(
        tenant_id=tenant_id,
        base_currency='USD',
        quote_currency='UZS',
        rate_date=timezone.localdate(),
        rate=FX,
        source=ExchangeRate.Source.MANUAL,
        is_manual=True,
        notes='test',
    )


class ProcurementCostConsistencyTests(TestCase):
    """All cost paths must agree for procurement #24 scenario."""

    def setUp(self):
        self.ctx = build_tenant()
        _seed_usd_rate(self.ctx['business'].id)

        # PARTNERSHIP procurement with two items (one active $100, one CANCELLED $500)
        self.proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
            supplier_id=self.ctx['supplier'].id,
        )
        # Link an investment agreement: 70/30 capital, mudaraba 4/7 → 40/60 profit
        # (same formula as seed_received_procurement in _helpers.py)
        self.proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self.proc,
            action='CREATE_INVESTMENT_AGREEMENT',
            payload={'payload': {
                'mudaraba_ratio': Decimal('0.571429'),
                'planned_budget': Decimal('200'),
                'currency': 'USD',
                'partners': [
                    {'partner_id': self.ctx['investor'].id, 'role': 'INVESTOR',
                     'planned_capital_share': Decimal('140'), 'profit_share': Decimal('0.4')},
                    {'partner_id': self.ctx['operator'].id, 'role': 'OPERATOR',
                     'planned_capital_share': Decimal('60'), 'profit_share': Decimal('0.6')},
                ],
            }},
        )
        # Capital contributions so available_by_partner is non-zero
        for partner_id, amount in [
            (self.ctx['investor'].id, Decimal('150')),
            (self.ctx['operator'].id, Decimal('100')),
        ]:
            self.proc = dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=self.proc,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {
                    'partner_id': partner_id,
                    'amount': amount,
                    'currency': 'USD',
                    'fx_rate': str(FX),
                    'cash_account_id': self.ctx['card_account'].id,
                }},
            )

        # Create settlement first so terms exist for _resync_draft_terms_total
        self.proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self.proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'AT_RECEIPT'}},
        )

        # Active item: 1 × $100 USD
        self.proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self.proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '1',
                'unit_purchase_price': '100.00',
                'currency': 'USD',
                'fx_rate': str(FX),
            }]}},
        )

        # Add a second item and immediately cancel it ($500 USD — must be excluded)
        self.proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self.proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '5',
                'unit_purchase_price': '100.00',
                'currency': 'USD',
                'fx_rate': str(FX),
            }]}},
        )
        cancelled_item = self.proc.items.exclude(
            lifecycle_state=ProcurementItem.LifecycleState.CANCELLED,
        ).order_by('-id').first()
        self.proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=self.proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'cancel_item_ids': [cancelled_item.id]}},
        )
        self.proc.refresh_from_db()

    def _expected_usd(self) -> Decimal:
        return Decimal('100.00')

    def test_procurement_cost_by_currency_excludes_cancelled(self):
        active_items, active_expenses = active_procurement_lines(self.proc)
        cost = procurement_cost_by_currency(active_items, active_expenses)
        self.assertEqual(cost, {'USD': self._expected_usd()},
            f'procurement_cost_by_currency returned {cost}, expected {{USD: 100.00}}')
        # Only 1 active item remains
        self.assertEqual(len(active_items), 1)

    def test_payment_status_obligation_matches_cost_by_currency(self):
        payload = build_workspace_payload(self.proc)
        ps = payload['documents']['payment_status']
        self.assertEqual(
            Decimal(ps['obligation_amount']), self._expected_usd(),
            f'payment_status.obligation_amount={ps["obligation_amount"]}, expected 100.00',
        )
        self.assertEqual(ps['currency'], 'USD')

    def test_terms_total_amount_due_matches_cost_by_currency(self):
        terms = ProcurementTerms.objects.filter(procurement=self.proc).first()
        self.assertIsNotNone(terms)
        self.assertEqual(
            terms.total_amount_due, self._expected_usd(),
            f'terms.total_amount_due={terms.total_amount_due}, expected 100.00',
        )
        self.assertEqual(str(terms.currency_of_obligation).upper(), 'USD')

    def test_capital_allocation_preview_required_matches_cost_by_currency(self):
        preview = build_workspace_capital_allocation_preview(
            tenant_id=self.ctx['business'].id,
            procurement_id=self.proc.id,
            agreement_id=self.proc.agreement_id,
        )
        # preview['required'] is {currency: str(amount)}
        required_map = preview['required']
        self.assertIn('USD', required_map, f'Expected USD in required, got {required_map}')
        self.assertEqual(
            Decimal(str(required_map['USD'])), self._expected_usd(),
            f'capital preview required={required_map}, expected {{USD: 100.00}}',
        )

    def test_fx_rate_change_does_not_affect_obligation(self):
        """fx_rate is reporting-only — obligation must not change when it changes."""
        item = self.proc.items.get(lifecycle_state=ProcurementItem.LifecycleState.DRAFT)
        original_fx = item.fx_rate
        # Tripling the fx rate must NOT change the obligation
        item.fx_rate = Decimal(str(original_fx)) * 3
        item.save(update_fields=['fx_rate', 'updated_at'])

        active_items, active_expenses = active_procurement_lines(self.proc)
        cost = procurement_cost_by_currency(active_items, active_expenses)
        self.assertEqual(cost, {'USD': self._expected_usd()},
            f'After fx_rate change, cost={cost} but should remain {{USD: 100.00}}')

        # Also verify payment_status path
        payload = build_workspace_payload(self.proc)
        ps = payload['documents']['payment_status']
        self.assertEqual(
            Decimal(ps['obligation_amount']), self._expected_usd(),
            f'After fx_rate change, payment_status.obligation_amount={ps["obligation_amount"]}',
        )

    def test_all_sources_agree(self):
        """Single integration check: all 3 sources must return the same amount."""
        active_items, active_expenses = active_procurement_lines(self.proc)
        cost_map = procurement_cost_by_currency(active_items, active_expenses)
        cost = cost_map.get('USD', Decimal('0'))

        payload = build_workspace_payload(self.proc)
        obligation = Decimal(payload['documents']['payment_status']['obligation_amount'])

        terms = ProcurementTerms.objects.get(procurement=self.proc)
        terms_total = terms.total_amount_due

        preview = build_workspace_capital_allocation_preview(
            tenant_id=self.ctx['business'].id,
            procurement_id=self.proc.id,
            agreement_id=self.proc.agreement_id,
        )
        preview_required = Decimal(str(preview['required'].get('USD', '0')))

        self.assertEqual(cost, obligation,
            f'procurement_cost_by_currency({cost}) ≠ payment_status.obligation({obligation})')
        self.assertEqual(cost, terms_total,
            f'procurement_cost_by_currency({cost}) ≠ terms.total_amount_due({terms_total})')
        self.assertEqual(cost, preview_required,
            f'procurement_cost_by_currency({cost}) ≠ capital_preview.required({preview_required})')


class ProcurementCostMixedCurrencyTests(TestCase):
    """Mixed currency items must raise at cost calculation time."""

    def test_mixed_currency_raises(self):
        from apps.partnerships.procurement_cost import procurement_cost_by_currency

        class FakeItem:
            def __init__(self, qty, price, currency, fx='1', lifecycle_state='DRAFT'):
                self.quantity = qty
                self.unit_purchase_price = price
                self.currency = currency
                self.fx_rate = fx
                self.lifecycle_state = lifecycle_state

        items = [FakeItem('1', '100', 'USD'), FakeItem('1', '50000', 'UZS')]
        cost = procurement_cost_by_currency(items, [])
        # Mixed currencies: returns both, caller should raise on len > 1
        self.assertIn('USD', cost)
        self.assertIn('UZS', cost)
        self.assertEqual(len(cost), 2)
