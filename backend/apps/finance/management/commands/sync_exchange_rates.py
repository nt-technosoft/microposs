"""
Sync official FX rates from CBU into tenant history table.
"""

from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.models import Business
from apps.finance.fx_rates import sync_official_exchange_rate


class Command(BaseCommand):
    help = (
        'Sync official exchange rate from CBU. '
        'Supports all active tenants or specific tenant.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Optional tenant id. If omitted, syncs all active tenants.',
        )
        parser.add_argument(
            '--base-currency',
            default=getattr(settings, 'FX_SYNC_BASE_CURRENCY', 'USD'),
            help='Base currency code. Defaults to FX_SYNC_BASE_CURRENCY.',
        )
        parser.add_argument(
            '--quote-currency',
            default=getattr(settings, 'FX_SYNC_QUOTE_CURRENCY', 'UZS'),
            help='Quote currency code. Defaults to FX_SYNC_QUOTE_CURRENCY.',
        )
        parser.add_argument(
            '--date',
            dest='rate_date',
            help='Rate date in YYYY-MM-DD. Defaults to today.',
        )
        parser.add_argument(
            '--overwrite-manual',
            action='store_true',
            default=getattr(settings, 'FX_SYNC_OVERWRITE_MANUAL', False),
            help='Allow overwriting manual rates for same date.',
        )
        parser.add_argument(
            '--no-overwrite-manual',
            action='store_false',
            dest='overwrite_manual',
            help='Prevent overwriting manual rates for same date.',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        base_currency = str(options['base_currency'] or 'USD').upper()
        quote_currency = str(options['quote_currency'] or 'UZS').upper()
        rate_date_raw = options.get('rate_date')
        overwrite_manual = bool(options.get('overwrite_manual', False))

        if rate_date_raw:
            try:
                target_date = datetime.strptime(rate_date_raw, '%Y-%m-%d').date()
            except ValueError as exc:
                raise CommandError('Invalid --date format. Use YYYY-MM-DD.') from exc
        else:
            target_date = timezone.localdate()

        if tenant_id:
            tenant_ids = [tenant_id]
        else:
            tenant_ids = list(
                Business.objects.filter(is_active=True).values_list('id', flat=True)
            )

        if not tenant_ids:
            self.stdout.write(self.style.WARNING('No active tenants found.'))
            return

        ok = 0
        fail = 0
        for current_tenant_id in tenant_ids:
            try:
                rate, created = sync_official_exchange_rate(
                    tenant_id=current_tenant_id,
                    base_currency=base_currency,
                    quote_currency=quote_currency,
                    rate_date=target_date,
                    overwrite_manual=overwrite_manual,
                )
                marker = 'created' if created else 'updated'
                self.stdout.write(
                    self.style.SUCCESS(
                        f'tenant={current_tenant_id} {base_currency}/{quote_currency} '
                        f'{rate.rate_date} rate={rate.rate} ({marker})'
                    )
                )
                ok += 1
            except Exception as exc:  # noqa: BLE001
                fail += 1
                self.stdout.write(
                    self.style.ERROR(
                        f'tenant={current_tenant_id} failed: {exc}'
                    )
                )

        self.stdout.write(f'completed: ok={ok}, failed={fail}')
