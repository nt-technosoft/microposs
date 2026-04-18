# MicroPOS — Role Matrix (Source of Truth)

**Snapshot:** 2026-04-14  
**Authority:** `AGENTS.md` + BRD

## Role Scope

| Role | Product Scope | Access Rule |
|---|---|---|
| `owner` | Full platform | Full access across all domain groups |
| `cashier` | Sales workflow | Sales + sales-required reference data only |
| `warehouse` | Intake/stock workflow | Inventory + stock + intake-required catalog read |
| `investor` | Investor cabinet | Investor summaries/profit records only |

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
