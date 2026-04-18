"""
Finance business logic — journal entries, daily summaries.
"""

import json
from decimal import Decimal
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event

from .models import Account, Expense, ExchangeRate, JournalEntry, JournalLine


_CBU_RATE_URL_TEMPLATE = 'https://cbu.uz/ru/arkhiv-kursov-valyut/json/{currency}/{rate_date}/'


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

    # Canonical storage: quote for 1 unit of base currency.
    per_unit_rate = (rate_raw / nominal_raw).quantize(Decimal('0.000001'))
    if per_unit_rate <= 0:
        raise ValueError(f'CBU returned invalid rate for {base_currency} on {target_date}')

    effective_date = _parse_cbu_date(str(row.get('Date', '') or ''), target_date)
    return per_unit_rate, effective_date, row


def fetch_official_cbu_rate(base_currency: str, rate_date: date) -> tuple[Decimal, date, dict]:
    """
    Fetch official FX rate from CBU JSON endpoint.
    Returns (rate_per_1_unit, effective_date, raw_payload_row).
    """
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
    If existing row is manual and overwrite_manual=False, automatic refresh keeps manual value.
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
    """
    Pull official rate from CBU and save to tenant history table.
    """
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
    """
    Get nearest historical rate up to requested date.
    """
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


def resolve_fx_rate_snapshot(
    *,
    tenant_id: int,
    operation_currency: str,
    operation_at: datetime | date | None = None,
    fx_rate_snapshot: Decimal | None = None,
) -> Decimal:
    """
    Resolve immutable FX snapshot for operation datetime/date.
    """
    currency = str(operation_currency or 'UZS').upper()
    if currency == 'UZS':
        return Decimal('1')

    if fx_rate_snapshot is not None:
        provided = _to_decimal(fx_rate_snapshot).quantize(Decimal('0.000001'))
        if provided <= 0:
            raise ValueError('fx_rate_snapshot must be > 0')
        return provided

    if isinstance(operation_at, datetime):
        target_date = operation_at.date()
    elif isinstance(operation_at, date):
        target_date = operation_at
    else:
        target_date = timezone.localdate()

    rate_row = get_fx_rate_for_date(
        tenant_id=tenant_id,
        base_currency=currency,
        quote_currency='UZS',
        rate_date=target_date,
    )
    if rate_row is None:
        raise ValueError(
            f'FX rate for {currency}/UZS is missing on {target_date}. '
            f'Add manual rate or run official sync first.'
        )
    return _to_decimal(rate_row.rate).quantize(Decimal('0.000001'))


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


def get_account(tenant_id: int, code: str) -> Account:
    """Get account by code for tenant."""
    return Account.objects.get(tenant_id=tenant_id, code=code)


def create_journal_entry(
    tenant_id: int,
    operation_type: str,
    operation_id: int,
    lines: list[dict],
    description: str = '',
    date=None,
) -> JournalEntry:
    """
    Create a balanced journal entry.
    Each line: {account_code, debit, credit, description}.
    Validates that total debits == total credits.
    """
    if date is None:
        date = timezone.now()

    total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
    total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)

    if total_debit != total_credit:
        raise ValueError(
            f'Journal entry not balanced: debit={total_debit}, credit={total_credit}'
        )

    with transaction.atomic():
        entry = JournalEntry.objects.create(
            tenant_id=tenant_id,
            operation_type=operation_type,
            operation_id=operation_id,
            description=description,
            date=date,
            status='confirmed',
        )

        for line_data in lines:
            account = get_account(tenant_id, line_data['account_code'])
            JournalLine.objects.create(
                tenant_id=tenant_id,
                journal_entry=entry,
                account=account,
                debit=Decimal(str(line_data.get('debit', 0))),
                credit=Decimal(str(line_data.get('credit', 0))),
                description=line_data.get('description', ''),
            )

    return entry


def create_reversal_entry(
    tenant_id: int,
    original_entry: JournalEntry,
    description: str = '',
) -> JournalEntry:
    """
    Create a reversal entry that mirrors the original with
    debits and credits swapped.
    """
    with transaction.atomic():
        reversal = JournalEntry.objects.create(
            tenant_id=tenant_id,
            operation_type=original_entry.operation_type,
            operation_id=original_entry.operation_id,
            description=description or f'Reversal of JE #{original_entry.pk}',
            date=timezone.now(),
            status='confirmed',
            is_reversal=True,
            reversed_entry=original_entry,
        )

        for original_line in original_entry.lines.all():
            JournalLine.objects.create(
                tenant_id=tenant_id,
                journal_entry=reversal,
                account=original_line.account,
                debit=original_line.credit,
                credit=original_line.debit,
                description=f'Reversal: {original_line.description}',
            )

    return reversal


