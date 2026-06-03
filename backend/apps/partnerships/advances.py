"""
E14 — CapitalAdvance settlement service.

An inter-partner capital advance is an interest-free qard: the debtor under-
contributed and the creditor (over-contributor) covered the gap so the receive
could hold the agreed shares. Settling repays the creditor's principal — never
more (principal-only, no markup).

Two sources:
- CASH: the debtor brings real cash into the agreement pool (completing their
  capital → debtor equity rises) and the creditor's fronted principal is returned
  out of the pool (creditor equity falls). Net pool cash is flat; equity converges
  to the agreed shares. Money moves only through the agreement pool (Rule #13).
- FROM_PROFIT: the debtor's undistributed profit repays the creditor instead of
  new cash. Bounded by the debtor's accrued-but-unpaid profit. The cash routing is
  wired with the profit-distribution path (T-3.2); here we enforce the bound.
"""

from decimal import Decimal

from django.db import transaction

from apps.finance.fx_rates import resolve_fx_rate_snapshot_details
from apps.finance.models import CashEntry
from apps.finance.services import create_cash_entry, create_journal_entry

from .models import (
    AgreementPartner,
    CapitalAdvance,
    CapitalAdvanceSettlement,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
    ProcurementPartnerLedger,
)

_CENTS = Decimal('0.01')


def _equity_account_code(*, role: str, legal_mode: str | None) -> str:
    """Role-correct equity COA (mirror of workspace_support._capital_equity_account_code)."""
    if role == AgreementPartner.Role.INVESTOR:
        if str(legal_mode) == InvestmentAgreement.LegalMode.MUSHARAKA:
            return '3110'
        return '3100'
    return '3000'


def _partner_role(agreement: InvestmentAgreement, partner_id: int) -> str:
    member = agreement.partners.filter(partner_id=partner_id).first()
    if member is None:
        raise ValueError(f'Partner {partner_id} is not a member of agreement {agreement.id}.')
    return member.role


def undistributed_profit_uzs(*, tenant_id: int, agreement_id: int, partner_id: int) -> Decimal:
    """Debtor's accrued-but-not-yet-paid-out profit (functional UZS) across all
    procurement ledgers of the agreement: Σ PROFIT_ACCRUED − PROFIT_REVERSED
    − LOSS_INCURRED − DIVIDEND_PAID, floored at zero."""
    from django.db.models import Sum

    procurement_ids = list(
        Procurement.objects.filter(tenant_id=tenant_id, agreement_id=agreement_id)
        .values_list('id', flat=True)
    )
    ledger_ids = list(
        ProcurementPartnerLedger.objects.filter(
            tenant_id=tenant_id, partner_id=partner_id, procurement_id__in=procurement_ids,
        ).values_list('id', flat=True)
    )
    if not ledger_ids:
        return Decimal('0.00')
    rows = (
        PartnerLedgerEntry.objects.filter(ledger_id__in=ledger_ids)
        .values('entry_type')
        .annotate(total=Sum('functional_amount_uzs'))
    )
    totals = {r['entry_type']: (r['total'] or Decimal('0')) for r in rows}
    ET = PartnerLedgerEntry.EntryType
    pending = (
        totals.get(ET.PROFIT_ACCRUED, Decimal('0'))
        - totals.get(ET.PROFIT_REVERSED, Decimal('0'))
        - totals.get(ET.LOSS_INCURRED, Decimal('0'))
        - totals.get(ET.DIVIDEND_PAID, Decimal('0'))
    )
    return max(Decimal('0.00'), Decimal(pending).quantize(_CENTS))


def _recompute_status(advance: CapitalAdvance) -> None:
    outstanding = advance.outstanding_balance
    if outstanding <= 0:
        advance.status = CapitalAdvance.Status.SETTLED
    elif advance.settled_amount > 0:
        advance.status = CapitalAdvance.Status.PARTIAL
    else:
        advance.status = CapitalAdvance.Status.OUTSTANDING
    advance.save(update_fields=['status'])


def settle_capital_advance(
    *,
    tenant_id: int,
    advance_id: int,
    amount: Decimal,
    source: str,
    client_request_id=None,
    paid_at=None,
) -> CapitalAdvance:
    """Append one settlement event, move money per `source`, recompute status.
    Principal-only; never below zero. Idempotent on client_request_id."""
    amount = Decimal(str(amount)).quantize(_CENTS)
    source = str(source).upper()

    with transaction.atomic():
        advance = CapitalAdvance.objects.select_for_update().get(pk=advance_id, tenant_id=tenant_id)

        # Idempotency: a prior settlement with the same request id is a no-op.
        if client_request_id is not None:
            existing = CapitalAdvanceSettlement.objects.filter(
                tenant_id=tenant_id, client_request_id=client_request_id,
            ).first()
            if existing is not None:
                return advance

        if amount <= 0:
            raise ValueError('Settlement amount must be positive.')
        if advance.status == CapitalAdvance.Status.CANCELLED:
            raise ValueError('Cannot settle a cancelled advance.')
        if amount - advance.outstanding_balance > _CENTS:
            raise ValueError(
                f'Settlement {amount} exceeds outstanding balance {advance.outstanding_balance}.'
            )

        agreement = advance.agreement
        when = paid_at or _now()
        fx = resolve_fx_rate_snapshot_details(
            tenant_id=tenant_id, operation_currency=advance.currency, operation_at=when,
        )
        functional = (amount * Decimal(str(fx.rate))).quantize(_CENTS)

        if source == CapitalAdvanceSettlement.Source.CASH:
            _settle_cash(
                tenant_id=tenant_id, advance=advance, agreement=agreement,
                amount=amount, functional=functional, when=when,
            )
        elif source == CapitalAdvanceSettlement.Source.FROM_PROFIT:
            pending = undistributed_profit_uzs(
                tenant_id=tenant_id, agreement_id=agreement.id, partner_id=advance.debtor_id,
            )
            if functional - pending > _CENTS:
                raise ValueError(
                    f'FROM_PROFIT settlement {functional} UZS exceeds the debtor\'s '
                    f'undistributed profit {pending} UZS.'
                )
            # Profit-routed repayment is wired with the profit-distribution path (T-3.2).
            raise NotImplementedError('FROM_PROFIT settlement money movement lands in T-3.2.')
        else:
            raise ValueError(f'Unknown settlement source: {source}.')

        CapitalAdvanceSettlement.objects.create(
            tenant_id=tenant_id, advance=advance, amount=amount, source=source,
            source_ref=f'capital_advance:{advance.id}', client_request_id=client_request_id,
        )
        _recompute_status(advance)
        return advance


