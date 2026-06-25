from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import InvestmentAgreement, PartnerPositionReadModel, Procurement
from .money_utils import money as _money

_ZERO = _money(None)


def _empty_payload() -> dict[str, Decimal]:
    return {field: _ZERO for field in PartnerPositionReadModel.MONEY_FIELDS}


def _row(
    rows: dict[tuple[int | None, int, str], dict[str, Decimal]],
    *,
    procurement_id: int | None,
    partner_id: int,
    currency: str,
) -> dict[str, Decimal]:
    key = (procurement_id, int(partner_id), str(currency or 'UZS').upper())
    return rows.setdefault(key, _empty_payload())


def _copy_money_fields(target: dict[str, Decimal], source: dict) -> None:
    for field in PartnerPositionReadModel.MONEY_FIELDS:
        if field in source:
            target[field] = _money(source[field])


def legacy_partner_position_rows(
    agreement: InvestmentAgreement,
) -> dict[tuple[int | None, int, str], dict[str, Decimal]]:
    """Fold the legacy three canonical nodes into the read-model shape."""
    from .advances import partner_capital_positions
    from .venture import procurement_venture_positions
    from .workspace_common import _agreement_available_by_partner

    rows: dict[tuple[int | None, int, str], dict[str, Decimal]] = {}

    for partner_id, by_currency in _agreement_available_by_partner(agreement).items():
        for currency, amount in by_currency.items():
            _row(
                rows,
                procurement_id=None,
                partner_id=partner_id,
                currency=currency,
            )['available'] = _money(amount)

    for partner_id, source in partner_capital_positions(agreement).items():
        currency = str(source.get('currency') or agreement.currency or 'UZS').upper()
        target = _row(
            rows,
            procurement_id=None,
            partner_id=partner_id,
            currency=currency,
        )
        _copy_money_fields(target, source)

    procurements = Procurement.objects.filter(
        tenant_id=agreement.tenant_id,
        agreement=agreement,
        funding_source=Procurement.FundingSource.PARTNERSHIP,
    )
    for procurement in procurements:
        for partner_id, source in procurement_venture_positions(procurement=procurement).items():
            target = _row(
                rows,
                procurement_id=procurement.id,
                partner_id=partner_id,
                currency='UZS',
            )
            _copy_money_fields(target, source)

    return rows


def _journal_line_amount_uzs(tag) -> Decimal:
    line = tag.journal_line
    return _money(Decimal(str(line.debit or _ZERO)) + Decimal(str(line.credit or _ZERO)))


def _apply_tag_realized_venture_fields(
    *,
    agreement: InvestmentAgreement,
    rows: dict[tuple[int | None, int, str], dict[str, Decimal]],
) -> None:
    from .models import PartnerJournalLineTag

    realized_keys: set[tuple[int, int]] = set()
    for procurement_id, partner_id, currency in list(rows.keys()):
        if procurement_id is None or currency != 'UZS':
            continue
        realized_keys.add((procurement_id, partner_id))
        target = rows[(procurement_id, partner_id, currency)]
        target['capital_returned_uzs'] = _ZERO
        target['dividends_paid_uzs'] = _ZERO
        target['profit_to_capital_uzs'] = _ZERO
        target['debt_repaid_uzs'] = _ZERO

    realized: dict[tuple[int, int], dict[str, Decimal]] = {}

    def bucket(procurement_id: int, partner_id: int) -> dict[str, Decimal]:
        return realized.setdefault((procurement_id, partner_id), {
            'capital_returned_uzs': _ZERO,
            'dividends_paid_uzs': _ZERO,
            'profit_to_capital_uzs': _ZERO,
            'repaid_liability_uzs': _ZERO,
            'repaid_capital_uzs': _ZERO,
            'repaid_dividend_uzs': _ZERO,
        })

    tags = (
        PartnerJournalLineTag.objects
        .filter(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            procurement__isnull=False,
        )
        .select_related('journal_line')
    )
    for tag in tags:
        amount = _journal_line_amount_uzs(tag)
        values = bucket(tag.procurement_id, tag.partner_id)
        if tag.flow == PartnerJournalLineTag.Flow.DIVIDEND:
            values['dividends_paid_uzs'] += amount
        elif (
            tag.flow == PartnerJournalLineTag.Flow.PROFIT_TO_CAPITAL
            and tag.pocket == PartnerJournalLineTag.Pocket.CAPITAL
        ):
            values['profit_to_capital_uzs'] += amount
        elif tag.flow in {
            PartnerJournalLineTag.Flow.CAPITAL_RETURN,
            PartnerJournalLineTag.Flow.OVERPAYMENT_REFUND,
        }:
            values['capital_returned_uzs'] += amount
        elif tag.flow == PartnerJournalLineTag.Flow.DEBT_REPAID_LIABILITY:
            values['repaid_liability_uzs'] += amount
        elif tag.flow == PartnerJournalLineTag.Flow.DEBT_REPAID_CAPITAL:
            values['repaid_capital_uzs'] += amount
        elif tag.flow == PartnerJournalLineTag.Flow.DEBT_REPAID_DIVIDEND:
            values['repaid_dividend_uzs'] += amount

    procurements = {
        procurement.id: procurement
        for procurement in Procurement.objects.filter(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            funding_source=Procurement.FundingSource.PARTNERSHIP,
        )
    }
    realized_keys.update(realized.keys())
    for procurement_id, partner_id in realized_keys:
        values = realized.get((procurement_id, partner_id), {
            'capital_returned_uzs': _ZERO,
            'dividends_paid_uzs': _ZERO,
            'profit_to_capital_uzs': _ZERO,
            'repaid_liability_uzs': _ZERO,
            'repaid_capital_uzs': _ZERO,
            'repaid_dividend_uzs': _ZERO,
        })
        target = _row(
            rows,
            procurement_id=procurement_id,
            partner_id=partner_id,
            currency='UZS',
        )
        target['capital_returned_uzs'] = _money(values['capital_returned_uzs'])
        target['dividends_paid_uzs'] = _money(values['dividends_paid_uzs'])
        target['profit_to_capital_uzs'] = _money(values['profit_to_capital_uzs'])

        repaid_liability = _money(values['repaid_liability_uzs'])
        repaid_capital = _money(values['repaid_capital_uzs'])
        repaid_dividend = _money(values['repaid_dividend_uzs'])

        capital_delta = _money(
            target['capital_recovered_uzs']
            - target['capital_returned_uzs']
            + repaid_capital
        )
        profit_delta = _money(
            target['provisional_profit_uzs']
            - target['dividends_paid_uzs']
            - target['profit_to_capital_uzs']
            + repaid_dividend
        )
        target['capital_return_available_uzs'] = max(_ZERO, capital_delta)
        has_settlement = bool(
            procurements.get(procurement_id)
            and procurements[procurement_id].venture_settlements.exists()
        )
        target['provisional_profit_available_uzs'] = (
            max(_ZERO, profit_delta) if has_settlement else _ZERO
        )
        target['negative_liability_uzs'] = max(
            _ZERO,
            _money(target['partner_liability_loss_uzs'] - repaid_liability),
        )
        target['negative_capital_uzs'] = max(_ZERO, -capital_delta)
        target['negative_dividend_uzs'] = max(_ZERO, -profit_delta)
        target['debt_repaid_uzs'] = _money(
            repaid_liability + repaid_capital + repaid_dividend,
        )
        target['negative_position_uzs'] = _money(
            target['negative_liability_uzs']
            + target['negative_capital_uzs']
            + target['negative_dividend_uzs'],
        )


