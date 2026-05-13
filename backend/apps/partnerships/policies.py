"""
Procurement policy layer for E07.

This module is intentionally framework-light: services and serializers can use
the same policy result before mutating procurement state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Procurement, ProcurementTerms


OWN_FUNDS = Procurement.FundingSource.OWN_FUNDS
PARTNERSHIP = Procurement.FundingSource.PARTNERSHIP
MUSHARAKA = 'MUSHARAKA'

PREPAID = ProcurementTerms.Type.PREPAID
PARTIAL = ProcurementTerms.Type.PARTIAL
DEFERRED = ProcurementTerms.Type.DEFERRED
INSTALLMENT = ProcurementTerms.Type.INSTALLMENT
CONSIGNMENT = ProcurementTerms.Type.CONSIGNMENT

OWN_FUNDS_SETTLEMENTS = (PREPAID, PARTIAL, DEFERRED, INSTALLMENT, CONSIGNMENT)
PARTNERSHIP_SETTLEMENTS = (PREPAID,)
SUPPLIER_REQUIRED_SETTLEMENTS = (PARTIAL, DEFERRED, INSTALLMENT, CONSIGNMENT)


@dataclass(frozen=True)
class ProcurementPolicyContext:
    """State facts needed to evaluate procurement workspace rules."""

    funding_source: str
    settlement_type: str | None = None
    status: str = Procurement.Status.OPEN
    has_supplier: bool = False
    has_investment_agreement: bool = False
    has_items: bool = False
    has_procurement_balance: bool = False
    has_capital_activity: bool = False
    has_payment_activity: bool = False
    has_receive_batches: bool = False
    has_installment_schedule: bool = False


@dataclass(frozen=True)
class ProcurementPolicyResult:
    """Policy output shared by backend validators and future workspace state."""

    funding_source: str
    normalized_funding_source: str
    allowed_settlements: tuple[str, ...]
    visible_sections: tuple[str, ...]
    required_sections: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    readiness: dict[str, bool]
    blocked_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        return not self.blocked_reasons


def normalize_funding_source(funding_source: str) -> str:
    """Map legacy funding labels to the E07 policy model."""

    if funding_source == MUSHARAKA:
        return PARTNERSHIP
    return funding_source


def allowed_settlements_for_funding(funding_source: str) -> tuple[str, ...]:
    funding = normalize_funding_source(funding_source)
    if funding == OWN_FUNDS:
        return OWN_FUNDS_SETTLEMENTS
    if funding == PARTNERSHIP:
        return PARTNERSHIP_SETTLEMENTS
    return ()


def evaluate_procurement_policy(context: ProcurementPolicyContext) -> ProcurementPolicyResult:
    funding = normalize_funding_source(context.funding_source)
    allowed_settlements = allowed_settlements_for_funding(context.funding_source)
    blocked: list[str] = []

    if not allowed_settlements:
        blocked.append('Unsupported funding source.')

    if context.funding_source == MUSHARAKA:
        blocked.append('MUSHARAKA is legacy-only; use PARTNERSHIP in new flows.')

    if context.settlement_type and context.settlement_type not in allowed_settlements:
        blocked.append(
            f'{funding} does not allow {context.settlement_type} settlement in MVP.',
        )

    if funding == OWN_FUNDS and context.has_procurement_balance:
        blocked.append('OWN_FUNDS must not use ProcurementBalance.')

    if funding == PARTNERSHIP:
        if not context.has_investment_agreement:
            blocked.append('PARTNERSHIP requires an InvestmentAgreement.')
        if not context.has_procurement_balance:
            blocked.append('PARTNERSHIP requires ProcurementBalance capital pool.')

    if (
        context.settlement_type in SUPPLIER_REQUIRED_SETTLEMENTS
        and not context.has_supplier
    ):
        blocked.append(f'{context.settlement_type} settlement requires supplier.')
    if context.settlement_type == INSTALLMENT and not context.has_installment_schedule:
        blocked.append('INSTALLMENT settlement requires payment schedule.')

    sections = ['overview', 'source', 'items_landed_cost', 'settlement', 'receive', 'history']
    required = ['source', 'items_landed_cost']
    if funding == PARTNERSHIP:
        sections.insert(4, 'capital')
        required.append('capital')
    if context.settlement_type:
        required.append('settlement')

    actions = _allowed_actions(context=context, normalized_funding=funding)
    readiness = {
        'source_ready': _source_ready(context, funding),
        'items_ready': context.has_items,
        'settlement_ready': _settlement_ready(context, allowed_settlements),
        'capital_ready': _capital_ready(context, funding),
        'payment_ready': not blocked,
        'receive_ready': not blocked,
    }

    return ProcurementPolicyResult(
        funding_source=context.funding_source,
        normalized_funding_source=funding,
        allowed_settlements=allowed_settlements,
        visible_sections=tuple(sections),
        required_sections=tuple(required),
        allowed_actions=actions,
        readiness=readiness,
        blocked_reasons=tuple(blocked),
    )


def validate_procurement_policy(context: ProcurementPolicyContext) -> ProcurementPolicyResult:
    result = evaluate_procurement_policy(context)
    if not result.is_valid:
        raise ValueError('; '.join(result.blocked_reasons))
    return result


def _source_ready(context: ProcurementPolicyContext, funding: str) -> bool:
    if funding == PARTNERSHIP:
        return context.has_investment_agreement
    if context.settlement_type in SUPPLIER_REQUIRED_SETTLEMENTS:
        return context.has_supplier
    return True


def _settlement_ready(
    context: ProcurementPolicyContext,
    allowed_settlements: tuple[str, ...],
) -> bool:
    if not context.settlement_type:
        return False
    if context.settlement_type not in allowed_settlements:
        return False
    if context.settlement_type == INSTALLMENT:
        return context.has_installment_schedule
    return True


def _capital_ready(context: ProcurementPolicyContext, funding: str) -> bool:
    if funding != PARTNERSHIP:
        return True
    return context.has_investment_agreement and context.has_procurement_balance


def _allowed_actions(
    *,
    context: ProcurementPolicyContext,
    normalized_funding: str,
) -> tuple[str, ...]:
    if context.status == Procurement.Status.CANCELLED:
        return ('view_history',)
    if context.status == Procurement.Status.CLOSED:
        return ('view_history',)
    if context.status == Procurement.Status.RECEIVED:
        return ('pay_supplier_payable', 'view_history')

    actions = ['edit_source', 'edit_items', 'pay', 'receive', 'view_history']
    if context.has_receive_batches:
        actions = ['pay', 'receive', 'amend_terms', 'view_history']
    elif context.has_payment_activity or context.has_capital_activity:
        actions = ['edit_items', 'pay', 'receive', 'view_history']

    if normalized_funding == PARTNERSHIP and 'pay' in actions:
        actions[actions.index('pay')] = 'pay_from_capital_pool'

    return tuple(actions)
