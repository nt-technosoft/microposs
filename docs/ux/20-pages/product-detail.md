# SCN-CSH-002 / Product Detail

## Route
- `/sales/product/:id`

## Roles
- owner
- cashier

## Goal
Помочь быстро выбрать variant, цену и количество и добавить товар в cart без перегруза.

## Primary actions
- выбрать variant
- изменить цену if pricing mode allows
- указать quantity
- выбрать discount reason if price changed
- добавить в cart

## Key sections
- product header
- category / availability
- variant selector
- quantity control
- price editor
- add-to-cart CTA

## Critical invariants
- variant must be valid/available
- price rules must reflect pricing mode
- changed price requires discount reason when business rule says so

## Acceptance criteria
- add-to-cart path работает за минимальное количество действий
- unavailable variant не даёт ложной кнопки добавления
- mobile layout не разваливается на длинных attribute combos
