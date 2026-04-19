# WGT-002 / Floating Cart

## Purpose
Быстрый persistent entry point в cart/checkout flow во время browsing catalog.

## Used in screens
- sales catalog
- product detail
- other sales-adjacent screens where cart context matters

## Foundation status after wipe
- Legacy `frontend/src/components/layout/AppFloatingCart.vue` was removed during frontend wipe.
- Recreate floating-cart as a new shared foundation component during restart.

## Inputs
- cart item count
- cart total
- current route context

## Required behavior
- visible only when cart is not empty
- hidden inside cart/checkout screens
- clear total and item count
- one-tap navigation to cart

## States
- hidden empty state
- visible active state
- press feedback

## Accessibility
- button semantics
- clear aria-label
- numeric values remain readable in tabular form

## Mobile behavior
- fixed position above bottom nav
- should not cover primary CTAs or critical content
