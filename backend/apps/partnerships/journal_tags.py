from __future__ import annotations

from django.db import models

from apps.finance.models import JournalEntry, JournalLine, Payment

from .money_utils import equity_account_code
from .models import (
    AgreementActionSource,
    AgreementAllocation,
    AgreementContribution,
    AgreementPartner,
    AgreementWithdrawal,
    DividendPayment,
    InvestmentAgreement,
    PartnerJournalLineTag,
    PartnerLedgerEntry,
    Procurement,
    ProcurementPartnerVentureDebtRepayment,
)


def _partner_equity_code(*, agreement: InvestmentAgreement, partner_id: int) -> str:
    member = AgreementPartner.objects.get(agreement=agreement, partner_id=partner_id)
    return equity_account_code(role=member.role, legal_mode=agreement.legal_mode)


def tag_journal_lines(
    *,
    tenant_id: int,
    journal_entry: JournalEntry | None,
    partner_id: int,
    agreement: InvestmentAgreement,
    procurement: Procurement | None,
    pocket: str,
    flow: str,
    account_codes: set[str] | tuple[str, ...] | list[str] | None = None,
    debit: bool | None = None,
    credit: bool | None = None,
) -> int:
    if journal_entry is None:
        return 0

    lines = JournalLine.objects.filter(tenant_id=tenant_id, journal_entry=journal_entry)
    if account_codes:
        lines = lines.filter(account__code__in=set(account_codes))
    if debit is True:
        lines = lines.filter(debit__gt=0)
    if credit is True:
        lines = lines.filter(credit__gt=0)

    created = 0
    for line in lines:
        _tag, was_created = PartnerJournalLineTag.all_objects.update_or_create(
            tenant_id=tenant_id,
            journal_line=line,
            partner_id=partner_id,
            agreement=agreement,
            procurement=procurement,
            pocket=pocket,
            defaults={'flow': flow, 'deleted_at': None},
        )
        if was_created:
            created += 1
    return created


def tag_capital_contribution(*, contribution: AgreementContribution, payment: Payment | None) -> int:
    pool_code = (
        contribution.agreement.capital_account.linked_account.code
        if contribution.agreement.capital_account_id
        and contribution.agreement.capital_account.linked_account_id
        else '1300'
    )
    return tag_journal_lines(
        tenant_id=contribution.tenant_id,
        journal_entry=payment.journal_entry if payment else None,
        partner_id=contribution.partner_id,
        agreement=contribution.agreement,
        procurement=None,
        pocket=PartnerJournalLineTag.Pocket.CAPITAL,
        flow=PartnerJournalLineTag.Flow.CONTRIBUTION,
        account_codes={pool_code},
        debit=True,
    )


def tag_capital_withdrawal(*, withdrawal: AgreementWithdrawal, journal_entry: JournalEntry | None) -> int:
    pocket = (
        PartnerJournalLineTag.Pocket.CAPITAL
        if withdrawal.return_kind == AgreementWithdrawal.ReturnKind.FROM_POOL
        else PartnerJournalLineTag.Pocket.PROCEEDS
    )
    flow = (
        PartnerJournalLineTag.Flow.POOL_RETURN
        if withdrawal.return_kind == AgreementWithdrawal.ReturnKind.FROM_POOL
        else PartnerJournalLineTag.Flow.CAPITAL_RETURN
    )
    return tag_journal_lines(
        tenant_id=withdrawal.tenant_id,
        journal_entry=journal_entry,
        partner_id=withdrawal.partner_id,
        agreement=withdrawal.agreement,
        procurement=withdrawal.procurement,
        pocket=pocket,
        flow=flow,
        account_codes={_partner_equity_code(agreement=withdrawal.agreement, partner_id=withdrawal.partner_id)},
        debit=True,
    )


def tag_dividend_payment(*, dividend: DividendPayment, journal_entry: JournalEntry | None) -> int:
    return tag_journal_lines(
        tenant_id=dividend.tenant_id,
        journal_entry=journal_entry,
        partner_id=dividend.partner_id,
        agreement=dividend.procurement.agreement,
        procurement=dividend.procurement,
        pocket=PartnerJournalLineTag.Pocket.DISTRIBUTION,
        flow=PartnerJournalLineTag.Flow.DIVIDEND,
        account_codes={'3200'},
        debit=True,
    )


