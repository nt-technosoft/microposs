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


def partner_capital_positions(agreement) -> dict:
    """E14 (participant↔pool): net capital position per partner vs the agreement
    pool, DERIVED from the immutable receive snapshots + settlements. Nets across
    all receives; reversed batches are excluded.

    Per partner: {agreed, actual, settled, net}. net > 0 → the partner owes the
    pool (under-contributed vs agreed). net < 0 → the pool owes the partner
    (over-contributed — withdrawable). Under FACTUAL the agreed share equals the
    actual, so net is ~0 and nobody owes."""
    from .models import (
        ProcurementReceiveBatch,
        ProcurementReceiveBatchCapitalAllocation,
    )
    tenant_id = agreement.tenant_id
    batches = (
        ProcurementReceiveBatch.objects
        .filter(tenant_id=tenant_id, procurement__agreement=agreement, is_reversal=False)
        .exclude(reversal_batches__isnull=False)
    )
    agreed: dict[int, Decimal] = {}
    actual: dict[int, Decimal] = {}
    for batch in batches:
        rows = list(ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=batch))
        required = sum((Decimal(str(r.amount_contract_currency)) for r in rows), Decimal('0'))
        for r in rows:
            ag = (Decimal(str(r.capital_share)) * required).quantize(_CENTS)
            agreed[r.partner_id] = agreed.get(r.partner_id, Decimal('0')) + ag
            actual[r.partner_id] = actual.get(r.partner_id, Decimal('0')) + Decimal(str(r.amount_contract_currency))

    # Settlements are currently recorded against per-batch advances; sum them by
    # the debtor partner (re-keying to (agreement, partner) is a later slice).
    settled: dict[int, Decimal] = {}
    for s in CapitalAdvanceSettlement.objects.filter(
        tenant_id=tenant_id, advance__agreement=agreement,
    ).select_related('advance'):
        pid = s.advance.debtor_id
        settled[pid] = settled.get(pid, Decimal('0')) + Decimal(str(s.amount))

    positions: dict[int, dict] = {}
    for pid in set(agreed) | set(actual):
        a = agreed.get(pid, Decimal('0')).quantize(_CENTS)
        ac = actual.get(pid, Decimal('0')).quantize(_CENTS)
        st = settled.get(pid, Decimal('0')).quantize(_CENTS)
        positions[pid] = {
            'agreed': a, 'actual': ac, 'settled': st,
            'net': (a - ac - st).quantize(_CENTS),
        }
    return positions


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
    from_account_id: int | None = None,
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
                amount=amount, when=when,
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
            _settle_from_profit(
                tenant_id=tenant_id, advance=advance, agreement=agreement,
                amount=amount, functional=functional, when=when, from_account_id=from_account_id,
            )
        else:
            raise ValueError(f'Unknown settlement source: {source}.')

        CapitalAdvanceSettlement.objects.create(
            tenant_id=tenant_id, advance=advance, amount=amount, source=source,
            source_ref=f'capital_advance:{advance.id}', client_request_id=client_request_id,
        )
        _recompute_status(advance)
        return advance


def _settle_cash(*, tenant_id, advance, agreement, amount, when) -> None:
    """Model B: settling with cash IS the debtor finally contributing the capital
    they owed. Recorded as a real agreement contribution (cash into the pool +
    debtor equity + AgreementContribution row, so the agreement's derived balances
    stay reconciled with the physical pool). The creditor recovers its
    over-contribution separately via a withdrawal. Money flows through the
    agreement (Rule #13)."""
    from apps.partnerships.workspace_support import add_agreement_contribution

    add_agreement_contribution(
        tenant_id=tenant_id, agreement_id=agreement.id, partner_id=advance.debtor_id,
        amount=amount, currency=advance.currency, date=when,
        notes=f'Погашение долга по авансу #{advance.id}',
    )


def auto_settle_advances_from_profit(
    *, tenant_id: int, agreement_id: int, partner_id: int, from_account_id: int, paid_at=None,
) -> Decimal:
    """E15: settle the partner's FROM_PROFIT-mode outstanding advances out of their
    available undistributed profit (oldest first), until profit runs out. Used to
    implement the "repay from profit" toggle — first profit closes the debt, the
    rest stays the partner's. Returns the total settled (advance currency)."""
    settled = Decimal('0.00')
    advances = (
        CapitalAdvance.objects.filter(
            tenant_id=tenant_id, agreement_id=agreement_id, debtor_id=partner_id,
            repayment_mode=CapitalAdvance.RepaymentMode.FROM_PROFIT,
        )
        .exclude(status__in=[CapitalAdvance.Status.SETTLED, CapitalAdvance.Status.CANCELLED])
        .order_by('id')
    )
    for adv in advances:
        pending = undistributed_profit_uzs(
            tenant_id=tenant_id, agreement_id=agreement_id, partner_id=partner_id)
        if pending <= 0:
            break
        take = min(adv.outstanding_balance, pending)
        if take <= 0:
            continue
        settle_capital_advance(
            tenant_id=tenant_id, advance_id=adv.id, amount=take,
            source=CapitalAdvanceSettlement.Source.FROM_PROFIT,
            from_account_id=from_account_id, paid_at=paid_at)
        settled += take
    return settled


