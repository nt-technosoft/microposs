"""
E09 Wave A — Slice 1 / OPEN-S1.1: AT_RECEIPT combined receive+pay action tests.

Tests cover:
  * Combined receive+pay creates both ReceiveBatch and Payment atomically (OWN_FUNDS)
  * Missing payment_payload rejected for OWN_FUNDS AT_RECEIPT
  * pay_workspace_costs / pay_workspace_supplier_payable blocked on AT_RECEIPT
  * LEGAL_COMBINATIONS accepts both AT_RECEIPT variants
  * PARTNERSHIP × AT_RECEIPT: explicit allocations, derived allocations, insufficient capital
"""

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from apps.partnerships.models import Procurement, ProcurementTerms
from apps.partnerships.policies import (
    LEGAL_COMBINATIONS,
    validate_procurement_combination,
)
from apps.partnerships.workspace import (
    create_workspace,
    dispatch_workspace_action,
    pay_workspace_costs,
    receive_workspace_batch,
)
from apps.finance.models import CashAccount, Payment
from apps.inventory.models import Lot
from apps.partnerships.models import ProcurementReceiveBatchCapitalAllocation

from ._helpers import build_tenant


def _fund_cash_account(cash_account, amount):
    """Direct balance top-up for test setup (bypasses CashEntry — test isolation only)."""
    CashAccount.objects.filter(pk=cash_account.pk).update(balance=Decimal(str(amount)))

OWN_FUNDS = Procurement.FundingSource.OWN_FUNDS
PARTNERSHIP = Procurement.FundingSource.PARTNERSHIP
OWNED = Procurement.GoodsOwnership.OWNED
AT_RECEIPT = ProcurementTerms.Type.AT_RECEIPT
PREPAID = ProcurementTerms.Type.PREPAID


class AtReceiptLegalCombinationsTests(SimpleTestCase):
    """Validator accepts both AT_RECEIPT combinations (pure logic, no DB)."""

    def test_at_receipt_legal_combinations(self):
        self.assertIn((OWN_FUNDS, AT_RECEIPT, OWNED), LEGAL_COMBINATIONS)
        self.assertIn((PARTNERSHIP, AT_RECEIPT, OWNED), LEGAL_COMBINATIONS)
        validate_procurement_combination(OWN_FUNDS, AT_RECEIPT, OWNED)
        validate_procurement_combination(PARTNERSHIP, AT_RECEIPT, OWNED)


def _build_at_receipt_procurement(ctx, *, total_uzs='1000000', qty=100, unit_price='10000'):
    """Helper: OWN_FUNDS procurement with AT_RECEIPT terms + items, not yet received."""
    proc = create_workspace(
        tenant_id=ctx['business'].id,
        funding_source=OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
    )
    dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='UPDATE_SETTLEMENT',
        payload={'payload': {
            'type': 'AT_RECEIPT',
            'total_amount_due': total_uzs,
            'currency_of_obligation': 'UZS',
            'fx_rate_at_obligation': '1',
        }},
    )
    proc = dispatch_workspace_action(
        tenant_id=ctx['business'].id,
        procurement=proc,
        action='UPDATE_ITEMS',
        payload={'payload': {
            'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': qty,
                'unit_purchase_price': unit_price,
                'currency': 'UZS',
                'fx_rate': '1',
            }],
        }},
    )
    return proc


