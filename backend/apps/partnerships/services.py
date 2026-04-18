"""
Partnerships services — ledger management, dividend payout, partner aggregates.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.core.services import publish_event
from apps.core.exceptions import ImmutableRecordError


def open_procurement(*args, **kwargs):
    raise NotImplementedError('open_procurement: implemented in PR-3')


def add_contribution(*args, **kwargs):
    raise NotImplementedError('add_contribution: implemented in PR-3')


def add_withdrawal(*args, **kwargs):
    raise NotImplementedError('add_withdrawal: implemented in PR-3')


def receive_procurement(*args, **kwargs):
    raise NotImplementedError('receive_procurement: implemented in PR-3')


# ─── Ledger ────────────────────────────────────────────────────────────────────

def get_or_create_ledger(
    *,
    procurement_id: int,
    partner_id: int,
    tenant_id: int,
):
    """Get (or lazily create) a ProcurementPartnerLedger."""
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
    source_ref: str = '',
    date=None,
):
    """
    Append an immutable entry to a ProcurementPartnerLedger.
    Always call inside a transaction.atomic().
    """
    from .models import PartnerLedgerEntry
    if date is None:
        date = timezone.now()
    return PartnerLedgerEntry.objects.create(
        tenant_id=ledger.tenant_id,
        ledger=ledger,
        date=date,
        amount=amount,
        currency=currency,
        entry_type=entry_type,
        source_ref=source_ref,
    )


def get_partner_aggregate(partner_id: int, tenant_id: int) -> dict:
    """
    Compute partner summary across all procurements — replaces InvestorSummary.
    Returns:
    {
        capital_in, capital_out, profit_accrued, profit_reversed,
        dividends_paid, losses_incurred, profit_pending_payout
    }
    all in UZS (multi-currency not yet normalised — PR-7 brings FX rates).
    """
    from .models import PartnerLedgerEntry, ProcurementPartnerLedger

    ledger_ids = ProcurementPartnerLedger.objects.filter(
        partner_id=partner_id,
        tenant_id=tenant_id,
    ).values_list('id', flat=True)

    agg = (
        PartnerLedgerEntry.objects
        .filter(ledger_id__in=ledger_ids)
        .values('entry_type')
        .annotate(total=models.Sum('amount'))
    )
    totals = {row['entry_type']: row['total'] or Decimal('0') for row in agg}

    capital_in = totals.get('CAPITAL_IN', Decimal('0'))
    capital_out = totals.get('CAPITAL_OUT', Decimal('0'))
    profit_accrued = totals.get('PROFIT_ACCRUED', Decimal('0'))
    profit_reversed = totals.get('PROFIT_REVERSED', Decimal('0'))
    dividends_paid = totals.get('DIVIDEND_PAID', Decimal('0'))
    losses = totals.get('LOSS_INCURRED', Decimal('0'))

    profit_net = profit_accrued - profit_reversed - losses
    profit_pending_payout = max(Decimal('0'), profit_net - dividends_paid)

    return {
        'capital_in': capital_in,
        'capital_out': capital_out,
        'capital_net': capital_in - capital_out,
        'profit_accrued': profit_accrued,
        'profit_reversed': profit_reversed,
        'losses_incurred': losses,
        'dividends_paid': dividends_paid,
        'profit_pending_payout': profit_pending_payout,
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
    Raises ValueError if invariant violated.
    """
    from .models import DividendPayment, ProcurementPartnerLedger, PartnerLedgerEntry

    if date is None:
        date = timezone.now()

    with transaction.atomic():
        ledger = get_or_create_ledger(
            procurement_id=procurement_id,
            partner_id=partner_id,
            tenant_id=tenant_id,
        )

        # Compute pending payout for this specific procurement
        agg = (
            PartnerLedgerEntry.objects
            .filter(ledger=ledger)
            .values('entry_type')
            .annotate(total=models.Sum('amount'))
        )
        totals = {row['entry_type']: row['total'] or Decimal('0') for row in agg}

        profit_net = (
            totals.get('PROFIT_ACCRUED', Decimal('0'))
            - totals.get('PROFIT_REVERSED', Decimal('0'))
            - totals.get('LOSS_INCURRED', Decimal('0'))
        )
        already_paid = totals.get('DIVIDEND_PAID', Decimal('0'))
        pending = max(Decimal('0'), profit_net - already_paid)

        if amount > pending:
            raise ValueError(
                f'Dividend amount {amount} exceeds pending payout {pending} '
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

        append_ledger_entry(
            ledger=ledger,
            entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID,
            amount=amount,
            currency=currency,
            source_ref=f'dividend_payment:{payment.pk}',
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
