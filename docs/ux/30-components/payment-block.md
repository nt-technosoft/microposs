# WGT-004 / Payment Block

## Purpose
Редактор списка платежей для sale checkout с поддержкой 0..N платежей и разных методов/валют.

## Used in screens
- checkout
- future refund/payment-related flows

## Planned role in PR-11
Новый крупный domain widget, который должен объединять payment rows, totals, outstanding state и validation.

## Required behavior
- add/remove payment rows
- choose method
- choose currency
- enter amount
- show running totals
- reflect receivable/outstanding state

## Critical invariants
- credit requires customer
- payment sum must be explicit and readable
- underpayment path must be visibly different from fully paid sale
- no hidden calculations without user feedback

## Mobile behavior
- rows should stack vertically
- numeric input controls must remain comfortable on 375px
- primary totals block should remain visible near CTA
