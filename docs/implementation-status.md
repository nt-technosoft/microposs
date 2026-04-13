# MicroPOS — Implementation Status

**Snapshot date:** 2026-04-13  
**Branch:** `codex/bootstrap`  
**Source of truth:** codebase + `AGENTS.md` + this status file

## Module Matrix

| Area | Scope | Status | Notes |
|---|---|---|---|
| Auth | JWT login/refresh | `Implemented` | Token endpoints work; local demo users provisioned. |
| Sales | Catalog, cart, checkout, history | `Partial` | Core flow работает; требуется полноформатный UI smoke + сессионный UX polishing. |
| Products | list/create/edit/categories | `Implemented` | API + views рабочие; create/edit/list verified. |
| Intake | list/create/detail/confirm | `Implemented` | Create+confirm smoke passed, lot creation verified. |
| Reports | Dashboard + date filters + debt/cash blocks | `Implemented` | Frontend contract aligned with backend finance payloads. |
| More | Customers/Suppliers/Settings | `Implemented` | CRUD/pay flows доступны, состояния empty/error/loading есть. |
| Investors | Dashboard + contract detail | `Implemented` | Investor-only data endpoints return seeded data. |
| Routing | Main routes + simple seller restrictions | `Implemented` | Frontend role-guard closed via `/api/v1/auth/me` + route `meta.roles` checks. |
| Backend schema | Domain migrations | `Implemented` | Initial migrations generated for all business apps. |
| Demo data | Seed/bootstrap | `Implemented` | Added idempotent `bootstrap_demo` command. |
| Backend quality gate | warnings + smoke tests | `Implemented` | Decimal/pagination warnings removed, smoke tests added and passing. |

## Closed In Current Iteration

1. Resolved backend access blockers for current auth model:
   - role fallback via Django groups + owner/superuser detection,
   - tenant fallback via owner business / investor profile / header / single-tenant dev fallback.
2. Added deterministic local bootstrap command:
   - creates users, role groups, tenant, baseline product/intake/sale, finance summary, investor summary.
3. Aligned frontend finance API adapter to backend contracts:
   - pagination-safe parsing,
   - mapping `daily-summaries` and `cash-flow`,
   - corrected trial-balance endpoint path.
4. Fixed broken cart navigation target:
   - removed dead `/sessions` route jump.
5. Closed frontend auth/role gap:
   - added backend endpoint `GET /api/v1/auth/me`,
   - implemented `fetchUser/ensureUserLoaded` in auth store,
   - enabled strict route guard based on `meta.roles`,
   - tightened bottom-nav fallback for unknown role.
6. Added startup source artifacts into repository:
   - `docs/source-inputs/MicroPOS_Claude_Code_Playbook.md`,
   - `docs/source-inputs/MicroPOS_BRD_v2.docx`,
   - `docs/source-inputs/README.md`.
7. Closed low-priority backend warning backlog:
   - converted Decimal serializer bounds to `Decimal(...)`,
   - fixed unordered pagination by adding default ordering for:
     `LocationViewSet`, `ProductVariantViewSet`, `ConsignmentAgreementViewSet`.
8. Added automated backend smoke tests:
   - `apps.core.tests.test_api_smoke` (auth context, read endpoints, critical write flow).

## Smoke Result (Local)

**Infra:** `redis + backend + frontend` started successfully.

### Route smoke (frontend)
- `/sales` -> `200`
- `/products` -> `200`
- `/intake` -> `200`
- `/reports` -> `200`
- `/customers` -> `200`
- `/suppliers` -> `200`
- `/settings` -> `200`
- `/investor` -> `200`

### API smoke (authenticated)
- Owner: products/categories/receipts/sessions/sales/customers/suppliers/reports -> `200` + non-empty counts.
- Investor: summaries/profit-records -> `200` + non-empty counts.

### Critical writes
- `POST /api/v1/catalog/products/` -> `201`
- `POST /api/v1/inventory/receipts/` -> `201`
- `POST /api/v1/inventory/receipts/{id}/confirm/` -> `200`
- `POST /api/v1/sales/sales/` -> `201`

## Remaining Work (Next Priority)

1. Full route-level UI smoke in browser session (manual checklist + screenshots).
2. Add frontend automated smoke (Playwright/Cypress) for auth + route guards + critical flow.
3. Keep backend API smoke in CI and expand with negative scenarios (validation, permissions, empty/error states).
