"""
E14/E17 — partner net-capital reconciliation (participant ↔ agreement pool).

The agreed-vs-actual capital gap is NOT reified as a CapitalAdvance entity any
more (E17 retired that). It is read directly as each partner's net capital
position vs the pool (`partner_capital_positions`) and settled explicitly
(`settle_partner_capital`):

- CASH: the under-contributor brings real cash into the agreement pool, raising
  their paid-in and lowering their net; money moves only through the pool
  (Rule #13). The over-contributor recovers its surplus separately via a
  capital withdrawal.
- FROM_PROFIT: the partner's undistributed venture profit is reinvested as
  capital. Bounded by `undistributed_profit_uzs` (venture-sourced — profit is
  unavailable before a venture settlement).
"""

from decimal import Decimal

from django.db import transaction

from apps.finance.fx_rates import resolve_fx_rate_snapshot_details
from apps.finance.models import CashEntry
from apps.finance.services import create_cash_entry, create_journal_entry, require_operating_cash_account

from .models import (
    AgreementPartner,
    CapitalSettlementSource,
    InvestmentAgreement,
    PartnerLedgerEntry,
    Procurement,
)
from .money_utils import equity_account_code

_CENTS = Decimal('0.01')


def _partner_role(agreement: InvestmentAgreement, partner_id: int) -> str:
    member = agreement.partners.filter(partner_id=partner_id).first()
    if member is None:
        raise ValueError(f'Partner {partner_id} is not a member of agreement {agreement.id}.')
    return member.role


def undistributed_profit_uzs(*, tenant_id: int, agreement_id: int, partner_id: int) -> Decimal:
    """Partner's venture profit available to consume (functional UZS), summed
    across the agreement's procurements.

    E17 T-1: sourced from venture positions, not the legacy PartnerLedgerEntry
    profit triad. Venture profit is unavailable before a constructive/final
    settlement, so this is 0 until the venture is settled — which is the correct
    "no profit withdrawal before capital preservation" behaviour."""
    from .venture import procurement_venture_positions

    total = Decimal('0.00')
    procurements = Procurement.objects.filter(tenant_id=tenant_id, agreement_id=agreement_id)
    for procurement in procurements:
        row = procurement_venture_positions(procurement=procurement).get(partner_id)
        if row:
            total += Decimal(str(row.get('provisional_profit_available_uzs', '0')))
    return max(Decimal('0.00'), total.quantize(_CENTS))


def settle_partner_capital(
    *, tenant_id: int, agreement_id: int, partner_id: int, amount, source: str,
    from_account_id: int | None = None, client_request_id=None, paid_at=None,
):
    """B (participant↔pool): settle a partner's net capital shortfall vs the pool.
    CASH — the partner contributes the owed capital into the pool; FROM_PROFIT —
    their accrued profit is reinvested as capital. Bounded by their net shortfall.
    The creditor side recovers its surplus separately via a capital withdrawal."""
    from .models import InvestmentAgreement

    amount = Decimal(str(amount)).quantize(_CENTS)
    source = str(source).upper()
    when = paid_at or _now()

    with transaction.atomic():
        agreement = InvestmentAgreement.objects.select_for_update().get(pk=agreement_id, tenant_id=tenant_id)

        if amount <= 0:
            raise ValueError('Settlement amount must be positive.')
        owed = (partner_capital_positions(agreement).get(partner_id) or {}).get('owed', Decimal('0'))
        if owed <= 0:
            raise ValueError('This partner has no outstanding capital owed to the pool.')
        if amount - owed > _CENTS:
            raise ValueError(f'Settlement {amount} exceeds the partner\'s outstanding {owed}.')

        # Settling IS contributing: the partner pays the owed capital into the
        # pool, which raises their paid-in and lowers their net automatically
        # (no separate settlement record). CASH = new money; FROM_PROFIT = their
        # profit reinvested as capital.
        currency = str(agreement.currency or 'UZS').upper()
        if source == CapitalSettlementSource.CASH:
            from apps.partnerships.workspace_support import add_agreement_contribution
            add_agreement_contribution(
                tenant_id=tenant_id, agreement_id=agreement_id, partner_id=partner_id,
                amount=amount, currency=currency, date=when,
                client_request_id=str(client_request_id) if client_request_id else None,
                notes='Погашение капитального долга (довнос в пул)')
        elif source == CapitalSettlementSource.FROM_PROFIT:
            functional = (amount * _agreement_fx_rate(tenant_id, currency, when)).quantize(_CENTS)
            pending = undistributed_profit_uzs(
                tenant_id=tenant_id, agreement_id=agreement_id, partner_id=partner_id)
            if functional - pending > _CENTS:
                raise ValueError(
                    f'FROM_PROFIT settlement {functional} UZS exceeds undistributed profit {pending} UZS.')
            _settle_partner_from_profit(
                tenant_id=tenant_id, agreement=agreement, partner_id=partner_id,
                amount=amount, functional=functional, when=when, from_account_id=from_account_id)
        else:
            raise ValueError(f'Unknown settlement source: {source}.')

        from .read_models import rebuild_agreement_positions
        rebuild_agreement_positions(agreement)
        return partner_capital_positions(agreement).get(partner_id)


