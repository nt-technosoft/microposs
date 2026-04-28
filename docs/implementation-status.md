# MicroPOS — Implementation Status

**Snapshot date:** 2026-04-27  
**Branch:** `vacuum-rework`  
**Hardening track:** Vacuum backend + clean-slate frontend restart

## Current Reality

- Frontend has been intentionally reset and rebuilt from a fresh scaffold.
- Backend Phase D audit follow-up is in progress.
- Docs in this file are a legacy snapshot and should be interpreted through the current vacuum-model/backend cleanup context, not the old `codex/bootstrap` pass.

## Current Pass: Phase D backend cleanup + frontend clean-slate bootstrap

| Scope | Status | Notes |
|---|---|---|
| Frontend scaffold | `Implemented` | New Vue/Vite foundation, canonical P0 routes, base stores, UI primitives, placeholder screens, green build/test |
| Analytics/outbox crashers | `Implemented` | Legacy analytics task paths retired/hardened; outbox consumer now safer against duplicate processing and silent drops |
| Sale credit receivable accrual | `Implemented` | Credit sale now accrues receivable and is covered by regression test |
| Sale cash/journal wiring | `Implemented` | Cash-linked sale paths now create cash entries and accounting side effects in current tested flows |
| Reporting read-models | `Implemented` | Sales/product/procurement profitability, investor capital-state, and reconciliation summary endpoints are live |
| Reporting / transparency UI | `Partial` | Owner reports, reconciliation view, sale explanation, and investor capital-state screens are live; deeper procurement/investor drill-down remains |
| Tenant/role hardening | `Partial` | Tenant selection and tenant-first role resolution improved; broader multi-tenant regression expansion still pending |
| Immutability/delete hardening | `Partial` | Core finalized-record protections improved; broader regression coverage still pending |
| Legacy docs alignment | `In progress` | Role matrix/compliance/frontend architecture are being brought to current vacuum state; reporting/audit docs still catching up to newer UI/API work |

## Gate Progress

| Gate | Status | Notes |
|---|---|---|
| Gate A (backend invariants + finance/outbox) | `In progress` | Major crashers and key financial defects reduced; more cleanup remains |
| Gate B (role matrix API) | `In progress` | Investor route matrix updated to current bridge routes; broader role policy cleanup remains |
| Gate C (frontend build/type + contract alignment) | `Done` | New clean-slate scaffold builds and tests green |
| Gate D (full regression + final compliance report) | `In progress` | Audit follow-up still actively landing |

## Evidence (Current)

- `backend/apps/core/tests/test_sale_multi_payment.py`
- `backend/apps/core/tests/test_sale_credit_integrity.py`
- `backend/apps/core/tests/test_returns_shariah.py`
- `backend/apps/core/tests/test_role_matrix.py`
- `backend/apps/core/tests/test_finance_bridge_api.py`
- `backend/apps/core/tests/test_investor_bridge_api.py`
- `backend/apps/core/tests/test_partnerships_api.py`
- Frontend gate: `frontend npm test` and `frontend npm run build` (green)

## Legacy Snapshot Below

## Current Pass: Products/Categories/Pricing/Sales Cart

| Scope | Status | Notes |
|---|---|---|
| Product photo | `Implemented` | Added product photo field + upload/remove API contract + frontend create/edit support |
| Category templates | `Partial` | Added UI/API for template attributes/characteristics and apply-settings; requires final UX polishing |
| Product create/edit flow | `Partial` | Unified around pricing mode + description + characteristics + photo; variant UX improved, deep variant editor still pending |
| Sales pricing-mode flow | `Partial` | Backend now enforces pricing policy + discount reason rules; frontend applies price-mode behavior in ProductDetail |
| Discount reason propagation | `Implemented` | Cart/checkout now sends `discount_reason_id`; backend resolves default `Торг` when price changed |
| Location-aware variant stock | `Implemented` | Added location-aware stock context in product/variant serializers and sales screens |

## Gate Progress

| Gate | Status | Notes |
|---|---|---|
| Gate A (backend invariants + finance/outbox) | `Done` | Added financial/outbox integrity tests and service hardening for contract-scoped investor logic |
| Gate B (role matrix API) | `Done` | Added role-matrix tests for `owner/cashier/warehouse/investor`; aligned permissions |
| Gate C (frontend build/type + contract alignment) | `Done` | Frontend build green after pagination-safe adapters and session/cart flow fixes |
| Gate D (full regression + final compliance report) | `In progress` | Compliance matrix added; full negative regression expansion remains |

## Module Matrix

| Area | Scope | Status | Notes |
|---|---|---|---|
| Auth | JWT + role context | `Implemented` | `auth/me` used as runtime role source |
| Sales | Catalog/cart/checkout/history | `Partial` | Runtime guard fixes merged; full e2e scenario pack still pending |
| Products | list/create/edit/categories | `Implemented` | Role/access and API contracts aligned |
| Intake | list/create/detail/confirm | `Partial` | Role-safe financing flow fixed for warehouse; participant validation polish remains |
| Reports | dashboard/read models | `Implemented` | Build/type passes and endpoints aligned |
| More | Customers/Suppliers/Settings | `Implemented` | Core flows available, permissions aligned |
| Investors | cabinet + contracts | `Partial` | Contract-scoped aggregation fixed; broader owner-side workflows pending |
| Role model | backend + frontend guards | `Implemented` | See `docs/role-matrix.md` |
| Compliance docs | invariant evidence | `Implemented` | See `docs/compliance-matrix.md` |

