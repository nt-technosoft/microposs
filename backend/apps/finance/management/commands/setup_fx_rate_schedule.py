"""
Create/update Celery Beat schedule for daily FX refresh task.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = 'Setup daily Celery Beat task for FX rate refresh.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hour',
            type=int,
            default=getattr(settings, 'FX_SYNC_HOUR', 8),
            help='Run hour (0-23). Defaults to FX_SYNC_HOUR.',
        )
        parser.add_argument(
            '--minute',
            type=int,
            default=getattr(settings, 'FX_SYNC_MINUTE', 5),
            help='Run minute (0-59). Defaults to FX_SYNC_MINUTE.',
        )
        parser.add_argument(
            '--timezone',
            default=getattr(settings, 'FX_SYNC_TIMEZONE', 'Asia/Tashkent'),
            help='Crontab timezone. Defaults to FX_SYNC_TIMEZONE.',
        )
        parser.add_argument(
            '--base-currency',
            default=getattr(settings, 'FX_SYNC_BASE_CURRENCY', 'USD'),
            help='Base currency for sync. Defaults to FX_SYNC_BASE_CURRENCY.',
        )
        parser.add_argument(
            '--quote-currency',
            default=getattr(settings, 'FX_SYNC_QUOTE_CURRENCY', 'UZS'),
            help='Quote currency for sync. Defaults to FX_SYNC_QUOTE_CURRENCY.',
        )
        parser.add_argument(
            '--overwrite-manual',
            action='store_true',
            default=getattr(settings, 'FX_SYNC_OVERWRITE_MANUAL', False),
            help='Allow scheduled official sync to overwrite same-day manual rates.',
        )
        parser.add_argument(
            '--no-overwrite-manual',
            action='store_false',
            dest='overwrite_manual',
            help='Prevent scheduled official sync from overwriting manual rates.',
        )

    def handle(self, *args, **options):
        hour = str(options['hour'])
        minute = str(options['minute'])
        tz = options['timezone']
        base = str(options['base_currency'] or 'USD').upper()
        quote = str(options['quote_currency'] or 'UZS').upper()
        overwrite_manual = bool(options['overwrite_manual'])

        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
            timezone=tz,
        )

        task_name = f'finance.fx.daily.refresh.{base.lower()}{quote.lower()}'
        kwargs = json.dumps({
            'base_currency': base,
            'quote_currency': quote,
            'overwrite_manual': overwrite_manual,
        })
        periodic_task, created = PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': 'apps.finance.tasks.refresh_daily_fx_rates',
                'crontab': crontab,
                'kwargs': kwargs,
                'enabled': True,
            },
        )

        marker = 'created' if created else 'updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'{marker}: {periodic_task.name} at {hour}:{minute} ({tz}), '
                f'overwrite_manual={overwrite_manual}'
            )
        )
