"""E17 T-5.3 — partner negative-position repayment (money slice).

Append-only repayment: debtor brings cash into operating cash; waterfall
liability → over-capital → over-dividend; component-correct GL (5100 / equity /
3200). Repayment cuts negative_position (originals untouched), the cash funds the
counterparty's claim, the conservation invariant stays balanced, and close
unblocks once the debt is cleared.
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashAccount, JournalEntry, JournalLine
from apps.partnerships.agreement_services import pay_dividend
from apps.partnerships.models import ProcurementVentureSettlement
from apps.partnerships.venture import (
    create_venture_settlement,
    procurement_venture_positions,
    repay_partner_venture_debt,
    venture_conservation,
)
from apps.risk.services import create_writeoff
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement

_EPS = Decimal('0.01')


def _sell(ctx, session, *, quantity, unit_price):
    return create_sale(
        tenant_id=ctx['business'].id, pos_session_id=session.id,
        location_id=ctx['store'].id, sold_by_id=ctx['cashier'].id,
        customer_id=ctx['customer'].id,
        lines=[{'product_variant_id': ctx['variant'].id, 'quantity': quantity,
                'unit_price': Decimal(unit_price)}],
        payments=[{'amount': Decimal(unit_price) * Decimal(quantity), 'currency': 'UZS',
                   'fx_rate': Decimal('1'), 'method': SalePayment.Method.CASH,
                   'account_id': ctx['cash_account'].id}],
    )


def _neg(ctx, procurement, partner_key):
    return procurement_venture_positions(procurement=procurement)[ctx[partner_key].id]


def _credits_by_account(tenant_id, repayment_pk):
    entry = JournalEntry.objects.get(
        tenant_id=tenant_id, operation_type='venture_debt_repay', operation_id=repayment_pk,
    )
    lines = JournalLine.objects.filter(journal_entry=entry)
    debit = sum((line.debit for line in lines), Decimal('0'))
    credit = sum((line.credit for line in lines), Decimal('0'))
    credits = {}
    for line in lines:
        if line.credit > 0:
            credits[line.account.code] = credits.get(line.account.code, Decimal('0')) + line.credit
    return debit, credit, credits


def _assert_conservation_balanced(test, procurement, msg=''):
    report = venture_conservation(procurement=procurement)
    test.assertTrue(report.is_balanced(_EPS), msg=f'{msg} {report.imbalances(_EPS)}')


class LiabilityRepaymentTests(TestCase):
    def _liability_negative(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        create_writeoff(
            tenant_id=ctx['business'].id, lot_id=lot.id, warehouse_id=ctx['store'].id,
            quantity=2, reason='negligence', responsible_user_id=ctx['owner'].id, negligence=True,
        )
        return ctx, procurement

    def test_liability_repayment_clears_negative_and_credits_5100(self):
        ctx, procurement = self._liability_negative()
        op = _neg(ctx, procurement, 'operator')
        debt = op['negative_liability_uzs']
        self.assertGreater(debt, Decimal('0'))
        self.assertEqual(op['negative_position_uzs'], debt)
        _assert_conservation_balanced(self, procurement, 'pre-repay')

        repayment = repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['operator'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id,
        )
        after = _neg(ctx, procurement, 'operator')
        self.assertEqual(after['negative_position_uzs'], Decimal('0.00'))
        self.assertEqual(after['debt_repaid_uzs'], debt)

        debit, credit, credits = _credits_by_account(ctx['business'].id, repayment.pk)
        self.assertEqual(debit, credit)  # journal balanced
        self.assertEqual(credits.get('5100'), debt)  # liability → loss account
        _assert_conservation_balanced(self, procurement, 'post-repay')

    def test_repayment_cash_funds_counterparty_claim(self):
        ctx, procurement = self._liability_negative()
        # Settlement turns the innocent partner's lost capital into a claim.
        create_venture_settlement(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        investor_before = _neg(ctx, procurement, 'investor')
        self.assertGreater(investor_before['liability_capital_recovered_uzs'], Decimal('0'))

        cash_before = CashAccount.objects.get(pk=ctx['cash_account'].id).balance
        debt = _neg(ctx, procurement, 'operator')['negative_position_uzs']
        repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['operator'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id,
        )
        # The repaid cash physically lands in operating cash → funds the claim.
        self.assertEqual(
            CashAccount.objects.get(pk=ctx['cash_account'].id).balance, cash_before + debt,
        )
        self.assertEqual(_neg(ctx, procurement, 'operator')['negative_position_uzs'], Decimal('0.00'))
        _assert_conservation_balanced(self, procurement, 'liability+settlement')


class OverDividendRepaymentTests(TestCase):
    def _over_dividend_negative(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        create_venture_settlement(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        pay_dividend(
            partner_id=ctx['investor'].id, procurement_id=procurement.id,
            amount=Decimal('216000.00'), currency='UZS',
            from_account_id=ctx['cash_account'].id, tenant_id=ctx['business'].id,
        )
        _sell(ctx, session, quantity=5, unit_price='100000.00')  # loss nets profit down
        return ctx, procurement

    def test_over_dividend_repayment_clears_negative_and_credits_3200(self):
        ctx, procurement = self._over_dividend_negative()
        inv = _neg(ctx, procurement, 'investor')
        debt = inv['negative_dividend_uzs']
        self.assertGreater(debt, Decimal('0'))
        self.assertEqual(inv['negative_position_uzs'], debt)
        _assert_conservation_balanced(self, procurement, 'pre-repay')

        repayment = repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['investor'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id,
        )
        self.assertEqual(_neg(ctx, procurement, 'investor')['negative_position_uzs'], Decimal('0.00'))
        debit, credit, credits = _credits_by_account(ctx['business'].id, repayment.pk)
        self.assertEqual(debit, credit)
        self.assertEqual(credits.get('3200'), debt)  # over-dividend → retained earnings
        _assert_conservation_balanced(self, procurement, 'post-repay')

    def test_partial_repayment_reduces_proportionally(self):
        ctx, procurement = self._over_dividend_negative()
        debt = _neg(ctx, procurement, 'investor')['negative_position_uzs']
        half = (debt / 2).quantize(Decimal('0.01'))
        repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['investor'].id, amount=half, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id,
        )
        self.assertEqual(_neg(ctx, procurement, 'investor')['negative_position_uzs'], debt - half)
        _assert_conservation_balanced(self, procurement, 'partial')

    def test_overpay_rejected(self):
        ctx, procurement = self._over_dividend_negative()
        debt = _neg(ctx, procurement, 'investor')['negative_position_uzs']
        with self.assertRaises(ValueError):
            repay_partner_venture_debt(
                tenant_id=ctx['business'].id, procurement_id=procurement.id,
                partner_id=ctx['investor'].id, amount=debt + Decimal('1000.00'), currency='UZS',
                paid_to_account_id=ctx['cash_account'].id,
            )

    def test_idempotent_on_client_request_id(self):
        ctx, procurement = self._over_dividend_negative()
        debt = _neg(ctx, procurement, 'investor')['negative_position_uzs']
        rid = uuid.uuid4()
        first = repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['investor'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id, client_request_id=rid,
        )
        second = repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['investor'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id, client_request_id=rid,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(_neg(ctx, procurement, 'investor')['negative_position_uzs'], Decimal('0.00'))

    def test_repayment_removes_negative_close_gate(self):
        from apps.partnerships.venture import procurement_close_blocking_reasons
        ctx, procurement = self._over_dividend_negative()
        before = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('отрицатель' in r.lower() for r in before), before)
        debt = _neg(ctx, procurement, 'investor')['negative_position_uzs']
        repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['investor'].id, amount=debt, currency='UZS',
            paid_to_account_id=ctx['cash_account'].id,
        )
        after = procurement_close_blocking_reasons(procurement=procurement)
        self.assertFalse(any('отрицатель' in r.lower() for r in after), after)


class CrossCurrencyRepaymentTests(TestCase):
    def test_repayment_in_usd_against_uzs_debt(self):
        from apps.finance.models import Account
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')
        create_writeoff(
            tenant_id=ctx['business'].id, lot_id=lot.id, warehouse_id=ctx['store'].id,
            quantity=2, reason='negligence', responsible_user_id=ctx['owner'].id, negligence=True,
        )
        usd_account = CashAccount.objects.create(
            tenant=ctx['business'], name='USD Cash', currency='USD', balance=Decimal('0.00'),
            kind=CashAccount.Kind.CASH,
            linked_account=Account.objects.get(tenant=ctx['business'], code='1000'),
        )
        debt = _neg(ctx, procurement, 'operator')['negative_position_uzs']  # UZS
        usd_amount = (debt / Decimal('12000')).quantize(Decimal('0.01'))
        repayment = repay_partner_venture_debt(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            partner_id=ctx['operator'].id, amount=usd_amount, currency='USD',
            paid_to_account_id=usd_account.id, fx_rate=Decimal('12000'),
        )
        # Cash lands in the USD account in native USD; debt cleared in functional UZS.
        usd_account.refresh_from_db()
        self.assertEqual(usd_account.balance, usd_amount)
        self.assertLess(_neg(ctx, procurement, 'operator')['negative_position_uzs'], Decimal('0.01'))
        debit, credit, credits = _credits_by_account(ctx['business'].id, repayment.pk)
        self.assertEqual(debit, credit)
        _assert_conservation_balanced(self, procurement, 'cross-currency')
