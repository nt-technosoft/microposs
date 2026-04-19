# SCN-CSH-001 / POS Session and Sales Catalog

## Route
- `/sales`

## Roles
- owner
- cashier

## Goal
Дать максимально быстрый вход в ежедневный sales flow: открыть/продолжить смену, найти товар, начать продажу.

## Primary actions
- увидеть текущую POS session state
- искать товары
- выбирать категории
- открывать product detail
- добавлять товар в cart

## Key UI sections
- session status header
- search input
- category chips
- product list/grid
- floating cart entry point

## Mandatory states
- loading
- empty catalog
- search empty state
- error
- forbidden

## Critical UX requirements
- mobile-first скорость важнее информационной плотности
- search и category filters должны быть доступны сразу
- cart entry point должен оставаться заметным, но не мешать каталогу

## Dependencies
- `/api/v1/sales/sessions/`
- `/api/v1/catalog/products/`
- `/api/v1/catalog/categories/`
- cart state/store

## Acceptance criteria
- session header reflects open/closed session state from backend
- catalog list renders deterministically for owner/cashier and hides owner-only admin controls
- search/filter interactions never block cart entry point visibility when cart has items
- forbidden/error states are explicit and recoverable (retry or back navigation)

## Open decision
- Exact POS session auto-open UX policy (manual open vs implicit open) remains to be finalized against backend workflow.
