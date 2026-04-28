"""Operational reconciliation summary for owner-facing audit UI."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.utils import timezone
from apps.sales.currency import functional_amount_uzs, payment_functional_amount_uzs


_ZERO = Decimal('0.00')


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _sample_refs(refs: list[str], *, limit: int = 5) -> list[str]:
    return refs[:limit]


def _build_check(
    *,
    code: str,
    title: str,
    summary: str,
    actual_label: str,
    expected_label: str,
    actual_amount: Decimal,
    expected_amount: Decimal,
    mismatch_count: int,
    sample_refs: list[str] | None = None,
    level: str = 'mismatch',
    actual_by_currency: dict[str, Decimal] | None = None,
    expected_by_currency: dict[str, Decimal] | None = None,
) -> dict:
    actual = _money(actual_amount)
    expected = _money(expected_amount)
    delta = _money(actual - expected)

    if mismatch_count == 0 and delta == _ZERO:
        status = 'ok'
    elif level == 'warning':
        status = 'warning'
    else:
        status = 'mismatch'

    payload = {
        'code': code,
        'title': title,
        'summary': summary,
        'status': status,
        'actual_label': actual_label,
        'expected_label': expected_label,
        'actual_amount': str(actual),
        'expected_amount': str(expected),
        'delta_amount': str(delta),
        'mismatch_count': mismatch_count,
        'sample_refs': _sample_refs(sample_refs or []),
    }
    if actual_by_currency is not None:
        payload['actual_by_currency'] = {
            currency: str(_money(amount))
            for currency, amount in sorted(actual_by_currency.items())
        }
    if expected_by_currency is not None:
        payload['expected_by_currency'] = {
            currency: str(_money(amount))
            for currency, amount in sorted(expected_by_currency.items())
        }
    return payload


def build_operational_reconciliation_summary(*, tenant_id: int) -> dict:
    from apps.customers.models import Receivable, ReceivableEntry
    from apps.finance.models import CashAccount, CashEntry, JournalEntry
    from apps.sales.models import PosSession, Sale, SalePayment
    from apps.suppliers.models import Supplier

    sales = list(
        Sale.objects
        .filter(tenant_id=tenant_id, status=Sale.SaleStatus.COMPLETED)
        .prefetch_related('payments')
        .order_by('id')
    )
    receivables = list(
        Receivable.objects
        .filter(tenant_id=tenant_id)
        .prefetch_related('entries')
        .select_related('customer')
        .order_by('id')
    )
    cash_accounts = list(
        CashAccount.objects
        .filter(tenant_id=tenant_id)
        .order_by('id')
    )
    cash_entries = list(
        CashEntry.objects
        .filter(tenant_id=tenant_id)
        .select_related('account')
        .order_by('id')
    )
    closed_sessions = list(
        PosSession.objects
        .filter(tenant_id=tenant_id, status=PosSession.SessionStatus.CLOSED)
        .order_by('id')
    )
    open_sessions_count = PosSession.objects.filter(
        tenant_id=tenant_id,
        status=PosSession.SessionStatus.OPEN,
    ).count()
    journal_entries = list(
        JournalEntry.objects
        .filter(tenant_id=tenant_id)
        .prefetch_related('lines__account')
        .order_by('id')
    )
    supplier_payables_total = _money(
        sum(
            (Decimal(str(supplier.outstanding_balance)) for supplier in Supplier.objects.filter(tenant_id=tenant_id)),
            _ZERO,
        )
    )

    sale_receivable_entries = (
        ReceivableEntry.objects
        .filter(tenant_id=tenant_id, source_ref__startswith='sale:')
        .order_by('id')
    )
    receivable_from_sale: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    for entry in sale_receivable_entries:
        try:
            sale_id = int(str(entry.source_ref).split(':', 1)[1])
        except (IndexError, TypeError, ValueError):
            continue
        receivable_from_sale[sale_id] += functional_amount_uzs(
            amount=entry.amount,
            currency=entry.currency,
            fx_rate=entry.fx_rate,
        )

    cash_incoming_by_session: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: _ZERO))
    for payment in (
        SalePayment.objects
        .filter(
            sale__tenant_id=tenant_id,
            sale__status=Sale.SaleStatus.COMPLETED,
            role=SalePayment.Role.INCOMING,
            method=SalePayment.Method.CASH,
        )
        .select_related('sale')
        .order_by('id')
    ):
        currency = str(payment.currency or 'UZS').upper()
        cash_incoming_by_session[payment.sale.pos_session_id][currency] += Decimal(str(payment.amount))

    revenue_by_sale: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    cogs_by_sale: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    journal_balance_mismatches: list[str] = []
    for journal in journal_entries:
        total_debit = _ZERO
        total_credit = _ZERO
        for line in journal.lines.all():
            debit = Decimal(str(line.debit))
            credit = Decimal(str(line.credit))
            total_debit += debit
            total_credit += credit

            if journal.operation_type == JournalEntry.OperationType.SALE:
                if line.account.code == '4000':
                    revenue_by_sale[journal.operation_id] += credit - debit
                elif line.account.code == '5000':
                    cogs_by_sale[journal.operation_id] += debit - credit

        if _money(total_debit) != _money(total_credit):
            journal_balance_mismatches.append(f'journal:{journal.id}')

    sales_total = _money(sum((Decimal(str(sale.total_amount)) for sale in sales), _ZERO))
    sales_settlement_total = _ZERO
    sales_settlement_mismatches: list[str] = []
    sales_revenue_journal_total = _ZERO
    sales_revenue_mismatches: list[str] = []
    sales_cogs_total = _money(sum((Decimal(str(sale.total_cogs)) for sale in sales), _ZERO))
    sales_cogs_journal_total = _ZERO
    sales_cogs_mismatches: list[str] = []

    for sale in sales:
        non_credit_incoming = sum(
            (
                payment_functional_amount_uzs(payment)
                for payment in sale.payments.all()
                if payment.role == SalePayment.Role.INCOMING
                and payment.method != SalePayment.Method.CREDIT
            ),
            _ZERO,
        )
        sale_settlement = _money(non_credit_incoming + receivable_from_sale.get(sale.id, _ZERO))
        sales_settlement_total += sale_settlement
        sale_total_amount = _money(sale.total_amount)
        if sale_settlement != sale_total_amount:
            sales_settlement_mismatches.append(f'sale:{sale.id}')

        sale_revenue_journal = _money(revenue_by_sale.get(sale.id, _ZERO))
        sales_revenue_journal_total += sale_revenue_journal
        if sale_revenue_journal != sale_total_amount:
            sales_revenue_mismatches.append(f'sale:{sale.id}')

        sale_cogs_journal = _money(cogs_by_sale.get(sale.id, _ZERO))
        sales_cogs_journal_total += sale_cogs_journal
        sale_total_cogs = _money(sale.total_cogs)
        if sale_cogs_journal != sale_total_cogs:
            sales_cogs_mismatches.append(f'sale:{sale.id}')

    receivable_snapshot_total = _ZERO
    receivable_ledger_total = _ZERO
    receivable_mismatches: list[str] = []
    for receivable in receivables:
        snapshot_amount = _money(
            sum((Decimal(str(value)) for value in (receivable.balances or {}).values()), _ZERO)
        )
        ledger_amount = _money(
            sum((Decimal(str(entry.amount)) for entry in receivable.entries.all()), _ZERO)
        )
        receivable_snapshot_total += snapshot_amount
        receivable_ledger_total += ledger_amount
        if snapshot_amount != ledger_amount:
            receivable_mismatches.append(f'customer:{receivable.customer_id}')

    cash_account_total = _ZERO
    cash_account_totals_by_currency: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    cash_entry_totals_by_account: dict[int, Decimal] = defaultdict(lambda: _ZERO)
    cash_entry_totals_by_currency: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for entry in cash_entries:
        signed_amount = Decimal(str(entry.amount))
        if entry.direction == CashEntry.Direction.OUT:
            signed_amount *= Decimal('-1')
        cash_entry_totals_by_account[entry.account_id] += signed_amount
        cash_entry_totals_by_currency[str(entry.account.currency or 'UZS').upper()] += signed_amount
    cash_entry_total = _money(sum(cash_entry_totals_by_account.values(), _ZERO))

    cash_account_mismatches: list[str] = []
    for account in cash_accounts:
        balance = _money(account.balance)
        cash_account_total += balance
        cash_account_totals_by_currency[str(account.currency or 'UZS').upper()] += balance
        ledger_total = _money(cash_entry_totals_by_account.get(account.id, _ZERO))
        if balance != ledger_total:
            cash_account_mismatches.append(f'cash_account:{account.id}')

    stored_expected_total = _ZERO
    formula_expected_total = _ZERO
    session_expected_mismatches: list[str] = []
    stored_difference_total = _ZERO
    formula_difference_total = _ZERO
    session_difference_mismatches: list[str] = []
    session_nonzero_differences: list[str] = []
    nonzero_cash_difference_total = _ZERO

    for session in closed_sessions:
        opening_by_currency = {
            str(currency).upper(): Decimal(str(amount))
            for currency, amount in (session.opening_cash_by_currency or {'UZS': session.opening_cash}).items()
        }
        expected_by_currency = dict(opening_by_currency)
        for currency, amount in cash_incoming_by_session.get(session.id, {}).items():
            expected_by_currency[currency] = expected_by_currency.get(currency, _ZERO) + amount

        stored_expected_by_currency = {
            str(currency).upper(): Decimal(str(amount))
            for currency, amount in (session.expected_cash_by_currency or {'UZS': session.expected_cash or _ZERO}).items()
        }
        actual_by_currency = {
            str(currency).upper(): Decimal(str(amount))
            for currency, amount in (session.actual_cash_by_currency or {'UZS': session.actual_cash or _ZERO}).items()
        }
        stored_difference_by_currency = {
            str(currency).upper(): Decimal(str(amount))
            for currency, amount in (session.cash_difference_by_currency or {'UZS': session.cash_difference or _ZERO}).items()
        }
        formula_difference_by_currency = {
            currency: actual_by_currency.get(currency, _ZERO) - stored_expected_by_currency.get(currency, _ZERO)
            for currency in set(actual_by_currency) | set(stored_expected_by_currency)
        }

        formula_expected = _money(
            expected_by_currency.get('UZS', _ZERO)
        )
        stored_expected = _money(stored_expected_by_currency.get('UZS', _ZERO))
        stored_expected_total += stored_expected
        formula_expected_total += formula_expected
        if {
            key: _money(value)
            for key, value in stored_expected_by_currency.items()
        } != {
            key: _money(value)
            for key, value in expected_by_currency.items()
        }:
            session_expected_mismatches.append(f'session:{session.id}')

        stored_difference = _money(stored_difference_by_currency.get('UZS', _ZERO))
        formula_difference = _money(formula_difference_by_currency.get('UZS', _ZERO))
        stored_difference_total += stored_difference
        formula_difference_total += formula_difference
        if {
            key: _money(value)
            for key, value in stored_difference_by_currency.items()
        } != {
            key: _money(value)
            for key, value in formula_difference_by_currency.items()
        }:
            session_difference_mismatches.append(f'session:{session.id}')
        session_abs_difference = sum(
            abs(_money(value))
            for value in stored_difference_by_currency.values()
        )
        if session_abs_difference != _ZERO:
            session_nonzero_differences.append(f'session:{session.id}')
            nonzero_cash_difference_total += session_abs_difference

    checks = [
        _build_check(
            code='sales_settlement',
            title='Продажи сходятся с оплатой и дебиторкой',
            summary='Для каждой продажи: сумма non-credit оплат плюс начисленная дебиторка должна покрывать total_amount.',
            actual_label='Сумма продаж',
            expected_label='Оплаты + дебиторка',
            actual_amount=sales_total,
            expected_amount=sales_settlement_total,
            mismatch_count=len(sales_settlement_mismatches),
            sample_refs=sales_settlement_mismatches,
        ),
        _build_check(
            code='receivable_ledger',
            title='Дебиторка сходится с receivable ledger',
            summary='Snapshot в Receivable.balances должен совпадать с суммой append-only ReceivableEntry.',
            actual_label='Snapshot дебиторки',
            expected_label='Ledger дебиторки',
            actual_amount=receivable_snapshot_total,
            expected_amount=receivable_ledger_total,
            mismatch_count=len(receivable_mismatches),
            sample_refs=receivable_mismatches,
        ),
        _build_check(
            code='cash_accounts_vs_entries',
            title='Остатки cash accounts сходятся с cash entries',
            summary='Баланс каждого cash account должен равняться чистой сумме его cash entries.',
            actual_label='Баланс cash accounts',
            expected_label='Net cash entries',
            actual_amount=cash_account_total,
            expected_amount=cash_entry_total,
            mismatch_count=len(cash_account_mismatches),
            sample_refs=cash_account_mismatches,
            actual_by_currency=cash_account_totals_by_currency,
            expected_by_currency=cash_entry_totals_by_currency,
        ),
        _build_check(
            code='closed_sessions_expected_cash',
            title='Закрытые смены сходятся по expected cash',
            summary='Stored expected_cash должен совпадать с opening_cash + cash sale payments по смене.',
            actual_label='Stored expected cash',
            expected_label='Расчетный expected cash',
            actual_amount=stored_expected_total,
            expected_amount=formula_expected_total,
            mismatch_count=len(session_expected_mismatches),
            sample_refs=session_expected_mismatches,
        ),
        _build_check(
            code='closed_sessions_cash_difference',
            title='Закрытые смены консистентны по cash_difference',
            summary='Stored cash_difference должен равняться actual_cash - expected_cash.',
            actual_label='Stored cash difference',
            expected_label='Расчетный cash difference',
            actual_amount=stored_difference_total,
            expected_amount=formula_difference_total,
            mismatch_count=len(session_difference_mismatches),
            sample_refs=session_difference_mismatches,
        ),
        _build_check(
            code='closed_sessions_nonzero_difference',
            title='Смены без недостачи или излишка',
            summary='Это не системная ошибка, а operational warning: ideal target — zero cash difference на закрытых сменах.',
            actual_label='Абсолютный cash difference',
            expected_label='Цель',
            actual_amount=nonzero_cash_difference_total,
            expected_amount=_ZERO,
            mismatch_count=len(session_nonzero_differences),
            sample_refs=session_nonzero_differences,
            level='warning',
        ),
        _build_check(
            code='journal_balance',
            title='Проводки сбалансированы',
            summary='У каждой проводки сумма дебета должна равняться сумме кредита.',
            actual_label='Несбалансированные проводки',
            expected_label='Цель',
            actual_amount=Decimal(len(journal_balance_mismatches)),
            expected_amount=_ZERO,
            mismatch_count=len(journal_balance_mismatches),
            sample_refs=journal_balance_mismatches,
        ),
        _build_check(
            code='sales_journal_revenue',
            title='Выручка продаж покрыта журналом',
            summary='Кредит по счёту 4000 в sale journals должен покрывать полный revenue completed sales.',
            actual_label='Выручка продаж',
            expected_label='Выручка в журнале',
            actual_amount=sales_total,
            expected_amount=sales_revenue_journal_total,
            mismatch_count=len(sales_revenue_mismatches),
            sample_refs=sales_revenue_mismatches,
        ),
        _build_check(
            code='sales_journal_cogs',
            title='COGS продаж покрыт журналом',
            summary='Дебет по счёту 5000 в sale journals должен покрывать полный total_cogs completed sales.',
            actual_label='COGS продаж',
            expected_label='COGS в журнале',
            actual_amount=sales_cogs_total,
            expected_amount=sales_cogs_journal_total,
            mismatch_count=len(sales_cogs_mismatches),
            sample_refs=sales_cogs_mismatches,
        ),
    ]

    mismatch_checks = sum(1 for check in checks if check['status'] == 'mismatch')
    warning_checks = sum(1 for check in checks if check['status'] == 'warning')
    ok_checks = sum(1 for check in checks if check['status'] == 'ok')
    if mismatch_checks:
        overall_status = 'mismatch'
    elif warning_checks:
        overall_status = 'warning'
    else:
        overall_status = 'ok'

    affected_records = sum(int(check['mismatch_count']) for check in checks)

    highlights = [
        {'key': 'sales_total', 'label': 'Продажи', 'value': str(sales_total)},
        {'key': 'receivable_total', 'label': 'Дебиторка', 'value': str(_money(receivable_snapshot_total))},
        *[
            {
                'key': f'cash_total_{currency}',
                'label': f'Касса {currency}',
                'value': str(_money(amount)),
                'currency': currency,
            }
            for currency, amount in sorted(cash_account_totals_by_currency.items())
        ],
        {'key': 'payables_total', 'label': 'Кредиторка', 'value': str(supplier_payables_total)},
        {'key': 'journal_entries', 'label': 'Проводки', 'value': str(len(journal_entries))},
        {'key': 'sessions', 'label': 'Смены', 'value': f"{len(closed_sessions)} закрыто / {open_sessions_count} открыто"},
    ]

    return {
        'generated_at': timezone.now(),
        'overall_status': overall_status,
        'totals': {
            'total_checks': len(checks),
            'ok_checks': ok_checks,
            'warning_checks': warning_checks,
            'mismatch_checks': mismatch_checks,
            'affected_records': affected_records,
        },
        'highlights': highlights,
        'checks': checks,
    }
