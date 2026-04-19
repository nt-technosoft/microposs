# SCN-WHS-004 / Transfers

## Route
- `/stock/transfers` or stock nested route

## Roles
- warehouse
- owner

## Goal
Перемещать lot-based stock между складами без потери traceability.

## Primary actions
- choose lot
- choose source warehouse
- choose destination warehouse
- enter quantity
- confirm transfer

## Critical invariants
- quantity must be available in source
- transfer does not change participant/shares semantics
- movement must be traceable in stock history
