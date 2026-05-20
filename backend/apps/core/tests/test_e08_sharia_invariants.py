"""
E08 Phase 2 — Sharia accounting invariants.

These tests are architecture guards, not feature tests. They lock in the
business rules that must hold for the partnership / FIFO / append-only
ledger model to stay sharia-correct after Phase 2's source-of-truth
consolidation. They are expected to outlive Phase 2 itself.

Invariants covered:
  * Σ(profit_share) == 1.0 across AgreementPartner rows of one agreement
  * Σ(capital_share) == 1.0 in Lot.contract_snapshot.partners
  * FIFO ordering requires Lot.received_at NOT NULL (defended at DB level)
  * Append-only ledgers: AgreementContribution / AgreementWithdrawal /
    AgreementAllocation / PartnerLedgerEntry forbid physical delete
  * Immutable snapshots: Lot.contract_snapshot cannot be rewritten by a
    later InvestmentAgreement mutation
  * Derived InvestmentAgreement.balances == aggregate of contribution /
    withdrawal / allocation events
"""

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.partnerships.models import (
    AgreementAllocation,
    AgreementContribution,
    AgreementPartner,
    AgreementWithdrawal,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementPartnerLedger,
)
from apps.inventory.models import Lot
from apps.finance.models import JournalEntry, JournalLine
from apps.suppliers.models import SupplierPayable

from ._helpers import build_tenant, seed_received_procurement, open_session
from apps.partnerships.workspace import create_workspace, dispatch_workspace_action


_ONE = Decimal('1.000000')
_TOL = Decimal('0.0001')


