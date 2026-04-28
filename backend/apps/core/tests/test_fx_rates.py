from datetime import date
from decimal import Decimal
import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import Business
from apps.finance.models import ExchangeRate, Expense
from apps.finance.tasks import refresh_daily_fx_rates
from django_celery_beat.models import PeriodicTask


class FxRateApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('bootstrap_demo')
        cls.tenant = Business.objects.order_by('id').first()
        assert cls.tenant is not None

    def _auth_owner(self) -> None:
        token_response = self.client.post('/api/v1/auth/token/', {
            'username': 'owner',
            'password': 'Owner123!',
        }, format='json')
        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        access = token_response.data.get('access')
        self.assertTrue(access)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

    def test_owner_can_create_manual_rate_and_read_latest(self):
        self._auth_owner()

        create_response = self.client.post('/api/v1/finance/fx-rates/manual/', {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
            'rate_date': '2026-04-16',
            'rate': '12650.000000',
            'notes': 'Manual market close rate',
        }, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data['base_currency'], 'USD')
        self.assertEqual(create_response.data['quote_currency'], 'UZS')
        self.assertEqual(create_response.data['source'], 'MANUAL')
        self.assertTrue(create_response.data['is_manual'])

        latest_response = self.client.get('/api/v1/finance/fx-rates/latest/', {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
            'on_date': '2026-04-16',
        })
        self.assertEqual(latest_response.status_code, status.HTTP_200_OK)
        self.assertEqual(latest_response.data['rate'], '12650.000000')

    def test_latest_usd_uzs_returns_not_found_when_history_is_empty(self):
        self._auth_owner()
        ExchangeRate.objects.filter(tenant=self.tenant, base_currency='USD', quote_currency='UZS').delete()

        response = self.client.get('/api/v1/finance/fx-rates/latest/', {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 'fx_rate_missing')

    def test_expense_uses_stored_rate_when_fx_not_passed(self):
        self._auth_owner()

        ExchangeRate.objects.create(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=date(2026, 4, 15),
            rate=Decimal('12500.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Test manual rate',
            raw_payload={},
        )

        response = self.client.post('/api/v1/finance/expenses/', {
            'title': 'USD expense from history rate',
            'category': 'ops',
            'payment_method': 'cash',
            'operation_currency': 'USD',
            'operation_amount': '10.00',
            'occurred_at': '2026-04-15T10:30:00Z',
            'notes': 'FX resolver smoke',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        expense = Expense.objects.get(pk=response.data['id'])
        self.assertEqual(expense.fx_rate_snapshot, Decimal('12500.000000'))
        self.assertEqual(expense.functional_amount_uzs, Decimal('125000.00'))

    @patch('apps.finance.fx_rates.fetch_official_cbu_rate')
    def test_daily_fx_task_keeps_manual_rate_when_overwrite_disabled(self, fetch_rate):
        target_date = timezone.localdate()
        fetch_rate.return_value = (
            Decimal('12072.960000'),
            target_date,
            {'Ccy': 'USD', 'Rate': '12072.96', 'Date': target_date.strftime('%d.%m.%Y')},
        )
        ExchangeRate.all_objects.filter(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        ).delete()
        ExchangeRate.objects.create(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
            rate=Decimal('12100.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Manual operator rate',
            raw_payload={},
        )

        stats = refresh_daily_fx_rates(
            base_currency='USD',
            quote_currency='UZS',
            overwrite_manual=False,
        )

        self.assertGreaterEqual(stats['tenants'], 1)
        row = ExchangeRate.objects.get(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        )
        self.assertEqual(row.rate, Decimal('12100.000000'))
        self.assertEqual(row.source, ExchangeRate.Source.MANUAL)
        self.assertTrue(row.is_manual)

    @patch('apps.finance.fx_rates.fetch_official_cbu_rate')
    def test_daily_fx_task_overwrites_manual_rate_when_enabled(self, fetch_rate):
        target_date = timezone.localdate()
        fetch_rate.return_value = (
            Decimal('12072.960000'),
            target_date,
            {'Ccy': 'USD', 'Rate': '12072.96', 'Date': target_date.strftime('%d.%m.%Y')},
        )
        ExchangeRate.all_objects.filter(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        ).delete()
        ExchangeRate.objects.create(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
            rate=Decimal('12100.000000'),
            source=ExchangeRate.Source.MANUAL,
            is_manual=True,
            notes='Manual operator rate',
            raw_payload={},
        )

        stats = refresh_daily_fx_rates(
            base_currency='USD',
            quote_currency='UZS',
            overwrite_manual=True,
        )

        self.assertGreaterEqual(stats['tenants'], 1)
        row = ExchangeRate.objects.get(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        )
        self.assertEqual(row.rate, Decimal('12072.960000'))
        self.assertEqual(row.source, ExchangeRate.Source.CBU)
        self.assertFalse(row.is_manual)

    @override_settings(
        FX_SYNC_BASE_CURRENCY='USD',
        FX_SYNC_QUOTE_CURRENCY='UZS',
        FX_SYNC_TIMEZONE='Asia/Tashkent',
        FX_SYNC_HOUR=8,
        FX_SYNC_MINUTE=5,
        FX_SYNC_OVERWRITE_MANUAL=True,
    )
    def test_setup_fx_rate_schedule_uses_settings_and_persists_kwargs(self):
        out = io.StringIO()
        call_command('setup_fx_rate_schedule', stdout=out)

        task = PeriodicTask.objects.get(name='finance.fx.daily.refresh.usduzs')
        self.assertEqual(task.task, 'apps.finance.tasks.refresh_daily_fx_rates')
        self.assertTrue(task.enabled)
        self.assertEqual(task.crontab.hour, '8')
        self.assertEqual(task.crontab.minute, '5')
        self.assertEqual(str(task.crontab.timezone), 'Asia/Tashkent')
        self.assertEqual(json.loads(task.kwargs), {
            'base_currency': 'USD',
            'quote_currency': 'UZS',
            'overwrite_manual': True,
        })

    @patch('apps.finance.fx_rates.fetch_official_cbu_rate')
    def test_sync_exchange_rates_command_creates_official_rate(self, fetch_rate):
        target_date = date(2026, 4, 18)
        fetch_rate.return_value = (
            Decimal('12050.500000'),
            target_date,
            {'Ccy': 'USD', 'Rate': '12050.50', 'Date': '18.04.2026'},
        )
        ExchangeRate.all_objects.filter(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        ).delete()

        out = io.StringIO()
        call_command(
            'sync_exchange_rates',
            '--tenant-id',
            str(self.tenant.id),
            '--base-currency',
            'USD',
            '--quote-currency',
            'UZS',
            '--date',
            target_date.isoformat(),
            stdout=out,
        )

        row = ExchangeRate.objects.get(
            tenant=self.tenant,
            base_currency='USD',
            quote_currency='UZS',
            rate_date=target_date,
        )
        self.assertEqual(row.rate, Decimal('12050.500000'))
        self.assertEqual(row.source, ExchangeRate.Source.CBU)
        self.assertFalse(row.is_manual)
