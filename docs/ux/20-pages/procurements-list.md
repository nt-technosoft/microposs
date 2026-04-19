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
- procurement list contract
- role-aware filtering
