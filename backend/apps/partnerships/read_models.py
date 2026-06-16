from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import InvestmentAgreement, PartnerPositionReadModel, Procurement

_CENT = Decimal('0.01')
_ZERO = Decimal('0.00')


def _money(value) -> Decimal:
    return Decimal(str(value or _ZERO)).quantize(_CENT)


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


def canonical_partner_position_rows(
    agreement: InvestmentAgreement,
) -> dict[tuple[int | None, int, str], dict[str, Decimal]]:
    """Fold the current three canonical nodes into the Phase 3 read-model shape."""
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


def rebuild_procurement_agreement_positions(procurement: Procurement) -> None:
    if procurement.agreement_id:
        rebuild_agreement_positions(procurement.agreement)
