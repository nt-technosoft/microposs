# SCN-INV-004 / Ledger Timeline Page

## Route
- `/investor/ledger` or nested timeline route

## Roles
- investor

## Goal
Дать инвестору полный chronological ledger view beyond the short preview inside procurement detail.

## Primary actions
- inspect chronological entries
- filter by procurement or event type later if needed

## Key sections
- timeline header
- filters (optional phase 2)
- chronological entries list

## Mandatory states
- loading
- empty timeline
- error
- forbidden

## Dependencies
- investor ledger payload (currently available via `/api/v1/investors/procurements/:id/`)

## Critical requirements
- entry semantics explicit in text
- color only as support, never as sole signal
- mobile readability first

## Acceptance criteria
- timeline entries keep deterministic ordering by date/id
- each entry displays type + amount + currency + source reference when available
- filter controls (if enabled) do not break chronological integrity

## Open decision
- Dedicated aggregated investor-ledger endpoint is not finalized; current data may be composed from procurement detail responses.
