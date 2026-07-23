from decimal import Decimal

from django.test import TestCase

from apps.finance.models import Account, CashAccount, CashEntry, JournalEntry
from apps.partnerships.models import ProcurementSaleRealization
from apps.sales.models import Sale, SalePayment
from apps.sales.serializers import SaleDetailSerializer, SaleListSerializer
from apps.sales.services import create_sale

from ._helpers import build_tenant, open_session, seed_received_procurement


class SaleMultiPaymentTests(TestCase):
    def test_create_sale_creates_multiple_payments_and_profit_ledger_entries(self):
        ctx = build_tenant()
        procurement, lot = seed_received_procurement(ctx)
        session = open_session(ctx)

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 5,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[
                {
                    'amount': Decimal('600000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CASH,
                    'account_id': ctx['cash_account'].id,
                },
                {
                    'amount': Decimal('600000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CARD,
                    'account_id': ctx['card_account'].id,
                },
            ],
            notes='PR-9c multi-payment test',
        )

        sale.refresh_from_db()
        line = sale.lines.get()
        payments = list(sale.payments.order_by('id'))
        realizations = list(
            ProcurementSaleRealization.objects.filter(
                procurement_id=procurement.id,
                event_type=ProcurementSaleRealization.EventType.REALIZATION,
            ).order_by('partner_id')
        )

        self.assertEqual(sale.status, Sale.SaleStatus.COMPLETED)
        self.assertEqual(line.lot_id, lot.id)
        self.assertEqual(len(payments), 2)
        self.assertEqual({payments[0].method, payments[1].method}, {
            SalePayment.Method.CASH,
            SalePayment.Method.CARD,
        })

        cash_entries = list(CashEntry.objects.filter(source_ref_type='sale_payment').order_by('id'))
        journals = list(JournalEntry.objects.filter(operation_type='sale'))
        self.assertEqual(len(cash_entries), 2)
        self.assertEqual(len(journals), 3)

        paid_total = sum(payment.amount for payment in payments)
        self.assertEqual(paid_total, sale.total_amount)
        self.assertEqual(sale.total_amount, line.unit_price * line.quantity)
        self.assertEqual(sale.total_cogs, line.unit_landed_cost * line.quantity)

        account_map: dict[str, tuple[Decimal, Decimal]] = {}
        for journal in journals:
            for journal_line in journal.lines.all():
                current = account_map.get(journal_line.account.code, (Decimal('0.00'), Decimal('0.00')))
                account_map[journal_line.account.code] = (
                    current[0] + journal_line.debit,
                    current[1] + journal_line.credit,
                )

        self.assertEqual(account_map['1000'], (Decimal('600000.00'), Decimal('0.00')))
        self.assertEqual(account_map['1010'], (Decimal('600000.00'), Decimal('0.00')))
        self.assertEqual(account_map['4000'], (Decimal('0.00'), sale.total_amount))
        self.assertEqual(account_map['5000'], (sale.total_cogs, Decimal('0.00')))
        self.assertEqual(account_map['1100'], (Decimal('0.00'), sale.total_cogs))

        snapshot = line.profit_distribution_snapshot
        self.assertSetEqual(
            set(snapshot.keys()),
            {str(ctx['investor'].id), str(ctx['operator'].id)},
        )
        snapshot_total = sum(Decimal(str(value)) for value in snapshot.values())
        self.assertEqual(
            snapshot_total,
            (sale.total_amount - sale.total_cogs).quantize(Decimal('0.01')),
        )

        realized = {r.partner_id: r.provisional_profit_uzs for r in realizations}
        self.assertEqual(len(realized), 2)
        self.assertEqual(
            realized[ctx['investor'].id],
            Decimal(str(snapshot[str(ctx['investor'].id)])),
        )
        self.assertEqual(
            realized[ctx['operator'].id],
            Decimal(str(snapshot[str(ctx['operator'].id)])),
        )

        self.assertEqual(lot.stocks.get(warehouse=ctx['store']).quantity_remaining, 50 - line.quantity)

    def test_mixed_cash_and_credit_sale_covers_revenue_and_cogs_in_journal(self):
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
                'quantity': 2,
                'unit_price': Decimal('240000.00'),
            }],
            payments=[
                {
                    'amount': Decimal('200000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CASH,
                    'account_id': ctx['cash_account'].id,
                },
                {
                    'amount': Decimal('280000.00'),
                    'currency': 'UZS',
                    'fx_rate': Decimal('1'),
                    'method': SalePayment.Method.CREDIT,
                },
            ],
        )

        journals = list(
            JournalEntry.objects
            .filter(operation_type='sale', operation_id=sale.pk)
            .prefetch_related('lines__account')
        )
        self.assertEqual(len(journals), 3)

        account_map: dict[str, tuple[Decimal, Decimal]] = {}
        for journal in journals:
            for journal_line in journal.lines.all():
                current = account_map.get(journal_line.account.code, (Decimal('0.00'), Decimal('0.00')))
                account_map[journal_line.account.code] = (
                    current[0] + journal_line.debit,
                    current[1] + journal_line.credit,
                )

        self.assertEqual(account_map['1000'], (Decimal('200000.00'), Decimal('0.00')))
        self.assertEqual(account_map['1200'], (Decimal('280000.00'), Decimal('0.00')))
        self.assertEqual(account_map['4000'], (Decimal('0.00'), sale.total_amount))
        self.assertEqual(account_map['5000'], (sale.total_cogs, Decimal('0.00')))
        self.assertEqual(account_map['1100'], (Decimal('0.00'), sale.total_cogs))

        list_payload = SaleListSerializer(sale).data
        detail_payload = SaleDetailSerializer(sale).data

        self.assertEqual(
            list_payload['payment_methods'],
            [SalePayment.Method.CASH, SalePayment.Method.CREDIT],
        )
        self.assertEqual(
            detail_payload['payment_methods'],
            [SalePayment.Method.CASH, SalePayment.Method.CREDIT],
        )

    def test_usd_cash_sale_keeps_cash_native_and_journal_functional(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)
        usd_cash = CashAccount.objects.create(
            tenant=ctx['business'],
            name='USD Cash',
            currency='USD',
            kind=CashAccount.Kind.CASH,
            linked_account=Account.objects.get(tenant=ctx['business'], code='1000'),
        )

        sale = create_sale(
            tenant_id=ctx['business'].id,
            pos_session_id=session.id,
            location_id=ctx['store'].id,
            sold_by_id=ctx['cashier'].id,
            customer_id=ctx['customer'].id,
            lines=[{
                'product_variant_id': ctx['variant'].id,
                'quantity': 1,
                'operation_currency': 'USD',
                'operation_unit_price': Decimal('20.00'),
                'fx_rate': Decimal('12000.00'),
                'unit_price': Decimal('240000.00'),
            }],
            payments=[{
                'amount': Decimal('20.00'),
                'currency': 'USD',
                'fx_rate': Decimal('12000.00'),
                'method': SalePayment.Method.CASH,
                'account_id': usd_cash.id,
            }],
        )

        usd_cash.refresh_from_db()
        line = sale.lines.get()
        payment = sale.payments.get()
        cash_entry = CashEntry.objects.get(source_ref_type='sale_payment', source_ref_id=payment.id)

        self.assertEqual(sale.total_amount, Decimal('240000.00'))
        self.assertEqual(line.operation_currency, 'USD')
        self.assertEqual(line.operation_unit_price, Decimal('20.00'))
        self.assertEqual(line.unit_price, Decimal('240000.00'))
        self.assertEqual(payment.amount, Decimal('20.00'))
        self.assertEqual(payment.currency, 'USD')
        self.assertEqual(cash_entry.amount, Decimal('20.00'))
        self.assertEqual(usd_cash.balance, Decimal('20.00'))

        revenue = Decimal('0.00')
        debit_cash = Decimal('0.00')
        for journal in JournalEntry.objects.filter(operation_type='sale', operation_id=sale.id):
            for journal_line in journal.lines.select_related('account'):
                if journal_line.account.code == '4000':
                    revenue += journal_line.credit - journal_line.debit
                if journal_line.account.code == '1000':
                    debit_cash += journal_line.debit - journal_line.credit
        self.assertEqual(revenue, Decimal('240000.00'))
        self.assertEqual(debit_cash, Decimal('240000.00'))
