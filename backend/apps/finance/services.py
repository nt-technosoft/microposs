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


def record_sale_settlement_journal(
    *,
    tenant_id: int,
    sale_id: int,
    amount: Decimal,
    payment_method: str,
    debit_account_code: str | None = None,
    description: str = '',
    date=None,
) -> JournalEntry:
    """
    Record only the revenue/settlement side of a sale.
    Used for cash/card/transfer/credit splits so mixed sales can be journaled
    without duplicating revenue or forcing everything into a single entry.
    """
    normalized_amount = _to_decimal(amount).quantize(Decimal('0.01'))
    if normalized_amount <= 0:
        raise ValueError('Sale settlement journal amount must be > 0')

    method = str(payment_method or '').upper()
    if debit_account_code:
        debit_code = debit_account_code
    elif method == 'CASH':
        debit_code = '1000'
    elif method in {'CARD', 'TRANSFER'}:
        debit_code = '1010'
    else:
        debit_code = '1200'

    journal_description = description or f'Sale #{sale_id} settlement'
    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='sale',
        operation_id=sale_id,
        lines=[
            {
                'account_code': debit_code,
                'debit': normalized_amount,
                'credit': Decimal('0'),
                'description': journal_description,
            },
            {
                'account_code': '4000',
                'debit': Decimal('0'),
                'credit': normalized_amount,
                'description': journal_description,
            },
        ],
        description=journal_description,
        date=date,
    )


