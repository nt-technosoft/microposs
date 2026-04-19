# WGT-006 / Balance Status Card

## Purpose
Показывать operational balance state для procurement и receive readiness.

## Used in screens
- procurement detail
- procurement create/edit summary
- warehouse receive flow

## Planned role in PR-11
Ключевой widget для проверки инварианта `balance must be zero before receive`.

## Required behavior
- show balances by currency
- clearly indicate zero / non-zero state
- explain why receive is blocked when not zero
- provide path to contribution/withdrawal actions

## Accessibility and UX
- статус должен читаться не только цветом
- zero-state and blocked-state must be obvious at a glance
- on mobile card must stay visually prominent near action controls
