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
- procurement detail read model
- investor ledger data
- payout history data