def canonical_partner_position_rows(
    agreement: InvestmentAgreement,
) -> dict[tuple[int | None, int, str], dict[str, Decimal]]:
    """Phase 4 source: pool/provisional legacy nodes + realized venture tags."""
    rows = legacy_partner_position_rows(agreement)
    _apply_tag_realized_venture_fields(agreement=agreement, rows=rows)
    return rows


def read_positions(agreement: InvestmentAgreement) -> dict[int, dict[str, Decimal]]:
    """Display read for agreement-level partner positions from materialized rows."""
    rows = (
        PartnerPositionReadModel.objects
        .filter(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            procurement__isnull=True,
            currency=str(agreement.currency or 'UZS').upper(),
        )
    )
    return {row.partner_id: row.money_payload for row in rows}


def read_venture_positions(procurement: Procurement) -> dict[int, dict[str, Decimal]]:
    """Display read for procurement venture positions from materialized rows."""
    if not procurement.agreement_id:
        return {}
    rows = (
        PartnerPositionReadModel.objects
        .filter(
            tenant_id=procurement.tenant_id,
            agreement_id=procurement.agreement_id,
            procurement=procurement,
            currency='UZS',
        )
    )
    return {row.partner_id: row.money_payload for row in rows}


def read_available_by_partner(agreement: InvestmentAgreement) -> dict[int, dict[str, Decimal]]:
    """Display read for agreement free capital by partner/currency."""
    rows = (
        PartnerPositionReadModel.objects
        .filter(
            tenant_id=agreement.tenant_id,
            agreement=agreement,
            procurement__isnull=True,
        )
    )
    available: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        available.setdefault(row.partner_id, {})[str(row.currency or 'UZS').upper()] = row.available
    return available


def rebuild_agreement_positions(agreement: InvestmentAgreement) -> None:
    """Rebuild all read-model rows for one agreement from Phase 3 sources."""
    with transaction.atomic():
        locked_agreement = InvestmentAgreement.objects.select_for_update().get(
            pk=agreement.pk,
            tenant_id=agreement.tenant_id,
        )
        computed_at = timezone.now()
        expected = canonical_partner_position_rows(locked_agreement)
        kept_ids: list[int] = []

        for (procurement_id, partner_id, currency), payload in expected.items():
            row, _ = PartnerPositionReadModel.all_objects.update_or_create(
                tenant_id=locked_agreement.tenant_id,
                agreement=locked_agreement,
                procurement_id=procurement_id,
                partner_id=partner_id,
                currency=currency,
                defaults={
                    **payload,
                    'computed_at': computed_at,
                    'deleted_at': None,
                },
            )
            kept_ids.append(row.pk)

        stale = PartnerPositionReadModel.all_objects.filter(
            tenant_id=locked_agreement.tenant_id,
            agreement=locked_agreement,
        )
        if kept_ids:
            stale = stale.exclude(pk__in=kept_ids)
        stale.delete()
    # E20 fund member positions are a materialized projection of the holder's
    # E18 rows. Rebuild after the agreement transaction is complete.
    from .fund_services import rebuild_fund_positions_for_agreement
    rebuild_fund_positions_for_agreement(agreement)


def rebuild_procurement_agreement_positions(procurement: Procurement) -> None:
    if procurement.agreement_id:
        rebuild_agreement_positions(procurement.agreement)
