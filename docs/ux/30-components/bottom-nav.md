# WGT-001 / Bottom Navigation

## Purpose
Главная mobile-first навигация для high-frequency flows.

## Used in screens
- sales catalog
- products
- procurements/intake
- reports
- settings/more

## Current foundation
- `frontend/src/components/layout/AppBottomNav.vue`

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
