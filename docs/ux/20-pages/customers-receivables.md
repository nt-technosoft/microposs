# SCN-CSH-007 / Customers and Receivables

## Route
- `/customers`

## Roles
- owner
- cashier (read-only for customer list/receivable visibility until policy update)

## Goal
Показывать клиентов не как простой справочник, а как operational screen для credit/receivable flows.

## Primary actions
- найти клиента
- увидеть outstanding summary
- открыть receivable drill-down
- зарегистрировать payment / settlement
- выбрать клиента для credit sale flow

## Key UI sections
- customer search and list
- receivable summary cards
- receivable timeline / entries preview
- payment action block

## Mandatory states
- loading
- empty list
- empty receivable state
- error
- forbidden

## Critical invariants in UI
- credit sale path должен быстро находить клиента
- outstanding не должен быть скалярной «магией» без drill-down
- payment registration должен быть защищён от double submit
- cashier не должен видеть owner-only create/pay controls до policy change

## Dependencies
- `/api/v1/customers/customers/`
- `/api/v1/customers/customers/:id/receivable/`
- owner-only write actions: `/api/v1/customers/customers/` (POST), `/api/v1/customers/customers/:id/pay/`

## Acceptance criteria
- owner sees create/pay actions; cashier sees read-only variant
- receivable drill-down доступен без скрытых вычислений и без scalar-only summary
- customer search latency acceptable on 375px flow
- forbidden write attempt in cashier context is mapped to explicit permission message

## Open decision
- Cashier write/pay enablement remains open and requires backend role policy + role-matrix update.
## Dependencies
- customers store
- receivable contracts
- customer payment actions