def record_sale_journal(
    tenant_id: int,
    sale_id: int,
    total_amount: Decimal,
    total_cogs: Decimal,
    payment_method: str,
    date=None,
) -> JournalEntry:
    """
    Record journal entry for a completed sale.
    DR Cash/Receivables | CR Revenue
    DR COGS             | CR Inventory
    """
    # Determine debit account by payment method
    if payment_method == 'cash':
        debit_code = '1000'  # Касса
    elif payment_method == 'card':
        debit_code = '1010'  # Банковский счёт
    else:  # credit
        debit_code = '1200'  # Дебиторская задолженность

    lines = [
        {
            'account_code': debit_code,
            'debit': total_amount,
            'credit': Decimal('0'),
            'description': f'Sale #{sale_id} revenue',
        },
        {
            'account_code': '4000',  # Выручка
            'debit': Decimal('0'),
            'credit': total_amount,
            'description': f'Sale #{sale_id} revenue',
        },
        {
            'account_code': '5000',  # COGS
            'debit': total_cogs,
            'credit': Decimal('0'),
            'description': f'Sale #{sale_id} cost of goods',
        },
        {
            'account_code': '1100',  # Товарные запасы
            'debit': Decimal('0'),
            'credit': total_cogs,
            'description': f'Sale #{sale_id} inventory reduction',
        },
    ]

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='sale',
        operation_id=sale_id,
        lines=lines,
        description=f'Sale #{sale_id}',
        date=date,
    )


def record_receipt_journal(
    tenant_id: int,
    receipt_id: int,
    total_cost: Decimal,
    receipt_type: str,
    supplier_id: int | None = None,
    date=None,
) -> JournalEntry:
    """
    Record journal entry for a confirmed receipt.
    DR Inventory | CR Cash/Payables/Investor Capital
    """
    if receipt_type == 'BUSINESS_OWNED':
        credit_code = '1000'  # Cash
    elif receipt_type == 'SUPPLIER_PURCHASE':
        credit_code = '2000'  # Supplier payables
    elif receipt_type == 'CONSIGNMENT':
        credit_code = '2200'  # Consignment liabilities
    elif receipt_type == 'MUDARABA':
        credit_code = '3100'  # Investor capital mudaraba
    elif receipt_type == 'MUSHARAKA':
        credit_code = '3110'  # Investor capital musharaka
    else:
        credit_code = '1000'

    lines = [
        {
            'account_code': '1100',
            'debit': total_cost,
            'credit': Decimal('0'),
            'description': f'Receipt #{receipt_id} inventory',
        },
        {
            'account_code': credit_code,
            'debit': Decimal('0'),
            'credit': total_cost,
            'description': f'Receipt #{receipt_id} obligation',
        },
    ]

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='receipt',
        operation_id=receipt_id,
        lines=lines,
        description=f'Receipt #{receipt_id} ({receipt_type})',
        date=date,
    )


def record_return_journal(
    tenant_id: int,
    sale_return_id: int,
    refund_amount: Decimal,
    cogs_amount: Decimal,
    payment_method: str,
    date=None,
) -> JournalEntry:
    """
    Record journal entry for a sale return.
    Reverses the original sale entries.
    """
    if payment_method == 'cash':
        credit_code = '1000'
    elif payment_method == 'card':
        credit_code = '1010'
    else:
        credit_code = '1200'

    lines = [
        {
            'account_code': '4000',
            'debit': refund_amount,
            'credit': Decimal('0'),
            'description': f'Return #{sale_return_id} revenue reversal',
        },
        {
            'account_code': credit_code,
            'debit': Decimal('0'),
            'credit': refund_amount,
            'description': f'Return #{sale_return_id} refund',
        },
        {
            'account_code': '1100',
            'debit': cogs_amount,
            'credit': Decimal('0'),
            'description': f'Return #{sale_return_id} inventory restore',
        },
        {
            'account_code': '5000',
            'debit': Decimal('0'),
            'credit': cogs_amount,
            'description': f'Return #{sale_return_id} COGS reversal',
        },
    ]

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='return',
        operation_id=sale_return_id,
        lines=lines,
        description=f'Sale return #{sale_return_id}',
        date=date,
    )


def record_debt_payment_journal(
    tenant_id: int,
    payment_id: int,
    amount: Decimal,
    payment_type: str,
    date=None,
) -> JournalEntry:
    """
    Record journal entry for a customer debt payment.
    DR Cash | CR Receivables
    """
    lines = [
        {
            'account_code': '1000',
            'debit': amount,
            'credit': Decimal('0'),
            'description': f'Debt payment #{payment_id}',
        },
        {
            'account_code': '1200',
            'debit': Decimal('0'),
            'credit': amount,
            'description': f'Debt payment #{payment_id} receivable reduction',
        },
    ]

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='debt_payment',
        operation_id=payment_id,
        lines=lines,
        description=f'Customer debt payment #{payment_id}',
        date=date,
    )


