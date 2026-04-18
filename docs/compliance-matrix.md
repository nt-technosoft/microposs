# MicroPOS — Invariant Compliance Matrix

**Snapshot:** 2026-04-14  
**Scope:** Architecture Hardening Program (Sprint 1)

| # | Invariant (`AGENTS.md`) | Status | Evidence |
|---|---|---|---|
| 1 | Products appear only through Receipt (except initial inventory) | `Partial` | Service flow uses `confirm_receipt -> Lot` creation; no dedicated negative API test yet for non-receipt stock bootstrap path |
| 2 | `Receipt.status=confirmed` is immutable | `Verified` | `confirm_receipt()` guard + `ImmutableRecordError`; covered in receipt confirm flow tests |
| 3 | `SaleLine` references `Lot` (not ProductVariant directly) | `Verified` | `sales/services.py:create_sale()` always resolves lot allocations and persists `SaleLine.lot` |
| 4 | FIFO lot selection by default | `Verified` | `inventory/services.py:get_lots_for_sale()` orders by `receipt__date`; exercised in sale service flow |
| 5 | `sum(profit_ratio participants) == 1.0` | `Verified` | `validate_participant_ratios()` invoked on Mudaraba/Musharaka confirm |
| 6 | `capital_ratio` auto-recalculated from `capital_amount` | `Verified` | `confirm_receipt()` recomputes and stores `capital_ratio` for participants |
| 7 | Credit sale requires `customer_id` | `Verified` | `CreditSaleRequiresCustomerError` in `create_sale()` |
| 8 | Investor contract closes only if no active lots remain | `Verified` | `close_investor_contract()` now checks contract-scoped receipts/lots |
| 9 | Moving lot changes location only | `Verified` | `transfer_lot()` moves/splits quantity without participant/share mutation |
| 10 | JournalEntry auto-created for every financial operation | `Partial` | Added tests for receipt/sale/return/customer payment/supplier payment/writeoff (`test_financial_integrity.py`) |
| 11 | Significant operations write OutboxEvent | `Partial` | Event coverage expanded (`sale.completed`, `receipt.confirmed`, `lot.transfer`, `pos_session.*`, `customer.payment`, `supplier.payment`, `risk.writeoff`) + tests for key flows |
| 12 | Physical `delete()` forbidden for Sale/Receipt/JournalEntry/Lot | `Partial` | Soft-delete pattern in models; no explicit regression test for every listed model yet |

## Test Evidence

- `backend/apps/core/tests/test_financial_integrity.py`
- `backend/apps/core/tests/test_role_matrix.py`
- `backend/apps/core/tests/test_api_smoke.py`

## Open Items

1. Add explicit negative tests for invariant #1 and #12.
2. Add immutable-update negative tests for confirmed/completed entities.
3. Add outbox-consumer assertion tests for analytics dispatch side effects.
