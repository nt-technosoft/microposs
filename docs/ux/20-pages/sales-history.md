# SCN-CSH-005 / Sales History

## Route
- `/sales/history`

## Roles
- owner
- cashier

## Goal
Показать недавние продажи, дать быстрый доступ к деталям и return path.

## Primary actions
- просмотреть recent sales
- открыть sale detail
- перейти в return flow
- отфильтровать / найти sale

## Key UI sections
- search / filters
- sale cards/list
- summary badges (status, payment state)
- quick return entry point

## Mandatory states
- loading
- empty history
- error
- forbidden

## Critical UX requirements
- recent sales must be scannable quickly on mobile
- return-related actions should be present but not visually dominant over browsing history

## Dependencies
- sales history contract
- sale detail
- return flow