def record_supplier_payment_journal(
    tenant_id: int,
    payment_id: int,
    amount: Decimal,
    date=None,
) -> JournalEntry:
    """
    Record journal entry for a supplier payment.
    DR Payables | CR Cash
    """
    lines = [
        {
            'account_code': '2000',
            'debit': amount,
            'credit': Decimal('0'),
            'description': f'Supplier payment #{payment_id}',
        },
        {
            'account_code': '1000',
            'debit': Decimal('0'),
            'credit': amount,
            'description': f'Supplier payment #{payment_id}',
        },
    ]

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='payment',
        operation_id=payment_id,
        lines=lines,
        description=f'Supplier payment #{payment_id}',
        date=date,
    )


def record_expense(
    *,
    tenant_id: int,
    title: str,
    operation_amount: Decimal,
    payment_method: str,
    occurred_at,
    category: str = '',
    notes: str = '',
    operation_currency: str = 'UZS',
    fx_rate_snapshot: Decimal | None = None,
    functional_amount_uzs: Decimal | None = None,
    source_account_code: str | None = None,
) -> Expense:
    """Record non-supplier expense as a first-class domain operation."""
    amount = Decimal(str(operation_amount)).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('operation_amount must be > 0')

    currency = str(operation_currency or 'UZS').upper()
    rate = resolve_fx_rate_snapshot(
        tenant_id=tenant_id,
        operation_currency=currency,
        operation_at=occurred_at,
        fx_rate_snapshot=fx_rate_snapshot,
    )

    if functional_amount_uzs is None:
        functional = to_functional_amount_uzs(
            operation_amount=amount,
            operation_currency=currency,
            fx_rate_snapshot=rate,
        )
    else:
        functional = Decimal(str(functional_amount_uzs)).quantize(Decimal('0.01'))

    if source_account_code:
        cash_account_code = source_account_code
    elif payment_method == 'bank':
        cash_account_code = '1010'
    else:
        cash_account_code = '1000'

    with transaction.atomic():
        expense = Expense.objects.create(
            tenant_id=tenant_id,
            title=title,
            category=category,
            payment_method=payment_method,
            source_account_code=cash_account_code,
            operation_currency=currency,
            operation_amount=amount,
            fx_rate_snapshot=rate,
            functional_amount_uzs=functional,
            occurred_at=occurred_at,
            notes=notes,
        )

        create_journal_entry(
            tenant_id=tenant_id,
            operation_type='payment',
            operation_id=expense.pk,
            lines=[
                {
                    'account_code': '5300',
                    'debit': functional,
                    'credit': Decimal('0'),
                    'description': f'Expense #{expense.pk}: {title}',
                },
                {
                    'account_code': cash_account_code,
                    'debit': Decimal('0'),
                    'credit': functional,
                    'description': f'Expense #{expense.pk} source',
                },
            ],
            description=f'Expense #{expense.pk}: {title}',
            date=occurred_at,
        )

        publish_event(
            event_type='expense.recorded',
            payload={
                'expense_id': expense.pk,
                'amount_uzs': str(functional),
                'currency': currency,
                'operation_amount': str(amount),
                'date': occurred_at.isoformat(),
            },
            tenant_id=tenant_id,
        )

    return expense


def get_account_balance(tenant_id: int, account_code: str) -> Decimal:
    """Calculate current balance for an account."""
    from django.db.models import Sum

    account = get_account(tenant_id, account_code)
    result = JournalLine.objects.filter(
        account=account,
        tenant_id=tenant_id,
    ).aggregate(
        total_debit=Sum('debit'),
        total_credit=Sum('credit'),
    )

    total_debit = result['total_debit'] or Decimal('0')
    total_credit = result['total_credit'] or Decimal('0')

    # Assets and Expenses have debit normal balance
    if account.account_type in ('asset', 'expense'):
        return total_debit - total_credit
    # Liabilities, Equity, Income have credit normal balance
    return total_credit - total_debit


def get_trial_balance(tenant_id: int) -> list[dict]:
    """Get trial balance — all accounts with their balances."""
    accounts = Account.objects.filter(
        tenant_id=tenant_id,
        is_active=True,
    ).order_by('code')

    result = []
    for account in accounts:
        balance = get_account_balance(tenant_id, account.code)
        if balance != 0:
            result.append({
                'account_id': account.pk,
                'code': account.code,
                'name': account.name,
                'account_type': account.account_type,
                'balance': balance,
            })

    return result
