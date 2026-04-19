# SCN-INV-003 / Investor Procurement Detail

## Route
- Target route after PR-11: `/investor/procurements/:id`

## Roles
- investor

## Goal
Дать инвестору прозрачный drill-down по конкретной закупке: вложение, статус, остатки товара, ledger, начисления/убытки.

## Primary actions
- просмотреть procurement summary
- просмотреть ledger timeline
- проверить stock/remaining exposure
- перейти к payout history if relevant

## Key UI sections
- procurement summary header
- partner/investor participation block
- inventory/stock exposure block
- ledger timeline
- payout summary

## Mandatory states
- loading
- partial data fallback
- error
- forbidden

## Critical UX requirements
- investor variant должен быть read-focused, без owner-only controls
- numbers and statuses must be understandable on 375px without admin tables

## Dependencies
- `/api/v1/investors/procurements/:id/`
- investor ledger payload from procurement detail response

## Acceptance criteria
- detail page uses canonical investor procurement endpoint only
- ledger entries and aggregates are consistent with dashboard totals for same investor scope
- read-only constraint is explicit (no owner-only financial action controls)
- missing/forbidden procurement id shows explicit investor-friendly error state

## Open decision
- Separate dedicated `/investor/ledger` page vs keeping timeline inside procurement detail remains open for later phase.