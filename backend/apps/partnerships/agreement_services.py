"""
Partnership agreement services — ledger management, dividend payout, partner aggregates.

Extracted from the legacy services.py (E08 T-1.2). Only live functions kept.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.finance.models import CashAccount, CashEntry
from apps.finance.services import create_cash_entry, record_journal_from_cash_entry
from apps.core.services import publish_event


_ZERO = Decimal('0')
_CENT = Decimal('0.01')


def _q(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(_CENT)


def _functional_uzs(
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
) -> Decimal:
    amount = Decimal(str(amount))
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    if currency == 'UZS':
        return _q(amount)
    return _q(amount * fx_rate)


def _empty_ledger_totals() -> dict:
    return {
        'capital_in': _ZERO,
        'capital_out': _ZERO,
        'capital_net': _ZERO,
        'profit_accrued': _ZERO,
        'profit_reversed': _ZERO,
        'losses_incurred': _ZERO,
        'dividends_paid': _ZERO,
        'profit_pending_payout': _ZERO,
    }


def _entry_key(entry_type: str) -> str | None:
    return {
        'CAPITAL_IN': 'capital_in',
        'CAPITAL_OUT': 'capital_out',
        'PROFIT_ACCRUED': 'profit_accrued',
        'PROFIT_REVERSED': 'profit_reversed',
        'LOSS_INCURRED': 'losses_incurred',
        'DIVIDEND_PAID': 'dividends_paid',
    }.get(entry_type)


def _finalize_ledger_totals(totals: dict) -> dict:
    totals['capital_net'] = _q(totals['capital_in'] - totals['capital_out'])
    profit_net = (
        totals['profit_accrued']
        - totals['profit_reversed']
        - totals['losses_incurred']
    )
    totals['profit_pending_payout'] = _q(
        max(_ZERO, profit_net - totals['dividends_paid'])
    )
    return totals


def get_or_create_ledger(
    *,
    procurement_id: int,
    partner_id: int,
    tenant_id: int,
):
    from .models import ProcurementPartnerLedger
    ledger, _ = ProcurementPartnerLedger.objects.get_or_create(
        tenant_id=tenant_id,
        procurement_id=procurement_id,
        partner_id=partner_id,
    )
    return ledger


def append_ledger_entry(
    *,
    ledger,
    entry_type: str,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    source_ref: str = '',
    date=None,
):
    from .models import PartnerLedgerEntry
    if date is None:
        date = timezone.now()
    currency = str(currency or 'UZS').upper()
    fx_rate = Decimal(str(fx_rate or Decimal('1')))
    return PartnerLedgerEntry.objects.create(
        tenant_id=ledger.tenant_id,
        ledger=ledger,
        date=date,
        amount=amount,
        currency=currency,
        fx_rate=fx_rate,
        functional_amount_uzs=_functional_uzs(amount, currency, fx_rate),
        entry_type=entry_type,
        source_ref=source_ref,
    )


def get_partner_aggregate(
    partner_id: int,
    tenant_id: int,
    procurement_id: int | None = None,
) -> dict:
    """
    Compute partner ledger summary across all procurements.
    Returns UZS functional totals plus per-currency breakdown.
    """
    from .models import PartnerLedgerEntry, ProcurementPartnerLedger

    ledger_qs = ProcurementPartnerLedger.objects.filter(
        partner_id=partner_id,
        tenant_id=tenant_id,
    )
    if procurement_id is not None:
        ledger_qs = ledger_qs.filter(procurement_id=procurement_id)
    ledger_ids = ledger_qs.values_list('id', flat=True)

    functional_rows = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type')
        .annotate(total=models.Sum('functional_amount_uzs'))
    )
    functional_uzs = _empty_ledger_totals()
    for row in functional_rows:
        key = _entry_key(row['entry_type'])
        if key:
            functional_uzs[key] = _q(row['total'] or _ZERO)
    functional_uzs = _finalize_ledger_totals(functional_uzs)

    currency_rows = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type', 'currency')
        .annotate(total=models.Sum('amount'))
    )
    by_currency: dict[str, dict] = {}
    for row in currency_rows:
        currency = str(row['currency'] or 'UZS').upper()
        key = _entry_key(row['entry_type'])
        if not key:
            continue
        totals = by_currency.setdefault(currency, _empty_ledger_totals())
        totals[key] = _q(row['total'] or _ZERO)

    for currency, totals in list(by_currency.items()):
        by_currency[currency] = _finalize_ledger_totals(totals)

    return {
        **functional_uzs,
        'summary_currency': 'UZS',
        'functional_uzs': functional_uzs,
        'by_currency': by_currency,
    }


def pay_dividend(
    *,
    partner_id: int,
    procurement_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    from_account_id: int | None = None,
    tenant_id: int,
    date=None,
):
    """
    Record a dividend payout to a partner.
    Invariant: amount <= profit_pending_payout for this procurement.
    """
    from .models import DividendPayment, PartnerLedgerEntry

    if date is None:
        date = timezone.now()

    with transaction.atomic():
        ledger = get_or_create_ledger(
            procurement_id=procurement_id,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )

        agg = (
            PartnerLedgerEntry.objects
            .filter(ledger=ledger)
            .values('entry_type')
            .annotate(total=models.Sum('functional_amount_uzs'))
        )
        totals = {row['entry_type']: row['total'] or _ZERO for row in agg}

        profit_net = (
            totals.get('PROFIT_ACCRUED', _ZERO)
            - totals.get('PROFIT_REVERSED', _ZERO)
            - totals.get('LOSS_INCURRED', _ZERO)
        )
        already_paid = totals.get('DIVIDEND_PAID', _ZERO)
        pending = max(_ZERO, profit_net - already_paid)

        payment_functional_uzs = _functional_uzs(amount, currency, fx_rate)
        if payment_functional_uzs > pending:
            raise ValueError(
                f'Dividend amount {payment_functional_uzs} UZS exceeds pending payout {pending} UZS '
                f'for partner {partner_id}, procurement {procurement_id}.'
            )

        payment = DividendPayment.objects.create(
            tenant_id=tenant_id,
            partner_id=partner_id,
            procurement_id=procurement_id,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            paid_from_account_id=from_account_id,
            date=date,
        )

        cash_entry = None
        if from_account_id is not None:
            account = CashAccount.objects.select_for_update().get(
                pk=from_account_id,
                tenant_id=tenant_id,
            )
            if account.currency != currency:
                raise ValueError(
                    f'Dividend currency {currency} does not match cash account '
                    f'{account.name} currency {account.currency}.'
                )
            if account.balance < amount:
                raise ValueError(
                    f'Insufficient cash in {account.name}: have {account.balance}, need {amount}.'
                )
            cash_entry = create_cash_entry(
                tenant_id=tenant_id,
                account=account,
                direction=CashEntry.Direction.OUT,
                amount=amount,
                date=date,
                source_ref_type='dividend_payment',
                source_ref_id=payment.pk,
            )

        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            source_ref=f'dividend_payment:{payment.pk}',
            date=date,
        )

        if cash_entry is not None and cash_entry.account.linked_account_id:
            record_journal_from_cash_entry(
                tenant_id=tenant_id,
                cash_entry=cash_entry,
                operation_type='payment',
                operation_id=payment.pk,
                counterpart_account_code='2100',
                description=f'Dividend payment #{payment.pk}',
                date=date,
            )

        publish_event(
            event_type='partnership.dividend_paid',
            payload={
                'payment_id': payment.pk,
                'partner_id': partner_id,
                'procurement_id': procurement_id,
                'amount': str(amount),
                'currency': currency,
            },
            tenant_id=tenant_id,
        )

    return payment
