# Frontend Cleanup Execution Plan

## Purpose
Этот документ фиксирует практический шаг физической очистки frontend feature layer перед clean-slate rewrite.

## Keep now
- `frontend/src/main.ts`
- `frontend/src/App.vue` (может быть упрощён как shell)
- `frontend/src/api/client.ts`
- `frontend/src/composables/*`
- `frontend/src/assets/styles/*`
- `frontend/src/components/base/*`
- `frontend/src/components/feedback/*`
- `frontend/src/modules/auth/views/LoginView.vue`
- `frontend/src/modules/more/views/SettingsView.vue`
- docs/ux layer

## Remove / replace now
- all existing feature views under:
  - `frontend/src/modules/sales/views/*`
  - `frontend/src/modules/products/views/*`
  - `frontend/src/modules/intake/views/*`
  - `frontend/src/modules/reports/views/*`
  - `frontend/src/modules/investors/views/*`
- utility-but-domain screens:
  - `frontend/src/modules/more/views/CustomersView.vue`
  - `frontend/src/modules/more/views/SuppliersView.vue`
- legacy layout artifacts:
  - `frontend/src/components/layout/AppBottomNav.vue`
  - `frontend/src/components/layout/AppFloatingCart.vue`

## Transitional shell rule
После удаления legacy feature screens routes и shell должны быть сведены к минимальному, buildable foundation state. Это временное состояние перед новым clean-slate rewrite.

## Expected result
- В файловой структуре не остаётся misleading legacy feature pages.
- build остаётся зелёным на минимальном foundation shell.
- следующая реализация идёт уже по `docs/ux` без адаптации старых screens.
