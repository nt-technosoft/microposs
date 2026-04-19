# SCN-INV-005 / Payout History

## Route
- `/investor/payouts` or nested under investor shell

## Roles
- investor

## Goal
Показать инвестору историю фактических выплат и связь с procurement/ledger событиями.

## Primary actions
- inspect payout history
- open linked procurement context

## Critical requirements
- payout history should not look like generic bank statements
- each payout should be attributable to procurement/ledger context when possible
