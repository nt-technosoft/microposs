# WGT-003 / Select / Dropdown Pattern

## Purpose
Единый mobile-first выбор значения через bottom-sheet/select trigger pattern.

## Used in screens
- warehouse selector
- customer selector
- supplier selector
- payment method selector
- procurement type selector
- category/filters where appropriate

## Current foundation
- `frontend/src/components/base/BaseSelect.vue`

## Required behavior
- trigger button with current label / placeholder
- bottom sheet list on mobile
- clear active selection state
- disabled option support
- long labels must truncate gracefully in trigger, not in option semantics

## States
- placeholder
- selected
- disabled
- active option

## Accessibility
- clear label/title
- keyboard and screen-reader compatible semantics where possible
- no tiny hit targets

## UX note
Этот pattern уже понравился пользователю и должен остаться базовым shared interaction pattern.
