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

from ._helpers import build_tenant, seed_received_procurement
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

    def test_consigned_lot_has_is_owned_false(self):
        ctx = build_tenant()
        proc = create_workspace(
            tenant_id=ctx['business'].id,
            funding_source=Procurement.FundingSource.OWN_FUNDS,
            supplier_id=ctx['supplier'].id,
        )
        proc.goods_ownership = Procurement.GoodsOwnership.CONSIGNED
        proc.save(update_fields=['goods_ownership'])

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
