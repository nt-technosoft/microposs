"""
Finance business logic — journal entries, daily summaries.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.core.services import publish_event

from .models import Account, JournalEntry, JournalLine


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
