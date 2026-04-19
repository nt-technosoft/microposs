# Foundation Keep/Delete Plan

## Purpose
Зафиксировать, что именно остаётся как foundation для clean-slate frontend rewrite, а что не должно служить основой для нового feature слоя.

## KEEP — foundation base
### Tooling / config
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`

### App foundation
- `frontend/src/main.ts`
- `frontend/src/App.vue` — как временный shell reference, не как immutable final shell
- `frontend/src/api/client.ts`

### Composables
- `frontend/src/composables/useBreakpoint.ts`
- `frontend/src/composables/useDebounce.ts`
- `frontend/src/composables/useIdempotency.ts`
- `frontend/src/composables/useToast.ts`

### Design system / styles
- `frontend/src/assets/styles/tokens.css`
- `frontend/src/assets/styles/reset.css`
- `frontend/src/assets/styles/typography.css`
- `frontend/src/assets/styles/animations.css`

### Shared/base UI primitives
- `frontend/src/components/base/BaseButton.vue`
- `frontend/src/components/base/BaseInput.vue`
- `frontend/src/components/base/BaseCard.vue`
- `frontend/src/components/base/BaseSelect.vue`
- other low-level shared primitives after quick consistency review

## KEEP AS REFERENCE ONLY — not final architecture
### API reference layer
- `frontend/src/api/auth.ts`
- `frontend/src/api/catalog.ts`
- `frontend/src/api/sales.ts`
- `frontend/src/api/inventory.ts`
- `frontend/src/api/customers.ts`
- `frontend/src/api/suppliers.ts`
- `frontend/src/api/finance.ts`
- `frontend/src/api/investors.ts`
- `frontend/src/api/risk.ts`

### State reference layer
- `frontend/src/stores/auth.ts`
- `frontend/src/stores/session.ts`
- `frontend/src/stores/ui.ts`
- `frontend/src/stores/cart.ts`
- `frontend/src/stores/products.ts`
- `frontend/src/stores/customers.ts`
- `frontend/src/stores/sales.ts`

### Types reference layer
- `frontend/src/types/enums.ts`
- `frontend/src/types/models.ts`

## DELETE / DO NOT USE AS BASE FOR NEW FEATURE LAYER
### Feature screens
- `frontend/src/modules/sales/views/*.vue`
- `frontend/src/modules/products/views/*.vue`
- `frontend/src/modules/intake/views/*.vue`
- `frontend/src/modules/reports/views/*.vue`
- `frontend/src/modules/more/views/*.vue`
- `frontend/src/modules/investors/views/*.vue`

### Feature-level layout artifacts
- `frontend/src/components/layout/AppBottomNav.vue`
- `frontend/src/components/layout/AppFloatingCart.vue`

Reason: these are part of the old or hybrid feature layer and should not dictate the new clean-slate architecture.

## Route policy
- existing route files are references for access semantics only
- target route language should move to `/procurements/*` and `/investor/procurements/:id`
- legacy aliases are transitional only

## Working rule
If a file contains domain flow decisions, page orchestration, mixed legacy contracts, or view-level hacks, it is **not foundation**.
If a file provides reusable styling, primitive interaction, or generic infrastructure, it is **candidate foundation**.