def _agreement_fx_rate(tenant_id: int, currency: str, when) -> Decimal:
    fx = resolve_fx_rate_snapshot_details(
        tenant_id=tenant_id, operation_currency=currency, operation_at=when)
    return Decimal(str(fx.rate))


def _settle_partner_from_profit(*, tenant_id, agreement, partner_id, amount, functional, when, from_account_id) -> None:
    """Per-partner FROM_PROFIT (Model B): venture profit cash (operating) → pool,
    retained earnings → partner equity. GL and cash entries are unchanged from the
    E17 design; only the domain records are now honest:
    - PROFIT_TO_CAPITAL ledger entry (was: fake DIVIDEND_PAID)
    - AgreementContribution with source=PROFIT_REINVEST (was: generic BUSINESS_RECORDED)
    UZS agreements only for now."""
    from apps.finance.models import CashAccount
    from apps.partnerships.agreement_services import append_ledger_entry, get_or_create_ledger
    from apps.partnerships.models import (
        AgreementActionSource,
        AgreementConfirmationStatus,
        AgreementContribution,
    )

    if from_account_id is None:
        raise ValueError('FROM_PROFIT settlement requires a source operating cash account.')
    if str(agreement.currency or 'UZS').upper() != 'UZS':
        raise ValueError('FROM_PROFIT settlement is supported only for UZS agreements for now.')
    pool = agreement.capital_account
    if pool is None:
        raise ValueError('Agreement has no capital pool account.')
    account = CashAccount.objects.select_for_update().get(pk=from_account_id, tenant_id=tenant_id)
    require_operating_cash_account(account, action='Profit-to-capital settlement')
    if not account.linked_account_id:
        raise ValueError('Source account has no linked GL account.')
    if Decimal(str(account.balance)) < amount:
        raise ValueError(f'Insufficient cash in {account.name}: have {account.balance}, need {amount}.')

    procurement = agreement.procurements.first()
    if procurement is None:
        raise ValueError('Agreement has no procurement for the profit ledger.')
    debtor_capital = equity_account_code(
        role=_partner_role(agreement, partner_id), legal_mode=agreement.legal_mode)

    # GL + cash entries: UNCHANGED from E17 (oracle G4 pins numbers/accounts).
    create_cash_entry(tenant_id=tenant_id, account=account, direction=CashEntry.Direction.OUT,
                      amount=amount, date=when, source_ref_type='partner_from_profit', source_ref_id=partner_id)
    create_cash_entry(tenant_id=tenant_id, account=pool, direction=CashEntry.Direction.IN,
                      amount=amount, date=when, source_ref_type='partner_from_profit', source_ref_id=partner_id)
    journal = create_journal_entry(
        tenant_id=tenant_id, operation_type='advance_settle', operation_id=agreement.id,
        lines=[
            {'account_code': pool.linked_account.code, 'debit': functional, 'credit': Decimal('0'),
             'description': 'Погашение из прибыли — в пул'},
            {'account_code': account.linked_account.code, 'debit': Decimal('0'), 'credit': functional,
             'description': 'Погашение из прибыли — из операционной кассы'},
            {'account_code': '3200', 'debit': functional, 'credit': Decimal('0'),
             'description': 'Прибыль партнёра потреблена'},
            {'account_code': debtor_capital, 'debit': Decimal('0'), 'credit': functional,
             'description': 'Капитал партнёра достроен'},
        ],
        description='Погашение капитального долга из прибыли', date=when)

    # E18 Phase 1: honest domain records (no fake dividend, no generic contribution).
    ledger = get_or_create_ledger(procurement_id=procurement.id, partner_id=partner_id, tenant_id=tenant_id)
    append_ledger_entry(
        ledger=ledger,
        entry_type=PartnerLedgerEntry.EntryType.PROFIT_TO_CAPITAL,
        amount=amount, currency=agreement.currency or 'UZS',
        source_ref=f'partner_from_profit:{partner_id}', date=when,
    )
    AgreementContribution.objects.create(
        tenant_id=tenant_id, agreement=agreement, partner_id=partner_id,
        amount=amount, currency=agreement.currency or 'UZS', fx_rate=Decimal('1'), date=when,
        source=AgreementActionSource.PROFIT_REINVEST,
        confirmation_status=AgreementConfirmationStatus.CONFIRMED,
        notes='Прибыль реинвестирована в капитал пула',
    )
    from .journal_tags import tag_profit_to_capital
    tag_profit_to_capital(
        tenant_id=tenant_id,
        journal_entry=journal,
        agreement=agreement,
        partner_id=partner_id,
        procurement=procurement,
    )


