# SCN-OWN-004 / Procurement Detail

## Route
- Target route after PR-11: `/procurements/:id`

## Roles
- owner
- warehouse (operational receive-focused view)

Note: investor uses dedicated screen `SCN-INV-003` (`/investor/procurements/:id`), not this owner/warehouse route.

## Goal
Показать полную картину закупки: статус, товары, расходы, баланс, контракт, ledger и действия следующего шага.

## Primary actions
- просмотреть состав закупки
- проверить баланс по валютам
- перейти к contribution / withdrawal
- выполнить receive, если инварианты соблюдены
- открыть partner/investor drill-down

## Key UI sections
- status summary card
- balance by currency
- items list
- expenses list
- contract / partner shares block
- ledger preview / timeline
- action footer

## Mandatory states
- loading
- empty sub-sections
- error
- success
- forbidden

## Critical invariants in UI
- receive CTA недоступен при non-zero balance
- partnership flows должны явно показывать operator/investor shares
- owner/warehouse route variant не должен смешиваться с investor-shell controls

## Dependencies
- `/api/v1/partnerships/procurements/:id/`
- `/api/v1/partnerships/procurements/:id/contributions/`
- `/api/v1/partnerships/procurements/:id/withdrawals/`
- `/api/v1/partnerships/procurements/:id/ledger/`
- `/api/v1/partnerships/procurements/:id/receive/`

## Acceptance criteria
- non-zero balance blocks receive action with explicit reason
- contribution/withdrawal actions are visible only for allowed roles/actions
- ledger preview reflects backend entry semantics (capital/profit/loss/dividend) without generic relabeling
- investor-shell variant remains read-only and does not expose owner operational controls

## Open decision
- Unified screen with role variants vs split owner/warehouse/investor detail implementations remains a design decision for implementation phase.
