# SCN-OWN-005 / Partner Ledger and Dividends

## Route
- Target route after PR-11: `/partners/ledger` or nested under procurement/finance

## Roles
- owner

## Goal
Дать owner понятный контроль над начисленной прибылью, сторно, убытками и payout path по procurement-driven ledger model.

## Primary actions
- выбрать procurement / partner
- просмотреть aggregate summary
- открыть ledger timeline
- инициировать dividend payout

## Key UI sections
- filter controls
- aggregate metric cards
- ledger timeline
- payout action block

## Mandatory states
- loading
- empty ledger
- error
- forbidden

## Critical invariants in UI
- payout should never look available above pending amount
- entry type semantics must stay explicit, not hidden behind generic “transactions” labels
- destructive/financial actions require confirmation clarity

## Dependencies
- partner ledger aggregate
- ledger entries
- dividend payment action
