from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sales.currency import money
from apps.sales.models import PosSession, Sale, SalePayment


ZERO = Decimal('0.00')


def _currency_map(value: dict | None, *, fallback_uzs: Decimal | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    if value:
        for currency, amount in value.items():
            normalized = str(currency or '').upper()
            if normalized:
                result[normalized] = str(money(amount or ZERO))
    if fallback_uzs is not None and 'UZS' not in result:
        result['UZS'] = str(money(fallback_uzs))
    return result


def _sum_maps(base: dict[str, str], incoming: dict[str, Decimal]) -> dict[str, str]:
    totals = {
        str(currency).upper(): Decimal(str(amount or ZERO))
        for currency, amount in base.items()
    }
    for currency, amount in incoming.items():
        normalized = str(currency or '').upper()
        if normalized:
            totals[normalized] = totals.get(normalized, ZERO) + Decimal(str(amount or ZERO))
    return {currency: str(money(amount)) for currency, amount in sorted(totals.items())}


def _diff_maps(actual: dict[str, str], expected: dict[str, str]) -> dict[str, str]:
    currencies = set(actual) | set(expected)
    return {
        currency: str(money(Decimal(str(actual.get(currency, ZERO))) - Decimal(str(expected.get(currency, ZERO)))))
        for currency in sorted(currencies)
    }


class Command(BaseCommand):
    help = 'Backfill native-currency POS session cash fields from sale payments.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-id', type=int, required=True)
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        apply_changes = options['apply']

        incoming_by_session: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
        for payment in (
            SalePayment.objects
            .filter(
                sale__tenant_id=tenant_id,
                sale__status=Sale.SaleStatus.COMPLETED,
                role=SalePayment.Role.INCOMING,
                method=SalePayment.Method.CASH,
            )
            .select_related('sale')
        ):
            currency = str(payment.currency or 'UZS').upper()
            incoming_by_session[payment.sale.pos_session_id][currency] += Decimal(str(payment.amount))

        sessions = (
            PosSession.objects
            .filter(tenant_id=tenant_id, status=PosSession.SessionStatus.CLOSED)
            .order_by('id')
        )

        repairs = []
        for session in sessions:
            opening = _currency_map(
                session.opening_cash_by_currency,
                fallback_uzs=Decimal(str(session.opening_cash or ZERO)),
            )
            expected = _sum_maps(opening, incoming_by_session.get(session.id, {}))

            if session.actual_cash_by_currency:
                actual = _currency_map(session.actual_cash_by_currency)
            elif money(session.cash_difference or ZERO) == ZERO:
                actual = dict(expected)
            else:
                actual = _currency_map(
                    None,
                    fallback_uzs=Decimal(str(session.actual_cash or ZERO)),
                )

            difference = _diff_maps(actual, expected)
            expected_uzs = Decimal(str(expected.get('UZS', ZERO)))
            actual_uzs = Decimal(str(actual.get('UZS', ZERO)))
            difference_uzs = Decimal(str(difference.get('UZS', ZERO)))

            desired = {
                'opening_cash_by_currency': opening,
                'expected_cash_by_currency': expected,
                'actual_cash_by_currency': actual,
                'cash_difference_by_currency': difference,
                'expected_cash': money(expected_uzs),
                'actual_cash': money(actual_uzs),
                'cash_difference': money(difference_uzs),
            }
            current = {
                'opening_cash_by_currency': _currency_map(session.opening_cash_by_currency),
                'expected_cash_by_currency': _currency_map(session.expected_cash_by_currency),
                'actual_cash_by_currency': _currency_map(session.actual_cash_by_currency),
                'cash_difference_by_currency': _currency_map(session.cash_difference_by_currency),
                'expected_cash': money(session.expected_cash or ZERO),
                'actual_cash': money(session.actual_cash or ZERO),
                'cash_difference': money(session.cash_difference or ZERO),
            }

            if current != desired:
                repairs.append((session, desired))

        for session, desired in repairs:
            self.stdout.write(
                f'session:{session.id} expected={desired["expected_cash_by_currency"]} '
                f'actual={desired["actual_cash_by_currency"]} '
                f'difference={desired["cash_difference_by_currency"]}'
            )
            if apply_changes:
                with transaction.atomic():
                    PosSession.objects.filter(pk=session.pk, tenant_id=tenant_id).update(
                        opening_cash_by_currency=desired['opening_cash_by_currency'],
                        expected_cash_by_currency=desired['expected_cash_by_currency'],
                        actual_cash_by_currency=desired['actual_cash_by_currency'],
                        cash_difference_by_currency=desired['cash_difference_by_currency'],
                        expected_cash=desired['expected_cash'],
                        actual_cash=desired['actual_cash'],
                        cash_difference=desired['cash_difference'],
                    )

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f'Repaired {len(repairs)} sessions.'))
        else:
            self.stdout.write(self.style.WARNING(f'Dry-run: {len(repairs)} sessions need repair.'))
