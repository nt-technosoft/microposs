from decimal import Decimal

from django.test import TestCase

from apps.partnerships.venture import create_venture_settlement, procurement_venture_positions
from apps.risk.services import build_writeoff_preview, create_writeoff
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


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

        self.assertFalse(risk_event.affects_investor)

        # E17: a negligence writeoff records partner loss only as a venture
        # realization (partner-liability), not a legacy LOSS_INCURRED ledger row.
        positions = procurement_venture_positions(procurement=procurement)
        self.assertEqual(
            positions[ctx['operator'].id]['loss_uzs'],
            lot.landed_cost_per_unit.quantize(Decimal('0.01')),
        )
        self.assertEqual(
            positions[ctx['operator'].id]['negative_position_uzs'],
            lot.landed_cost_per_unit.quantize(Decimal('0.01')),
        )

    def test_partner_liability_writeoff_restores_innocent_partner_capital_on_settlement(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx, qty=10, unit_usd=10, customs_usd=0)
        session = open_session(ctx)

        create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('180000.00'),
            }],
            payments=[{
                'amount': Decimal('900000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )
        create_writeoff(
            tenant_id=ctx['business'].id,
            lot_id=lot.id,
            warehouse_id=ctx['store'].id,
            quantity=5,
            reason='Утрата по вине бизнеса',
            responsible_user_id=ctx['owner'].id,
            negligence=True,
        )

        create_venture_settlement(
            tenant_id=ctx['business'].id,
            procurement_id=procurement.id,
            settlement_type='FINAL',
        )
        positions = procurement_venture_positions(procurement=procurement)
        investor = positions[ctx['investor'].id]
        operator = positions[ctx['operator'].id]

        self.assertEqual(investor['capital_return_available_uzs'], Decimal('840000.00'))
        self.assertEqual(investor['provisional_profit_available_uzs'], Decimal('120000.00'))
        self.assertEqual(investor['remaining_inventory_capital_uzs'], Decimal('0.00'))
        self.assertEqual(investor['negative_position_uzs'], Decimal('0.00'))
        self.assertEqual(investor['liability_capital_recovered_uzs'], Decimal('420000.00'))

        self.assertEqual(operator['capital_return_available_uzs'], Decimal('180000.00'))
        self.assertEqual(operator['provisional_profit_available_uzs'], Decimal('180000.00'))
        self.assertEqual(operator['partner_liability_loss_uzs'], Decimal('600000.00'))
        self.assertEqual(operator['negative_position_uzs'], Decimal('600000.00'))
        self.assertEqual(operator['remaining_inventory_capital_uzs'], Decimal('0.00'))
