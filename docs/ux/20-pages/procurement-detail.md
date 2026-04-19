# SCN-OWN-004 / Procurement Detail

## Route
- Target route after PR-11: `/procurements/:id`

## Roles
- owner
- warehouse (operational receive-focused view)
- investor (restricted read variant in investor shell)

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
- investor view не должен видеть owner-only controls

## Dependencies
- procurement details
- procurement balance
- contributions / withdrawals
- partner ledger summary
- receive action
