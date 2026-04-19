# WGT-008 / Procurement Partner Block

## Purpose
Редактировать и показывать участников procurement contract: role, capital share, profit share, mudaraba-related info.

## Used in screens
- procurement create
- procurement detail

## Required behavior
- add/edit/remove partner rows where allowed
- clearly show operator vs investor role
- show share totals and validation state
- support progressive disclosure for complex formula inputs

## Critical invariants
- operator must exist
- shares must stay visibly validated
- user must understand when values are input vs derived

## Mobile behavior
- stack rows vertically
- keep summary totals visible near editor