## Completed In This Iteration

1. Backend invariants hardening:
   - sale/receipt/return/payment/writeoff financial journaling verified by tests,
   - outbox coverage expanded to key operation events,
   - investor aggregation and contract-close checks moved to contract-scoped logic.
2. Role model hardening:
   - introduced warehouse demo user (`bootstrap_demo`),
   - aligned read/write permissions with role matrix,
   - added API positive/negative role tests.
3. Frontend contract alignment:
   - pagination-safe adapters for catalog/inventory/sales/investors/risk/analytics/customers/suppliers,
   - fixed risk API path mismatches,
   - centralized POS session preloading in router for sales roles,
   - fixed cart visibility guard on cart/checkout paths,
   - added defensive guard for add-to-cart event payload.
4. Products + Intake UX hardening (post-review):
   - replaced native selects with sheet-based `BaseSelect` across product/intake screens to remove broken popup anchoring,
   - improved intake item picker: full variant browse by default + category chips + search by name/SKU/attributes,
   - standardized SKU fallback (`display_sku`) backend/frontend so empty SKU no longer blocks operations,
   - expanded product edit form to include category, pricing mode, and description (not only name/price/active),
   - surfaced SKU in product list and intake lines for operator visibility,
   - fixed `warehouse` intake bootstrap by splitting reference loading (locations no longer blocked by 403 on suppliers/investors),
   - limited warehouse financing types in intake form to allowed operational flow (`Свои деньги`).
5. Role-support UX update:
   - opened `/settings` route for `investor`,
   - added settings entry action in investor cabinet header for language/theme/logout access.
6. Dev auth stability hardening:
   - incident root cause confirmed: PostgreSQL connection exhaustion (`too many clients already`) caused `500` on `/api/v1/auth/token/`,
   - `development` settings now force non-persistent DB connections (`CONN_MAX_AGE=0`) with health checks enabled,
   - operational rule fixed: run exactly one backend `runserver` process in local dev,
   - canonical local backend start: `backend/run_devserver.sh` (with autoreload enabled, never `--noreload` for partial receive checks).

## Excel Alignment (Iteration 1)

| Scope | Status | Notes |
|---|---|---|
| Canonical source model docs | `Implemented` | Added source model, sheet mapping, reconciliation spec, and gap backlog docs |
| Staging import layer | `Implemented` | Added `ExcelImportBatch` + `ExcelImportRow` with row fingerprint, parse status, and money trace fields |
| Import pipeline command | `Implemented` | Added `excel_align_import` with modes: `dry-run`, `load-master`, `load-transactions`, `reconcile` |
| Primary events import | `Implemented` | Pipeline processes `MALUMOTLAR`, `SOTIB OLISH`, `STOCK TRANSFER`, `SOTUV`, `TUSHUM`, `XARAJAT`, `PUL AYRIBOSHLASH` |
| Reconciliation baseline | `Implemented` | Reconcile mode computes DB-based cash, stock, AR/AP, revenue, COGS, gross profit + expected deltas |
| Source of truth parity | `Partial` | Core operational logic covered; advanced report parity and optimizer backlog fixed in `docs/excel-gap-backlog.md` |

## Excel Alignment (Iteration 2)

| Scope | Status | Notes |
|---|---|---|
| Sandbox pilot runbook | `Implemented` | Added `excel_align_pilot` command (`dry-run -> load-master -> load-transactions(slice) -> reconcile`) |
| Gap-log categorization | `Implemented` | `ExcelImportRow.failure_category` now classifies failed rows (`parse/mapping/domain/other`) |
| AP lifecycle hardening | `Implemented` | Supplier credit accrual moved into `inventory.confirm_receipt` domain flow + outbox event `supplier.payable_accrued` |
| Expense first-class domain | `Implemented` | Added `finance.Expense` model/service/API and journal/outbox integration |
| Timestamp parity | `Implemented` | Expense, sale, receipt, customer/supplier payment flows preserve operation datetime in financial side-effects |
| Multi-currency trace in read models | `Implemented` | Added `operation_currency/operation_amount/fx_rate_snapshot/functional_amount_uzs` to receipt/sale/payment reads |
| Reconciliation owner endpoint | `Implemented` | Added `/api/v1/core/excel/reconciliation/latest/` with `computed/expected/deltas + gap_summary` |
| Frontend parity widgets | `Implemented` | Reports dashboard now shows KASSA/OMBOR/AR/AP operational cards + link to reconciliation view |
| Frontend FX/source visibility | `Implemented` | Added source+functional trace badges in Intake list and Sales history |
| Import posted-flag normalization | `Implemented` | Fixed Excel `POSTED=None` handling in importer (`None` treated as blank/posted by default), removed false transaction skips |
| FX history + official sync | `Implemented` | Added `finance.ExchangeRate`, owner API (`fx-rates` manual/refresh/latest), CBU sync command, and service-level snapshot resolver |

## Evidence (Automated)

- `backend/apps/core/tests/test_api_smoke.py`
- `backend/apps/core/tests/test_financial_integrity.py`
- `backend/apps/core/tests/test_role_matrix.py`
- Frontend gate: `npm run build` (green)

## Remaining Work

1. Expand invariant negatives (`delete` forbiddance, immutable update attempts, non-receipt stock injection).
2. Full manual/e2e role smoke for all critical screens and mobile overlap scenarios.
3. Finalize Gate D with consolidated regression + sign-off report.
