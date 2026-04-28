"""
Finance background tasks.
"""

from celery import shared_task
from django.utils import timezone

from apps.core.models import Business

from .fx_rates import sync_official_exchange_rate


@shared_task
def refresh_daily_fx_rates(
    base_currency: str = 'USD',
    quote_currency: str = 'UZS',
    overwrite_manual: bool = False,
):
    """
    Pull official rate once per day for every active tenant.
    Designed for Celery beat scheduling.
    """
    target_date = timezone.localdate()
    stats = {'tenants': 0, 'created': 0, 'updated': 0, 'failed': 0}
    active_tenants = Business.objects.filter(is_active=True).values_list('id', flat=True)
    for tenant_id in active_tenants:
        stats['tenants'] += 1
        try:
            _, created = sync_official_exchange_rate(
                tenant_id=tenant_id,
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate_date=target_date,
                overwrite_manual=bool(overwrite_manual),
            )
            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1
        except Exception:  # noqa: BLE001
            stats['failed'] += 1
    return stats
