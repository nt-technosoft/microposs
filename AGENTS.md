# MicroPOS — Agent Instructions

## Overview
MicroPOS — mobile-first POS platform for small retail businesses with Islamic partnership financing (Mudaraba, Musharaka), consignment trading, and multi-location inventory.

**Full documentation:** `docs/README.md` → links to all domain docs.

## Quick Reference

### Where to find business logic
| Domain | Backend service | Frontend module |
|---|---|---|
| Inventory / Lots / FIFO | `apps/inventory/services.py` | `src/modules/inventory/` |
| Procurement / Receipt | `apps/partnerships/services.py` | `src/modules/intake/` |
| Sales / POS / Returns | `apps/sales/services.py` | `src/modules/sales/` |
| Finance / Accounting | `apps/finance/services.py` | `src/modules/finance/` |
| Partnerships / Profit | `apps/partnerships/services.py` | `src/modules/investors/` |
| Customers / Debt | `apps/customers/services.py` | — |
| Suppliers / Payables | `apps/suppliers/services.py` | — |
| Reporting | `apps/finance/views.py` | `src/modules/reports/` |
| Async aggregation | `apps/analytics/tasks.py` | — |

### Key files
- `backend/apps/finance/views.py` — combined report endpoints, profitability views, caching
- `backend/apps/analytics/tasks.py` — OutboxEvent processing, DailySummary aggregation
- `frontend/src/modules/reports/views/ReportsDashboard.vue` — main reporting screen
- `frontend/src/api/finance.ts` — typed finance API client
- `frontend/src/router/index.ts` — auth guard + role routing

### Running tests
```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/core/tests/ -q
```
All 108 tests should pass.

## Architecture
- **Monorepo**: `backend/` (Django) + `frontend/` (Vue.js 3)
- **Backend**: Python 3.12 / Django 5.x / DRF / PostgreSQL 16 / Redis / Celery
- **Frontend**: Vue.js 3 + TypeScript + Pinia + Vue Router + Vite

## Key Business Rules (NEVER violate)
1. Products appear ONLY through Procurement / Receipt (except initial inventory)
2. Receipt.status = confirmed → immutable forever
3. SaleLine always references Lot (not ProductVariant directly) — one SaleLine per FIFO lot-slice
4. FIFO by default: ordered by (lot.received_at, lot.id)
5. sum(profit_ratio of all participants) == 1.0
6. capital_ratio is auto-calculated from capital_amount
7. Credit sale requires customer_id
8. InvestorContract closes only if no active Lots remain
9. Moving Lot changes only location, not participants/shares
10. JournalEntry created automatically for every financial operation
11. All significant operations write OutboxEvent
12. Physical delete() forbidden for Sale, Receipt, JournalEntry, Lot

## Backend Conventions
- All models inherit `core.BaseModel` (soft-delete, timestamps)
- Domain apps don't import each other's models for business logic
- Cross-domain communication: services layer + OutboxEvent
- ForeignKey across domains is allowed
- Service layer pattern: `services.py` in each app
- All POST endpoints for financial ops accept `client_request_id` (idempotency)
- Multi-tenant: `tenant_id` on all business data models
- Immutable financial records after confirmed/completed status
- `CELERY_TASK_ALWAYS_EAGER=True` in development settings — tasks run synchronously in dev/test

## Frontend Conventions
- Mobile-first, responsive (375px → 768px → 1024px → 1440px)
- Vue 3 Composition API + `<script setup>` syntax
- Pinia stores per domain
- API layer in `src/api/` with typed clients
- Components: `src/components/` (shared) + `src/modules/<domain>/components/`
- Design tokens in CSS custom properties
- Lucide icons (no emojis as structural icons)
- All animations 150-300ms, respect prefers-reduced-motion
- AbortController pattern for all data-loading functions; cancel in onBeforeUnmount
- Debounce 300ms on currency switches and search inputs

## Important: Celery in dev/test
`CELERY_TASK_ALWAYS_EAGER=True` is set in `config/settings/development.py`. This means all `.delay()` calls execute synchronously — no Celery worker needed in development. Tests rely on this behaviour.

## Vacuum Rework Note
- Frontend migration: reuse foundation, rewrite feature-domain.
- `Receipt` is being replaced by `Procurement` in product and UX terminology.
- PR-12 (Excel mapping) is a separate track, not a default continuation.
