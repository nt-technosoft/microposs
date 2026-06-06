"""Presentation-currency helpers for reports.

Accounting stays in tenant functional currency (UZS). This module only builds
derived display values for reports and UI.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .fx_rates import get_fx_rate_for_date


SUPPORTED_REPORT_CURRENCIES = {'UZS', 'USD'}
MONEY_Q = Decimal('0.01')


class ReportCurrencyError(ValueError):
    """Raised when a report currency cannot be resolved safely."""


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value or '0')).quantize(MONEY_Q)


def normalize_report_currency(value: str | None, default: str = 'UZS') -> str:
    currency = str(value or default or 'UZS').strip().upper()
    if currency not in SUPPORTED_REPORT_CURRENCIES:
        raise ReportCurrencyError(f'Валюта отчёта {currency} не поддерживается.')
    return currency


@dataclass(frozen=True)
class ReportCurrencyContext:
    currency: str
    rate: Decimal
    rate_date: date
    source: str
    policy: str

    def convert_uzs(self, amount_uzs: Decimal | int | float | str) -> Decimal:
        functional = money(amount_uzs)
        if self.currency == 'UZS':
            return functional
        if self.rate <= 0:
            raise ReportCurrencyError('Курс отчёта должен быть больше нуля.')
        return money(functional / self.rate)

    def amount(self, amount_uzs: Decimal | int | float | str) -> dict:
        functional = money(amount_uzs)
        return {
            'amount': str(self.convert_uzs(functional)),
            'currency': self.currency,
            'functional_amount_uzs': str(functional),
        }

    def values(self, source: dict, keys: list[str]) -> dict:
        return {
            key: str(self.convert_uzs(source.get(key, Decimal('0'))))
            for key in keys
        }

    def meta(self) -> dict:
        return {
            'currency': self.currency,
            'fx_rate': str(self.rate),
            'rate_date': self.rate_date.isoformat(),
            'source': self.source,
            'policy': self.policy,
        }


def resolve_report_currency_context(
    *,
    tenant_id: int,
    requested_currency: str | None = None,
    default_currency: str = 'UZS',
    rate_date: date | None = None,
) -> ReportCurrencyContext:
    currency = normalize_report_currency(requested_currency, default_currency)
    target_date = rate_date or timezone.localdate()
    if currency == 'UZS':
        return ReportCurrencyContext(
            currency='UZS',
            rate=Decimal('1.000000'),
            rate_date=target_date,
            source='FUNCTIONAL',
            policy='functional',
        )

    row = get_fx_rate_for_date(
        tenant_id=tenant_id,
        base_currency=currency,
        quote_currency='UZS',
        rate_date=target_date,
    )
    if row is None:
        raise ReportCurrencyError(
            f'Курс {currency}/UZS не найден на {target_date}. '
            'Синхронизируйте курс или добавьте ручной курс.'
        )
    return ReportCurrencyContext(
        currency=currency,
        rate=Decimal(str(row.rate)),
        rate_date=row.rate_date,
        source=row.source,
        policy='report_date',
    )


REPORT_AMOUNT_KEYS = [
    'current_unit_price',
    'unit_purchase_price',
    'landed_cost_per_unit',
    'revenue',
    'cogs',
    'gross_profit',
    'investor_profit',
    'business_profit',
    'remaining_landed_cost',
    'projected_revenue',
    'projected_gross_profit',
    'projected_investor_profit',
    'projected_business_profit',
    'received_landed_cost',
    'pending_prepaid_cost',
    'venture_deployed_uzs',
    'venture_capital_recovered_uzs',
    'venture_capital_return_available_uzs',
    'venture_provisional_profit_available_uzs',
    'venture_loss_uzs',
    'venture_negative_position_uzs',
]
