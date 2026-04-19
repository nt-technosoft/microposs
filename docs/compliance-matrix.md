# MicroPOS — Invariant Compliance Matrix

**Snapshot:** 2026-04-14  
**Scope:** Architecture Hardening Program (Sprint 1)

| # | Invariant (`AGENTS.md`) | Status | Evidence |
|---|---|---|---|
| 1 | Products appear only through Receipt (except initial inventory) | `Partial` | Legacy docs still describe Receipt, but current vacuum flow is procurement receive -> lot creation; negative regression test for non-procurement stock injection still missing |
| 2 | Confirmed/received financial inventory records become immutable | `Partial` | `ImmutableMixin` now normalizes status checks, but broader regression coverage for all finalized statuses still needs expansion |
| 3 | `SaleLine` references `Lot` (not ProductVariant directly) | `Verified` | `backend/apps/sales/services.py:create_sale()` always allocates and stores `SaleLine.lot` |
| 4 | FIFO lot selection by default | `Verified` | `backend/apps/inventory/services.py:allocate_lot()` orders by lot receive chronology |
| 5 | `sum(profit_ratio participants) == 1.0` | `Partial` | Audit flagged missing procurement-side enforcement; explicit validation still needs confirmation/refinement |
| 6 | `capital_ratio` auto-recalculated from `capital_amount` | `Partial` | Legacy receipt participant path remains stale; procurement-side contract snapshot is current, but legacy field semantics remain debt |
| 7 | Credit sale requires `customer_id` | `Verified` | `CreditSaleRequiresCustomerError` plus receivable accrual regression in `backend/apps/core/tests/test_sale_credit_integrity.py` |
| 8 | Investor contract closes only if no active lots remain | `Partial` | Audit still flags legacy contract-close path dependence on receipt surfaces; needs follow-up cleanup |
| 9 | Moving lot changes location only | `Verified` | `backend/apps/inventory/services.py:transfer_lot_stock()` mutates only stock placement |
| 10 | JournalEntry auto-created for every financial operation | `Partial` | Sale credit path and cash-linked sale paths now covered, but procurement/dividend/full refund surface still needs follow-up wiring |
| 11 | Significant operations write OutboxEvent | `Partial` | Outbox writing is broad and consumer is safer, but more regression tests for consumer behavior and event coverage are still needed |
| 12 | Physical `delete()` forbidden for Sale/Receipt/JournalEntry/Lot | `Partial` | `Sale`, `JournalEntry`, and `Lot` now explicitly reject delete; receipt and queryset-level regressions still need broader verification |

## Test Evidence

- `backend/apps/core/tests/test_financial_integrity.py`
- `backend/apps/core/tests/test_role_matrix.py`
- `backend/apps/core/tests/test_api_smoke.py`

## Open Items

1. Add explicit negative tests for invariant #1 and #12.
2. Add immutable-update negative tests for confirmed/completed entities.
3. Add outbox-consumer assertion tests for analytics dispatch side effects.
