"""
FX rate services.

This module is the single backend entrypoint for exchange-rate history,
official CBU sync, and immutable operation snapshots.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from .models import ExchangeRate


_CBU_RATE_URL_TEMPLATE = 'https://cbu.uz/ru/arkhiv-kursov-valyut/json/{currency}/{rate_date}/'


class OperationFxRateSource:
    """Operation-level FX snapshot source labels."""

    CBU = 'CBU'
    MANUAL = 'MANUAL'
    CUSTOM = 'CUSTOM'
    FUNCTIONAL = 'FUNCTIONAL'
    DERIVED = 'DERIVED'


@dataclass(frozen=True)
class FxRateSnapshot:
    rate: Decimal
    rate_date: date
    source: str


def _to_decimal(value: str | int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def _parse_cbu_date(raw: str | None, fallback: date) -> date:
    if not raw:
        return fallback
    text = str(raw).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return fallback


def _parse_cbu_rate_payload(
    payload: object,
    *,
    base_currency: str,
    target_date: date,
) -> tuple[Decimal, date, dict]:
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    elif isinstance(payload, dict):
        rows = [payload]

    if not rows:
        raise ValueError(f'CBU returned empty payload for {base_currency} on {target_date}')

    row = rows[0]
    rate_raw = _to_decimal(str(row.get('Rate', '0')).replace(',', '.'))
    nominal_raw = _to_decimal(str(row.get('Nominal', '1')).replace(',', '.'))
    if nominal_raw <= 0:
        nominal_raw = Decimal('1')

    per_unit_rate = (rate_raw / nominal_raw).quantize(Decimal('0.000001'))
    if per_unit_rate <= 0:
        raise ValueError(f'CBU returned invalid rate for {base_currency} on {target_date}')

    effective_date = _parse_cbu_date(str(row.get('Date', '') or ''), target_date)
    return per_unit_rate, effective_date, row


def fetch_official_cbu_rate(base_currency: str, rate_date: date) -> tuple[Decimal, date, dict]:
    """Fetch official CBU rate for one currency/date."""
    currency = str(base_currency or 'USD').upper()
    target_date = rate_date.isoformat()
    url = _CBU_RATE_URL_TEMPLATE.format(currency=currency, rate_date=target_date)
    req = Request(
        url,
        headers={
            'Accept': 'application/json',
            'User-Agent': 'MicroPOS/1.0 (+https://microposs.local)',
        },
    )
    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except HTTPError as exc:
        raise ValueError(
            f'CBU request failed for {currency} on {rate_date}: HTTP {exc.code}'
        ) from exc
    except URLError as exc:
        raise ValueError(
            f'CBU request failed for {currency} on {rate_date}: {exc.reason}'
        ) from exc

    return _parse_cbu_rate_payload(payload, base_currency=currency, target_date=rate_date)


def upsert_exchange_rate(
    *,
    tenant_id: int,
    base_currency: str,
    quote_currency: str,
    rate_date: date,
    rate: Decimal,
    source: str,
    is_manual: bool,
    notes: str = '',
    raw_payload: dict | None = None,
    overwrite_manual: bool = False,
) -> tuple[ExchangeRate, bool]:
    """
    Create or update rate for (tenant, base, quote, date).
    Automatic sync keeps manual rows unless overwrite_manual=True.
    """
    base = str(base_currency or 'USD').upper()
    quote = str(quote_currency or 'UZS').upper()
    normalized_rate = _to_decimal(rate).quantize(Decimal('0.000001'))
    if normalized_rate <= 0:
        raise ValueError('FX rate must be > 0')

    with transaction.atomic():
        existing = (
            ExchangeRate.objects
            .select_for_update()
            .filter(
                tenant_id=tenant_id,
                base_currency=base,
                quote_currency=quote,
                rate_date=rate_date,
            )
            .first()
        )

        if existing is not None:
            if existing.is_manual and source != ExchangeRate.Source.MANUAL and not overwrite_manual:
                return existing, False

            existing.rate = normalized_rate
            existing.source = source
            existing.is_manual = is_manual
            existing.notes = notes
            existing.raw_payload = raw_payload or {}
            existing.fetched_at = timezone.now()
            existing.save(update_fields=[
                'rate',
                'source',
                'is_manual',
                'notes',
                'raw_payload',
                'fetched_at',
                'updated_at',
            ])
            return existing, False

        created = ExchangeRate.objects.create(
            tenant_id=tenant_id,
            base_currency=base,
            quote_currency=quote,
            rate_date=rate_date,
            rate=normalized_rate,
            source=source,
            is_manual=is_manual,
            notes=notes,
            raw_payload=raw_payload or {},
            fetched_at=timezone.now(),
        )
        return created, True


def sync_official_exchange_rate(
    *,
    tenant_id: int,
    base_currency: str = 'USD',
    quote_currency: str = 'UZS',
    rate_date: date | None = None,
    overwrite_manual: bool = False,
) -> tuple[ExchangeRate, bool]:
    """Pull official CBU rate and save it to tenant FX history."""
    quote = str(quote_currency or 'UZS').upper()
    if quote != 'UZS':
        raise ValueError('Only UZS quote currency is supported for official CBU sync')

    target_date = rate_date or timezone.localdate()
    rate, effective_date, raw = fetch_official_cbu_rate(
        base_currency=str(base_currency or 'USD').upper(),
        rate_date=target_date,
    )
    return upsert_exchange_rate(
        tenant_id=tenant_id,
        base_currency=str(base_currency or 'USD').upper(),
        quote_currency=quote,
        rate_date=effective_date,
        rate=rate,
        source=ExchangeRate.Source.CBU,
        is_manual=False,
        notes='Official CBU sync',
        raw_payload=raw,
        overwrite_manual=overwrite_manual,
    )


def get_fx_rate_for_date(
    *,
    tenant_id: int,
    base_currency: str,
    quote_currency: str = 'UZS',
    rate_date: date | None = None,
) -> ExchangeRate | None:
    """Get nearest historical rate up to requested date."""
    base = str(base_currency or 'USD').upper()
    quote = str(quote_currency or 'UZS').upper()
    target_date = rate_date or timezone.localdate()
    return (
        ExchangeRate.objects
        .filter(
            tenant_id=tenant_id,
            base_currency=base,
            quote_currency=quote,
            rate_date__lte=target_date,
        )
        .order_by('-rate_date', '-is_manual', '-updated_at')
        .first()
    )


def _operation_rate_date(operation_at: datetime | date | None = None) -> date:
    if isinstance(operation_at, datetime):
        return operation_at.date()
    if isinstance(operation_at, date):
        return operation_at
    return timezone.localdate()


def resolve_fx_rate_snapshot_details(
    *,
    tenant_id: int,
    operation_currency: str,
    operation_at: datetime | date | None = None,
    fx_rate_snapshot: Decimal | None = None,
) -> FxRateSnapshot:
    """Resolve immutable FX snapshot with source/date metadata."""
    currency = str(operation_currency or 'UZS').upper()
    target_date = _operation_rate_date(operation_at)

    if currency == 'UZS':
        return FxRateSnapshot(
            rate=Decimal('1'),
            rate_date=target_date,
            source=OperationFxRateSource.FUNCTIONAL,
        )

    if fx_rate_snapshot is not None:
        provided = _to_decimal(fx_rate_snapshot).quantize(Decimal('0.000001'))
        if provided <= 0:
            raise ValueError('fx_rate_snapshot must be > 0')
        return FxRateSnapshot(
            rate=provided,
            rate_date=target_date,
            source=OperationFxRateSource.CUSTOM,
        )

    rate_row = get_fx_rate_for_date(
        tenant_id=tenant_id,
        base_currency=currency,
        quote_currency='UZS',
        rate_date=target_date,
    )
    if rate_row is None:
        try:
            rate_row, _ = sync_official_exchange_rate(
                tenant_id=tenant_id,
                base_currency=currency,
                quote_currency='UZS',
                rate_date=target_date,
                overwrite_manual=False,
            )
        except ValueError as exc:
            raise ValueError(
                f'FX rate for {currency}/UZS is missing on {target_date}. '
                f'Official sync failed; add a manual rate or run official sync first. '
                f'Details: {exc}'
            ) from exc
    return FxRateSnapshot(
        rate=_to_decimal(rate_row.rate).quantize(Decimal('0.000001')),
        rate_date=rate_row.rate_date,
        source=rate_row.source,
    )


def resolve_fx_rate_snapshot(
    *,
    tenant_id: int,
    operation_currency: str,
    operation_at: datetime | date | None = None,
    fx_rate_snapshot: Decimal | None = None,
) -> Decimal:
    """Resolve immutable FX snapshot for operation datetime/date."""
    return resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id,
        operation_currency=operation_currency,
        operation_at=operation_at,
        fx_rate_snapshot=fx_rate_snapshot,
    ).rate


def to_functional_amount_uzs(
    *,
    operation_amount: Decimal,
    operation_currency: str,
    fx_rate_snapshot: Decimal,
) -> Decimal:
    amount = _to_decimal(operation_amount).quantize(Decimal('0.01'))
    currency = str(operation_currency or 'UZS').upper()
    if currency == 'UZS':
        return amount
    rate = _to_decimal(fx_rate_snapshot).quantize(Decimal('0.000001'))
    return (amount * rate).quantize(Decimal('0.01'))