def _settle_from_profit(*, tenant_id, advance, agreement, amount, functional, when, from_account_id) -> None:
    """Model B: the debtor reinvests their accrued profit as capital. The profit
    cash moves operating → agreement pool (DR 1300 / CR operating cash), and the
    debtor's retained-earnings share converts to their capital (DR 3200 / CR
    debtor capital). The cash stays in the pool; the creditor recovers their
    over-contribution separately via a withdrawal. profit_pending drops
    (DIVIDEND_PAID). Principal-only."""
    from apps.finance.models import CashAccount
    from apps.partnerships.agreement_services import append_ledger_entry, get_or_create_ledger

    if from_account_id is None:
        raise ValueError('FROM_PROFIT settlement requires a source operating cash account (from_account_id).')
    if str(advance.currency).upper() != 'UZS':
        raise ValueError('FROM_PROFIT settlement is supported only for UZS agreements for now.')

    pool = agreement.capital_account
    if pool is None:
        raise ValueError('Agreement has no capital pool account.')
    account = CashAccount.objects.select_for_update().get(pk=from_account_id, tenant_id=tenant_id)
    if not account.linked_account_id:
        raise ValueError('Source account has no linked GL account.')
    if Decimal(str(account.balance)) < amount:
        raise ValueError(f'Insufficient cash in {account.name}: have {account.balance}, need {amount}.')

    debtor_capital = _equity_account_code(
        role=_partner_role(agreement, advance.debtor_id), legal_mode=agreement.legal_mode)

    # Cash relocation operating → pool.
    create_cash_entry(
        tenant_id=tenant_id, account=account, direction=CashEntry.Direction.OUT,
        amount=amount, date=when,
        source_ref_type='advance_from_profit', source_ref_id=advance.id)
    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.IN,
        amount=amount, date=when,
        source_ref_type='advance_from_profit', source_ref_id=advance.id)
    create_journal_entry(
        tenant_id=tenant_id, operation_type='advance_settle', operation_id=advance.id,
        lines=[
            {'account_code': pool.linked_account.code, 'debit': functional, 'credit': Decimal('0'),
             'description': f'Advance #{advance.id}: profit moved into pool'},
            {'account_code': account.linked_account.code, 'debit': Decimal('0'), 'credit': functional,
             'description': f'Advance #{advance.id}: profit cash out of operating'},
            {'account_code': '3200', 'debit': functional, 'credit': Decimal('0'),
             'description': f'Advance #{advance.id}: debtor profit consumed'},
            {'account_code': debtor_capital, 'debit': Decimal('0'), 'credit': functional,
             'description': f'Advance #{advance.id}: debtor capital completed'},
        ],
        description=f'Capital advance #{advance.id} settled from profit', date=when)

    ledger = get_or_create_ledger(
        procurement_id=advance.batch.procurement_id, partner_id=advance.debtor_id, tenant_id=tenant_id)
    append_ledger_entry(
        ledger=ledger, entry_type=PartnerLedgerEntry.EntryType.DIVIDEND_PAID,
        amount=amount, currency=advance.currency,
        source_ref=f'advance_from_profit:{advance.id}', date=when)

    # Reconciliation: the reinvested profit is the debtor's capital contribution,
    # so the agreement's derived balances stay in sync with the physical pool.
    from apps.partnerships.models import AgreementConfirmationStatus, AgreementContribution
    AgreementContribution.objects.create(
        tenant_id=tenant_id, agreement=agreement, partner_id=advance.debtor_id,
        amount=amount, currency=advance.currency, fx_rate=Decimal('1'), date=when,
        confirmation_status=AgreementConfirmationStatus.CONFIRMED,
        notes=f'Погашение долга по авансу #{advance.id} (из прибыли)',
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
    """Inverse of _settle_cash (Model B): take the debtor's deposit back OUT of
    the pool and undo their capital completion (DR debtor equity / CR 1300).
    Append-only reversing postings."""
    pool = agreement.capital_account
    fx = resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id, operation_currency=advance.currency, operation_at=when)
    functional = (Decimal(str(amount)) * Decimal(str(fx.rate))).quantize(_CENTS)

    create_cash_entry(
        tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.OUT,
        amount=amount, date=when,
        source_ref_type='advance_settle_reversal', source_ref_id=advance.id)

    debtor_equity = _equity_account_code(
        role=_partner_role(agreement, advance.debtor_id), legal_mode=agreement.legal_mode)
    create_journal_entry(
        tenant_id=tenant_id, operation_type='advance_settle', operation_id=advance.id,
        lines=[
            {'account_code': debtor_equity, 'debit': functional, 'credit': Decimal('0'),
             'description': f'Advance #{advance.id} settlement reversed'},
            {'account_code': pool.linked_account.code, 'debit': Decimal('0'), 'credit': functional,
             'description': f'Advance #{advance.id} settlement reversed'},
        ],
        description=f'Capital advance #{advance.id} settlement reversal', date=when)


def _now():
    from django.utils import timezone
    return timezone.now()
