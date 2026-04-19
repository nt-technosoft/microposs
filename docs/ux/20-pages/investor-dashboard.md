# SCN-INV-001 / Investor Dashboard

## Route
- `/investor`

## Roles
- investor

## Goal
Дать инвестору быстрый обзор участия в закупках, текущей прибыли/убытков и доступных выплат.

## Primary actions
- просмотреть aggregate metrics
- открыть procurement detail
- перейти к ledger/payout history

## Key UI sections
- portfolio summary cards
- procurement participation list
- pending payout indicator
- ledger timeline preview

## Mandatory states
- loading
- empty participation state
- error
- forbidden

## Critical UX requirements
- investor shell должен быть визуально отделён от owner/cashier flow
- ключевые метрики должны читаться на 375px без таблиц
- timeline/cards важнее dense admin tables

## Dependencies
- `/api/v1/investors/dashboard/`
- `/api/v1/investors/procurements/`
- investor payout read model

## Acceptance criteria
- dashboard metrics sourced from investor bridge contracts, not legacy summary endpoints
- tap from dashboard to procurement participation list works without cross-shell navigation glitches
- investor sees only investor-scope data (no owner finance/cash/admin sections)

## Open decision
- Detailed payout endpoint shape for investor self-service history still needs final backend contract confirmation.
