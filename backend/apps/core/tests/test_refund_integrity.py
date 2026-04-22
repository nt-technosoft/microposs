from decimal import Decimal

from django.test import TestCase

from apps.finance.models import CashEntry, JournalEntry, Refund
from apps.finance.services import refund_customer
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class RefundIntegrityTests(TestCase):
    def test_cash_refund_creates_cash_entry_and_journal(self):
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

        ctx['cash_account'].balance = Decimal('300000.00')
        ctx['cash_account'].save(update_fields=['balance', 'updated_at'])

        refund = refund_customer(
            tenant_id=ctx['business'].id,
            customer_id=ctx['customer'].id,
            sale_id=sale.pk,
            amount=Decimal('50000.00'),
            currency='UZS',
            method=Refund.Method.CASH,
            account_id=ctx['cash_account'].id,
        )

        self.assertEqual(CashEntry.objects.filter(source_ref_type='refund', source_ref_id=refund.pk).count(), 1)
        self.assertEqual(JournalEntry.objects.filter(operation_id=refund.pk).count(), 1)