def record_sale_cogs_journal(
    *,
    tenant_id: int,
    sale_id: int,
    total_cogs: Decimal,
    date=None,
) -> JournalEntry | None:
    """Record the cost/inventory side of a sale once per completed sale."""
    normalized_cogs = _to_decimal(total_cogs).quantize(Decimal('0.01'))
    if normalized_cogs <= 0:
        return None

    return create_journal_entry(
        tenant_id=tenant_id,
        operation_type='sale',
        operation_id=sale_id,
        lines=[
            {
                'account_code': '5000',
                'debit': normalized_cogs,
                'credit': Decimal('0'),
                'description': f'Sale #{sale_id} cost of goods',
            },
            {
                'account_code': '1100',
                'debit': Decimal('0'),
                'credit': normalized_cogs,
                'description': f'Sale #{sale_id} inventory reduction',
            },
        ],
        description=f'Sale #{sale_id} COGS',
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


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal('0.00')
    return ((numerator / denominator) * Decimal('100')).quantize(Decimal('0.01'))


def _investor_profit_from_distribution(line) -> Decimal:
    snapshot = line.profit_distribution_snapshot or {}
    contract_snapshot = line.lot.contract_snapshot or {}
    return _investor_profit_from_snapshot(
        snapshot=snapshot,
        contract_snapshot=contract_snapshot,
    )


def _investor_profit_from_snapshot(
    *,
    snapshot: dict | None,
    contract_snapshot: dict | None,
) -> Decimal:
    snapshot = snapshot or {}
    contract_snapshot = contract_snapshot or {}
    partner_roles = {
        str(meta.get('partner_id')): meta.get('role')
        for meta in contract_snapshot.get('partners', []) or []
        if meta.get('partner_id') is not None
    }
    return sum(
        (
            Decimal(str(amount))
            for partner_id, amount in snapshot.items()
            if partner_roles.get(str(partner_id)) == 'INVESTOR'
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))


def get_sales_profitability_rows(
    *,
    tenant_id: int,
    date_from=None,
    date_to=None,
    location_id: int | None = None,
) -> list[dict]:
    from apps.sales.models import Sale

    queryset = (
        Sale.objects
        .filter(tenant_id=tenant_id, status=Sale.SaleStatus.COMPLETED)
        .select_related('location', 'customer')
        .prefetch_related('payments', 'lines__lot', 'lines__product_variant__product')
        .order_by('-date', '-id')
    )
    if date_from:
        queryset = queryset.filter(date__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(date__date__lte=date_to)
    if location_id:
        queryset = queryset.filter(location_id=location_id)

    rows: list[dict] = []
    for sale in queryset:
        investor_profit = sum(
            (_investor_profit_from_distribution(line) for line in sale.lines.all()),
            Decimal('0.00'),
        ).quantize(Decimal('0.01'))
        gross_profit = _money(sale.total_amount - sale.total_cogs)
        rows.append({
            'sale_id': sale.id,
            'date': sale.date,
            'location_id': sale.location_id,
            'location_name': sale.location.name,
            'customer_id': sale.customer_id,
            'customer_name': getattr(sale.customer, 'name', None),
            'payment_methods': sorted({payment.method for payment in sale.payments.all()}),
            'line_count': sale.lines.count(),
            'quantity_sold': sum(int(line.quantity) for line in sale.lines.all()),
            'revenue': _money(sale.total_amount),
            'cogs': _money(sale.total_cogs),
            'gross_profit': gross_profit,
            'investor_profit': investor_profit,
            'business_profit': _money(gross_profit - investor_profit),
            'margin_percent': _percent(gross_profit, _money(sale.total_amount)),
            'markup_percent': _percent(gross_profit, _money(sale.total_cogs)),
        })
    return rows


def get_product_profitability_rows(
    *,
    tenant_id: int,
    date_from=None,
    date_to=None,
    location_id: int | None = None,
    warehouse_id: int | None = None,
) -> list[dict]:
    from apps.inventory.models import LotStock
    from apps.sales.models import SaleLine
    from apps.sales.services import calculate_profit_distribution

    sale_lines = (
        SaleLine.objects
        .filter(tenant_id=tenant_id, sale__status='completed')
        .select_related('sale__location', 'lot', 'product_variant__product')
        .order_by('product_variant_id', 'id')
    )
    if date_from:
        sale_lines = sale_lines.filter(sale__date__date__gte=date_from)
    if date_to:
        sale_lines = sale_lines.filter(sale__date__date__lte=date_to)
    if location_id:
        sale_lines = sale_lines.filter(sale__location_id=location_id)

    rows: dict[int, dict] = {}

    def ensure_row(variant) -> dict:
        row = rows.get(variant.id)
        if row is None:
            current_unit_price = _money(variant.effective_price or Decimal('0'))
            row = {
                'product_variant_id': variant.id,
                'product_name': variant.product.name,
                'current_unit_price': current_unit_price,
                'quantity_sold': 0,
                'revenue': Decimal('0.00'),
                'cogs': Decimal('0.00'),
                'gross_profit': Decimal('0.00'),
                'investor_profit': Decimal('0.00'),
                'business_profit': Decimal('0.00'),
                'margin_percent': Decimal('0.00'),
                'markup_percent': Decimal('0.00'),
                'remaining_quantity': 0,
                'remaining_landed_cost': Decimal('0.00'),
                'projected_revenue': Decimal('0.00'),
                'projected_gross_profit': Decimal('0.00'),
                'projected_investor_profit': Decimal('0.00'),
                'projected_business_profit': Decimal('0.00'),
            }
            rows[variant.id] = row
        return row

    for line in sale_lines:
        row = ensure_row(line.product_variant)
        revenue = _money(Decimal(str(line.unit_price)) * Decimal(str(line.quantity)))
        cogs = _money(Decimal(str(line.unit_landed_cost)) * Decimal(str(line.quantity)))
        gross = _money(revenue - cogs)
        investor_profit = _investor_profit_from_distribution(line)
        row['quantity_sold'] += int(line.quantity)
        row['revenue'] += revenue
        row['cogs'] += cogs
        row['gross_profit'] += gross
        row['investor_profit'] += investor_profit

    remaining_stock = (
        LotStock.objects
        .filter(tenant_id=tenant_id, quantity_remaining__gt=0)
        .select_related('lot__product_variant__product')
        .order_by('lot__product_variant_id', 'id')
    )
    if warehouse_id:
        remaining_stock = remaining_stock.filter(warehouse_id=warehouse_id)

    for stock in remaining_stock:
        variant = stock.lot.product_variant
        row = ensure_row(variant)
        qty = int(stock.quantity_remaining)
        current_price = row['current_unit_price']
        remaining_cost = _money(Decimal(str(stock.lot.landed_cost_per_unit)) * Decimal(str(qty)))
        projected_revenue = _money(current_price * Decimal(str(qty)))
        projected_gross = _money(projected_revenue - remaining_cost)
        distribution = calculate_profit_distribution(
            lot=stock.lot,
            unit_price=current_price,
            quantity=qty,
            unit_landed_cost=Decimal(str(stock.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = sum(
            (
                Decimal(str(amount))
                for partner_id, amount in distribution.items()
                if any(
                    str(meta.get('partner_id')) == str(partner_id)
                    and meta.get('role') == 'INVESTOR'
                    for meta in (stock.lot.contract_snapshot or {}).get('partners', []) or []
                )
            ),
            Decimal('0.00'),
        ).quantize(Decimal('0.01'))

        row['remaining_quantity'] += qty
        row['remaining_landed_cost'] += remaining_cost
        row['projected_revenue'] += projected_revenue
        row['projected_gross_profit'] += projected_gross
        row['projected_investor_profit'] += projected_investor_profit

    result: list[dict] = []
    for row in rows.values():
        row['revenue'] = _money(row['revenue'])
        row['cogs'] = _money(row['cogs'])
        row['gross_profit'] = _money(row['gross_profit'])
        row['investor_profit'] = _money(row['investor_profit'])
        row['business_profit'] = _money(row['gross_profit'] - row['investor_profit'])
        row['margin_percent'] = _percent(row['gross_profit'], row['revenue'])
        row['markup_percent'] = _percent(row['gross_profit'], row['cogs'])
        row['remaining_landed_cost'] = _money(row['remaining_landed_cost'])
        row['projected_revenue'] = _money(row['projected_revenue'])
        row['projected_gross_profit'] = _money(row['projected_gross_profit'])
        row['projected_investor_profit'] = _money(row['projected_investor_profit'])
        row['projected_business_profit'] = _money(
            row['projected_gross_profit'] - row['projected_investor_profit']
        )
        result.append(row)

    result.sort(key=lambda item: (-Decimal(str(item['gross_profit'])), item['product_name']))
    return result


def get_procurement_profitability_rows(
    *,
    tenant_id: int,
    date_from=None,
    date_to=None,
    procurement_id: int | None = None,
) -> list[dict]:
    from apps.inventory.models import LotStock
    from apps.partnerships.models import Procurement
    from apps.sales.models import SaleLine
    from apps.sales.services import calculate_profit_distribution

    sale_lines = (
        SaleLine.objects
        .filter(
            tenant_id=tenant_id,
            sale__status='completed',
            lot__procurement_item__isnull=False,
        )
        .select_related(
            'sale',
            'lot__product_variant',
            'lot__procurement_item__procurement__supplier',
        )
        .order_by('lot__procurement_item__procurement_id', 'id')
    )
    if date_from:
        sale_lines = sale_lines.filter(sale__date__date__gte=date_from)
    if date_to:
        sale_lines = sale_lines.filter(sale__date__date__lte=date_to)
    if procurement_id:
        sale_lines = sale_lines.filter(lot__procurement_item__procurement_id=procurement_id)
    sale_lines = list(sale_lines)

    remaining_stock = list(
        LotStock.objects
        .filter(
            tenant_id=tenant_id,
            quantity_remaining__gt=0,
            lot__procurement_item__isnull=False,
        )
        .select_related(
            'lot__product_variant',
            'lot__procurement_item__procurement__supplier',
        )
        .order_by('lot__procurement_item__procurement_id', 'id')
    )
    if procurement_id:
        remaining_stock = [
            stock for stock in remaining_stock
            if stock.lot.procurement_item.procurement_id == procurement_id
        ]

    procurement_ids = {
        line.lot.procurement_item.procurement_id
        for line in sale_lines
        if line.lot.procurement_item_id
    } | {
        stock.lot.procurement_item.procurement_id
        for stock in remaining_stock
        if stock.lot.procurement_item_id
    }

    procurements = (
        Procurement.objects
        .filter(tenant_id=tenant_id, id__in=procurement_ids)
        .select_related('supplier')
        .prefetch_related('items')
    )
    procurement_map = {procurement.id: procurement for procurement in procurements}

    rows: dict[int, dict] = {}

    def ensure_row(procurement_id: int) -> dict | None:
        procurement = procurement_map.get(procurement_id)
        if procurement is None:
            return None

        row = rows.get(procurement_id)
        if row is None:
            row = {
                'procurement_id': procurement.id,
                'procurement_type': procurement.procurement_type,
                'status': procurement.status,
                'opened_at': procurement.opened_at,
                'received_at': procurement.received_at,
                'supplier_name': getattr(procurement.supplier, 'name', None),
                'item_count': len(procurement.items.all()),
                'quantity_sold': 0,
                'remaining_quantity': 0,
                'revenue': Decimal('0.00'),
                'cogs': Decimal('0.00'),
                'gross_profit': Decimal('0.00'),
                'investor_profit': Decimal('0.00'),
                'business_profit': Decimal('0.00'),
                'margin_percent': Decimal('0.00'),
                'markup_percent': Decimal('0.00'),
                'remaining_landed_cost': Decimal('0.00'),
                'projected_revenue': Decimal('0.00'),
                'projected_gross_profit': Decimal('0.00'),
                'projected_investor_profit': Decimal('0.00'),
                'projected_business_profit': Decimal('0.00'),
            }
            rows[procurement_id] = row
        return row

    for line in sale_lines:
        procurement_id = line.lot.procurement_item.procurement_id
        row = ensure_row(procurement_id)
        if row is None:
            continue

        revenue = _money(Decimal(str(line.unit_price)) * Decimal(str(line.quantity)))
        cogs = _money(Decimal(str(line.unit_landed_cost)) * Decimal(str(line.quantity)))
        gross = _money(revenue - cogs)
        investor_profit = _investor_profit_from_distribution(line)

        row['quantity_sold'] += int(line.quantity)
        row['revenue'] += revenue
        row['cogs'] += cogs
        row['gross_profit'] += gross
        row['investor_profit'] += investor_profit

    for stock in remaining_stock:
        procurement_id = stock.lot.procurement_item.procurement_id
        row = ensure_row(procurement_id)
        if row is None:
            continue

        qty = int(stock.quantity_remaining)
        current_price = _money(stock.lot.product_variant.effective_price or Decimal('0'))
        remaining_cost = _money(Decimal(str(stock.lot.landed_cost_per_unit)) * Decimal(str(qty)))
        projected_revenue = _money(current_price * Decimal(str(qty)))
        projected_gross = _money(projected_revenue - remaining_cost)
        distribution = calculate_profit_distribution(
            lot=stock.lot,
            unit_price=current_price,
            quantity=qty,
            unit_landed_cost=Decimal(str(stock.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = _investor_profit_from_snapshot(
            snapshot=distribution,
            contract_snapshot=stock.lot.contract_snapshot,
        )

        row['remaining_quantity'] += qty
        row['remaining_landed_cost'] += remaining_cost
        row['projected_revenue'] += projected_revenue
        row['projected_gross_profit'] += projected_gross
        row['projected_investor_profit'] += projected_investor_profit

    result: list[dict] = []
    for row in rows.values():
        row['revenue'] = _money(row['revenue'])
        row['cogs'] = _money(row['cogs'])
        row['gross_profit'] = _money(row['gross_profit'])
        row['investor_profit'] = _money(row['investor_profit'])
        row['business_profit'] = _money(row['gross_profit'] - row['investor_profit'])
        row['margin_percent'] = _percent(row['gross_profit'], row['revenue'])
        row['markup_percent'] = _percent(row['gross_profit'], row['cogs'])
        row['remaining_landed_cost'] = _money(row['remaining_landed_cost'])
        row['projected_revenue'] = _money(row['projected_revenue'])
        row['projected_gross_profit'] = _money(row['projected_gross_profit'])
        row['projected_investor_profit'] = _money(row['projected_investor_profit'])
        row['projected_business_profit'] = _money(
            row['projected_gross_profit'] - row['projected_investor_profit']
        )
        result.append(row)

    result.sort(
        key=lambda item: (
            -Decimal(str(item['gross_profit'])),
            -Decimal(str(item['projected_gross_profit'])),
            item['procurement_id'],
        )
    )
    return result


def get_procurement_profitability_detail(
    *,
    tenant_id: int,
    procurement_id: int,
) -> dict:
    from apps.inventory.models import LotStock
    from apps.partnerships.models import Procurement
    from apps.sales.models import SaleLine
    from apps.sales.services import calculate_profit_distribution

    procurement = (
        Procurement.objects
        .filter(tenant_id=tenant_id, id=procurement_id)
        .select_related('supplier')
        .prefetch_related('items__product_variant__product', 'items__lots__stocks')
        .first()
    )
    if procurement is None:
        raise Procurement.DoesNotExist

    summary_rows = get_procurement_profitability_rows(
        tenant_id=tenant_id,
        procurement_id=procurement_id,
    )
    summary = summary_rows[0] if summary_rows else {
        'procurement_id': procurement.id,
        'procurement_type': procurement.procurement_type,
        'status': procurement.status,
        'opened_at': procurement.opened_at,
        'received_at': procurement.received_at,
        'supplier_name': getattr(procurement.supplier, 'name', None),
        'item_count': procurement.items.count(),
        'quantity_sold': 0,
        'remaining_quantity': 0,
        'revenue': Decimal('0.00'),
        'cogs': Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
        'investor_profit': Decimal('0.00'),
        'business_profit': Decimal('0.00'),
        'margin_percent': Decimal('0.00'),
        'markup_percent': Decimal('0.00'),
        'remaining_landed_cost': Decimal('0.00'),
        'projected_revenue': Decimal('0.00'),
        'projected_gross_profit': Decimal('0.00'),
        'projected_investor_profit': Decimal('0.00'),
        'projected_business_profit': Decimal('0.00'),
    }

    sale_lines = list(
        SaleLine.objects
        .filter(
            tenant_id=tenant_id,
            sale__status='completed',
            lot__procurement_item__procurement_id=procurement_id,
        )
        .select_related('lot__procurement_item', 'product_variant__product')
        .order_by('lot__procurement_item_id', 'id')
    )
    remaining_stock = list(
        LotStock.objects
        .filter(
            tenant_id=tenant_id,
            quantity_remaining__gt=0,
            lot__procurement_item__procurement_id=procurement_id,
        )
        .select_related('lot__procurement_item', 'lot__product_variant__product')
        .order_by('lot__procurement_item_id', 'id')
    )

    rows: dict[int, dict] = {}

    def ensure_item_row(procurement_item) -> dict:
        row = rows.get(procurement_item.id)
        if row is not None:
            return row

        lots = list(procurement_item.lots.all())
        current_unit_price = _money(procurement_item.product_variant.effective_price or Decimal('0'))
        if lots:
            landed_cost_per_unit = _money(
                sum((Decimal(str(lot.landed_cost_per_unit)) for lot in lots), Decimal('0.00'))
                / Decimal(str(len(lots)))
            )
            unit_purchase_price = _money(
                sum((Decimal(str(lot.unit_purchase_price)) for lot in lots), Decimal('0.00'))
                / Decimal(str(len(lots)))
            )
        else:
            landed_cost_per_unit = Decimal('0.00')
            unit_purchase_price = _money(
                Decimal(str(procurement_item.unit_purchase_price))
                * Decimal(str(procurement_item.fx_rate or '1'))
            )

        row = {
            'procurement_item_id': procurement_item.id,
            'product_variant_id': procurement_item.product_variant_id,
            'product_name': procurement_item.product_variant.product.name,
            'current_unit_price': current_unit_price,
            'purchased_quantity': int(procurement_item.quantity),
            'sold_quantity': 0,
            'remaining_quantity': 0,
            'unit_purchase_price': unit_purchase_price,
            'landed_cost_per_unit': landed_cost_per_unit,
            'revenue': Decimal('0.00'),
            'cogs': Decimal('0.00'),
            'gross_profit': Decimal('0.00'),
            'investor_profit': Decimal('0.00'),
            'business_profit': Decimal('0.00'),
            'margin_percent': Decimal('0.00'),
            'markup_percent': Decimal('0.00'),
            'remaining_landed_cost': Decimal('0.00'),
            'projected_revenue': Decimal('0.00'),
            'projected_gross_profit': Decimal('0.00'),
            'projected_investor_profit': Decimal('0.00'),
            'projected_business_profit': Decimal('0.00'),
        }
        rows[procurement_item.id] = row
        return row

    for item in procurement.items.all():
        ensure_item_row(item)

    for line in sale_lines:
        row = ensure_item_row(line.lot.procurement_item)
        revenue = _money(Decimal(str(line.unit_price)) * Decimal(str(line.quantity)))
        cogs = _money(Decimal(str(line.unit_landed_cost)) * Decimal(str(line.quantity)))
        gross_profit = _money(revenue - cogs)
        investor_profit = _investor_profit_from_distribution(line)

        row['sold_quantity'] += int(line.quantity)
        row['revenue'] += revenue
        row['cogs'] += cogs
        row['gross_profit'] += gross_profit
        row['investor_profit'] += investor_profit

    for stock in remaining_stock:
        row = ensure_item_row(stock.lot.procurement_item)
        quantity = int(stock.quantity_remaining)
        current_price = row['current_unit_price']
        remaining_cost = _money(Decimal(str(stock.lot.landed_cost_per_unit)) * Decimal(str(quantity)))
        projected_revenue = _money(current_price * Decimal(str(quantity)))
        projected_gross_profit = _money(projected_revenue - remaining_cost)
        distribution = calculate_profit_distribution(
            lot=stock.lot,
            unit_price=current_price,
            quantity=quantity,
            unit_landed_cost=Decimal(str(stock.lot.landed_cost_per_unit)),
        )
        projected_investor_profit = _investor_profit_from_snapshot(
            snapshot=distribution,
            contract_snapshot=stock.lot.contract_snapshot,
        )

        row['remaining_quantity'] += quantity
        row['remaining_landed_cost'] += remaining_cost
        row['projected_revenue'] += projected_revenue
        row['projected_gross_profit'] += projected_gross_profit
        row['projected_investor_profit'] += projected_investor_profit

    item_rows: list[dict] = []
    for row in rows.values():
        row['revenue'] = _money(row['revenue'])
        row['cogs'] = _money(row['cogs'])
        row['gross_profit'] = _money(row['gross_profit'])
        row['investor_profit'] = _money(row['investor_profit'])
        row['business_profit'] = _money(row['gross_profit'] - row['investor_profit'])
        row['margin_percent'] = _percent(row['gross_profit'], row['revenue'])
        row['markup_percent'] = _percent(row['gross_profit'], row['cogs'])
        row['remaining_landed_cost'] = _money(row['remaining_landed_cost'])
        row['projected_revenue'] = _money(row['projected_revenue'])
        row['projected_gross_profit'] = _money(row['projected_gross_profit'])
        row['projected_investor_profit'] = _money(row['projected_investor_profit'])
        row['projected_business_profit'] = _money(
            row['projected_gross_profit'] - row['projected_investor_profit']
        )
        item_rows.append(row)

    item_rows.sort(
        key=lambda item: (
            -Decimal(str(item['gross_profit'])),
            -Decimal(str(item['projected_gross_profit'])),
            item['product_name'],
        )
    )

    return {
        'procurement': summary,
        'items': item_rows,
    }


def get_agreement_profitability_detail(
    *,
    tenant_id: int,
    agreement_id: int,
) -> dict:
    from apps.partnerships.models import (
        AgreementAllocation,
        InvestmentAgreement,
        PartnerLedgerEntry,
        ProcurementPartnerLedger,
    )

    agreement = (
        InvestmentAgreement.objects
        .filter(tenant_id=tenant_id, id=agreement_id)
        .select_related('supplier')
        .prefetch_related(
            'partners__partner',
            'contributions',
            'withdrawals',
            'allocations',
            'procurements__supplier',
            'procurements__items',
            'procurements__expenses',
            'procurements__receive_batches__capital_allocations__partner',
        )
        .first()
    )
    if agreement is None:
        raise InvestmentAgreement.DoesNotExist

    procurement_rows: list[dict] = []
    totals = {
        'revenue': Decimal('0.00'),
        'cogs': Decimal('0.00'),
        'gross_profit': Decimal('0.00'),
        'investor_profit': Decimal('0.00'),
        'business_profit': Decimal('0.00'),
        'remaining_landed_cost': Decimal('0.00'),
        'projected_revenue': Decimal('0.00'),
        'projected_gross_profit': Decimal('0.00'),
        'projected_investor_profit': Decimal('0.00'),
        'projected_business_profit': Decimal('0.00'),
        'pending_prepaid_cost': Decimal('0.00'),
        'quantity_sold': 0,
        'remaining_quantity': 0,
    }
    procurements = list(agreement.procurements.all())
    pending_prepaid_by_procurement: dict[int, Decimal] = {}
    for procurement in procurements:
        rows = get_procurement_profitability_rows(
            tenant_id=tenant_id,
            procurement_id=procurement.id,
        )
        if rows:
            row = rows[0]
        else:
            row = {
                'procurement_id': procurement.id,
                'procurement_type': procurement.procurement_type,
                'status': procurement.status,
                'opened_at': procurement.opened_at,
                'received_at': procurement.received_at,
                'supplier_name': getattr(procurement.supplier, 'name', None),
                'item_count': procurement.items.count(),
                'quantity_sold': 0,
                'remaining_quantity': 0,
                'revenue': Decimal('0.00'),
                'cogs': Decimal('0.00'),
                'gross_profit': Decimal('0.00'),
                'investor_profit': Decimal('0.00'),
                'business_profit': Decimal('0.00'),
                'margin_percent': Decimal('0.00'),
                'markup_percent': Decimal('0.00'),
                'remaining_landed_cost': Decimal('0.00'),
                'projected_revenue': Decimal('0.00'),
                'projected_gross_profit': Decimal('0.00'),
                'projected_investor_profit': Decimal('0.00'),
                'projected_business_profit': Decimal('0.00'),
            }
        procurement_pending_cost = Decimal('0.00')
        pending_paid_items_count = 0
        draft_items_count = 0
        for key in ['revenue', 'cogs', 'gross_profit', 'investor_profit', 'business_profit',
                    'remaining_landed_cost', 'projected_revenue', 'projected_gross_profit',
                    'projected_investor_profit', 'projected_business_profit']:
            totals[key] += Decimal(str(row[key]))
        totals['quantity_sold'] += int(row['quantity_sold'])
        totals['remaining_quantity'] += int(row['remaining_quantity'])
        for item in procurement.items.all():
            if item.status == 'PAID':
                pending_paid_items_count += 1
                procurement_pending_cost += _money(
                    Decimal(str(item.quantity))
                    * Decimal(str(item.unit_purchase_price))
                    * Decimal(str(item.fx_rate or '1'))
                )
            elif item.status == 'DRAFT':
                draft_items_count += 1
        for expense in procurement.expenses.all():
            if expense.status == 'PAID':
                procurement_pending_cost += _money(
                    Decimal(str(expense.amount))
                    * Decimal(str(expense.fx_rate or '1'))
                )
        pending_prepaid_by_procurement[procurement.id] = _money(procurement_pending_cost)
        totals['pending_prepaid_cost'] += _money(procurement_pending_cost)
        row['received_landed_cost'] = _money(Decimal(str(row['cogs'])) + Decimal(str(row['remaining_landed_cost'])))
        row['pending_prepaid_cost'] = _money(procurement_pending_cost)
        row['receive_batches_count'] = procurement.receive_batches.count()
        row['receive_batches'] = [
            {
                'id': batch.id,
                'received_at': batch.received_at,
                'items_count': batch.items_count,
                'total_inventory_uzs': _money(batch.total_inventory_uzs),
                'capital_allocations': [
                    {
                        'partner_id': allocation.partner_id,
                        'partner_name': allocation.partner.display_name,
                        'role': allocation.role,
                        'amount_contract_currency': _money(allocation.amount_contract_currency),
                        'capital_share': Decimal(str(allocation.capital_share)).quantize(Decimal('0.000001')),
                        'profit_share': Decimal(str(allocation.profit_share)).quantize(Decimal('0.000001')),
                    }
                    for allocation in batch.capital_allocations.all()
                ],
            }
            for batch in procurement.receive_batches.all()
        ]
        row['pending_paid_items_count'] = pending_paid_items_count
        row['draft_items_count'] = draft_items_count
        procurement_rows.append(row)

    ledger_rows = (
        PartnerLedgerEntry.objects
        .filter(
            ledger__tenant_id=tenant_id,
            ledger__procurement__agreement_id=agreement.id,
        )
        .values('ledger__partner_id', 'ledger__partner__display_name', 'entry_type')
        .annotate(total=models.Sum('functional_amount_uzs'))
    )
    partner_rows = {
        member.partner_id: {
            'partner_id': member.partner_id,
            'partner_name': member.partner.display_name,
            'role': member.role,
            'agreement_currency': agreement.currency,
            'planned_capital_share': str(_money(Decimal(str(member.planned_capital_share)))),
            'planned_profit_share': str(Decimal(str(member.profit_share)).quantize(Decimal('0.000001'))),
            'agreement_contributed': Decimal('0.00'),
            'agreement_withdrawn': Decimal('0.00'),
            'agreement_allocated': Decimal('0.00'),
            'agreement_returned': Decimal('0.00'),
            'agreement_available': Decimal('0.00'),
            'capital_in': Decimal('0.00'),
            'capital_out': Decimal('0.00'),
            'profit_accrued': Decimal('0.00'),
            'profit_reversed': Decimal('0.00'),
            'losses_incurred': Decimal('0.00'),
            'dividends_paid': Decimal('0.00'),
        }
        for member in agreement.partners.all()
    }
    entry_map = {
        'CAPITAL_IN': 'capital_in',
        'CAPITAL_OUT': 'capital_out',
        'PROFIT_ACCRUED': 'profit_accrued',
        'PROFIT_REVERSED': 'profit_reversed',
        'LOSS_INCURRED': 'losses_incurred',
        'DIVIDEND_PAID': 'dividends_paid',
    }
    for row in ledger_rows:
        partner_id = row['ledger__partner_id']
        target = partner_rows.setdefault(partner_id, {
            'partner_id': partner_id,
            'partner_name': row['ledger__partner__display_name'],
            'role': '',
            'agreement_currency': agreement.currency,
            'planned_capital_share': '0.00',
            'planned_profit_share': '0.000000',
            'agreement_contributed': Decimal('0.00'),
            'agreement_withdrawn': Decimal('0.00'),
            'agreement_allocated': Decimal('0.00'),
            'agreement_returned': Decimal('0.00'),
            'agreement_available': Decimal('0.00'),
            'capital_in': Decimal('0.00'),
            'capital_out': Decimal('0.00'),
            'profit_accrued': Decimal('0.00'),
            'profit_reversed': Decimal('0.00'),
            'losses_incurred': Decimal('0.00'),
            'dividends_paid': Decimal('0.00'),
        })
        key = entry_map.get(row['entry_type'])
        if key:
            target[key] += Decimal(str(row['total'] or '0'))

    def _to_agreement_currency(amount, currency, fx_rate) -> Decimal:
        amount_dec = Decimal(str(amount))
        source = str(currency or agreement.currency or 'UZS').upper()
        target = str(agreement.currency or 'UZS').upper()
        rate_dec = Decimal(str(fx_rate or '1'))
        if source == target:
            return _money(amount_dec)
        if source == 'USD' and target == 'UZS':
            return _money(amount_dec * rate_dec)
        if source == 'UZS' and target == 'USD':
            if rate_dec <= 0:
                return Decimal('0.00')
            return _money(amount_dec / rate_dec)
        return _money(amount_dec)

    for contribution in agreement.contributions.all():
        if contribution.partner_id in partner_rows:
            partner_rows[contribution.partner_id]['agreement_contributed'] += _to_agreement_currency(
                contribution.amount,
                contribution.currency,
                contribution.fx_rate,
            )

    for withdrawal in agreement.withdrawals.all():
        if withdrawal.partner_id in partner_rows:
            partner_rows[withdrawal.partner_id]['agreement_withdrawn'] += _to_agreement_currency(
                withdrawal.amount,
                withdrawal.currency,
                withdrawal.fx_rate,
            )

    allocations = AgreementAllocation.objects.filter(agreement=agreement)
    allocated_by_partner: dict[int, Decimal] = {}
    returned_by_partner: dict[int, Decimal] = {}
    for allocation in allocations:
        if allocation.partner_id in partner_rows:
            agreement_amount = _to_agreement_currency(
                allocation.amount,
                allocation.currency,
                allocation.fx_rate,
            )
            key = (
                'agreement_returned'
                if allocation.direction == AgreementAllocation.Direction.FROM_PROCUREMENT
                else 'agreement_allocated'
            )
            partner_rows[allocation.partner_id][key] += agreement_amount
        amount = Decimal(str(allocation.amount)) * Decimal(str(allocation.fx_rate or '1'))
        target = returned_by_partner if allocation.direction == AgreementAllocation.Direction.FROM_PROCUREMENT else allocated_by_partner
        target[allocation.partner_id] = _money(target.get(allocation.partner_id, Decimal('0.00')) + amount)

    procurement_capital: dict[int, dict[int, Decimal]] = {}
    capital_entries = (
        PartnerLedgerEntry.objects
        .filter(
            ledger__tenant_id=tenant_id,
            ledger__procurement__agreement_id=agreement.id,
            entry_type__in=['CAPITAL_IN', 'CAPITAL_OUT'],
        )
        .values('ledger__procurement_id', 'ledger__partner_id', 'entry_type')
        .annotate(total=models.Sum('functional_amount_uzs'))
    )
    for entry in capital_entries:
        procurement_id = entry['ledger__procurement_id']
        partner_id = entry['ledger__partner_id']
        sign = Decimal('1') if entry['entry_type'] == 'CAPITAL_IN' else Decimal('-1')
        bucket = procurement_capital.setdefault(procurement_id, {})
        bucket[partner_id] = _money(bucket.get(partner_id, Decimal('0.00')) + sign * Decimal(str(entry['total'] or '0')))

    pending_prepaid_by_partner: dict[int, Decimal] = {}
    for procurement_id, pending_cost in pending_prepaid_by_procurement.items():
        if pending_cost <= 0:
            continue
        capital_map = {
            partner_id: amount
            for partner_id, amount in procurement_capital.get(procurement_id, {}).items()
            if amount > 0
        }
        total_capital = sum(capital_map.values(), Decimal('0.00'))
        if total_capital <= 0:
            continue
        for partner_id, amount in capital_map.items():
            share_amount = _money(pending_cost * amount / total_capital)
            pending_prepaid_by_partner[partner_id] = _money(
                pending_prepaid_by_partner.get(partner_id, Decimal('0.00')) + share_amount
            )

    serialized_partners = []
    for row in partner_rows.values():
        profit_pending = (
            row['profit_accrued']
            - row['profit_reversed']
            - row['losses_incurred']
            - row['dividends_paid']
        )
        row['allocated_functional_uzs'] = allocated_by_partner.get(row['partner_id'], Decimal('0.00'))
        row['returned_functional_uzs'] = returned_by_partner.get(row['partner_id'], Decimal('0.00'))
        row['pending_prepaid_cost_estimate_uzs'] = pending_prepaid_by_partner.get(row['partner_id'], Decimal('0.00'))
        row['agreement_available'] = (
            row['agreement_contributed']
            - row['agreement_withdrawn']
            - row['agreement_allocated']
            + row['agreement_returned']
        )
        row['profit_pending_payout'] = max(Decimal('0.00'), profit_pending)
        for key, value in list(row.items()):
            if isinstance(value, Decimal):
                row[key] = str(_money(value))
        serialized_partners.append(row)

    summary = {
        'agreement_id': agreement.id,
        'status': agreement.status,
        'opened_at': agreement.opened_at,
        'closed_at': agreement.closed_at,
        'supplier_name': getattr(agreement.supplier, 'name', None),
        'planned_budget': agreement.planned_budget,
        'currency': agreement.currency,
        'balances': agreement.balances or {},
        'procurements_count': len(procurements),
        'quantity_sold': totals['quantity_sold'],
        'remaining_quantity': totals['remaining_quantity'],
        'revenue': _money(totals['revenue']),
        'cogs': _money(totals['cogs']),
        'gross_profit': _money(totals['gross_profit']),
        'investor_profit': _money(totals['investor_profit']),
        'business_profit': _money(totals['business_profit']),
        'received_landed_cost': _money(totals['cogs'] + totals['remaining_landed_cost']),
        'pending_prepaid_cost': _money(totals['pending_prepaid_cost']),
        'remaining_landed_cost': _money(totals['remaining_landed_cost']),
        'projected_revenue': _money(totals['projected_revenue']),
        'projected_gross_profit': _money(totals['projected_gross_profit']),
        'projected_investor_profit': _money(totals['projected_investor_profit']),
        'projected_business_profit': _money(totals['projected_business_profit']),
    }
    return {
        'agreement': summary,
        'partners': sorted(serialized_partners, key=lambda item: (item['role'], item['partner_id'])),
        'procurements': procurement_rows,
    }