def _settle_cash(*, tenant_id, advance, agreement, amount, functional, when) -> None:
    """Debtor brings cash into the pool (equity up); creditor's principal is
    returned out of the pool (equity down). Net pool cash flat."""
    pool = agreement.capital_account
    if pool is None:
        raise ValueError('Agreement has no capital pool account.')

    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.IN,
        amount=amount, date=when,
        source_ref_type='capital_advance_settlement', source_ref_id=advance.id,
    )
    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.OUT,
        amount=amount, date=when,
        source_ref_type='capital_advance_settlement', source_ref_id=advance.id,
    )

    debtor_equity = _equity_account_code(
        role=_partner_role(agreement, advance.debtor_id), legal_mode=agreement.legal_mode)
    creditor_equity = _equity_account_code(
        role=_partner_role(agreement, advance.creditor_id), legal_mode=agreement.legal_mode)

    # Equity moves from creditor (over-contributed, returned) to debtor (capital
    # completed). Pool linked 1300 nets to zero (cash IN then OUT), so it is omitted.
    create_journal_entry(
        tenant_id=tenant_id,
        operation_type='advance_settle',
        operation_id=advance.id,
        lines=[
            {'account_code': creditor_equity, 'debit': functional, 'credit': Decimal('0'),
             'description': f'Advance #{advance.id} settled (creditor return)'},
            {'account_code': debtor_equity, 'debit': Decimal('0'), 'credit': functional,
             'description': f'Advance #{advance.id} settled (debtor capital completed)'},
        ],
        description=f'Capital advance #{advance.id} cash settlement',
        date=when,
    )


def cancel_advances_for_batch(*, tenant_id: int, batch_id: int, when=None) -> int:
    """E14: when a receive batch is reversed (only possible while fully unsold),
    cancel its advances and refund any prior CASH settlements. The advance
    creation posted no GL (equity stayed at actual contributions), so only
    settlements need reversing. Returns the number of advances cancelled."""
    when = when or _now()
    cancelled = 0
    for advance in CapitalAdvance.objects.select_for_update().filter(
        tenant_id=tenant_id, batch_id=batch_id,
    ).exclude(status=CapitalAdvance.Status.CANCELLED):
        agreement = advance.agreement
        for settlement in advance.settlements.all():
            if settlement.source == CapitalAdvanceSettlement.Source.CASH:
                _refund_cash_settlement(
                    tenant_id=tenant_id, advance=advance, agreement=agreement,
                    amount=Decimal(settlement.amount), when=when,
                )
        advance.status = CapitalAdvance.Status.CANCELLED
        advance.save(update_fields=['status'])
        cancelled += 1
    return cancelled


def _refund_cash_settlement(*, tenant_id, advance, agreement, amount, when) -> None:
    """Inverse of _settle_cash: debtor's equity back down, creditor's back up,
    cash returned to the debtor. Append-only reversing postings."""
    pool = agreement.capital_account
    fx = resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id, operation_currency=advance.currency, operation_at=when)
    functional = (Decimal(str(amount)) * Decimal(str(fx.rate))).quantize(_CENTS)

    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.IN,
        amount=amount, date=when,
        source_ref_type='advance_settle_reversal', source_ref_id=advance.id)
    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.OUT,
        amount=amount, date=when,
        source_ref_type='advance_settle_reversal', source_ref_id=advance.id)

    debtor_equity = _equity_account_code(
        role=_partner_role(agreement, advance.debtor_id), legal_mode=agreement.legal_mode)
    creditor_equity = _equity_account_code(
        role=_partner_role(agreement, advance.creditor_id), legal_mode=agreement.legal_mode)
    create_journal_entry(
        tenant_id=tenant_id, operation_type='advance_settle', operation_id=advance.id,
        lines=[
            {'account_code': debtor_equity, 'debit': functional, 'credit': Decimal('0'),
             'description': f'Advance #{advance.id} settlement reversed'},
            {'account_code': creditor_equity, 'debit': Decimal('0'), 'credit': functional,
             'description': f'Advance #{advance.id} settlement reversed'},
        ],
        description=f'Capital advance #{advance.id} settlement reversal', date=when)


def _now():
    from django.utils import timezone
    return timezone.now()