class AtReceiptCombinedActionTests(TestCase):
    def setUp(self):
        self.ctx = build_tenant()

    def test_at_receipt_combined_action_creates_payment_and_batch(self):
        """receive_workspace_batch with AT_RECEIPT + payment_payload creates both records atomically."""
        _fund_cash_account(self.ctx['cash_account'], '2000000')
        proc = _build_at_receipt_procurement(self.ctx)
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'payment_payload': {
                    'cash_account_id': self.ctx['cash_account'].id,
                    'amount': '1000000',
                    'currency': 'UZS',
                },
            },
        )
        self.assertIsNotNone(batch.pk)
        payment_qs = Payment.objects.filter(
            tenant_id=self.ctx['business'].id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.pk,
        )
        self.assertTrue(payment_qs.exists(), 'AT_RECEIPT receive must create a Payment.')
        self.assertEqual(payment_qs.count(), 1)
        payment = payment_qs.first()
        self.assertEqual(payment.amount, Decimal('1000000'))

    def test_at_receipt_usd_obligation_rejects_uzs_cash_account(self):
        """Money discipline: a USD obligation must NOT be payable from a UZS cash
        account. Previously the at-receipt path defaulted the payment currency to
        the account's, booking e.g. $440 as 440 UZS out of the sum register."""
        biz = self.ctx['business'].id
        proc = create_workspace(
            tenant_id=biz, funding_source=OWN_FUNDS, supplier_id=self.ctx['supplier'].id,
        )
        dispatch_workspace_action(
            tenant_id=biz, procurement=proc, action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'AT_RECEIPT', 'total_amount_due': '440',
                'currency_of_obligation': 'USD', 'fx_rate_at_obligation': '12000',
            }},
        )
        proc = dispatch_workspace_action(
            tenant_id=biz, procurement=proc, action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': 44, 'unit_purchase_price': '10',
                'currency': 'USD', 'fx_rate': '12000',
            }]}},
        )
        uzs_account = self.ctx['cash_account']  # UZS register
        _fund_cash_account(uzs_account, '5000000')
        with self.assertRaises(ValueError):
            receive_workspace_batch(
                tenant_id=biz, procurement=proc,
                payload={
                    'warehouse_id': self.ctx['store'].id,
                    'payment_payload': {
                        'cash_account_id': uzs_account.id,
                        'amount': '440', 'currency': 'UZS',
                    },
                },
            )

    def test_at_receipt_receive_without_payment_payload_rejected(self):
        """receive_workspace_batch on AT_RECEIPT without payment_payload raises ValueError."""
        proc = _build_at_receipt_procurement(self.ctx)
        with self.assertRaises(ValueError, msg='missing payment_payload must be rejected'):
            receive_workspace_batch(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={'warehouse_id': self.ctx['store'].id},
            )

    def test_at_receipt_separate_pay_action_rejected(self):
        """pay_workspace_costs on AT_RECEIPT procurement raises ValueError."""
        proc = _build_at_receipt_procurement(self.ctx)
        terms = proc.terms
        with self.assertRaises(ValueError, msg='separate pay action must be blocked for AT_RECEIPT'):
            pay_workspace_costs(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={
                    'cash_account_id': self.ctx['cash_account'].id,
                    'amount': '1000000',
                },
            )

    def _build_partnership_at_receipt_procurement(self, ctx, *, total_uzs='5000', qty=5, unit_price='1000'):
        """PARTNERSHIP + AT_RECEIPT procurement with capital contributed but NOT yet allocated."""
        from django.utils import timezone
        from apps.finance.models import ExchangeRate
        from apps.finance.fx_rates import upsert_exchange_rate

        proc = create_workspace(
            tenant_id=ctx['business'].id,
            funding_source=PARTNERSHIP,
            supplier_id=ctx['supplier'].id,
        )
        proc = dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc,
            action='CREATE_INVESTMENT_AGREEMENT',
            payload={'payload': {
                'mudaraba_ratio': '0.571429',
                'planned_budget': total_uzs,
                'currency': 'UZS',
                'partners': [
                    {'partner_id': ctx['investor'].id, 'role': 'INVESTOR',
                     'planned_capital_share': str(int(total_uzs) * 7 // 10),
                     'profit_share': '0.4'},
                    {'partner_id': ctx['operator'].id, 'role': 'OPERATOR',
                     'planned_capital_share': str(int(total_uzs) - int(total_uzs) * 7 // 10),
                     'profit_share': '0.6'},
                ],
            }},
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'AT_RECEIPT',
                'total_amount_due': total_uzs,
                'currency_of_obligation': 'UZS',
            }},
        )
        proc = dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [{
                'product_variant_id': ctx['variant'].id,
                'quantity': qty,
                'unit_purchase_price': unit_price,
                'currency': 'UZS', 'fx_rate': '1',
            }]}},
        )
        # Contribute capital to the agreement pool (both partners)
        inv_amount = str(int(total_uzs) * 7 // 10)
        op_amount = str(int(total_uzs) - int(total_uzs) * 7 // 10)
        for partner_id, amount in (
            (ctx['investor'].id, inv_amount),
            (ctx['operator'].id, op_amount),
        ):
            CashAccount.objects.filter(pk=ctx['card_account'].pk).update(balance=Decimal('100000'))
            dispatch_workspace_action(
                tenant_id=ctx['business'].id, procurement=proc,
                action='RECORD_CAPITAL_CONTRIBUTION',
                payload={'payload': {
                    'partner_id': partner_id,
                    'amount': amount,
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'cash_account_id': ctx['card_account'].id,
                }},
            )
        proc.refresh_from_db()
        return proc

    def test_partnership_at_receipt_derives_from_planned_shares(self):
        """PARTNERSHIP × AT_RECEIPT without capital_allocations → derives from planned shares."""
        proc = self._build_partnership_at_receipt_procurement(self.ctx)
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={'warehouse_id': self.ctx['store'].id},
        )
        self.assertIsNotNone(batch.pk)
        allocs = ProcurementReceiveBatchCapitalAllocation.objects.filter(
            tenant_id=self.ctx['business'].id, batch=batch,
        )
        self.assertEqual(allocs.count(), 2)
        lot = Lot.objects.get(procurement_item__procurement=proc)
        self.assertTrue(lot.contract_snapshot.get('partners'))

    def test_partnership_at_receipt_with_explicit_allocations(self):
        """PARTNERSHIP × AT_RECEIPT with explicit capital_allocations uses provided amounts."""
        proc = self._build_partnership_at_receipt_procurement(self.ctx)
        proc.refresh_from_db()
        agreement = proc.agreement
        members = list(agreement.partners.all())
        total_uzs = Decimal('5000')
        explicit_allocs = [
            {'partner_id': members[0].partner_id, 'amount': '3500', 'currency': 'UZS'},
            {'partner_id': members[1].partner_id, 'amount': '1500', 'currency': 'UZS'},
        ]
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'capital_allocations': explicit_allocs,
            },
        )
        self.assertIsNotNone(batch.pk)
        alloc_amounts = {
            a.partner_id: a.amount_contract_currency
            for a in ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=batch)
        }
        self.assertEqual(sum(alloc_amounts.values()), total_uzs)

    def test_partnership_at_receipt_second_partial_receive_uses_remaining_agreement_capital(self):
        """PARTNERSHIP × AT_RECEIPT derives later receive snapshots from remaining pool balances."""
        proc = self._build_partnership_at_receipt_procurement(
            self.ctx,
            total_uzs='200',
            qty=10,
            unit_price='10',
        )
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {'items': [
                {
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': '1',
                },
                {
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': Decimal('10'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'UZS',
                    'fx_rate': '1',
                },
            ]}},
        )
        first_item, second_item = list(proc.items.order_by('id'))[:2]

        first_batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'item_ids': [first_item.id],
                'capital_allocations': [
                    {'partner_id': self.ctx['investor'].id, 'amount': Decimal('100'), 'currency': 'UZS'},
                    {'partner_id': self.ctx['operator'].id, 'amount': Decimal('0'), 'currency': 'UZS'},
                ],
            },
        )
        second_batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'item_ids': [second_item.id],
            },
        )

        first_allocs = {
            row.partner_id: row.amount_contract_currency
            for row in ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=first_batch)
        }
        second_allocs = {
            row.partner_id: row.amount_contract_currency
            for row in ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=second_batch)
        }
        self.assertEqual(first_allocs[self.ctx['investor'].id], Decimal('100.00'))
        self.assertEqual(first_allocs[self.ctx['operator'].id], Decimal('0.00'))
        self.assertEqual(second_allocs[self.ctx['investor'].id], Decimal('40.00'))
        self.assertEqual(second_allocs[self.ctx['operator'].id], Decimal('60.00'))

    def test_partnership_at_receipt_insufficient_capital_rejected(self):
        """PARTNERSHIP × AT_RECEIPT with explicit allocation exceeding pool → ValueError."""
        proc = self._build_partnership_at_receipt_procurement(self.ctx)
        agreement = proc.agreement
        members = list(agreement.partners.all())
        with self.assertRaises(ValueError, msg='Over-allocation must raise ValueError'):
            receive_workspace_batch(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                payload={
                    'warehouse_id': self.ctx['store'].id,
                    'capital_allocations': [
                        {'partner_id': members[0].partner_id, 'amount': '999999', 'currency': 'UZS'},
                        {'partner_id': members[1].partner_id, 'amount': '999999', 'currency': 'UZS'},
                    ],
                },
            )


