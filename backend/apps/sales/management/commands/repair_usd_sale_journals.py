from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.finance.models import CashAccount
from apps.finance.models import JournalEntry
from apps.finance.services import create_reversal_entry, record_sale_settlement_journal
from apps.sales.currency import payment_functional_amount_uzs
from apps.sales.models import Sale, SalePayment


ZERO = Decimal('0.00')


class Command(BaseCommand):
    help = 'Repair sale settlement journals that stored native USD amounts instead of UZS equivalents.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        apply_changes = options['apply']
        repairs = []

        sales = (
            Sale.objects
            .filter(tenant_id=tenant_id, status=Sale.SaleStatus.COMPLETED)
            .prefetch_related('payments')
            .order_by('id')
        )

        for sale in sales:
            payments = [
                payment for payment in sale.payments.all()
                if payment.role == SalePayment.Role.INCOMING
                and payment.method != SalePayment.Method.CREDIT
            ]
            if not any(str(payment.currency or 'UZS').upper() != 'UZS' for payment in payments):
                continue

            functional_total = sum(
                (payment_functional_amount_uzs(payment) for payment in payments),
                ZERO,
            ).quantize(Decimal('0.01'))

            settlement_journals = list(
                JournalEntry.objects
                .filter(
                    tenant_id=tenant_id,
                    operation_type=JournalEntry.OperationType.SALE,
                    operation_id=sale.id,
                    is_reversal=False,
                    reversed_entry__isnull=True,
                    lines__account__code='4000',
                )
                .exclude(lines__account__code='5000')
                .distinct()
                .prefetch_related('lines__account', 'reversals')
                .order_by('id')
            )
            if not settlement_journals:
                continue

            already_reversed = any(journal.reversals.exists() for journal in settlement_journals)
            current_revenue = sum(
                (
                    line.credit - line.debit
                    for journal in settlement_journals
                    for line in journal.lines.all()
                    if line.account.code == '4000'
                ),
                ZERO,
            ).quantize(Decimal('0.01'))

            if current_revenue == functional_total or already_reversed:
                continue

            repairs.append((sale, payments, settlement_journals, current_revenue, functional_total))

        for sale, payments, settlement_journals, current_revenue, functional_total in repairs:
            self.stdout.write(
                f'sale:{sale.id} journal={current_revenue} expected={functional_total} '
                f'delta={(functional_total - current_revenue).quantize(Decimal("0.01"))}'
            )

            if apply_changes:
                with transaction.atomic():
                    for journal in settlement_journals:
                        create_reversal_entry(
                            tenant_id=tenant_id,
                            original_entry=journal,
                            description=f'Reversal of native-currency sale settlement JE #{journal.pk}',
                        )
                    for payment in payments:
                        debit_account_code = None
                        if payment.account_id:
                            account = (
                                CashAccount.objects
                                .select_related('linked_account')
                                .filter(pk=payment.account_id, tenant_id=tenant_id)
                                .first()
                            )
                            if account and account.linked_account_id:
                                debit_account_code = account.linked_account.code
                        record_sale_settlement_journal(
                            tenant_id=tenant_id,
                            sale_id=sale.id,
                            amount=payment_functional_amount_uzs(payment),
                            payment_method=payment.method,
                            debit_account_code=debit_account_code,
                            description=f'Corrected sale payment #{payment.pk}',
                            date=payment.date,
                        )

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f'Repaired {len(repairs)} sales.'))
        else:
            self.stdout.write(self.style.WARNING(f'Dry-run: {len(repairs)} sales need repair.'))
