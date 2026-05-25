"""Single source of truth for procurement obligation cost calculations.

Design invariants (see docs/architecture.md — Currency Discipline):
- Obligation amounts are always in the items' own currency. NO × fx.
- fx_rate exists only for UZS reporting/analytics (procurement_cost_uzs_for_reporting).
- Mixed-currency items raise ValueError — caller / save-time validation owns that.
- CANCELLED and RECEIVED items are excluded from obligation cost.
"""
from __future__ import annotations

from decimal import Decimal


def procurement_cost_by_currency(items, expenses) -> dict[str, Decimal]:
    """Single source of truth: obligation cost grouped by currency.

    Σ(qty × unit_purchase_price) for items + Σ(amount) for expenses,
    each in its own currency. No × fx. Caller passes ACTIVE lines
    (use active_procurement_lines to filter CANCELLED/RECEIVED).

    Returns: {'USD': Decimal('100.00')} or {'UZS': Decimal('1200000.00')}
    """
    CENT = Decimal('0.01')
    totals: dict[str, Decimal] = {}
    for it in items:
        cur = str(it.currency or 'UZS').upper()
        amount = Decimal(str(it.quantity)) * Decimal(str(it.unit_purchase_price))
        totals[cur] = totals.get(cur, Decimal('0')) + amount
    for ex in expenses:
        cur = str(ex.currency or 'UZS').upper()
        totals[cur] = totals.get(cur, Decimal('0')) + Decimal(str(ex.amount))
    return {c: v.quantize(CENT) for c, v in totals.items()}


def active_procurement_lines(procurement) -> tuple[list, list]:
    """Return (items, expenses) filtered to ACTIVE (non-CANCELLED, non-RECEIVED).

    Use as the standard input to procurement_cost_by_currency for any
    obligation-facing calculation.
    """
    items = [
        i for i in procurement.items.all()
        if i.lifecycle_state not in ('CANCELLED', 'RECEIVED')
    ]
    expenses = [
        e for e in procurement.expenses.all()
        if e.lifecycle_state not in ('CANCELLED', 'RECEIVED')
    ]
    return items, expenses


def procurement_cost_uzs_for_reporting(items, expenses) -> Decimal:
    """UZS-equivalent cost for REPORTING ONLY — analytics, dashboards, UZS ledger display.

    NOT for obligation amounts, NOT for payment coverage checks that compare
    against same-currency payments. Multiplies by fx_rate — result is an
    approximate UZS equivalent, not the contractual obligation.
    """
    CENT = Decimal('0.01')
    item_total = sum(
        Decimal(str(it.quantity)) * Decimal(str(it.unit_purchase_price)) * Decimal(str(it.fx_rate))
        for it in items
    )
    expense_total = sum(
        Decimal(str(ex.amount)) * Decimal(str(ex.fx_rate))
        for ex in expenses
    )
    return (item_total + expense_total).quantize(CENT)
