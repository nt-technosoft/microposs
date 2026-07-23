"""E17 Phase 3 — procurement venture close lifecycle & read-only lock.

close_procurement_venture sets CLOSED only when every gate passes: a FINAL
settlement exists, no active lots, no negative positions, the conservation
invariant nets to zero in every pocket/currency, and no entitlement is left
hanging (available capital/profit not yet paid out). After CLOSED, every
economy-changing operation on the procurement is blocked.
"""

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.partnerships.agreement_services import (
    agreement_close_blocking_reasons,
    close_investment_agreement,
    pay_dividend,
)
from apps.partnerships.models import (
    InvestmentAgreement,
    Procurement,
    ProcurementSaleRealization,
    ProcurementVentureSettlement,
)
from apps.partnerships.venture import (
    close_procurement_venture,
    create_venture_settlement,
    procurement_close_blocking_reasons,
    procurement_venture_positions,
)
from apps.partnerships.workspace_support import add_agreement_contribution, add_agreement_withdrawal
from apps.risk.services import create_writeoff
from apps.sales.models import Return, SalePayment
from apps.sales.services import create_sale, process_return

from ._helpers import build_tenant, open_session, seed_received_procurement


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


def _final_settle(ctx, procurement):
    return create_venture_settlement(
        tenant_id=ctx['business'].id, procurement_id=procurement.id,
        settlement_type=ProcurementVentureSettlement.SettlementType.FINAL,
    )


def _pay_out_everything(ctx, procurement):
    """Withdraw all recovered capital and pay all available profit so nothing is
    left hanging (available == 0)."""
    positions = procurement_venture_positions(procurement=procurement)
    for partner_id, row in positions.items():
        cap = Decimal(str(row['capital_return_available_uzs']))
        if cap > 0:
            add_agreement_withdrawal(
                tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id,
                procurement_id=procurement.id, partner_id=partner_id,
                amount=cap, currency='UZS', from_account_id=ctx['cash_account'].id,
            )
        profit = Decimal(str(row['provisional_profit_available_uzs']))
        if profit > 0:
            pay_dividend(
                partner_id=partner_id, procurement_id=procurement.id, amount=profit,
                currency='UZS', from_account_id=ctx['cash_account'].id,
                tenant_id=ctx['business'].id,
            )


class ProcurementCloseGateTests(TestCase):
    def test_blocked_without_final_settlement(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')  # fully sold, no FINAL
        reasons = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('FINAL' in r or 'финальн' in r.lower() for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)

    def test_blocked_by_active_lots(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=5, unit_price='240000.00')  # 45 remain
        create_venture_settlement(
            tenant_id=ctx['business'].id, procurement_id=procurement.id,
            settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
        )
        reasons = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('товар' in r.lower() for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)

    def test_blocked_by_hanging_claim(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)  # FINAL, but nothing paid out → available > 0
        reasons = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('выплач' in r.lower() or 'claim' in r.lower() or 'долг' in r.lower()
                            for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)

    def test_blocked_by_conservation_residual(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)
        _pay_out_everything(ctx, procurement)
        # Inject a discrepancy AFTER a clean FINAL settlement.
        row = ProcurementSaleRealization.objects.filter(
            procurement=procurement,
            event_type=ProcurementSaleRealization.EventType.REALIZATION,
        ).first()
        ProcurementSaleRealization.objects.filter(pk=row.pk).update(
            capital_recovered_uzs=row.capital_recovered_uzs + Decimal('5000.00'),
        )
        reasons = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('residual' in r.lower() or 'сохранен' in r.lower()
                            or 'инвариант' in r.lower() for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)

    def test_blocked_by_negative_position(self):
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
        _sell(ctx, session, quantity=5, unit_price='100000.00')  # loss → negative position
        reasons = procurement_close_blocking_reasons(procurement=procurement)
        self.assertTrue(any('отрицатель' in r.lower() for r in reasons), reasons)


class ProcurementCloseHappyPathTests(TestCase):
    def test_full_close_sets_status_closed(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)
        _pay_out_everything(ctx, procurement)

        self.assertEqual(procurement_close_blocking_reasons(procurement=procurement), [])
        closed = close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)
        self.assertEqual(closed.status, Procurement.Status.CLOSED)
        self.assertIsNotNone(closed.closed_at)

    def test_close_is_idempotent(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)
        _pay_out_everything(ctx, procurement)
        rid = uuid.uuid4()
        close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id, client_request_id=rid)
        # second call is a no-op, not an error
        again = close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id, client_request_id=rid)
        self.assertEqual(again.status, Procurement.Status.CLOSED)


