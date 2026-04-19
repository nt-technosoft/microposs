# SCN-INV-002 / Procurement Participation List

## Route
- Target route after PR-11: `/investor/procurements`

## Roles
- investor

## Goal
Показать инвестору список закупок, в которых он участвует, с приоритетом на trust/transparency and quick scanning.

## Primary actions
- просмотреть participations
- открыть procurement detail
- быстро увидеть status / pending payout / performance snapshot

## Key UI sections
- summary strip
- procurement cards/list
- status and payout indicators

## Mandatory states
- loading
- empty portfolio
- error
- forbidden

## Critical UX requirements
- mobile list should favour compact but readable cards
- cards should surface status, participation role, pending payout, and recent signal

## Dependencies
- `/api/v1/investors/procurements/`
- `/api/v1/investors/dashboard/` (summary strip/aggregate)

## Acceptance criteria
- list renders only procurements where current investor participates
- cards include status + supplier + participation signal without requiring detail open
- tap on card opens canonical `/investor/procurements/:id` route
- empty state explicitly explains "no participations yet" instead of generic no-data

## Open decision
- Whether to include period/filter controls in P0 or postpone to P1 remains open.