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

## Mandatory states
- loading
- empty transfer candidates
- validation error
- success
- forbidden

## Dependencies
- `/api/v1/inventory/stock/summary/`
- `/api/v1/inventory/stock/transfer/`
- `/api/v1/inventory/lots/`

## Critical invariants
- quantity must be available in source
- transfer does not change participant/shares semantics
- movement must be traceable in stock history

## Acceptance criteria
- source==destination is blocked with clear validation message
- transfer success updates visible stock state for both warehouses
- low-stock/insufficient-quantity error shown inline, not generic toast only
- transfer history is discoverable from stock/movements view

## Open decision
- Single-lot transfer (current API) vs multi-line transfer batch UX is still undecided.
