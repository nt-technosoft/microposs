from decimal import Decimal

from django.test import TestCase

from apps.partnerships.models import PartnerLedgerEntry
from apps.risk.services import build_writeoff_preview, create_writeoff

from ._helpers import build_tenant, seed_received_procurement


class WriteoffFinmodelTests(TestCase):
    def test_writeoff_preview_shows_loss_distribution(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)

        preview = build_writeoff_preview(
            tenant_id=ctx['business'].id,
            lot_id=lot.id,
            warehouse_id=ctx['storage'].id,
            quantity=2,
            negligence=False,
        )

        self.assertEqual(preview['lot_id'], lot.id)
        self.assertEqual(preview['quantity'], 2)
        self.assertEqual(preview['loss_amount'], str((lot.landed_cost_per_unit * 2).quantize(Decimal('0.01'))))
        self.assertIn(str(ctx['investor'].id), preview['loss_distribution'])
        self.assertIn(str(ctx['operator'].id), preview['loss_distribution'])

    def test_negligence_writeoff_allocates_loss_to_business_operator(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)

        risk_event = create_writeoff(
            tenant_id=ctx['business'].id,
            lot_id=lot.id,
            warehouse_id=ctx['storage'].id,
            quantity=1,
            reason='Брак по вине бизнеса',
            responsible_user_id=ctx['owner'].id,
            negligence=True,
        )

        loss_entries = list(
            PartnerLedgerEntry.objects.filter(
                ledger__procurement_id=procurement.id,
                entry_type=PartnerLedgerEntry.EntryType.LOSS_INCURRED,
            ).order_by('ledger__partner_id')
        )
        self.assertFalse(risk_event.affects_investor)
        self.assertEqual(len(loss_entries), 1)
        self.assertEqual(loss_entries[0].ledger.partner_id, ctx['operator'].id)
        self.assertEqual(loss_entries[0].amount, lot.landed_cost_per_unit.quantize(Decimal('0.01')))
