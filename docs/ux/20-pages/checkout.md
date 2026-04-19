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
- sales store
- cart store
- customers / receivable contracts
- warehouse options
