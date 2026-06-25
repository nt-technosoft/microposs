"""
E12 — Multi-currency agreement capital (FIFO cost-basis).

Shares stay in the agreement's accounting (base) currency; the pool may
physically hold several currencies obtained via real spot conversion (sarf).
Each conversion is a FIFO lot carrying its base-currency cost. Spending a held
currency consumes lots oldest-first and returns the base-currency cost — that
cost (never the receive-day market rate) feeds snapshots / landed cost.

Precision: cost-basis math is kept at full Decimal precision and is NOT
quantized to 0.01. Rounding belongs to the presentation layer only.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finance.models import CashAccount

from .models import (
    AgreementCurrencyPool,
    CurrencyConversionLot,
    InvestmentAgreement,
)


def _ccy(value: str) -> str:
    return str(value or 'UZS').upper()


def get_or_create_currency_pool(*, tenant_id: int, agreement: InvestmentAgreement, currency: str):
    """Return the agreement's cash pool (CashAccount) for `currency`.

    Base currency → the existing `agreement.capital_account`. Other currencies →
    a dedicated AGREEMENT_CAPITAL CashAccount, registered in AgreementCurrencyPool.
    """
    from apps.finance.models import Account, CashAccount

    currency = _ccy(currency)
    base_ccy = _ccy(agreement.currency)

    if currency == base_ccy:
        if agreement.capital_account_id is None:
            raise ValueError('Agreement has no base capital pool.')
        AgreementCurrencyPool.objects.get_or_create(
            tenant_id=tenant_id, agreement=agreement, currency=currency,
            defaults={'cash_account_id': agreement.capital_account_id},
        )
        return agreement.capital_account

    existing = (
        AgreementCurrencyPool.objects
        .filter(tenant_id=tenant_id, agreement=agreement, currency=currency)
        .select_related('cash_account')
        .first()
    )
    if existing is not None:
        return existing.cash_account

    coa = Account.objects.get(tenant_id=tenant_id, code='1300')
    account = CashAccount.objects.create(
        tenant_id=tenant_id,
        name=f'Капитал договора #{agreement.pk} ({currency})',
        currency=currency,
        kind=CashAccount.Kind.AGREEMENT_CAPITAL,
        linked_account=coa,
        balance=Decimal('0'),
        is_active=True,
    )
    AgreementCurrencyPool.objects.create(
        tenant_id=tenant_id, agreement=agreement, currency=currency, cash_account=account,
    )
    return account


def convert_agreement_pool(
    *,
    tenant_id: int,
    agreement_id: int,
    to_currency: str,
    from_amount: Decimal,
    rate: Decimal,
    converted_at=None,
    source_ref: str = '',
) -> CurrencyConversionLot:
    """Real spot conversion of base-currency pool money into `to_currency`.

    Moves `from_amount` (base currency) out of the base pool into the
    `to_currency` pool at `rate` (held per 1 base), and records a FIFO lot
    carrying the base-currency cost. Reuses finance.exchange_currency for the
    physical cash move; this only adds the cost-basis lot on top.
    """
    from apps.finance.services import exchange_currency

    converted_at = converted_at or timezone.now()
    from_amount = Decimal(str(from_amount))
    rate = Decimal(str(rate))
    if from_amount <= 0:
        raise ValueError('Conversion from_amount must be > 0.')
    if rate <= 0:
        raise ValueError('Conversion rate must be > 0.')

    to_currency = _ccy(to_currency)

    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement_id, tenant_id=tenant_id,
        )
        base_ccy = _ccy(agreement.currency)
        if to_currency == base_ccy:
            raise ValueError('Conversion target must differ from the base currency.')

        base_pool = get_or_create_currency_pool(
            tenant_id=tenant_id, agreement=agreement, currency=base_ccy,
        )
        target_pool = get_or_create_currency_pool(
            tenant_id=tenant_id, agreement=agreement, currency=to_currency,
        )
        if (
            base_pool.kind != CashAccount.Kind.AGREEMENT_CAPITAL
            or target_pool.kind != CashAccount.Kind.AGREEMENT_CAPITAL
        ):
            raise ValueError('Agreement pool conversion requires agreement capital accounts.')

        exchange = exchange_currency(
            tenant_id=tenant_id,
            from_account_id=base_pool.pk,
            to_account_id=target_pool.pk,
            from_amount=from_amount,
            rate=rate,
            date=converted_at,
            notes=f'Agreement #{agreement_id} capital conversion {base_ccy}->{to_currency}',
            allow_restricted_accounts=True,
        )
        to_amount = Decimal(str(exchange.to_amount))

        lot = CurrencyConversionLot.objects.create(
            tenant_id=tenant_id,
            agreement=agreement,
            base_currency=base_ccy,
            currency=to_currency,
            rate=rate,
            amount_initial=to_amount,
            amount_remaining=to_amount,
            base_cost_initial=from_amount,
            base_cost_remaining=from_amount,
            converted_at=converted_at,
            source_ref=source_ref,
        )
        from .read_models import rebuild_agreement_positions
        rebuild_agreement_positions(agreement)
    return lot


def pool_currency_balance(*, tenant_id: int, agreement_id: int, currency: str) -> Decimal:
    """Remaining held amount of `currency` across the agreement's conversion lots."""
    currency = _ccy(currency)
    total = Decimal('0')
    for lot in CurrencyConversionLot.objects.filter(
        tenant_id=tenant_id, agreement_id=agreement_id, currency=currency,
        amount_remaining__gt=0,
    ):
        total += Decimal(str(lot.amount_remaining))
    return total


def spend_pool_cost_basis(
    *,
    tenant_id: int,
    agreement_id: int,
    currency: str,
    amount: Decimal,
    source_ref: str = '',
) -> Decimal:
    """Consume `amount` of `currency` from the agreement's conversion lots FIFO.

    Returns the base-currency cost of the consumed amount (full precision, NOT
    quantized). Mutates each lot's running `amount_remaining` / `base_cost_remaining`
    proportionally. Raises if the held currency is insufficient.
    """
    currency = _ccy(currency)
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError('Spend amount must be > 0.')

    base_cost = Decimal('0')
    remaining = amount

    with transaction.atomic():
        lots = (
            CurrencyConversionLot.objects
            .select_for_update()
            .filter(
                tenant_id=tenant_id, agreement_id=agreement_id, currency=currency,
                amount_remaining__gt=0,
            )
            .order_by('converted_at', 'id')
        )
        for lot in lots:
            if remaining <= 0:
                break
            lot_amount = Decimal(str(lot.amount_remaining))
            take = lot_amount if lot_amount < remaining else remaining
            # Proportional cost basis of the slice (full precision).
            base_slice = Decimal(str(lot.base_cost_remaining)) * take / lot_amount
            lot.amount_remaining = lot_amount - take
            lot.base_cost_remaining = Decimal(str(lot.base_cost_remaining)) - base_slice
            lot.source_ref = lot.source_ref
            lot.save(update_fields=['amount_remaining', 'base_cost_remaining', 'updated_at'])
            base_cost += base_slice
            remaining -= take

        if remaining > 0:
            raise ValueError(
                f'Insufficient {currency} in agreement #{agreement_id} pool: '
                f'short by {remaining}.'
            )

    return base_cost
