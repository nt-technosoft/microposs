from decimal import Decimal

from django.test import TestCase

from apps.customers.models import ReceivableEntry
from apps.finance.models import JournalEntry
from apps.sales.models import SalePayment
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class SaleCreditIntegrityTests(TestCase):
    def test_credit_sale_accrues_receivable_and_writes_sale_journal(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['storage'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 2,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('480000.00'),
                'currency': 'UZS',
                'fx_rate': Decimal('1'),
                'method': SalePayment.Method.CREDIT,
            }],
        )

        receivable_entry = ReceivableEntry.objects.get(source_ref=f'sale:{sale.pk}')
        customer_receivable = ctx['customer'].receivable
        journals = JournalEntry.objects.filter(operation_type='sale', operation_id=sale.pk)

        self.assertEqual(receivable_entry.amount, Decimal('480000.00'))
        self.assertEqual(customer_receivable.balances['UZS'], '480000.00')
        self.assertEqual(journals.count(), 1)
