"""
Finance business logic — journal entries, daily summaries.
"""

import json
from decimal import Decimal
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import models, transaction
from django.utils import timezone

from apps.core.services import publish_event

from .models import (
    Account, CashAccount, CashEntry, CurrencyExchange, Expense,
    ExchangeRate, JournalEntry, JournalLine, OwnerContribution, Refund,
)


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
    cash_account_code = '1000' if payment_type == 'cash' else '1010'
    lines = [
        {
            'account_code': cash_account_code,
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


# ---------------------------------------------------------------------------
# Cash layer
# ---------------------------------------------------------------------------

def create_cash_entry(
    *,
    tenant_id: int,
    account: CashAccount,
    direction: str,
    amount: Decimal,
    date,
    source_ref_type: str = '',
    source_ref_id: int | None = None,
) -> CashEntry:
    """
    Create a CashEntry and update CashAccount.balance atomically.
    Must be called inside an outer transaction.atomic() block.
    """
    amount = _to_decimal(amount).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('CashEntry amount must be > 0')

    entry = CashEntry.objects.create(
        tenant_id=tenant_id,
        account=account,
        direction=direction,
        amount=amount,
        date=date,
        source_ref_type=source_ref_type,
        source_ref_id=source_ref_id,
    )

    if direction == CashEntry.Direction.IN:
        CashAccount.objects.filter(pk=account.pk).update(
            balance=models.F('balance') + amount,
        )
    else:
        CashAccount.objects.filter(pk=account.pk).update(
            balance=models.F('balance') - amount,
        )

    return entry


def record_journal_from_cash_entry(
    *,
    tenant_id: int,
    cash_entry: CashEntry,
    operation_type: str,
    operation_id: int,
    counterpart_account_code: str,
    description: str = '',
    date=None,
) -> JournalEntry:
    """
    Auto-generate a balanced JournalEntry for a CashEntry.
    CashAccount must have a linked_account set.
    direction IN  → DR cash_account | CR counterpart
    direction OUT → DR counterpart  | CR cash_account
    """
    cash_account = cash_entry.account
    if not cash_account.linked_account_id:
        raise ValueError(
            f'CashAccount {cash_account.pk} has no linked COA account.'
        )
    cash_code = cash_account.linked_account.code
    amount = cash_entry.amount

    if cash_entry.direction == CashEntry.Direction.IN:
        dr_code, cr_code = cash_code, counterpart_account_code
    else:
        dr_code, cr_code = counterpart_account_code, cash_code

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type=operation_type,
        operation_id=operation_id,
        lines=[
            {
                'account_code': dr_code,
                'debit': amount,
                'credit': Decimal('0'),
                'description': description,
            },
            {
                'account_code': cr_code,
                'debit': Decimal('0'),
                'credit': amount,
                'description': description,
            },
        ],
        description=description,
        date=date or cash_entry.date,
    )


def exchange_currency(
    *,
    tenant_id: int,
    from_account_id: int,
    to_account_id: int,
    from_amount: Decimal,
    rate: Decimal,
    date=None,
    notes: str = '',
) -> CurrencyExchange:
    """
    Atomically exchange from_amount from from_account into to_account at rate.
    Updates both balances and creates a CurrencyExchange record + JournalEntry.
    """
    from_amount = _to_decimal(from_amount).quantize(Decimal('0.01'))
    rate = _to_decimal(rate).quantize(Decimal('0.000001'))
    if from_amount <= 0:
        raise ValueError('from_amount must be > 0')
    if rate <= 0:
        raise ValueError('rate must be > 0')

    to_amount = (from_amount * rate).quantize(Decimal('0.01'))

    if date is None:
        date = timezone.now()

    with transaction.atomic():
        from_acc = CashAccount.objects.select_for_update().get(
            pk=from_account_id, tenant_id=tenant_id,
        )
        to_acc = CashAccount.objects.select_for_update().get(
            pk=to_account_id, tenant_id=tenant_id,
        )

        if from_acc.balance < from_amount:
            raise ValueError(
                f'Insufficient balance in {from_acc.name}: '
                f'have {from_acc.balance}, need {from_amount}.'
            )

        exchange = CurrencyExchange.objects.create(
            tenant_id=tenant_id,
            from_account=from_acc,
            to_account=to_acc,
            from_amount=from_amount,
            from_currency=from_acc.currency,
            to_amount=to_amount,
            to_currency=to_acc.currency,
            effective_rate=rate,
            date=date,
            notes=notes,
        )

        CashAccount.objects.filter(pk=from_acc.pk).update(
            balance=models.F('balance') - from_amount,
        )
        CashAccount.objects.filter(pk=to_acc.pk).update(
            balance=models.F('balance') + to_amount,
        )

        publish_event(
            event_type='finance.currency_exchange',
            payload={
                'exchange_id': exchange.pk,
                'from_amount': str(from_amount),
                'from_currency': from_acc.currency,
                'to_amount': str(to_amount),
                'to_currency': to_acc.currency,
                'rate': str(rate),
            },
            tenant_id=tenant_id,
        )

    return exchange


def refund_customer(
    *,
    tenant_id: int,
    customer_id: int,
    sale_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    fx_rate: Decimal = Decimal('1'),
    method: str,
    account_id: int | None = None,
    return_ref_id: int | None = None,
    date=None,
) -> Refund:
    """
    Issue a customer refund. Invariant: Σ refunds per currency ≤ Σ sale payments per currency.
    CASH/PLASTIK → CashEntry(OUT) + balance reduction.
    RECEIVABLE_OFFSET → reduces Receivable.balances (cancel debt).
    """
    from apps.sales.models import Sale, SalePayment

    if date is None:
        date = timezone.now()

    amount = _to_decimal(amount).quantize(Decimal('0.01'))
    currency = currency.upper()

    if amount <= 0:
        raise ValueError('Refund amount must be > 0')

    with transaction.atomic():
        sale = Sale.objects.get(pk=sale_id, tenant_id=tenant_id)

        paid_total = (
            SalePayment.objects
            .filter(sale=sale, currency=currency, role=SalePayment.Role.INCOMING)
            .aggregate(total=models.Sum('amount'))['total']
        ) or Decimal('0')

        already_refunded = (
            Refund.objects
            .filter(
                tenant_id=tenant_id,
                return_ref__sale_id=sale_id,
                currency=currency,
            )
            .aggregate(total=models.Sum('amount'))['total']
        ) or Decimal('0')

        if already_refunded + amount > paid_total:
            raise ValueError(
                f'Refund {amount} {currency} exceeds paid total '
                f'{paid_total} (already refunded: {already_refunded}).'
            )

        account = None
        if method in (Refund.Method.CASH, Refund.Method.PLASTIK):
            if account_id is None:
                raise ValueError('account_id is required for cash/plastik refund.')
            account = CashAccount.objects.select_for_update().get(
                pk=account_id, tenant_id=tenant_id,
            )
            if account.balance < amount:
                raise ValueError(
                    f'Insufficient cash in {account.name}: '
                    f'have {account.balance}, need {amount}.'
                )
            create_cash_entry(
                tenant_id=tenant_id,
                account=account,
                direction=CashEntry.Direction.OUT,
                amount=amount,
                date=date,
                source_ref_type='refund',
                source_ref_id=None,
            )

        elif method == Refund.Method.RECEIVABLE_OFFSET:
            from apps.customers.services import get_or_create_receivable
            from apps.customers.models import Customer, ReceivableEntry
            customer_obj = Customer.objects.get(pk=customer_id, tenant_id=tenant_id)
            receivable = get_or_create_receivable(customer_obj, tenant_id)
            receivable = type(receivable).objects.select_for_update().get(pk=receivable.pk)
            balances = dict(receivable.balances)
            current = Decimal(str(balances.get(currency, '0')))
            balances[currency] = str(current - amount)
            receivable.balances = balances
            receivable.save(update_fields=['balances', 'updated_at'])

            ReceivableEntry.objects.create(
                tenant_id=tenant_id,
                receivable=receivable,
                date=date,
                amount=-amount,
                currency=currency,
                fx_rate=fx_rate,
                entry_type=ReceivableEntry.EntryType.ADJUSTMENT,
                source_ref=f'refund:pending',
            )

        refund = Refund.objects.create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            date=date,
            amount=amount,
            currency=currency,
            fx_rate=fx_rate,
            account=account,
            method=method,
            return_ref_id=return_ref_id,
        )

        if method != Refund.Method.RECEIVABLE_OFFSET and account and account.linked_account_id:
            cash_entry_qs = CashEntry.objects.filter(
                tenant_id=tenant_id,
                account=account,
                source_ref_type='refund',
                direction=CashEntry.Direction.OUT,
            ).order_by('-id').first()
            if cash_entry_qs:
                cash_entry_qs.source_ref_id = refund.pk
                cash_entry_qs.save(update_fields=['source_ref_id'])
                record_journal_from_cash_entry(
                    tenant_id=tenant_id,
                    cash_entry=cash_entry_qs,
                    operation_type='return',
                    operation_id=refund.pk,
                    counterpart_account_code='1200',
                    description=f'Customer refund #{refund.pk}',
                    date=date,
                )

        publish_event(
            event_type='finance.refund',
            payload={
                'refund_id': refund.pk,
                'customer_id': customer_id,
                'amount': str(amount),
                'currency': currency,
                'method': method,
            },
            tenant_id=tenant_id,
        )

    return refund


