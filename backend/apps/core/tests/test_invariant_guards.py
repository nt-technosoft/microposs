from decimal import Decimal

from django.test import TestCase

from apps.core.exceptions import ImmutableRecordError
from apps.finance.models import JournalEntry
from apps.inventory.models import Lot, Receipt
from apps.partnerships.models import Procurement
from apps.partnerships.services import open_procurement, add_contribution, add_withdrawal, receive_procurement
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class InvariantGuardTests(TestCase):
    def test_received_procurement_is_immutable(self):
        ctx = build_tenant()
        procurement, _ = seed_received_procurement(ctx)

        procurement.notes = 'mutated after receive'
        with self.assertRaises(ImmutableRecordError):
            procurement.save()

    def test_sale_delete_is_forbidden(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CASH,
                'account_id': ctx['cash_account'].id,
            }],
        )

        with self.assertRaisesMessage(ValueError, 'Physical delete forbidden for Sale.'):
            sale.delete()

    def test_journal_entry_delete_is_forbidden(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)
        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 1,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('240000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CREDIT,
            }],
        )
        journal = JournalEntry.objects.filter(
            operation_type='sale',
            operation_id=sale.pk,
        ).order_by('id').first()
        self.assertIsNotNone(journal)

        with self.assertRaisesMessage(ValueError, 'Physical delete forbidden for JournalEntry.'):
            journal.delete()

    def test_lot_delete_is_forbidden(self):
        ctx = build_tenant()
        _, lot = seed_received_procurement(ctx)

        with self.assertRaisesMessage(ValueError, 'Physical delete forbidden for Lot.'):
            lot.delete()

    def test_receipt_delete_is_forbidden(self):
        ctx = build_tenant()
        receipt = Receipt.objects.create(
            tenant_id=ctx['business'].id,
            receipt_type=Receipt.ReceiptType.BUSINESS_OWNED,
            status=Receipt.ReceiptStatus.DRAFT,
            date=ctx['business'].created_at,
            destination=ctx['storage'],
        )

        with self.assertRaisesMessage(ValueError, 'Physical delete forbidden for Receipt.'):
            receipt.delete()

    def test_confirmed_receipt_is_immutable(self):
        ctx = build_tenant()
        receipt = Receipt.objects.create(
            tenant_id=ctx['business'].id,
            receipt_type=Receipt.ReceiptType.BUSINESS_OWNED,
            status=Receipt.ReceiptStatus.CONFIRMED,
            date=ctx['business'].created_at,
            destination=ctx['storage'],
        )
        receipt.notes = 'mutated'

        with self.assertRaises(ImmutableRecordError):
            receipt.save()

    def test_lot_requires_source_document(self):
        ctx = build_tenant()

        with self.assertRaisesMessage(ValueError, 'Lot must originate from receipt or procurement item.'):
            Lot.objects.create(
                tenant=ctx['business'],
                product_variant=ctx['variant'],
                quantity_initial=1,
                unit_purchase_price=Decimal('10.00'),
                landed_cost_per_unit=Decimal('10.00'),
            )

    def test_partnership_profit_share_sum_must_equal_one(self):
        ctx = build_tenant()

        with self.assertRaisesMessage(ValueError, 'Sum of partner profit_share must equal 1.0.'):
            open_procurement(
                tenant_id=ctx['business'].id,
                procurement_type=Procurement.Type.PARTNERSHIP,
                supplier_id=ctx['supplier'].id,
                contract={
                    'mudaraba_ratio': Decimal('0.571429'),
                    'planned_budget': Decimal('100'),
                    'currency': 'USD',
                    'partners': [
                        {
                            'partner_id': ctx['investor'].id,
                            'role': 'INVESTOR',
                            'planned_capital_share': Decimal('70'),
                            'profit_share': Decimal('0.3'),
                        },
                        {
                            'partner_id': ctx['operator'].id,
                            'role': 'OPERATOR',
                            'planned_capital_share': Decimal('30'),
                            'profit_share': Decimal('0.6'),
                        },
                    ],
                },
                items=[{
                    'product_variant_id': ctx['variant'].id,
                    'quantity': Decimal('1'),
                    'unit_purchase_price': Decimal('10'),
                    'currency': 'USD',
                    'fx_rate': Decimal('12000'),
                }],
            )
