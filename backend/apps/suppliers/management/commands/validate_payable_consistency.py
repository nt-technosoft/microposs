"""
E08 T-2.4 — payable / terms status consistency check.

After Phase 2 (paid_amount / remaining_amount / outstanding_balance become
derived from finance.Payment), the only stored bit is `status`. This command
walks every payable and every procurement-terms row and flags any case where
the stored `status` does not match what the derived amounts say it should be.

Useful as a CI smoke check, and as a post-incident sanity tool when a write
site forgets to maintain status alongside Payment creation.

Logs only — does not mutate anything.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.partnerships.models import ProcurementTerms
from apps.suppliers.models import SupplierPayable

_ZERO = Decimal('0.01')


def _expected_payable_status(payable: SupplierPayable) -> str:
    remaining = payable.remaining_amount
    paid = payable.paid_amount
    if payable.status == SupplierPayable.Status.CANCELLED:
        return SupplierPayable.Status.CANCELLED
    if remaining <= _ZERO:
        return SupplierPayable.Status.FULLY_PAID
    if paid > _ZERO:
        return SupplierPayable.Status.PARTIALLY_PAID
    return SupplierPayable.Status.OPEN


def _expected_terms_status(terms: ProcurementTerms) -> str:
    if terms.status == ProcurementTerms.Status.CANCELLED:
        return ProcurementTerms.Status.CANCELLED
    paid = terms.paid_amount
    total = Decimal(str(terms.total_amount_due or 0))
    if total > 0 and paid >= total:
        return ProcurementTerms.Status.FULLY_PAID
    if paid > 0:
        return ProcurementTerms.Status.PARTIALLY_PAID
    return ProcurementTerms.Status.OPEN


class Command(BaseCommand):
    help = (
        'Walk SupplierPayable and ProcurementTerms; report any row whose '
        'stored status does not match its derived paid/remaining amounts.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            type=int,
            default=None,
            help='Restrict check to a single tenant_id.',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant')
        drift_count = 0

        payables = SupplierPayable.objects.all()
        if tenant_id is not None:
            payables = payables.filter(tenant_id=tenant_id)
        for payable in payables:
            expected = _expected_payable_status(payable)
            if expected != payable.status:
                drift_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'SupplierPayable#{payable.pk} tenant={payable.tenant_id}: '
                        f'stored status={payable.status} expected={expected} '
                        f'(paid={payable.paid_amount} remaining={payable.remaining_amount} '
                        f'original={payable.original_amount} {payable.currency_of_obligation})'
                    )
                )

        terms_qs = ProcurementTerms.objects.all()
        if tenant_id is not None:
            terms_qs = terms_qs.filter(tenant_id=tenant_id)
        for terms in terms_qs:
            expected = _expected_terms_status(terms)
            if expected != terms.status:
                drift_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'ProcurementTerms#{terms.pk} tenant={terms.tenant_id}: '
                        f'stored status={terms.status} expected={expected} '
                        f'(paid={terms.paid_amount} remaining={terms.remaining_amount} '
                        f'total_due={terms.total_amount_due} {terms.currency_of_obligation})'
                    )
                )

        if drift_count == 0:
            self.stdout.write(self.style.SUCCESS('OK — all payable/terms statuses consistent with derived amounts.'))
        else:
            self.stdout.write(self.style.ERROR(f'{drift_count} drift(s) detected.'))