def record_owner_contribution(
    *,
    tenant_id: int,
    amount: Decimal,
    currency: str = 'UZS',
    to_account_id: int,
    date=None,
    notes: str = '',
) -> OwnerContribution:
    """
    Record equity injection by owner into a CashAccount.
    DR CashAccount | CR Owner equity (3000).
    """
    if date is None:
        date = timezone.now()

    amount = _to_decimal(amount).quantize(Decimal('0.01'))
    if amount <= 0:
        raise ValueError('Contribution amount must be > 0')

    with transaction.atomic():
        account = CashAccount.objects.select_for_update().get(
            pk=to_account_id, tenant_id=tenant_id,
        )

        contribution = OwnerContribution.objects.create(
            tenant_id=tenant_id,
            amount=amount,
            currency=currency,
            to_account=account,
            date=date,
            notes=notes,
        )

        cash_entry = create_cash_entry(
            tenant_id=tenant_id,
            account=account,
            direction=CashEntry.Direction.IN,
            amount=amount,
            date=date,
            source_ref_type='owner_contribution',
            source_ref_id=contribution.pk,
        )

        if account.linked_account_id:
            record_journal_from_cash_entry(
                tenant_id=tenant_id,
                cash_entry=cash_entry,
                operation_type='payment',
                operation_id=contribution.pk,
                counterpart_account_code='3000',
                description=f'Owner contribution #{contribution.pk}',
                date=date,
            )

        publish_event(
            event_type='finance.owner_contribution',
            payload={
                'contribution_id': contribution.pk,
                'amount': str(amount),
                'currency': currency,
                'account_id': account.pk,
            },
            tenant_id=tenant_id,
        )

    return contribution
