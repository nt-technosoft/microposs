# SCN-CSH-004 / Checkout

## Route
- `/sales/checkout`

## Roles
- owner
- cashier

## Goal
Завершить продажу из одного склада с multi-payment flow, соблюдая бизнес-инварианты backend.

## Primary actions
- проверить cart
- выбрать warehouse
- выбрать customer if needed
- добавить 0..N payments
- подтвердить sale

## Key UI sections
- cart summary
- warehouse selector
- customer selector
- payment list editor
- totals / outstanding summary
- sticky primary CTA

## Mandatory states
- loading
- empty cart
- validation error
- submit success
- forbidden

## Critical invariants in UI
- sale happens from one warehouse
- credit sale requires customer
- sum(payments) may be < total only if receivable path is valid
- double submit must be blocked

## Dependencies
- `/api/v1/sales/sales/`
- `/api/v1/sales/sessions/`
- `/api/v1/customers/customers/`
- warehouse options read model

## API contract note
- Checkout submit must include `client_request_id` for idempotent create-sale behavior.
- Duplicate submit with same `client_request_id` must resolve predictably (no double sale).
