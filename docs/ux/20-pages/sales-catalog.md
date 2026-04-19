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
- product catalog store
- current session state
- cart store
