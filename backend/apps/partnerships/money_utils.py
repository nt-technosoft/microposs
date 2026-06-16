"""Shared money helpers for the partnerships domain."""

from decimal import Decimal


ZERO = Decimal('0')
MONEY_Q = Decimal('0.01')
RATIO_Q = Decimal('0.000001')


def money(amount: Decimal | str | int | float | None) -> Decimal:
    return Decimal(str(amount if amount is not None else ZERO)).quantize(MONEY_Q)


def ratio(amount: Decimal | str | int | float | None) -> Decimal:
    return Decimal(str(amount if amount is not None else ZERO)).quantize(RATIO_Q)


def functional_uzs(
    amount: Decimal | str | int | float | None,
    currency: str = 'UZS',
    fx_rate: Decimal | str | int | float | None = Decimal('1'),
) -> Decimal:
    amount_dec = Decimal(str(amount if amount is not None else ZERO))
    currency = str(currency or 'UZS').upper()
    rate = Decimal(str(fx_rate if fx_rate not in (None, '') else Decimal('1')))
    return money(amount_dec if currency == 'UZS' else amount_dec * rate)


def equity_account_code(*, role: str, legal_mode: str | None) -> str:
    """Role-correct equity COA for partner capital movements."""
    if str(role) == 'INVESTOR':
        if str(legal_mode) == 'MUSHARAKA':
            return '3110'
        return '3100'
    return '3000'
