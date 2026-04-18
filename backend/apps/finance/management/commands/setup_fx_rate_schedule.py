"""
Create/update Celery Beat schedule for daily FX refresh task.
"""

from django.core.management.base import BaseCommand

from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    help = 'Setup daily Celery Beat task for FX rate refresh.'

    def add_arguments(self, parser):
        parser.add_argument('--hour', type=int, default=8, help='Run hour (0-23), default 8')
        parser.add_argument('--minute', type=int, default=5, help='Run minute (0-59), default 5')
        parser.add_argument('--timezone', default='Asia/Tashkent', help='Crontab timezone')
        parser.add_argument('--base-currency', default='USD', help='Base currency for sync')
        parser.add_argument('--quote-currency', default='UZS', help='Quote currency for sync')

    def handle(self, *args, **options):
        hour = str(options['hour'])
        minute = str(options['minute'])
        tz = options['timezone']
        base = str(options['base_currency'] or 'USD').upper()
        quote = str(options['quote_currency'] or 'UZS').upper()

        crontab, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
            timezone=tz,
        )

        task_name = f'finance.fx.daily.refresh.{base.lower()}{quote.lower()}'
        kwargs = f'{{"base_currency": "{base}", "quote_currency": "{quote}"}}'
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
                f'{marker}: {periodic_task.name} at {hour}:{minute} ({tz})'
            )
        )
