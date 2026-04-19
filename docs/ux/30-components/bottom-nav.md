# WGT-001 / Bottom Navigation

## Purpose
Главная mobile-first навигация для high-frequency flows.

## Used in screens
- sales catalog
- products
- procurements
- reports
- settings/more

## Role tab map (startup baseline)
- owner: sales, procurements, finance/reports, settings
- cashier: sales, sales-history, settings
- warehouse: procurements/receiving, stock, transfers, settings
- investor: no shared bottom-nav (investor shell has dedicated navigation)

## Foundation status after wipe
- Legacy `frontend/src/components/layout/AppBottomNav.vue` was removed during frontend wipe.
- Recreate bottom-nav as a new shared foundation component during restart.

## Inputs
- active route
- current role
- simple seller mode flag

## Required behavior
- role-aware visible tabs
- max 5 primary items
- active state clearly visible
- labels always visible
- safe-area aware

## States
- default
- active item
- simple seller restricted mode
- hidden on blank/investor shells

## Accessibility
- min touch target 44x44
- current page exposed with `aria-current`
- icon + text together, not icon-only

## Open note
PR-11 may rename tabs and paths, but the bottom-nav pattern itself stays as foundation.
