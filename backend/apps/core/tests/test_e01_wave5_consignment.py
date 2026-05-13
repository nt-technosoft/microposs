"""
Wave 5 — Consignment Return processing tests.

Covers all 4 dispositions:
  - RETURN_TO_SUPPLIER     (stock -, payable - agreed_price * qty)
  - DISPOSE_SUPPLIER_LOSS  (stock -, payable - cost * qty)
  - DISPOSE_BUSINESS_LOSS  (stock -, payable unchanged)
  - CONVERT_TO_OWN         (split lot: old qty -, new owned lot, payable + agreed * qty)
And mixed scenarios within a single ConsignmentReturn document.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.inventory.models import Lot, LotStock, StockMovement
from apps.partnerships.models import (
    ConsignmentReturn,
    ConsignmentReturnLine,
    Procurement,
)
from apps.partnerships.services import (
    add_contribution,
    open_procurement,
    pay_procurement_items,
    process_consignment_return,
    receive_procurement,
)
from apps.suppliers.models import (
    ConsignmentAgreement,
    SupplierPayable,
)

from ._helpers import build_tenant


def _seed_consignment_procurement(
    ctx, *, qty=10, unit_price='100', margin='0.20',
):
    """Open and receive a CONSIGNMENT-typed procurement."""
    agreement = ConsignmentAgreement.objects.create(
        tenant=ctx['business'],
        supplier=ctx['supplier'],
        rule_type=ConsignmentAgreement.RuleType.MARGIN,
        rule_value=Decimal(margin),
        damage_liability_on_business=False,
    )
    total = Decimal(qty) * Decimal(unit_price)
    proc = open_procurement(
        tenant_id=ctx['business'].id,
        procurement_type=Procurement.Type.OWN_FUNDS,
        supplier_id=ctx['supplier'].id,
        items=[{
            'product_variant_id': ctx['variant'].id,
            'quantity': Decimal(qty),
            'unit_purchase_price': Decimal(unit_price),
            'currency': 'UZS',
            'fx_rate': Decimal('1'),
        }],
    )
    add_contribution(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        partner_id=ctx['operator'].id,
        amount=total, currency='UZS', fx_rate=Decimal('1'),
    )
    pay_procurement_items(tenant_id=ctx['business'].id, procurement_id=proc.id)
    receive_procurement(
        tenant_id=ctx['business'].id,
        procurement_id=proc.id,
        destination_warehouse_id=ctx['storage'].id,
        terms_payload={
            'type': 'CONSIGNMENT',
            'currency_of_obligation': 'UZS',
            'total_amount_due': str(total),
            'consignment_agreement_id': agreement.id,
        },
    )
    payable = SupplierPayable.objects.get(procurement=proc)
    lot = Lot.objects.get(procurement_item__procurement=proc)
    return proc, payable, lot, agreement


def _create_return(business, proc, supplier, lines):
    """lines: list of (lot, qty, disposition, agreed_price)."""
    ret = ConsignmentReturn.objects.create(
        tenant=business,
        procurement=proc,
        supplier=supplier,
        return_date=timezone.now(),
        status=ConsignmentReturn.Status.DRAFT,
    )
    for (lot, qty, disp, price) in lines:
        ConsignmentReturnLine.objects.create(
            tenant=business,
            consignment_return=ret,
            lot=lot,
            quantity=Decimal(qty),
            disposition=disp,
            agreed_price_per_unit=Decimal(price),
        )
    return ret


class ReturnToSupplierTests(TestCase):
    def test_full_return_reduces_stock_and_payable(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')

        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[
                (lot, 10, ConsignmentReturnLine.Disposition.RETURN_TO_SUPPLIER, '100'),
            ],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )

        ret.refresh_from_db()
        self.assertEqual(ret.status, ConsignmentReturn.Status.CONFIRMED)

        # Stock = 0
        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])
        self.assertEqual(stock.quantity_remaining, 0)

        # Payable - 10 * 100 = 1000 → fully paid (assume original was 1000)
        payable.refresh_from_db()
        self.assertEqual(payable.original_amount, Decimal('0.00'))
        self.assertEqual(payable.remaining_amount, Decimal('0.00'))
        self.assertEqual(payable.status, SupplierPayable.Status.FULLY_PAID)

        # Stock movement CONSIGNMENT_RETURN_OUT
        mov = StockMovement.objects.filter(
            lot=lot, movement_type=StockMovement.MovementType.CONSIGNMENT_RETURN_OUT,
        ).first()
        self.assertIsNotNone(mov)
        self.assertEqual(mov.quantity, -10)


class DisposeSupplierLossTests(TestCase):
    def test_dispose_supplier_loss_reduces_payable_by_cost(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')

        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[(lot, 4, ConsignmentReturnLine.Disposition.DISPOSE_SUPPLIER_LOSS, '100')],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )

        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])
        self.assertEqual(stock.quantity_remaining, 6)

        payable.refresh_from_db()
        # cost_per_unit = landed_cost = 100, reduction = 4*100 = 400
        self.assertEqual(payable.original_amount, Decimal('600.00'))
        self.assertEqual(payable.remaining_amount, Decimal('600.00'))


class DisposeBusinessLossTests(TestCase):
    def test_dispose_business_loss_keeps_payable_intact(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')

        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[(lot, 3, ConsignmentReturnLine.Disposition.DISPOSE_BUSINESS_LOSS, '100')],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )

        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])
        self.assertEqual(stock.quantity_remaining, 7)

        payable.refresh_from_db()
        # Payable untouched
        self.assertEqual(payable.original_amount, Decimal('1000.00'))
        self.assertEqual(payable.remaining_amount, Decimal('1000.00'))


class ConvertToOwnTests(TestCase):
    def test_convert_creates_new_owned_lot_and_adds_payable(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')
        original_payable_amount = payable.original_amount

        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[(lot, 5, ConsignmentReturnLine.Disposition.CONVERT_TO_OWN, '90')],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )

        # Original lot: 5 left
        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])
        self.assertEqual(stock.quantity_remaining, 5)

        # New OWNED lot exists
        new_lot = Lot.objects.exclude(pk=lot.pk).get(
            product_variant=lot.product_variant
        )
        self.assertEqual(new_lot.landed_cost_per_unit, Decimal('90.00'))
        self.assertEqual(new_lot.contract_snapshot, {})  # owned

        new_stock = LotStock.objects.get(lot=new_lot, warehouse=ctx['storage'])
        self.assertEqual(new_stock.quantity_remaining, 5)

        # Payable + 5 * 90 = 450 over original
        payable.refresh_from_db()
        self.assertEqual(
            payable.original_amount,
            original_payable_amount + Decimal('450.00'),
        )


class MixedDispositionTests(TestCase):
    def test_mixed_return_dispose_business_loss(self):
        """6 RETURN_TO_SUPPLIER + 2 DISPOSE_BUSINESS_LOSS + 2 left in stock."""
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')

        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[
                (lot, 6, ConsignmentReturnLine.Disposition.RETURN_TO_SUPPLIER, '100'),
                (lot, 2, ConsignmentReturnLine.Disposition.DISPOSE_BUSINESS_LOSS, '100'),
            ],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )

        stock = LotStock.objects.get(lot=lot, warehouse=ctx['storage'])
        self.assertEqual(stock.quantity_remaining, 2)

        payable.refresh_from_db()
        # Only 6 * 100 = 600 reduction (DISPOSE_BUSINESS_LOSS doesn't reduce)
        self.assertEqual(payable.original_amount, Decimal('400.00'))


class ConsignmentReturnGuardTests(TestCase):
    def test_cannot_process_twice(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=10, unit_price='100')
        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[(lot, 1, ConsignmentReturnLine.Disposition.RETURN_TO_SUPPLIER, '100')],
        )
        process_consignment_return(
            tenant_id=ctx['business'].id,
            consignment_return_id=ret.id,
            warehouse_id=ctx['storage'].id,
        )
        with self.assertRaises(ValueError):
            process_consignment_return(
                tenant_id=ctx['business'].id,
                consignment_return_id=ret.id,
                warehouse_id=ctx['storage'].id,
            )

    def test_overdraw_rejected(self):
        ctx = build_tenant()
        proc, payable, lot, _ = _seed_consignment_procurement(ctx, qty=5, unit_price='100')
        ret = _create_return(
            ctx['business'], proc, ctx['supplier'],
            lines=[(lot, 10, ConsignmentReturnLine.Disposition.RETURN_TO_SUPPLIER, '100')],
        )
        with self.assertRaises(ValueError):
            process_consignment_return(
                tenant_id=ctx['business'].id,
                consignment_return_id=ret.id,
                warehouse_id=ctx['storage'].id,
            )