class AtReceiptSupplierOptionalTests(TestCase):
    """Canonical rule: AT_RECEIPT does NOT require a supplier (cash-now settlement).
    DEFERRED/PARTIAL/INSTALLMENT/ON_SALE DO require a supplier (debt obligation).
    """

    def setUp(self):
        self.ctx = build_tenant()

    def test_at_receipt_own_funds_no_supplier_succeeds(self):
        """OWN_FUNDS × AT_RECEIPT procurement receives+pays without a supplier."""
        _fund_cash_account(self.ctx['cash_account'], '2000000')
        # Create procurement explicitly without a supplier
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=OWN_FUNDS,
            supplier_id=None,
        )
        dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'AT_RECEIPT',
                'total_amount_due': '500000',
                'currency_of_obligation': 'UZS',
                'fx_rate_at_obligation': '1',
            }},
        )
        proc = dispatch_workspace_action(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': self.ctx['variant'].id,
                    'quantity': 50,
                    'unit_purchase_price': '10000',
                    'currency': 'UZS',
                    'fx_rate': '1',
                }],
            }},
        )
        # Must NOT raise — AT_RECEIPT is cash-now, supplier optional
        batch = receive_workspace_batch(
            tenant_id=self.ctx['business'].id,
            procurement=proc,
            payload={
                'warehouse_id': self.ctx['store'].id,
                'payment_payload': {
                    'cash_account_id': self.ctx['cash_account'].id,
                    'amount': '500000',
                    'currency': 'UZS',
                },
            },
        )
        self.assertIsNotNone(batch.pk)
        payment_qs = Payment.objects.filter(
            tenant_id=self.ctx['business'].id,
            target_type=Payment.TargetType.PROCUREMENT_COST,
            target_id=proc.pk,
        )
        self.assertTrue(payment_qs.exists(), 'AT_RECEIPT receive must create a Payment even without supplier.')

    def test_deferred_without_supplier_raises(self):
        """OWN_FUNDS × DEFERRED procurement without supplier raises at terms validation."""
        proc = create_workspace(
            tenant_id=self.ctx['business'].id,
            funding_source=OWN_FUNDS,
            supplier_id=None,
        )
        with self.assertRaises(ValueError, msg='DEFERRED without supplier must be rejected'):
            dispatch_workspace_action(
                tenant_id=self.ctx['business'].id,
                procurement=proc,
                action='UPDATE_SETTLEMENT',
                payload={'payload': {
                    'type': 'DEFERRED',
                    'total_amount_due': '500000',
                    'currency_of_obligation': 'UZS',
                    'fx_rate_at_obligation': '1',
                    'deadline_date': '2026-12-31',
                }},
            )
