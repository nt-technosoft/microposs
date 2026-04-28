"""Currency helpers for sales.

Sales accounting uses UZS as the functional currency. Payments and cash
accounts stay in their native currency.
"""

from decimal import Decimal

from apps.finance.fx_rates import to_functional_amount_uzs


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def functional_amount_uzs(
    *,
    amount: Decimal | int | float | str,
    currency: str,
    fx_rate: Decimal | int | float | str,
) -> Decimal:
    return to_functional_amount_uzs(
        operation_amount=Decimal(str(amount)),
        operation_currency=str(currency or 'UZS').upper(),
        fx_rate_snapshot=Decimal(str(fx_rate or '1')),
    )


def payment_functional_amount_uzs(payment) -> Decimal:
    return functional_amount_uzs(
        amount=payment.amount,
        currency=payment.currency,
        fx_rate=payment.fx_rate,
    )
