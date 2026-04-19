# MicroPOS — Role Matrix (Source of Truth)

**Snapshot:** 2026-04-14  
**Authority:** `AGENTS.md` + BRD

## Role Scope

| Role | Product Scope | Access Rule |
|---|---|---|
| `owner` | Full platform | Full access across all domain groups |
| `cashier` | Sales workflow | Sales + sales-required reference data only |
| `warehouse` | Procurements/stock workflow | Inventory + stock + procurements-required catalog read |
| `investor` | Investor cabinet | Investor dashboard + investor procurements read surface |

## Role Source of Truth

- Tenant selection is resolved into `request.tenant_id`.
- Tenant-scoped `Partner` membership is the primary role source inside a tenant.
- Django groups are legacy/bootstrap fallback only, not the preferred tenant authority.
- Frontend route guards must consume `GET /api/v1/auth/me/` with tenant-aware role context.

## Startup policy note

- `cashier` may read customers, but customer create/pay mutations remain owner-only until a separate policy change is approved.
- Canonical frontend route language is `/procurements/*`, not `/intake/*`.
- Canonical investor detail routes are `/investor/procurements/*`.

## Backend Endpoint Matrix

| Endpoint group | owner | cashier | warehouse | investor |
|---|:---:|:---:|:---:|:---:|
| `/api/v1/sales/*` | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/catalog/products/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/categories/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/variants/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/*` (write) | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/inventory/receipts/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/lots/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/stock/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/locations/*` read | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/locations/*` write | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/customers/*` read | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/customers/*` write/pay | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/suppliers/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/finance/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/analytics/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/investors/investors|contracts/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/investors/dashboard|procurements/*` | ❌ | ❌ | ❌ | ✅ |

## Verification

- Automated API role-matrix tests: `backend/apps/core/tests/test_role_matrix.py`.
- Frontend route guards use `meta.roles` and server role from `GET /api/v1/auth/me/`.
- Utility screen note: `/settings` is available to all authenticated roles (`owner/cashier/warehouse/investor`) for language/theme/session controls.

## Legacy note

- Older references to investor summaries/profit-records and `/intake/*` routes should be treated as legacy snapshots, not current frontend/backend targets.

## Backend Endpoint Matrix

| Endpoint group | owner | cashier | warehouse | investor |
|---|:---:|:---:|:---:|:---:|
| `/api/v1/sales/*` | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/catalog/products/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/categories/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/variants/*` (read) | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/catalog/*` (write) | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/inventory/receipts/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/lots/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/stock/*` | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/locations/*` read | ✅ | ❌ | ✅ | ❌ |
| `/api/v1/inventory/locations/*` write | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/customers/*` read | ✅ | ✅ | ❌ | ❌ |
| `/api/v1/customers/*` write/pay | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/suppliers/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/finance/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/analytics/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/investors/investors|contracts/*` | ✅ | ❌ | ❌ | ❌ |
| `/api/v1/investors/summaries|profit-records/*` | ❌ | ❌ | ❌ | ✅ |

## Verification

- Automated API role-matrix tests: `backend/apps/core/tests/test_role_matrix.py`.
- Frontend route guards use `meta.roles` and server role from `GET /api/v1/auth/me/`.
- Utility screen note: `/settings` is available to all authenticated roles (`owner/cashier/warehouse/investor`) for language/theme/session controls.