def partner_capital_positions(agreement) -> dict:
    """E14 (participant↔pool, unified): each partner's capital position vs the
    agreement pool, DERIVED entirely from facts — no separate "settlement" concept
    (settling IS contributing). For each partner:

      deployed = Σ (agreed ownership share × deployed receive cost)  [from snapshots]
      paid_in  = Σ contributions − Σ POOL withdrawals                [actual pool cash in]
      net      = deployed − paid_in
        net > 0 → owes the pool (must contribute `net` more)
        net < 0 → over-contributed (claim on the pool)

    Only withdrawals explicitly classified as FROM_POOL reduce paid_in. E16
    recovered-capital returns leave the OPERATING cash (a venture distribution,
    counted in the venture position), so they do NOT touch the pool net.

    `withdrawable` = how much an over-contributor can actually take out NOW,
    bounded by the pool's free cash (overpaid money tied up in inventory becomes
    withdrawable only once debtors top up). Reversed batches are excluded. A
    fresh agreement (no receives) → everything 0, nothing owed/withdrawable."""
    from .models import (
        AgreementWithdrawal,
        ProcurementReceiveBatch,
        ProcurementReceiveBatchCapitalAllocation,
    )
    tenant_id = agreement.tenant_id
    currency = str(agreement.currency or 'UZS').upper()

    batches = (
        ProcurementReceiveBatch.objects
        .filter(tenant_id=tenant_id, procurement__agreement=agreement, is_reversal=False)
        .exclude(reversal_batches__isnull=False)
    )
    deployed: dict[int, Decimal] = {}
    for batch in batches:
        rows = list(ProcurementReceiveBatchCapitalAllocation.objects.filter(batch=batch))
        required = sum((Decimal(str(r.amount_contract_currency)) for r in rows), Decimal('0'))
        for r in rows:
            share = (Decimal(str(r.capital_share)) * required).quantize(_CENTS)
            deployed[r.partner_id] = deployed.get(r.partner_id, Decimal('0')) + share

    paid_in: dict[int, Decimal] = {}
    for c in agreement.contributions.filter(currency=currency):
        paid_in[c.partner_id] = paid_in.get(c.partner_id, Decimal('0')) + Decimal(str(c.amount))
    # E17/E18: only explicit POOL withdrawals reduce pool paid-in. E16
    # recovered-capital returns leave the OPERATING cash
    # and are a venture distribution already counted in the venture position
    # (capital_returned_uzs); counting them here too double-counted the same return
    # and falsely inflated net into "owes the pool".
    for w in agreement.withdrawals.filter(
        currency=currency,
        return_kind=AgreementWithdrawal.ReturnKind.FROM_POOL,
    ):
        paid_in[w.partner_id] = paid_in.get(w.partner_id, Decimal('0')) - Decimal(str(w.amount))

    total_paid = sum(paid_in.values(), Decimal('0'))
    total_deployed = sum(deployed.values(), Decimal('0'))
    pool_free = max(Decimal('0'), (total_paid - total_deployed).quantize(_CENTS))

    venture_uzs: dict[int, dict[str, Decimal]] = {}
    for procurement in agreement.procurements.all():
        from .venture import procurement_venture_positions
        for partner_id, row in procurement_venture_positions(procurement=procurement).items():
            target = venture_uzs.setdefault(partner_id, {
                'deployed_uzs': Decimal('0.00'),
                'capital_recovered_uzs': Decimal('0.00'),
                'remaining_inventory_capital_uzs': Decimal('0.00'),
                'liability_capital_recovered_uzs': Decimal('0.00'),
                'provisional_profit_uzs': Decimal('0.00'),
                'loss_uzs': Decimal('0.00'),
                'partner_liability_loss_uzs': Decimal('0.00'),
                'capital_returned_uzs': Decimal('0.00'),
                'dividends_paid_uzs': Decimal('0.00'),
                'profit_to_capital_uzs': Decimal('0.00'),
                'capital_return_available_uzs': Decimal('0.00'),
                'provisional_profit_available_uzs': Decimal('0.00'),
                'negative_position_uzs': Decimal('0.00'),
            })
            for key in target:
                target[key] += Decimal(str(row.get(key, Decimal('0.00'))))

    positions: dict[int, dict] = {}
    for pid in set(deployed) | set(paid_in):
        d = deployed.get(pid, Decimal('0')).quantize(_CENTS)
        p = paid_in.get(pid, Decimal('0')).quantize(_CENTS)
        net = (d - p).quantize(_CENTS)
        withdrawable = min(-net, pool_free).quantize(_CENTS) if net < 0 else Decimal('0.00')
        venture = {
            key: value.quantize(_CENTS)
            for key, value in venture_uzs.get(pid, {}).items()
        }
        positions[pid] = {
            # E17 T-1.7: native pool-capital amounts (deployed/paid_in/net/owed/
            # withdrawable) are in `currency` (the agreement currency); the
            # venture buckets carry an explicit `_uzs` suffix and are functional
            # UZS. The two units must never be summed together — `currency` makes
            # the native leg self-describing so non-UZS agreements can't silently
            # mix scales.
            'currency': currency,
            'deployed': d, 'paid_in': p, 'net': net,
            'owed': max(Decimal('0.00'), net), 'withdrawable': max(Decimal('0.00'), withdrawable),
            # E16: these functional UZS buckets describe sold-capital/proceeds
            # economics. They are informational here; pool withdrawals still
            # require physical pool cash until an explicit recovered-proceeds
            # transfer/payout source is used.
            **venture,
        }
    return positions


def _now():
    from django.utils import timezone
    return timezone.now()
