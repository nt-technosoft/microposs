from decimal import Decimal

from django.test import TestCase

from apps.core.exceptions import ImmutableRecordError
from apps.inventory.models import Lot
from apps.partnerships.models import (
    ProcurementReceiveBatch,
    ProcurementReceiveBatchCapitalAllocation,
    ProcurementReceiveBatchExpense,
    ProcurementReceiveBatchLine,
)

from ._helpers import build_tenant, seed_received_procurement


class ImmutableReceiveSnapshotTests(TestCase):
    def test_lot_contract_snapshot_cannot_be_changed_after_receive(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        lot.contract_snapshot = {'tampered': True}

        with self.assertRaises(ImmutableRecordError):
            lot.save()

    def test_lot_cost_snapshot_cannot_be_changed_after_receive(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        lot.landed_cost_per_unit = Decimal('999.00')

        with self.assertRaises(ImmutableRecordError):
            lot.save()

    def test_lot_active_flag_can_still_change(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        lot.is_active = False
        lot.save(update_fields=['is_active', 'updated_at'])

        self.assertFalse(Lot.objects.get(pk=lot.pk).is_active)

    def test_receive_batch_documents_are_append_only(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)
        batch = procurement.receive_batches.get()
        line = ProcurementReceiveBatchLine.objects.get(batch=batch)
        expense = ProcurementReceiveBatchExpense.objects.get(batch=batch)
        allocation = ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=batch).first()

        batch.items_count = 999
        with self.assertRaises(ImmutableRecordError):
            batch.save()
        with self.assertRaises(ImmutableRecordError):
            batch.delete()

        line.quantity = Decimal('999')
        with self.assertRaises(ImmutableRecordError):
            line.save()
        with self.assertRaises(ImmutableRecordError):
            line.delete()

        expense.allocated_amount_uzs = Decimal('999')
        with self.assertRaises(ImmutableRecordError):
            expense.save()
        with self.assertRaises(ImmutableRecordError):
            expense.delete()

        allocation.amount_contract_currency = Decimal('999')
        with self.assertRaises(ImmutableRecordError):
            allocation.save()
        with self.assertRaises(ImmutableRecordError):
            allocation.delete()

