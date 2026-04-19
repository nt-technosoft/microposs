# SCN-OWN-007 / Products List

## Route
- `/products`

## Roles
- owner
- warehouse (read/operational variant)

## Goal
Управлять каталогом товаров и быстро находить нужный товар для администрирования или складской проверки.

## Primary actions
- search/filter products
- open product detail/edit
- create product (owner)
- inspect stock signal

## Key sections
- search/filter bar
- product cards/list
- create CTA
- category shortcuts

## Mandatory states
- loading
- empty list
- filtered empty
- error
- forbidden

## Dependencies
- `/api/v1/catalog/products/`
- `/api/v1/catalog/categories/`

## Acceptance criteria
- owner видит management actions
- warehouse variant не выглядит как кассовый каталог
- stock signal читается без открытия карточки
- non-owner попытка owner-action получает predictable forbidden UX state
- mobile 375px supports search + quick open without horizontal overflow

## Open decision
- Product create/edit remains P2 in restart sequence; exact inline-edit vs separate-page policy deferred.
