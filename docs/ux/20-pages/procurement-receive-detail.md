# SCN-WHS-002 / Procurement Receive Detail

## Route
- `/procurements/:id` (warehouse operational variant)

## Roles
- warehouse
- owner

## Goal
Выполнить приемку закупки на склад при соблюдении всех инвариантов и с понятной operational обратной связью.

## Primary actions
- review items/expenses/partners/balance
- choose destination warehouse
- confirm receive

## States
- loading
- blocked by non-zero balance
- blocked by missing warehouse
- success
- forbidden

## Critical invariants
- receive only from `OPEN`
- zero balance before receive
- valid warehouse required
- no ambiguous success state after submit
