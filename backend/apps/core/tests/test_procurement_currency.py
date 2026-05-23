"""
Currency discipline tests for procurement payment flow.

Rules verified here:
  1. currency_of_obligation derived from items (single currency required).
  2. total_amount_due = Σ(qty × price) in obligation currency — NO fx multiplication.
  3. Mixed-currency items are rejected.
  4. pay_workspace_costs rejects cash_account.currency != obligation currency.
  5. pay_workspace_supplier_payable rejects mismatched cash account currency.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import CashAccount, Account, Payment, ExchangeRate
from apps.finance.fx_rates import upsert_exchange_rate
from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action
from apps.suppliers.models import SupplierPayable

from ._helpers import build_tenant

FX = Decimal('12000')


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


def _make_procurement(ctx, currency='UZS', unit_price='100', qty='10', fx_rate='1'):
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=Procurement.FundingSource.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    return dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {'items': [{
            'product_variant_id': ctx['variant'].id,
            'quantity': qty,
            'unit_purchase_price': unit_price,
            'currency': currency,
            'fx_rate': fx_rate,
        }]}},
    )


class TermsCurrencyDerivationTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_terms_currency_derived_from_items_usd(self):
        """USD items → settlement currency_of_obligation is USD."""
        proc = _make_procurement(self.ctx, currency='USD', unit_price='10', qty='5', fx_rate='12000')
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'DEFERRED'}},
        )
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.currency_of_obligation, 'USD')

    def test_terms_currency_derived_from_items_uzs(self):
        """UZS items → settlement currency_of_obligation is UZS."""
        proc = _make_procurement(self.ctx, currency='UZS', unit_price='100000', qty='2', fx_rate='1')
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'DEFERRED'}},
        )
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.currency_of_obligation, 'UZS')

    def test_total_amount_due_in_obligation_currency_no_fx(self):
        """
        Items: 5 × $10, fx_rate=12000.
        total_amount_due must be 50 USD (not 600000 UZS).
        """
        proc = _make_procurement(self.ctx, currency='USD', unit_price='10', qty='5', fx_rate='12000')
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'PREPAID'}},
        )
        terms = ProcurementTerms.objects.get(procurement=proc)
        self.assertEqual(terms.currency_of_obligation, 'USD')
        self.assertEqual(terms.total_amount_due, Decimal('50.00'))

    def test_terms_mixed_currencies_rejected_on_settlement(self):
        """Items in two currencies → UPDATE_SETTLEMENT raises on mixed currencies."""
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=self.ctx['supplier'].id,
        )
        # Add first item in UZS
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '1',
                'unit_purchase_price': '100000',
                'currency': 'UZS',
                'fx_rate': '1',
            }]}},
        )
        # Add second item in USD — stored as a new ProcurementItem
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': '1',
                'unit_purchase_price': '10',
                'currency': 'USD',
                'fx_rate': '12000',
            }]}},
        )
        # Mixed currencies → rejected when settlement is set
        with self.assertRaises(ValueError) as exc_ctx:
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                action='UPDATE_SETTLEMENT',
                payload={'payload': {'type': 'PREPAID'}},
            )
        self.assertIn('одной валюте', str(exc_ctx.exception))


class PayCostsCurrencyValidationTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        _seed_usd_rate(self.ctx['business'].id)
        self.uzs_account = self.ctx['cash_account']
        self.uzs_account.balance = Decimal('999999999.00')
        self.uzs_account.save(update_fields=['balance', 'updated_at'])

        self.usd_account = CashAccount.objects.create(
            tenant=self.ctx['business'],
            name='USD Cash',
            currency='USD',
            kind=CashAccount.Kind.CASH,
            balance=Decimal('99999.00'),
            linked_account=Account.objects.get(tenant=self.ctx['business'], code='1000'),
        )

    def test_pay_costs_rejects_mismatched_cash_account_currency(self):
        """USD items, UZS cash → ValueError about currency mismatch."""
        proc = _make_procurement(self.ctx, currency='USD', unit_price='100', qty='1', fx_rate='12000')
        item = proc.items.first()
        with self.assertRaises(ValueError) as ctx:
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                action='PAY_COSTS',
                payload={'payload': {
                    'cash_account_id': self.uzs_account.id,
                    'item_ids': [item.id],
                }},
            )
        self.assertIn('UZS', str(ctx.exception))
        self.assertIn('USD', str(ctx.exception))

    def test_pay_costs_with_matching_currency_success(self):
        """USD items, USD cash → payment succeeds in USD."""
        proc = _make_procurement(self.ctx, currency='USD', unit_price='100', qty='2', fx_rate='12000')
        item = proc.items.first()

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='PAY_COSTS',
            payload={'payload': {
                'cash_account_id': self.usd_account.id,
                'item_ids': [item.id],
            }},
        )

        payment = Payment.objects.get(
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.id,
        )
        self.assertEqual(payment.currency, 'USD')
        # total = 2 × 100 = 200 USD (NOT 2400000 UZS)
        self.assertEqual(payment.amount, Decimal('200.00'))

    def test_pay_costs_uzs_items_uzs_cash_success(self):
        """UZS items, UZS cash → payment succeeds in UZS at correct amount."""
        proc = _make_procurement(self.ctx, currency='UZS', unit_price='50000', qty='3', fx_rate='1')
        item = proc.items.first()

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='PAY_COSTS',
            payload={'payload': {
                'cash_account_id': self.uzs_account.id,
                'item_ids': [item.id],
            }},
        )

        payment = Payment.objects.get(
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.id,
        )
        self.assertEqual(payment.currency, 'UZS')
        self.assertEqual(payment.amount, Decimal('150000.00'))


class PaySupplierPayableCurrencyValidationTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        _seed_usd_rate(self.ctx['business'].id)
        self.uzs_account = self.ctx['cash_account']
        self.uzs_account.balance = Decimal('999999999.00')
        self.uzs_account.save(update_fields=['balance', 'updated_at'])

        self.usd_account = CashAccount.objects.create(
            tenant=self.ctx['business'],
            name='USD Cash',
            currency='USD',
            kind=CashAccount.Kind.CASH,
            balance=Decimal('99999.00'),
            linked_account=Account.objects.get(tenant=self.ctx['business'], code='1000'),
        )

    def _make_deferred_procurement_with_payable(self, currency='USD', unit_price='100', qty='2'):
        """Create OWN_FUNDS DEFERRED procurement and trigger payable creation via receive."""
        proc = _make_procurement(self.ctx, currency=currency, unit_price=unit_price, qty=qty)
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'DEFERRED'}},
        )
        # Receive creates the SupplierPayable
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': self.ctx['storage'].id}},
        )
        proc.refresh_from_db()
        return proc

    def test_pay_supplier_payable_rejects_mismatched_currency(self):
        """USD payable, UZS cash → ValueError about currency mismatch."""
        proc = self._make_deferred_procurement_with_payable(currency='USD', unit_price='50', qty='4')
        payable = SupplierPayable.objects.get(procurement=proc)
        self.assertEqual(payable.currency_of_obligation, 'USD')

        with self.assertRaises(ValueError) as ctx:
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                action='PAY_SUPPLIER_PAYABLE',
                payload={'payload': {
                    'payable_id': payable.id,
                    'cash_account_id': self.uzs_account.id,
                    'amount': '200',
                }},
            )
        self.assertIn('UZS', str(ctx.exception))
        self.assertIn('USD', str(ctx.exception))

    def test_pay_supplier_payable_matching_currency_success(self):
        """USD payable, USD cash → payment succeeds."""
        proc = self._make_deferred_procurement_with_payable(currency='USD', unit_price='50', qty='4')
        payable = SupplierPayable.objects.get(procurement=proc)

        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='PAY_SUPPLIER_PAYABLE',
            payload={'payload': {
                'payable_id': payable.id,
                'cash_account_id': self.usd_account.id,
                'amount': '200',
            }},
        )
        payable.refresh_from_db()
        self.assertEqual(payable.paid_amount, Decimal('200.00'))
