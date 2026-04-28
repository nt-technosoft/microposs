"""Shared Musharaka/Mudaraba calculation helpers.

Keep the capital -> profit formula here so receive, sales, reports and risk
flows use one source of truth.
"""

from decimal import Decimal


ZERO = Decimal('0')
MONEY_Q = Decimal('0.01')
RATIO_Q = Decimal('0.000001')


def money(amount: Decimal | str | int | float) -> Decimal:
    return Decimal(str(amount)).quantize(MONEY_Q)


def ratio(amount: Decimal | str | int | float) -> Decimal:
    return Decimal(str(amount)).quantize(RATIO_Q)


def profit_shares_from_capital(
    partners_meta: list[dict],
    mudaraba_ratio: Decimal | str | int | float,
) -> dict[int, Decimal]:
    """Derive partner profit shares from capital shares.

    Formula:
      investor_profit_share = investor_capital_share * mudaraba_ratio
      operator_profit_share = operator_capital_share
        + (1 - mudaraba_ratio) * sum(investor_capital_shares)
    """

    mudaraba = Decimal(str(mudaraba_ratio))
    investor_capital_total = sum(
        (
            Decimal(str(partner.get('capital_share', '0')))
            for partner in partners_meta
            if partner.get('role') == 'INVESTOR'
        ),
        ZERO,
    )
    operator = next(
        (partner for partner in partners_meta if partner.get('role') == 'OPERATOR'),
        None,
    )

    result: dict[int, Decimal] = {}
    for partner in partners_meta:
        partner_id = int(partner['partner_id'])
        capital_share = Decimal(str(partner.get('capital_share', '0')))
        role = partner.get('role')
        if role == 'INVESTOR':
            share = capital_share * mudaraba
        elif role == 'OPERATOR':
            share = capital_share + ((Decimal('1') - mudaraba) * investor_capital_total)
        else:
            share = ZERO
        result[partner_id] = ratio(share)

    if operator is not None:
        distributed = sum(result.values(), ZERO)
        residue = ratio(Decimal('1') - distributed)
        if residue:
            operator_id = int(operator['partner_id'])
            result[operator_id] = ratio(result.get(operator_id, ZERO) + residue)

    return result


def distribute_profit_from_snapshot(
    *,
    contract_snapshot: dict | None,
    gross_profit: Decimal | str | int | float,
) -> dict[str, str]:
    """Distribute gross profit by the lot/batch contract snapshot."""

    gross = money(gross_profit)
    if gross <= 0:
        return {}

    snapshot = contract_snapshot or {}
    partners = snapshot.get('partners') or []
    if not partners:
        return {}

    operator = next((p for p in partners if p.get('role') == 'OPERATOR'), None)
    fallback_profit_shares = (
        {}
        if all('profit_share' in partner for partner in partners)
        else profit_shares_from_capital(partners, Decimal(str(snapshot.get('mudaraba_ratio', '0'))))
    )

    result: dict[str, str] = {}
    for partner in partners:
        partner_id = partner.get('partner_id')
        if partner_id is None:
            continue
        profit_share = Decimal(str(
            partner.get('profit_share', fallback_profit_shares.get(int(partner_id), ZERO)),
        ))
        share = money(gross * profit_share)
        if share != 0:
            result[str(partner_id)] = str(share)

    if operator is not None:
        distributed = sum((Decimal(value) for value in result.values()), ZERO)
        residue = money(gross - distributed)
        if residue:
            operator_id = str(operator['partner_id'])
            current = Decimal(result.get(operator_id, '0'))
            result[operator_id] = str(money(current + residue))

    return result


def distribute_loss_by_capital_from_snapshot(
    *,
    contract_snapshot: dict | None,
    loss_amount: Decimal | str | int | float,
) -> dict[str, str]:
    """Distribute loss/risk by capital shares."""

    loss = money(loss_amount)
    if loss <= 0:
        return {}

    snapshot = contract_snapshot or {}
    partners = snapshot.get('partners') or []
    result: dict[str, str] = {}
    operator = next((p for p in partners if p.get('role') == 'OPERATOR'), None)

    for partner in partners:
        partner_id = partner.get('partner_id')
        if partner_id is None:
            continue
        share = money(loss * Decimal(str(partner.get('capital_share', '0'))))
        if share != 0:
            result[str(partner_id)] = str(share)

    if operator is not None:
        distributed = sum((Decimal(value) for value in result.values()), ZERO)
        residue = money(loss - distributed)
        if residue:
            operator_id = str(operator['partner_id'])
            current = Decimal(result.get(operator_id, '0'))
            result[operator_id] = str(money(current + residue))

    return result
