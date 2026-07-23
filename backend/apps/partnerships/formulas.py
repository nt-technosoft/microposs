"""Shared Musharaka/Mudaraba calculation helpers.

Keep the capital -> profit formula here so receive, sales, reports and risk
flows use one source of truth.
"""

from decimal import Decimal

from .money_utils import ZERO, money, ratio


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


def calculate_lot_profit_distribution(
    *,
    contract_snapshot: dict | None,
    unit_price: Decimal | str | int | float,
    quantity: int | Decimal | str,
    unit_landed_cost: Decimal | str | int | float,
) -> dict[str, str]:
    """Compute sale profit distribution from one lot/batch snapshot."""

    gross = (
        Decimal(str(unit_price)) - Decimal(str(unit_landed_cost))
    ) * Decimal(str(quantity))
    return distribute_profit_from_snapshot(
        contract_snapshot=contract_snapshot,
        gross_profit=gross,
    )


def calculate_profit_distribution(
    *,
    lot,
    unit_price: Decimal | str | int | float,
    quantity: int | Decimal | str,
    unit_landed_cost: Decimal | str | int | float,
) -> dict[str, str]:
    """Compatibility-shaped helper for callers that already have a Lot."""

    return calculate_lot_profit_distribution(
        contract_snapshot=getattr(lot, 'contract_snapshot', None),
        unit_price=unit_price,
        quantity=quantity,
        unit_landed_cost=unit_landed_cost,
    )


def calculate_sale_realization_distribution(
    *,
    contract_snapshot: dict | None,
    sale_proceeds: Decimal | str | int | float,
    cost_basis: Decimal | str | int | float,
) -> dict[str, dict[str, str]]:
    """Split one realized sale slice into capital recovery, provisional P&L.

    Sale realization is not final venture settlement. It records the economic
    fact that inventory capital has been converted into sale proceeds and,
    depending on proceeds vs cost, either provisional profit or loss appeared.
    """

    proceeds = money(sale_proceeds)
    cost = money(cost_basis)
    snapshot = contract_snapshot or {}
    partners = snapshot.get('partners') or []
    if proceeds <= 0 or cost <= 0 or not partners:
        return {}

    recovered_total = min(proceeds, cost)
    provisional_profit_total = max(ZERO, proceeds - cost)
    loss_total = max(ZERO, cost - proceeds)

    profit_distribution = distribute_profit_from_snapshot(
        contract_snapshot=contract_snapshot,
        gross_profit=provisional_profit_total,
    )
    loss_distribution = distribute_loss_by_capital_from_snapshot(
        contract_snapshot=contract_snapshot,
        loss_amount=loss_total,
    )

    result: dict[str, dict[str, str]] = {}
    operator = next((p for p in partners if p.get('role') == 'OPERATOR'), None)
    recovered_distributed = ZERO

    for partner in partners:
        partner_id = partner.get('partner_id')
        if partner_id is None:
            continue
        partner_key = str(partner_id)
        capital_share = Decimal(str(partner.get('capital_share', '0')))
        capital_recovered = money(recovered_total * capital_share)
        recovered_distributed += capital_recovered
        result[partner_key] = {
            'capital_recovered': str(capital_recovered),
            'provisional_profit': str(Decimal(str(profit_distribution.get(partner_key, '0')))),
            'loss': str(Decimal(str(loss_distribution.get(partner_key, '0')))),
        }

    if operator is not None:
        residue = money(recovered_total - recovered_distributed)
        if residue:
            operator_key = str(operator['partner_id'])
            row = result.setdefault(operator_key, {
                'capital_recovered': '0.00',
                'provisional_profit': '0.00',
                'loss': '0.00',
            })
            row['capital_recovered'] = str(
                money(Decimal(str(row['capital_recovered'])) + residue),
            )

    return {
        partner_id: values
        for partner_id, values in result.items()
        if any(Decimal(str(amount)) != 0 for amount in values.values())
    }


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
