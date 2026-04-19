# Navigation and Roles

## Roles
- **owner** — полный доступ к платформе и административным сценариям
- **cashier** — продажа, чек-аут, возвраты, клиенты/долги в пределах sales flow
- **warehouse** — приёмка, lots, stock, transfers, stock movements/disposals
- **investor** — кабинет участия в закупках, ledger, payouts, история

## Role-first navigation principle
Навигация и экранный состав определяются сначала ролью и primary workflows, а не текущей структурой старых модулей.

## Primary workflows by role
### Owner
- dashboard
- procurements lifecycle
- partner ledger + dividends
- finance / cash / FX / journals
- catalog / suppliers / warehouses

### Cashier
- POS session
- sales catalog
- cart / checkout / multi-payment
- return processing
- customers with receivable drill-down

### Warehouse
- receiving queue / procurement receiving
- lots and stock by warehouse
- stock transfers
- movements / disposals

### Investor
- investor dashboard
- procurement participation list
- procurement detail with ledger timeline
- payout history

## Navigation principles
- Mobile-first primary navigation should prioritize high-frequency actions, not admin completeness.
- Bottom nav must stay compact and role-aware.
- Deep screens should be reachable by route, but not necessarily primary nav items.
- Investor flow should remain visually and structurally isolated from owner/cashier shell.

## Current route foundation to preserve
- `frontend/src/router/routes.ts`
- `frontend/src/App.vue`

## Initial screen inventory
### Owner
- Dashboard
- Procurements List
- Procurement Create
- Procurement Detail
- Partner Ledger / Dividends
- Finance Hub
- Catalog
- Suppliers
- Warehouses
- Settings

### Cashier
- Sales Catalog
- Product Detail
- Cart
- Checkout
- Sales History
- Return Flow
- Customers / Receivables
- Settings

### Warehouse
- Receiving Queue
- Procurement Receive Detail
- Lots & Stock
- Transfers
- Movements / Disposals
- Settings

### Investor
- Investor Dashboard
- Procurement Participation List
- Procurement Detail
- Ledger Timeline
- Payout History
- Settings

## Mandatory screen states
Для каждого role-facing экрана должны быть описаны:
- loading
- empty
- error
- success
- forbidden
- optional: offline / partial-data