class AgreementShareInvariants(TestCase):
    def test_partner_profit_share_sum_equals_one_per_agreement(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        agreement = procurement.agreement
        self.assertIsNotNone(agreement, 'Partnership procurement must have an agreement.')

        total = sum(
            (Decimal(str(member.profit_share)) for member in agreement.partners.all()),
            Decimal('0'),
        )
        self.assertLess(
            abs(total - _ONE), _TOL,
            f'Σ(profit_share) for agreement #{agreement.pk} = {total}; expected 1.0.',
        )


class LotSnapshotInvariants(TestCase):
    def test_received_at_is_not_null_at_db_level(self):
        # Verifies the migration that flipped Lot.received_at to NOT NULL
        # (Phase 1 / T-1.6) is still in place at the DB.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = 'inventory_lot' AND column_name = 'received_at'
                """
            )
            row = cursor.fetchone()
        self.assertIsNotNone(row, 'inventory_lot.received_at column not found.')
        self.assertEqual(row[0], 'NO', 'Lot.received_at must be NOT NULL.')

    def test_contract_snapshot_capital_shares_sum_to_one(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        snapshot = lot.contract_snapshot or {}
        partners = snapshot.get('partners') or []
        if not partners:
            self.skipTest('Lot contract_snapshot empty (non-partnership scenario).')
        total = sum(
            (Decimal(str(p.get('capital_share') or '0')) for p in partners),
            Decimal('0'),
        )
        self.assertLess(
            abs(total - _ONE), _TOL,
            f'Lot#{lot.pk}.contract_snapshot capital_share sum = {total}.',
        )

    def test_contract_snapshot_is_frozen_after_agreement_changes(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        original_snapshot = dict(lot.contract_snapshot or {})
        if not original_snapshot:
            self.skipTest('Lot contract_snapshot empty.')

        agreement = procurement.agreement
        # Mutate the agreement after the lot is born — the snapshot must stay.
        agreement.notes = 'agreement-mutated-after-receive'
        agreement.save(update_fields=['notes', 'updated_at'])

        lot.refresh_from_db()
        self.assertEqual(lot.contract_snapshot, original_snapshot)


class AppendOnlyLedgerInvariants(TestCase):
    def setUp(self):
        self.ctx = build_tenant()
        self.procurement, _ = seed_received_procurement(self.ctx)
        self.agreement = self.procurement.agreement

    def test_agreement_contribution_delete_is_forbidden(self):
        contribution = AgreementContribution.objects.filter(
            agreement=self.agreement,
        ).first()
        if contribution is None:
            self.skipTest('No AgreementContribution to test.')
        with self.assertRaises(ValueError):
            contribution.delete()

    def test_agreement_withdrawal_delete_is_forbidden(self):
        withdrawal = AgreementWithdrawal(
            tenant_id=self.ctx['business'].id,
            agreement=self.agreement,
            partner_id=self.ctx['investor'].id,
            amount=Decimal('1.00'),
            currency='UZS',
            fx_rate=Decimal('1'),
            date=timezone.now(),
        )
        withdrawal.save()
        with self.assertRaises(ValueError):
            withdrawal.delete()

    def test_agreement_allocation_delete_is_forbidden(self):
        allocation = AgreementAllocation.objects.filter(
            agreement=self.agreement,
        ).first()
        if allocation is None:
            self.skipTest('No AgreementAllocation to test.')
        with self.assertRaises(ValueError):
            allocation.delete()

    def test_partner_ledger_entry_delete_is_forbidden(self):
        ledger = ProcurementPartnerLedger.objects.filter(
            procurement=self.procurement,
        ).first()
        if ledger is None:
            self.skipTest('No ProcurementPartnerLedger to test.')
        entry = PartnerLedgerEntry.objects.filter(ledger=ledger).first()
        if entry is None:
            self.skipTest('No PartnerLedgerEntry to test.')
        with self.assertRaises(ValueError):
            entry.delete()


class DerivedAgreementBalanceInvariants(TestCase):
    def test_balances_property_matches_event_aggregate(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        agreement = procurement.agreement
        derived = agreement.balances

        # Independently recompute the aggregate so the property and the
        # ledger view cannot drift silently.
        expected: dict[str, Decimal] = {}

        def _bump(cur: str, delta: Decimal) -> None:
            key = str(cur or 'UZS').upper()
            expected[key] = expected.get(key, Decimal('0')) + delta

        for c in agreement.contributions.all():
            _bump(c.currency, Decimal(str(c.amount)))
        for w in agreement.withdrawals.all():
            _bump(w.currency, -Decimal(str(w.amount)))
        for a in agreement.allocations.all():
            amt = Decimal(str(a.amount))
            if a.direction == AgreementAllocation.Direction.TO_PROCUREMENT:
                _bump(a.currency, -amt)
            else:
                _bump(a.currency, amt)

        expected_view = {
            cur: str(value.quantize(Decimal('0.01')))
            for cur, value in expected.items()
        }
        self.assertEqual(derived, expected_view)


class LotOwnershipInvariants(TestCase):
    def test_owned_lot_has_is_owned_true(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)
        self.assertTrue(lot.is_owned)

    def test_consigned_receive_creates_no_payable_and_no_inventory_journal(self):
        ctx = build_tenant()
        proc, lot = self._seed_consigned_received(ctx)

        # No SupplierPayable created at receive time
        payables = SupplierPayable.objects.filter(procurement=proc)
        self.assertEqual(payables.count(), 0, 'CONSIGNED receive must not create any SupplierPayable')

        # No JournalEntry with operation_type='receipt' that debits inventory account 1100
        batch = lot.receive_batch_line.batch
        journal_lines = JournalLine.objects.filter(
            journal_entry__operation_type='receipt',
            journal_entry__operation_id=batch.id,
        )
        self.assertEqual(journal_lines.count(), 0, 'CONSIGNED receive must not write any journal entry')

    def test_consigned_procurement_rejects_expenses(self):
        ctx = build_tenant()
        proc = create_workspace(
            tenant_id=ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{'product_variant_id': ctx['variant'].id, 'quantity': 5,
                           'unit_purchase_price': '3000.00', 'currency': 'UZS', 'fx_rate': '1',
                           'goods_ownership': 'CONSIGNED'}],
                'expenses': [],
            }},
        )
        with self.assertRaises(ValueError, msg='CONSIGNED procurement must reject landed expenses'):
            dispatch_workspace_action(
                tenant_id=ctx['business'].id,
                procurement=proc,
                action='UPDATE_EXPENSES',
                payload={'payload': {
                    'expenses': [{'expense_type': 'CUSTOMS', 'amount': '500.00',
                                  'currency': 'UZS', 'fx_rate': '1'}],
                }},
            )

    @staticmethod
    def _seed_consigned_received(ctx):
        """Create OWN_FUNDS + CONSIGNED procurement, add items, receive. Returns (proc, lot)."""
        proc = create_workspace(
            tenant_id=ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc, action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{'product_variant_id': ctx['variant'].id, 'quantity': 10,
                           'unit_purchase_price': '3000.00', 'currency': 'UZS', 'fx_rate': '1',
                           'goods_ownership': 'CONSIGNED'}],
                'expenses': [],
            }},
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc, action='UPDATE_SETTLEMENT',
            payload={'payload': {'type': 'ON_SALE', 'total_amount_due': '30000.00',
                                 'currency_of_obligation': 'UZS'}},
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id, procurement=proc, action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': ctx['storage'].id}},
        )
        lot = Lot.objects.get(procurement_item__procurement=proc)
        return proc, lot

    def test_consigned_lot_has_is_owned_false(self):
        ctx = build_tenant()
        proc = create_workspace(
            tenant_id=ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=proc,
            action='UPDATE_ITEMS',
            payload={'payload': {
                'items': [{
                    'product_variant_id': ctx['variant'].id,
                    'quantity': 10,
                    'unit_purchase_price': '5000.00',
                    'currency': 'UZS',
                    'fx_rate': '1',
                    'goods_ownership': 'CONSIGNED',
                }],
                'expenses': [],
            }},
        )
        # ON_SALE + CONSIGNED is the legal combination; terms unlock items for receive.
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=proc,
            action='UPDATE_SETTLEMENT',
            payload={'payload': {
                'type': 'ON_SALE',
                'total_amount_due': '50000.00',
                'currency_of_obligation': 'UZS',
            }},
        )
        dispatch_workspace_action(
            tenant_id=ctx['business'].id,
            procurement=proc,
            action='RECEIVE_BATCH',
            payload={'payload': {'warehouse_id': ctx['storage'].id}},
        )
        lot = Lot.objects.get(procurement_item__procurement=proc)
        self.assertFalse(lot.is_owned)


class OwnedSaleNoConsignmentPayableInvariant(TestCase):
    """Separate class to avoid username collision with ConsignmentObligationInvariants setUp."""

    def test_owned_sale_does_not_create_consignment_payable(self):
        from apps.sales.services import create_sale
        ctx = build_tenant()
        _, _ = seed_received_procurement(ctx)
        session = open_session(ctx)
        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=None,
            lines=[{'product_variant_id': ctx['variant'].id,
                    'quantity': 1, 'unit_price': '300000.00'}],
            payments=[{'amount': '300000.00', 'currency': 'UZS',
                       'method': 'CASH', 'account_id': ctx['cash_account'].id}],
        )
        self.assertEqual(
            SupplierPayable.objects.filter(
                reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
            ).count(),
            0,
        )


class ConsignmentObligationInvariants(TestCase):
    """
    E09 Phase 2 — guards that consignment auto-obligation logic is correct.
    """

    def setUp(self):
        from apps.sales.services import create_sale
        self.create_sale = create_sale
        self.ctx = build_tenant()
        self.proc, self.lot = LotOwnershipInvariants._seed_consigned_received(self.ctx)
        self.session = open_session(self.ctx)

    def _sell_one(self, qty=1):
        return self.create_sale(
            tenant_id=self.ctx['business'].id,
            pos_session_id=self.session.id,
            location_id=self.ctx['store'].id,
            sold_by_id=self.ctx['cashier'].id,
            customer_id=None,
            lines=[{
                'product_variant_id': self.ctx['variant'].id,
                'quantity': qty,
                'unit_price': '5000.00',
            }],
            payments=[{
                'amount': str(Decimal('5000.00') * qty),
                'currency': 'UZS',
                'method': 'CASH',
                'account_id': self.ctx['cash_account'].id,
            }],
        )

    def test_consigned_sale_creates_payable_with_correct_amount(self):
        """Продажа CONSIGNED Lot → payable с правильной суммой и валютой."""
        sale = self._sell_one(qty=3)
        payables = SupplierPayable.objects.filter(
            procurement=self.proc,
            reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
        )
        self.assertEqual(payables.count(), 1)
        p = payables.first()
        # unit_purchase_price=3000 UZS, qty=3 → 9000
        self.assertEqual(p.original_amount, Decimal('9000.00'))
        self.assertEqual(p.currency_of_obligation, 'UZS')

    def test_consigned_payable_has_open_status_initially(self):
        """Созданный payable имеет status=OPEN и paid_amount=0."""
        self._sell_one(qty=2)
        p = SupplierPayable.objects.get(
            procurement=self.proc,
            reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
        )
        self.assertEqual(p.status, SupplierPayable.Status.OPEN)
        self.assertEqual(p.paid_amount, Decimal('0.00'))
        self.assertEqual(p.remaining_amount, p.original_amount)

    def test_multiple_consigned_sales_create_separate_payables(self):
        """Две продажи из одного Lot → два разных payable."""
        self._sell_one(qty=1)
        self._sell_one(qty=2)
        payables = SupplierPayable.objects.filter(
            procurement=self.proc,
            reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
        )
        self.assertEqual(payables.count(), 2)

    def test_consigned_sale_journal_credits_ap_not_inventory_with_correct_amount(self):
        """
        Journal для CONSIGNED продажи кредитует A/P (2000), не Inventory (1100).
        CR 2000 = unit_purchase_price × qty (в UZS).
        """
        sale = self._sell_one(qty=2)
        # There are multiple JournalEntry per sale; gather all lines across all of them.
        lines = list(
            JournalLine.objects.filter(
                journal_entry__operation_type='sale',
                journal_entry__operation_id=sale.pk,
            ).select_related('account')
        )
        account_codes = {line.account.code for line in lines}

        self.assertIn('5000', account_codes, 'DR COGS должен быть')
        self.assertIn('2000', account_codes, 'CR A/P должен быть для CONSIGNED')
        self.assertNotIn('1100', account_codes, 'CR Inventory не должно быть для CONSIGNED')

        ap_credit = sum(
            line.credit for line in lines if line.account.code == '2000'
        )
        # unit_purchase_price=3000, qty=2 → 6000 UZS
        self.assertEqual(ap_credit.quantize(Decimal('0.01')), Decimal('6000.00'))
