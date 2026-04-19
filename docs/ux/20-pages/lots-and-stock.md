# SCN-WHS-003 / Lots and Stock

## Route
- Target route after PR-11: `/stock` or `/warehouses/:id/stock`

## Roles
- owner
- warehouse

## Goal
Дать складу операционную картину по lot-based stock: остатки, распределение по складам, движения и risk-sensitive actions.

## Primary actions
- просмотреть остатки по lot/warehouse
- открыть lot detail
- инициировать transfer
- перейти к movements/disposals

## Key UI sections
- warehouse filter
- stock summary cards
- lot list / cards
- movement entry points
- low-stock / inactive indicators

## Mandatory states
- loading
- empty stock
- error
- forbidden

## Critical UX requirements
- на mobile приоритет у card/timeline views, а не dense tables
- lot identity, quantity and warehouse must stay readable at 375px
- risky actions (dispose/writeoff/transfer) should be clearly separated

## Dependencies
- inventory lots
- lot stock by warehouse
- stock movement history
- transfer/disposal actions