class ProcurementReadOnlyLockTests(TestCase):
    def _closed_procurement(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)
        _pay_out_everything(ctx, procurement)
        close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)
        return ctx, procurement, lot, session, sale

    def test_settlement_blocked_after_close(self):
        ctx, procurement, _, _, _ = self._closed_procurement()
        with self.assertRaises(ValueError):
            create_venture_settlement(
                tenant_id=ctx['business'].id, procurement_id=procurement.id,
                settlement_type=ProcurementVentureSettlement.SettlementType.CONSTRUCTIVE,
            )

    def test_writeoff_blocked_after_close(self):
        ctx, procurement, lot, _, _ = self._closed_procurement()
        with self.assertRaises(ValueError):
            create_writeoff(
                tenant_id=ctx['business'].id, lot_id=lot.id, warehouse_id=ctx['store'].id,
                quantity=1, reason='x', responsible_user_id=ctx['owner'].id, negligence=False,
            )

    def test_dividend_blocked_after_close(self):
        ctx, procurement, _, _, _ = self._closed_procurement()
        with self.assertRaises(ValueError):
            pay_dividend(
                partner_id=ctx['investor'].id, procurement_id=procurement.id,
                amount=Decimal('1.00'), currency='UZS',
                from_account_id=ctx['cash_account'].id, tenant_id=ctx['business'].id,
            )

    def test_withdrawal_blocked_after_close(self):
        ctx, procurement, _, _, _ = self._closed_procurement()
        with self.assertRaises(ValueError):
            add_agreement_withdrawal(
                tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id,
                procurement_id=procurement.id, partner_id=ctx['investor'].id,
                amount=Decimal('1.00'), currency='UZS', from_account_id=ctx['cash_account'].id,
            )

    def test_return_blocked_after_close(self):
        ctx, procurement, _, _, sale = self._closed_procurement()
        with self.assertRaises(ValueError):
            process_return(
                sale=sale, return_lines=[{'sale_line_id': sale.lines.first().id, 'quantity': 1}],
                resolution=Return.Resolution.RESTOCK, reason=Return.Reason.CLIENT_REFUSE,
                processed_by_id=ctx['cashier'].id, tenant_id=ctx['business'].id,
            )


class AgreementCloseTests(TestCase):
    def _full_close_procurement(self, ctx, procurement, session):
        _sell(ctx, session, quantity=50, unit_price='240000.00')
        _final_settle(ctx, procurement)
        _pay_out_everything(ctx, procurement)
        close_procurement_venture(tenant_id=ctx['business'].id, procurement_id=procurement.id)

    def test_blocked_until_procurements_closed(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        agreement = procurement.agreement
        reasons = agreement_close_blocking_reasons(agreement=agreement)
        self.assertTrue(any('приход' in r.lower() for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=agreement.id)

    def test_blocked_by_unsettled_net_position(self):
        # AGREED under-funding: investor contributes 66 vs agreed 70 → net != 0.
        from .test_e14_capital_advances import _build_funded, _receive
        ctx = build_tenant()
        procurement = _build_funded(
            ctx, planned=(Decimal('70'), Decimal('30')),
            profit=(Decimal('0.35'), Decimal('0.65')),
            contributions=(Decimal('66'), Decimal('34')),
        )
        _receive(ctx, procurement, share_basis='AGREED', allocations=(Decimal('66'), Decimal('34')))
        reasons = agreement_close_blocking_reasons(agreement=procurement.agreement)
        self.assertTrue(any('нетто-позиц' in r.lower() for r in reasons), reasons)

    def test_full_close_happy_path(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        self._full_close_procurement(ctx, procurement, session)
        agreement = procurement.agreement

        self.assertEqual(agreement_close_blocking_reasons(agreement=agreement), [])
        closed = close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=agreement.id)
        self.assertEqual(closed.status, InvestmentAgreement.Status.CLOSED)
        self.assertIsNotNone(closed.closed_at)

    def test_close_agreement_idempotent(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        self._full_close_procurement(ctx, procurement, session)
        close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id)
        again = close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id)
        self.assertEqual(again.status, InvestmentAgreement.Status.CLOSED)

    def test_agreement_read_only_after_close(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        self._full_close_procurement(ctx, procurement, session)
        close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id)
        with self.assertRaises(ValueError):
            add_agreement_contribution(
                tenant_id=ctx['business'].id, agreement_id=procurement.agreement_id,
                partner_id=ctx['investor'].id, amount=Decimal('10.00'), currency='USD',
            )

    def test_blocked_by_unreconciled_pool(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        self._full_close_procurement(ctx, procurement, session)
        agreement = procurement.agreement
        # Sanity: closeable before tampering.
        self.assertEqual(agreement_close_blocking_reasons(agreement=agreement), [])
        # Inject a pool discrepancy (physical balance no longer matches its records).
        pool = agreement.capital_account
        type(pool).objects.filter(pk=pool.pk).update(balance=Decimal(str(pool.balance)) + Decimal('1000.00'))
        agreement = InvestmentAgreement.objects.get(pk=agreement.id)  # fresh (uncached pool balance)
        reasons = agreement_close_blocking_reasons(agreement=agreement)
        self.assertTrue(any('пул' in r.lower() for r in reasons), reasons)
        with self.assertRaises(ValueError):
            close_investment_agreement(tenant_id=ctx['business'].id, agreement_id=agreement.id)