def tag_profit_to_capital(
    *,
    tenant_id: int,
    journal_entry: JournalEntry | None,
    agreement: InvestmentAgreement,
    partner_id: int,
    procurement: Procurement | None,
) -> int:
    created = tag_journal_lines(
        tenant_id=tenant_id,
        journal_entry=journal_entry,
        partner_id=partner_id,
        agreement=agreement,
        procurement=procurement,
        pocket=PartnerJournalLineTag.Pocket.DISTRIBUTION,
        flow=PartnerJournalLineTag.Flow.PROFIT_TO_CAPITAL,
        account_codes={'3200'},
        debit=True,
    )
    created += tag_journal_lines(
        tenant_id=tenant_id,
        journal_entry=journal_entry,
        partner_id=partner_id,
        agreement=agreement,
        procurement=procurement,
        pocket=PartnerJournalLineTag.Pocket.CAPITAL,
        flow=PartnerJournalLineTag.Flow.PROFIT_TO_CAPITAL,
        account_codes={_partner_equity_code(agreement=agreement, partner_id=partner_id)},
        credit=True,
    )
    return created


def tag_venture_debt_repayment(
    *,
    repayment: ProcurementPartnerVentureDebtRepayment,
    journal_entry: JournalEntry | None,
) -> int:
    agreement = repayment.procurement.agreement
    if agreement is None:
        return 0
    created = 0
    if repayment.repaid_liability_uzs:
        created += tag_journal_lines(
            tenant_id=repayment.tenant_id,
            journal_entry=journal_entry,
            partner_id=repayment.partner_id,
            agreement=agreement,
            procurement=repayment.procurement,
            pocket=PartnerJournalLineTag.Pocket.CAPITAL,
            flow=PartnerJournalLineTag.Flow.DEBT_REPAID_LIABILITY,
            account_codes={'5100'},
            credit=True,
        )
    if repayment.repaid_capital_uzs:
        created += tag_journal_lines(
            tenant_id=repayment.tenant_id,
            journal_entry=journal_entry,
            partner_id=repayment.partner_id,
            agreement=agreement,
            procurement=repayment.procurement,
            pocket=PartnerJournalLineTag.Pocket.CAPITAL,
            flow=PartnerJournalLineTag.Flow.DEBT_REPAID_CAPITAL,
            account_codes={_partner_equity_code(agreement=agreement, partner_id=repayment.partner_id)},
            credit=True,
        )
    if repayment.repaid_dividend_uzs:
        created += tag_journal_lines(
            tenant_id=repayment.tenant_id,
            journal_entry=journal_entry,
            partner_id=repayment.partner_id,
            agreement=agreement,
            procurement=repayment.procurement,
            pocket=PartnerJournalLineTag.Pocket.DISTRIBUTION,
            flow=PartnerJournalLineTag.Flow.DEBT_REPAID_DIVIDEND,
            account_codes={'3200'},
            credit=True,
        )
    return created


def tag_overpayment_refund(
    *,
    tenant_id: int,
    journal_entry: JournalEntry | None,
    agreement: InvestmentAgreement,
    procurement: Procurement,
    partner_id: int,
) -> int:
    pool_code = (
        agreement.capital_account.linked_account.code
        if agreement.capital_account_id and agreement.capital_account.linked_account_id
        else '1300'
    )
    return tag_journal_lines(
        tenant_id=tenant_id,
        journal_entry=journal_entry,
        partner_id=partner_id,
        agreement=agreement,
        procurement=procurement,
        pocket=PartnerJournalLineTag.Pocket.CAPITAL,
        flow=PartnerJournalLineTag.Flow.OVERPAYMENT_REFUND,
        account_codes={pool_code},
        debit=True,
    )


def _backfill_contributions(tenant_id: int | None) -> int:
    rows = AgreementContribution.objects.select_related('agreement', 'agreement__capital_account')
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for contribution in rows:
        payment = Payment.objects.filter(
            tenant_id=contribution.tenant_id,
            target_type=Payment.TargetType.CAPITAL_CONTRIBUTION,
            target_id=contribution.id,
        ).select_related('journal_entry').first()
        created += tag_capital_contribution(contribution=contribution, payment=payment)
    return created


