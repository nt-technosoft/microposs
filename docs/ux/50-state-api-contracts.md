# State and API Contracts

## Purpose
Слой связывает frontend stores / UI flows с backend contracts и помогает PR-10 не потерять доменную модель.

## Rules
- UI не должен зависеть от legacy `Receipt` / `InvestorSummary` / single-payment assumptions.
- Все draft states должны отражать новую доменную реальность: procurement, multi-payment, receivable, partner ledger, cash accounts.
- Любой critical submit flow должен иметь idempotent request strategy.

## PR-10 contract migration focus
- `types/models.ts`
- `types/enums.ts`
- `api/*.ts`
- `stores/*.ts`

## Core contract groups
- auth/session (`/api/v1/auth/token/`, `/api/v1/auth/me/`)
- partnerships / procurements
- inventory / lots / lot stock
- sales / sale lines / sale payments / returns
- customers / receivables / entries
- finance / cash / fx / refunds / journals
- investor / partner ledger / dividends

## Backend-aligned role notes (startup)
- Customers: cashier currently read-only, owner write/pay.
- Investor cabinet: canonical bridge is `/api/v1/investors/dashboard/` + `/api/v1/investors/procurements/*`.
- Procurement flows: canonical write/read is `/api/v1/partnerships/procurements/*`; legacy inventory receipts are not target procurement UX contract.

## Idempotency note (startup-critical)
- Include `client_request_id` for critical POST flows where backend supports it:
  - sales create (`/api/v1/sales/sales/`)
  - procurement create (`/api/v1/partnerships/procurements/`)
- Treat other financial POST actions as non-idempotent until backend contract explicitly adds `client_request_id`.
## Validation note
Если backend invariant влияет на UX, он должен быть явно отражён в page spec.
Примеры:
- credit sale requires customer
- receive requires zero balance
- sale happens from one warehouse
- return resolution changes downstream UX and financial impact
