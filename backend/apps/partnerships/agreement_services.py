"""
Partnership agreement services — ledger management, dividend payout, partner aggregates.

Extracted from the legacy services.py (E08 T-1.2). Only live functions kept.
"""

from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone

from apps.finance.models import CashAccount, CashEntry
from apps.finance.fx_rates import resolve_fx_rate_snapshot_details
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


def _venture_partner_profit(*, tenant_id: int, partner_id: int, procurement_ids: list[int]):
    """Partner's venture profit/loss across the given procurements (functional
    UZS): (net provisional profit entitlement, loss, profit available to pay).
    Available profit is 0 until a venture settlement exists — the venture model
    forbids profit withdrawal before capital preservation is fixed."""
    from .models import Procurement
    from .venture import procurement_venture_positions

    profit = _ZERO
    loss = _ZERO
    available = _ZERO
    if not procurement_ids:
        return profit, loss, available
    procurements = Procurement.objects.filter(
        tenant_id=tenant_id, id__in=set(procurement_ids),
    )
    for procurement in procurements:
        row = procurement_venture_positions(procurement=procurement).get(partner_id)
        if not row:
            continue
        profit += Decimal(str(row.get('provisional_profit_uzs', '0')))
        loss += Decimal(str(row.get('loss_uzs', '0')))
        available += Decimal(str(row.get('provisional_profit_available_uzs', '0')))
    return _q(profit), _q(loss), _q(available)


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

    E17 T-1.6: PartnerLedgerEntry now records only physical/audit money events
    (CAPITAL_IN/OUT, DIVIDEND_PAID). The profit triad (profit_accrued/
    profit_reversed/losses_incurred) is no longer written, so those fields are
    always 0 here. Partner profit/loss truth lives in the venture model
    (procurement_venture_positions); do not derive distributable profit from
    this aggregate.
    """
    from .models import PartnerLedgerEntry, ProcurementPartnerLedger

    ledger_qs = ProcurementPartnerLedger.objects.filter(
        partner_id=partner_id,
        tenant_id=tenant_id,
    )
    if procurement_id is not None:
        ledger_qs = ledger_qs.filter(procurement_id=procurement_id)
    ledger_ids = list(ledger_qs.values_list('id', flat=True))
    procurement_ids = list(ledger_qs.values_list('procurement_id', flat=True))

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

    # E17 T-1.2/T-1.6: capital_in/out and dividends_paid stay physical (ledger),
    # but partner profit/loss truth is the venture model. Override the profit
    # fields from venture positions across the partner's procurements; profit is
    # only payable (pending) after a constructive/final venture settlement.
    venture_profit, venture_loss, venture_available = _venture_partner_profit(
        tenant_id=tenant_id, partner_id=partner_id, procurement_ids=procurement_ids,
    )
    functional_uzs['profit_accrued'] = venture_profit
    functional_uzs['profit_reversed'] = _ZERO
    functional_uzs['losses_incurred'] = venture_loss
    functional_uzs['profit_pending_payout'] = venture_available

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
    fx_rate: Decimal | None = None,
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
    currency = str(currency or 'UZS').upper()
    # E15: a dividend is a real payout — it must move cash from a concrete
    # account (sales proceeds live in operating cash). No ledger-only dividends.
    if from_account_id is None:
        raise ValueError('Dividend payout requires a source cash account (from_account_id).')
    fx_snapshot = resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id,
        operation_currency=currency,
        operation_at=date,
        fx_rate_snapshot=fx_rate,
    )

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

        payment_functional_uzs = _functional_uzs(amount, currency, fx_snapshot.rate)
        from .models import Procurement
        from .venture import assert_procurement_open
        procurement = Procurement.objects.get(pk=procurement_id, tenant_id=tenant_id)
        assert_procurement_open(procurement)
        if procurement.funding_source == Procurement.FundingSource.PARTNERSHIP:
            from .venture import procurement_venture_positions
            venture_row = procurement_venture_positions(procurement=procurement).get(partner_id, {})
            has_venture_facts = any(
                Decimal(str(venture_row.get(key, _ZERO))) != 0
                for key in ('capital_recovered_uzs', 'provisional_profit_uzs', 'loss_uzs')
            )
            pending = (
                Decimal(str(venture_row.get('provisional_profit_available_uzs', _ZERO)))
                if has_venture_facts
                else None
            )
        else:
            pending = None
        if pending is None:
            profit_net = (
                totals.get('PROFIT_ACCRUED', _ZERO)
                - totals.get('PROFIT_REVERSED', _ZERO)
                - totals.get('LOSS_INCURRED', _ZERO)
            )
            already_paid = totals.get('DIVIDEND_PAID', _ZERO)
            pending = max(_ZERO, profit_net - already_paid)

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
            fx_rate=fx_snapshot.rate,
            fx_rate_source=fx_snapshot.source,
            fx_rate_date=fx_snapshot.rate_date,
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
            fx_rate=fx_snapshot.rate,
            source_ref=f'dividend_payment:{payment.pk}',
            date=date,
        )

        if cash_entry is not None and cash_entry.account.linked_account_id:
            # E15: profit distribution reduces retained earnings (3200), not the
            # investor-payable liability (2100, the old placeholder). DR 3200 / CR cash.
            record_journal_from_cash_entry(
                tenant_id=tenant_id,
                cash_entry=cash_entry,
                operation_type='profit_distrib',
                operation_id=payment.pk,
                counterpart_account_code='3200',
                description=f'Profit distribution #{payment.pk}',
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
                'date': date.isoformat(),
            },
            tenant_id=tenant_id,
        )

    return payment


# ---------------------------------------------------------------------------
# E17 Phase 3 — investment agreement close lifecycle & read-only lock
# ---------------------------------------------------------------------------

_EPS = Decimal('0.01')


def agreement_pool_reconciliation_residual(agreement) -> Decimal:
    """Pool reconciliation (agreement currency): pool.balance must equal
    Σ contributions − Σ pool-funded receives − Σ pool capital returns.
    Returns balance − expected (0 = reconciled). Recovered-capital returns leave
    the operating cash, not the pool, so they are excluded (matching the net fix)."""
    from apps.finance.models import CashEntry, Payment
    from .models import AgreementWithdrawal

    pool = agreement.capital_account
    if pool is None:
        return _ZERO
    tenant_id = agreement.tenant_id
    ccy = str(agreement.currency or 'UZS').upper()

    contrib = sum(
        (Decimal(str(c.amount)) for c in agreement.contributions.filter(currency=ccy)),
        _ZERO,
    )
    deployed = sum(
        (Decimal(str(p.amount)) for p in Payment.objects.filter(
            tenant_id=tenant_id,
            source_type=Payment.SourceType.CAPITAL_POOL,
            source_id=pool.pk,
            currency=ccy,
            status=Payment.Status.POSTED,
            reversed_payment__isnull=True,
        )),
        _ZERO,
    )
    withdrawals = list(agreement.withdrawals.filter(currency=ccy))
    pool_return_ids = set(
        CashEntry.objects.filter(
            tenant_id=tenant_id,
            source_ref_type='agreement_withdrawal',
            source_ref_id__in=[w.id for w in withdrawals],
            account_id=pool.pk,
            direction=CashEntry.Direction.OUT,
        ).values_list('source_ref_id', flat=True)
    ) if withdrawals else set()
    pool_returns = sum(
        (Decimal(str(w.amount)) for w in withdrawals if w.id in pool_return_ids),
        _ZERO,
    )
    expected = _q(contrib - deployed - pool_returns)
    return _q(Decimal(str(pool.balance)) - expected)


def agreement_close_blocking_reasons(*, agreement) -> list[str]:
    """Reasons an investment agreement cannot be closed yet (empty = closeable).

    Gates: every partnership procurement CLOSED; all partner net positions = 0
    (settled vs the pool); the pool reconciles to its domain records; no hanging
    claims; and the conservation invariant nets to zero across all ventures."""
    from .advances import partner_capital_positions
    from .models import Procurement
    from .venture import ConservationReport, venture_conservation

    reasons: list[str] = []

    procurements = list(Procurement.objects.filter(
        tenant_id=agreement.tenant_id, agreement=agreement,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
    ))
    open_procs = [
        p for p in procurements
        if p.status not in (Procurement.Status.CLOSED, Procurement.Status.CANCELLED)
    ]
    if open_procs:
        reasons.append(
            'Не все приходы договора закрыты: '
            + ', '.join(f'#{p.id} ({p.status})' for p in open_procs) + '.'
        )

    positions = partner_capital_positions(agreement)
    for partner_id, pos in positions.items():
        net = _q(Decimal(str(pos.get('net', _ZERO))))
        if abs(net) > _EPS:
            reasons.append(
                f'Нетто-позиция партнёра {partner_id} не сведена (net={net} '
                f'{agreement.currency}); сначала сведите взаиморасчёты.'
            )

    residual = agreement_pool_reconciliation_residual(agreement)
    if abs(residual) > _EPS:
        reasons.append(
            f'Капитал-пул договора не сведён (residual={residual} {agreement.currency}).'
        )

    merged = ConservationReport()
    for procurement in procurements:
        merged.merge(venture_conservation(procurement=procurement))
    if not merged.is_balanced():
        reasons.append(
            f'Нарушен инвариант сохранения денег по венчурам: {merged.breakdown()}.'
        )

    return reasons


def close_investment_agreement(*, tenant_id: int, agreement_id: int, client_request_id=None):
    """Close an investment agreement once every gate passes. Idempotent: an
    already-closed agreement is returned unchanged. After CLOSED the agreement is
    read-only."""
    from django.utils import timezone
    from .models import InvestmentAgreement

    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(pk=agreement_id, tenant_id=tenant_id)
        if agreement.status == InvestmentAgreement.Status.CLOSED:
            return agreement

        reasons = agreement_close_blocking_reasons(agreement=agreement)
        if reasons:
            raise ValueError('Нельзя закрыть договор: ' + ' '.join(reasons))

        InvestmentAgreement.objects.filter(pk=agreement_id, tenant_id=tenant_id).update(
            status=InvestmentAgreement.Status.CLOSED,
            closed_at=timezone.now(),
        )
        agreement.refresh_from_db()
        publish_event(
            event_type='investment_agreement.closed',
            payload={'agreement_id': agreement_id},
            tenant_id=tenant_id,
        )
        return agreement


def assert_agreement_open(agreement) -> None:
    """Read-only lock: after CLOSED, operations changing agreement economics
    (contributions, allocations, new procurements) are forbidden (T-3.5)."""
    from .models import InvestmentAgreement
    if getattr(agreement, 'status', None) == InvestmentAgreement.Status.CLOSED:
        raise ValueError(
            'Договор закрыт (CLOSED): операции, меняющие его экономику '
            '(взносы, аллокации, новые приходы), запрещены.'
        )
