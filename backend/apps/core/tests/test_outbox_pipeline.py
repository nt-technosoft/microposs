from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.analytics.tasks import process_outbox_events
from apps.core.models import OutboxEvent
from apps.customers.services import record_customer_payment
from apps.finance.models import Account, CashAccount
from apps.finance.services import (
    exchange_currency,
    record_owner_contribution,
    refund_customer,
)
from apps.sales.models import SalePayment
from apps.sales.services import create_sale
from apps.suppliers.services import record_supplier_payment

from ._helpers import build_tenant, open_session, seed_received_procurement


class OutboxPipelineTests(TestCase):
    def test_operational_flows_publish_expected_outbox_events(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
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
            }],
        )

        event_types = set(
            OutboxEvent.objects
            .filter(tenant_id=ctx['business'].id)
            .values_list('event_type', flat=True)
        )
        self.assertTrue({
            'procurement.opened',
            'procurement.contribution_added',
            'procurement.items_paid',
            'procurement.expenses_paid',
            'procurement.received',
            'lot.transfer',
            'pos_session.opened',
            'sale.completed',
        }.issubset(event_types))

    def test_finance_and_counterparty_flows_publish_expected_outbox_events(self):
        ctx = build_tenant()
        seed_received_procurement(ctx)
        session = open_session(ctx)

        create_sale(
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

        record_customer_payment(
            tenant_id=ctx['business'].id,
            customer_id=ctx['customer'].id,
            amount=Decimal('100000.00'),
            payment_method='cash',
            currency='UZS',
            account_id=ctx['cash_account'].id,
        )

        ctx['supplier'].outstanding_balance = Decimal('500000.00')
        ctx['supplier'].save(update_fields=['outstanding_balance', 'updated_at'])
        record_supplier_payment(
            tenant_id=ctx['business'].id,
            supplier_id=ctx['supplier'].id,
            amount=Decimal('100000.00'),
            payment_method='cash',
        )

        record_owner_contribution(
            tenant_id=ctx['business'].id,
            amount=Decimal('500000.00'),
            currency='UZS',
            to_account_id=ctx['cash_account'].id,
        )

        usd_account = CashAccount.objects.create(
            tenant=ctx['business'],
            name='USD Cash',
            currency='USD',
            kind=CashAccount.Kind.CASH,
            linked_account=Account.objects.get(tenant=ctx['business'], code='1000'),
        )
        exchange_currency(
            tenant_id=ctx['business'].id,
            from_account_id=ctx['cash_account'].id,
            to_account_id=usd_account.id,
            from_amount=Decimal('120000.00'),
            rate=Decimal('0.000083'),
        )

        cash_sale = create_sale(
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
        refund_customer(
            tenant_id=ctx['business'].id,
            customer_id=ctx['customer'].id,
            sale_id=cash_sale.pk,
            amount=Decimal('50000.00'),
            currency='UZS',
            method='cash',
            account_id=ctx['cash_account'].id,
        )

        event_types = set(
            OutboxEvent.objects
            .filter(tenant_id=ctx['business'].id)
            .values_list('event_type', flat=True)
        )
        self.assertTrue({
            'customer.debt_accrued',
            'customer.payment',
            'supplier.payment',
            'finance.owner_contribution',
            'finance.currency_exchange',
            'finance.refund',
        }.issubset(event_types))

    @patch('apps.analytics.tasks.aggregate_daily_pnl.delay')
    def test_consumer_processes_known_events_and_marks_them_processed(self, aggregate_delay):
        ctx = build_tenant()
        event = OutboxEvent.objects.create(
            event_type='sale.completed',
            payload={'date': timezone.localdate().isoformat()},
            tenant_id=ctx['business'].id,
        )

        process_outbox_events()

        event.refresh_from_db()
        self.assertIsNotNone(event.processed_at)
        self.assertIsNone(event.failed_at)
        self.assertEqual(event.last_error, '')
        aggregate_delay.assert_called_once_with(
            ctx['business'].id,
            timezone.localdate().isoformat(),
        )

    def test_consumer_processes_supported_noop_events_without_false_failures(self):
        ctx = build_tenant()
        noop_event_types = [
            'investor.invite_created',
            'investor.invite_accepted',
            'procurement.updated',
            'procurement.balance_exchanged',
            'procurement.items_paid',
            'procurement.expenses_paid',
        ]
        events = [
            OutboxEvent.objects.create(
                event_type=event_type,
                payload={'id': index},
                tenant_id=ctx['business'].id,
            )
            for index, event_type in enumerate(noop_event_types, start=1)
        ]

        process_outbox_events()

        for event in events:
            event.refresh_from_db()
            self.assertIsNotNone(event.processed_at, event.event_type)
            self.assertIsNone(event.failed_at, event.event_type)
            self.assertEqual(event.last_error, '', event.event_type)

    def test_consumer_marks_unknown_events_failed(self):
        ctx = build_tenant()
        event = OutboxEvent.objects.create(
            event_type='unknown.event',
            payload={},
            tenant_id=ctx['business'].id,
        )

        process_outbox_events()

        event.refresh_from_db()
        self.assertIsNone(event.processed_at)
        self.assertIsNotNone(event.failed_at)
        self.assertEqual(event.attempts, 1)
        self.assertIn('Unhandled event type: unknown.event', event.last_error)
