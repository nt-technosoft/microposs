# Route ↔ Screen Matrix

## Purpose
Этот документ связывает реальные маршруты, роли, screen IDs, текущие view-файлы и целевые API/contract dependencies. Он нужен, чтобы разработка шла не по ощущениям, а по явной карте.

## Current route map
| Route | Route name | Role(s) | Screen ID | Current view file | Target state |
|---|---|---|---|---|---|
| `/login` | `login` | public | SCN-AUTH-001 | `frontend/src/modules/auth/views/LoginView.vue` | keep / refine |
| `/sales` | `sales-catalog` | owner, cashier | SCN-CSH-001 | `frontend/src/modules/sales/views/SalesCatalog.vue` | clean-slate rewrite |
| `/sales/product/:id` | `product-detail` | owner, cashier | SCN-CSH-002 | `frontend/src/modules/sales/views/ProductDetail.vue` | clean-slate rewrite |
| `/sales/cart` | `cart` | owner, cashier | SCN-CSH-003 | `frontend/src/modules/sales/views/CartView.vue` | clean-slate rewrite |
| `/sales/checkout` | `checkout` | owner, cashier | SCN-CSH-004 | `frontend/src/modules/sales/views/CheckoutView.vue` | clean-slate rewrite |
| `/sales/history` | `sales-history` | owner, cashier | SCN-CSH-005 | `frontend/src/modules/sales/views/SalesHistory.vue` | clean-slate rewrite |
| `/sales/:id/return` | _(target)_ | owner, cashier | SCN-CSH-006 | _(new / dedicated flow)_ | must add |
| `/customers` | `customers` | owner (+ cashier if policy approved) | SCN-CSH-007 / SCN-OWN-011 | `frontend/src/modules/more/views/CustomersView.vue` | clean-slate rewrite |
| `/products` | `products` | owner, warehouse | SCN-OWN-007 | `frontend/src/modules/products/views/ProductList.vue` | rewrite later |
| `/products/create` | `product-create` | owner | SCN-OWN-007A | `frontend/src/modules/products/views/ProductCreate.vue` | rewrite later |
| `/products/:id` | `product-edit` | owner | SCN-OWN-007B | `frontend/src/modules/products/views/ProductEdit.vue` | rewrite later |
| `/categories` | `categories` | owner | SCN-OWN-007C | `frontend/src/modules/products/views/CategoryList.vue` | rewrite later |
| `/intake` / `/procurements` | `intake-list` / target `procurement-list` | owner, warehouse | SCN-OWN-002 / SCN-WHS-001 | `frontend/src/modules/intake/views/IntakeList.vue` | target route = procurements |
| `/intake/create` / `/procurements/create` | `intake-create` / target `procurement-create` | owner, warehouse | SCN-OWN-003 | `frontend/src/modules/intake/views/IntakeCreate.vue` | target route = procurements |
| `/intake/:id` / `/procurements/:id` | `intake-detail` / target `procurement-detail` | owner, warehouse | SCN-OWN-004 / SCN-WHS-002 | `frontend/src/modules/intake/views/IntakeDetail.vue` | target route = procurements |
| `/reports` | `reports` | owner | SCN-OWN-001R | `frontend/src/modules/reports/views/ReportsDashboard.vue` | rewrite later |
| `/reports/reconciliation` | `reports-reconciliation` | owner | SCN-OWN-001R2 | `frontend/src/modules/reports/views/ReconciliationView.vue` | rewrite later |
| `/suppliers` | `suppliers` | owner | SCN-OWN-008 | `frontend/src/modules/more/views/SuppliersView.vue` | rewrite later |
| `/settings` | `settings` | all authenticated roles | SCN-COM-001 | `frontend/src/modules/more/views/SettingsView.vue` | foundation / refine |
| `/investor` | `investor-dashboard` | investor | SCN-INV-001 | `frontend/src/modules/investors/views/InvestorDashboard.vue` | clean-slate rewrite |
| `/investor/contracts/:id` / target `/investor/procurements/:id` | `investor-contract` / target `investor-procurement` | investor | SCN-INV-003 | `frontend/src/modules/investors/views/ContractDetail.vue` | target route = investor procurements |

## Contract dependencies by route family
- Sales family → `sales.ts`, `cart.ts`, `session.ts`, `customers.ts`, `discount reasons`, lots/variants read models
- Procurements family → `partnerships.ts`, `inventory.ts`, suppliers/investors/catalog read models
- Investor family → `investors.ts`, procurement participation read models
- Reports/finance family → `finance.ts`, supplier/customer debt summaries, stock summary, trial balance

## Known mismatches to resolve
1. `role-matrix.md` says customer write/pay is owner-only, but cashier flow needs receivable interaction.
2. Current router still reflects legacy `/intake` and `/investor/contracts/:id`; target UX wants `/procurements/*` and `/investor/procurements/:id`.
3. Return flow has UX spec but no dedicated route yet.
