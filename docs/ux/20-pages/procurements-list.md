# SCN-OWN-002 / Procurements List

## Route
- Target route after PR-11: `/procurements`

## Roles
- owner
- warehouse (operationally filtered variant)

## Goal
Дать owner/warehouse обзор всех закупок с фокусом на статус, next action и быстрый переход в detail/create flows.

## Primary actions
- просмотреть procurements by status
- отфильтровать open / received / closed / blocked
- открыть procurement detail
- перейти в procurement create

## Key UI sections
- status filter chips
- procurement list/cards
- quick summary counts
- primary create CTA

## Mandatory states
- loading
- empty list
- filtered empty state
- error
- forbidden

## Critical UX requirements
- статус и actionable next step должны быть понятны без открытия detail
- на mobile используется card-first layout
- owner variant может показывать richer summaries, warehouse variant — operational status first

## Dependencies
- `/api/v1/partnerships/procurements/`
- role-aware filtering

## Acceptance criteria
- owner and warehouse see only allowed actions (no hidden permission escalation)
- each card surfaces readiness/block reason for receive-related flows
- list supports status filtering without route/query ambiguity
- tap from list opens canonical `/procurements/:id` route

## Open decision
- Separate `/receiving` dedicated route vs filter preset inside `/procurements` remains unresolved.
