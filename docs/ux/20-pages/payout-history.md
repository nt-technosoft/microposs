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

## Mandatory states
- loading
- empty payouts history
- error
- forbidden

## Dependencies
- investor payout history endpoint (TBD)
- optional link target: `/investor/procurements/:id`

## Critical requirements
- payout history should not look like generic bank statements
- each payout should be attributable to procurement/ledger context when possible

## Acceptance criteria
- payout list shows amount/currency/date and source procurement context when available
- empty state explicitly communicates no paid dividends yet
- each row has deterministic behavior: opens linked procurement or shows explicit "link unavailable"

## Open decision
- Exact backend endpoint/shape for investor payout history is still undecided and blocks final contract typing.
