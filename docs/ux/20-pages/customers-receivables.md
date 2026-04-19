# SCN-CSH-007 / Customers and Receivables

## Route
- `/customers`

## Roles
- owner
- cashier (sales-related customer handling)

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

## Dependencies
- customers store
- receivable contracts
- customer payment actions