def _backfill_withdrawals(tenant_id: int | None) -> int:
    rows = AgreementWithdrawal.objects.select_related('agreement', 'procurement')
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for withdrawal in rows:
        journal = JournalEntry.objects.filter(
            tenant_id=withdrawal.tenant_id,
            operation_type='capital_return',
            operation_id=withdrawal.id,
        ).first()
        created += tag_capital_withdrawal(withdrawal=withdrawal, journal_entry=journal)
    return created


def _backfill_dividends(tenant_id: int | None) -> int:
    rows = DividendPayment.objects.select_related('procurement', 'procurement__agreement')
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for dividend in rows:
        journal = JournalEntry.objects.filter(
            tenant_id=dividend.tenant_id,
            operation_type='profit_distrib',
            operation_id=dividend.id,
        ).first()
        created += tag_dividend_payment(dividend=dividend, journal_entry=journal)
    return created


def _backfill_profit_to_capital(tenant_id: int | None) -> int:
    rows = (
        AgreementContribution.objects
        .filter(source=AgreementActionSource.PROFIT_REINVEST)
        .select_related('agreement')
    )
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for contribution in rows:
        entries = list(JournalEntry.objects.filter(
            tenant_id=contribution.tenant_id,
            operation_type='advance_settle',
            operation_id=contribution.agreement_id,
        ))
        if len(entries) != 1:
            continue
        procurement = contribution.agreement.procurements.first()
        created += tag_profit_to_capital(
            tenant_id=contribution.tenant_id,
            journal_entry=entries[0],
            agreement=contribution.agreement,
            partner_id=contribution.partner_id,
            procurement=procurement,
        )
    return created


def _backfill_repayments(tenant_id: int | None) -> int:
    rows = ProcurementPartnerVentureDebtRepayment.objects.select_related('procurement', 'procurement__agreement')
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for repayment in rows:
        journal = JournalEntry.objects.filter(
            tenant_id=repayment.tenant_id,
            operation_type='venture_debt_repay',
            operation_id=repayment.id,
        ).first()
        created += tag_venture_debt_repayment(repayment=repayment, journal_entry=journal)
    return created


def _backfill_overpayment_refunds(tenant_id: int | None) -> int:
    rows = AgreementAllocation.objects.filter(
        direction=AgreementAllocation.Direction.FROM_PROCUREMENT,
    ).select_related('agreement', 'agreement__capital_account', 'procurement')
    if tenant_id is not None:
        rows = rows.filter(tenant_id=tenant_id)
    created = 0
    for allocation in rows:
        if not PartnerLedgerEntry.objects.filter(
            tenant_id=allocation.tenant_id,
            ledger__procurement_id=allocation.procurement_id,
            ledger__partner_id=allocation.partner_id,
            entry_type=PartnerLedgerEntry.EntryType.CAPITAL_OUT,
            source_ref=f'allocation:{allocation.id}',
        ).exists():
            continue
        payments = list(
            Payment.objects.filter(
                tenant_id=allocation.tenant_id,
                target_type=Payment.TargetType.PROCUREMENT_COST,
                target_id=allocation.procurement_id,
                source_type=Payment.SourceType.CAPITAL_POOL,
                status=Payment.Status.POSTED,
                reversed_payment__isnull=False,
                currency=allocation.currency,
                paid_at=allocation.date,
            ).select_related('journal_entry')
        )
        if len(payments) != 1:
            continue
        created += tag_overpayment_refund(
            tenant_id=allocation.tenant_id,
            journal_entry=payments[0].journal_entry,
            agreement=allocation.agreement,
            procurement=allocation.procurement,
            partner_id=allocation.partner_id,
        )
    return created


def backfill_partner_journal_line_tags(*, tenant_id: int | None = None) -> int:
    """Best-effort metadata backfill; ambiguous history is skipped."""
    created = 0
    created += _backfill_contributions(tenant_id)
    created += _backfill_withdrawals(tenant_id)
    created += _backfill_dividends(tenant_id)
    created += _backfill_profit_to_capital(tenant_id)
    created += _backfill_overpayment_refunds(tenant_id)
    created += _backfill_repayments(tenant_id)
    return created
