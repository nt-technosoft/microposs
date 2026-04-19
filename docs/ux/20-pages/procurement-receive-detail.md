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

## Dependencies
- `/api/v1/partnerships/procurements/:id/`
- `/api/v1/partnerships/procurements/:id/receive/`
- `/api/v1/inventory/warehouses/`

## Critical invariants
- receive only from `OPEN`
- zero balance before receive
- valid warehouse required
- no ambiguous success state after submit

## Acceptance criteria
- if procurement balance non-zero, receive CTA is blocked with explicit reason
- success state confirms status transition to `RECEIVED`
- repeated tap during submit does not create duplicate receive operations
- non-owner/non-warehouse role gets explicit forbidden state

## Open decision
- Whether warehouse role can edit procurement metadata from this screen remains undecided; default is read + receive only.
