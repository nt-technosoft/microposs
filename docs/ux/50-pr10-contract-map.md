# PR-10 Contract Map

## Purpose
Зафиксировать точную карту изменений для frontend `types / api / stores` перед реализацией PR-10, чтобы migration была controlled, а не хаотичной.

## Foundation to preserve
- `frontend/src/api/client.ts` — как transport foundation с JWT/refresh идеей, но с возможной последующей чисткой side effects.
- `frontend/src/stores/auth.ts` — как auth/session access backbone.
- `frontend/src/stores/session.ts` — как session foundation.
- `frontend/src/stores/ui.ts` — как theme/locale/layout foundation.

Note: frontend is intentionally wiped; this section defines what to reconstruct first, not what to patch in-place.

## High-priority rewrite targets
### Types
Current legacy hotspots:
- `ReceiptType`, `ReceiptStatus`, `PaymentMethod`, `ContractType`, `ContractStatus`, `ReturnCondition` in `frontend/src/types/enums.ts`
- `Location`, `Receipt`, `ReceiptLine`, `ReceiptParticipant`, `InvestorSummary`, old `Sale` and `Customer` shapes in `frontend/src/types/models.ts`

PR-10 direction:
- replace `Receipt*` with `Procurement*`
- replace `Location` with `Warehouse` semantics
- replace single `payment_method` sale model with nested `SalePayment[]`
- replace scalar customer debt assumption with `Receivable` / `ReceivableEntry`
- replace investor summary-era types with `PartnerLedgerEntry`, aggregates, procurement participation

### API
Current legacy hotspots:
- `frontend/src/api/sales.ts` assumes `payment_method` on sale payload and legacy return payload
- `frontend/src/api/investors.ts` assumes `summaries` / `profit-records` endpoints as primary investor contract
- `frontend/src/api/customers.ts` assumes scalar debt-summary and payment flow only
- `frontend/src/api/inventory.ts` assumes `locations` and old lot/location shapes

PR-10 direction:
- update `sales.ts` to multi-payment payloads and newer sale shape
- add `partnerships.ts` for procurements/contracts/balance/contributions/withdrawals/receive
- introduce `cash.ts` for cash accounts / fx / exchange / refunds where needed
- evolve customer API around receivable drill-down
- keep inventory API focused on lots/stock/warehouses, not as intake source of truth

### Stores
Current rewrite targets:
- `frontend/src/stores/cart.ts` — needs warehouse-aware sale context and payment-aware checkout prep
- `frontend/src/stores/sales.ts` — needs sale shape + return flow updates
- missing dedicated `partnerships.ts`
- likely need customer receivable-oriented state

Keep with light adaptation:
- `auth.ts`
- `session.ts`
- `ui.ts`

## Suggested implementation order
1. enums + domain model interfaces
2. `api/partnerships.ts` and `api/sales.ts`
3. `api/customers.ts`, `api/investors.ts`, `api/inventory.ts`
4. `stores/partnerships.ts`
5. `stores/cart.ts` + `stores/sales.ts`
6. then contract pass over screens to identify PR-11 breakpoints

## Non-negotiable invariants to reflect in contracts
- sale from one warehouse
- credit requires customer
- receive requires zero procurement balance
- return resolution is RESTOCK or DISPOSE with distinct downstream meaning
- investor-facing read model must come from ledger/procurement participation, not old summary abstraction
