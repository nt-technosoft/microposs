# SCN-CSH-003 / Cart

## Route
- `/sales/cart`

## Roles
- owner
- cashier

## Goal
Дать пользователю промежуточную review-stage перед checkout: проверить позиции, количество, цены и перейти к оформлению.

## Primary actions
- изменить quantity
- удалить позицию
- вернуться в каталог
- перейти в checkout

## Key sections
- cart line list
- line totals
- overall total
- CTA block

## States
- empty cart
- editing state
- loading (if async recompute needed later)
- error

## Functional requirements
- lines come from cart store
- quantity update immutable in store
- total recalculates immediately
- checkout blocked if cart empty

## Non-functional requirements
- fast on mobile
- line actions easy to hit with thumb
- numbers tabular and readable

## Acceptance criteria
- user can edit/remove lines without leaving screen
- total updates correctly
- checkout CTA clearly visible and sticky if needed
