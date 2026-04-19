# Route ↔ Screen Matrix

## Purpose
Этот документ связывает реальные маршруты, роли, screen IDs и целевые API/contract dependencies для чистого рестарта frontend. Он нужен, чтобы разработка шла не по ощущениям, а по явной карте.

## Restart route map (frontend is intentionally wiped)

Current frontend view files are absent and should not be used as implementation reference.

| Route | Route name | Role(s) | Screen ID | Backend/API anchor | Restart priority |
|---|---|---|---|---|---|
| `/login` | `login` | public | SCN-AUTH-001 | `/api/v1/auth/token/`, `/api/v1/auth/me/` | P0 |
| `/sales` | `sales-catalog` | owner, cashier | SCN-CSH-001 | `/api/v1/sales/sessions/`, `/api/v1/catalog/products/` | P0 |
| `/sales/product/:id` | `product-detail` | owner, cashier | SCN-CSH-002 | `/api/v1/catalog/products/:id/`, `/api/v1/catalog/products/:id/variants/` | P1 |
| `/sales/cart` | `cart` | owner, cashier | SCN-CSH-003 | cart/session local state + sales contracts | P0 |
| `/sales/checkout` | `checkout` | owner, cashier | SCN-CSH-004 | `/api/v1/sales/sales/` | P0 |
| `/sales/history` | `sales-history` | owner, cashier | SCN-CSH-005 | `/api/v1/sales/sales/` | P1 |
| `/sales/:id/return` | `sale-return` | owner, cashier | SCN-CSH-006 | `/api/v1/sales/sales/:id/return/` | P1 |
| `/customers` | `customers` | owner, cashier (read-only for cashier at startup) | SCN-CSH-007 / SCN-OWN-011 | `/api/v1/customers/customers/`, `/pay/`, `/receivable/` | P1 |
| `/products` | `products` | owner, warehouse | SCN-OWN-007 | `/api/v1/catalog/products/` | P2 |
| `/products/create` | `product-create` | owner | SCN-OWN-007A | `/api/v1/catalog/products/` | P2 |
| `/products/:id` | `product-edit` | owner | SCN-OWN-007B | `/api/v1/catalog/products/:id/` | P2 |
| `/categories` | `categories` | owner | SCN-OWN-007C | `/api/v1/catalog/categories/` | P2 |
| `/procurements` | `procurement-list` | owner, warehouse | SCN-OWN-002 / SCN-WHS-001 | `/api/v1/partnerships/procurements/` | P0 |
| `/procurements/create` | `procurement-create` | owner, warehouse | SCN-OWN-003 | `/api/v1/partnerships/procurements/` | P1 |
| `/procurements/:id` | `procurement-detail` | owner, warehouse | SCN-OWN-004 / SCN-WHS-002 | `/api/v1/partnerships/procurements/:id/` | P0 |
| `/reports` | `reports` | owner | SCN-OWN-001R | `/api/v1/finance/daily-summaries/`, `/cash-flow/` | P2 |
| `/reports/reconciliation` | `reports-reconciliation` | owner | SCN-OWN-001R2 | `/api/v1/core/excel/reconciliation/latest/` | P2 |
| `/suppliers` | `suppliers` | owner | SCN-OWN-008 | `/api/v1/suppliers/suppliers/` | P2 |
| `/settings` | `settings` | all authenticated roles | SCN-COM-001 | role context from `/api/v1/auth/me/` | P0 |
| `/investor` | `investor-dashboard` | investor | SCN-INV-001 | `/api/v1/investors/dashboard/` | P0 |
| `/investor/procurements` | `investor-procurements` | investor | SCN-INV-002 | `/api/v1/investors/procurements/` | P0 |
| `/investor/procurements/:id` | `investor-procurement` | investor | SCN-INV-003 | `/api/v1/investors/procurements/:id/` | P0 |

## Legacy alias policy
- Legacy `/intake/*` and `/investor/contracts/:id` are transitional compatibility aliases only.
- New frontend must use canonical routes `/procurements/*` and `/investor/procurements/:id`.
- If aliases are exposed, they must redirect to canonical paths and never be shown in primary navigation.
## Contract dependencies by route family
- Sales family → `sales.ts`, `cart.ts`, `session.ts`, `customers.ts`, `discount reasons`, lots/variants read models
- Procurements family → `partnerships.ts`, `inventory.ts`, suppliers/investors/catalog read models
- Investor family → `investors.ts`, procurement participation read models
- Reports/finance family → `finance.ts`, supplier/customer debt summaries, stock summary, trial balance

## Known mismatches to resolve
1. `role-matrix.md` says customer write/pay is owner-only, but cashier flow needs receivable interaction.
2. Backend/runtime may still expose legacy aliases `/intake/*` and `/investor/contracts/:id`; target UX is `/procurements/*` and `/investor/procurements/:id` only.
3. Return flow has UX spec but no dedicated route yet.
