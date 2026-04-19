# SCN-CSH-006 / Return Flow

## Route
- `/sales/:id/return`

## Roles
- owner
- cashier

## Goal
Провести возврат так, чтобы пользователь явно понимал разницу между RESTOCK и DISPOSE и не ломал финансовый смысл операции.

## Primary actions
- выбрать sale line
- указать quantity
- выбрать resolution
- подтвердить return

## Key UI sections
- sale summary
- return line selector
- quantity control
- resolution selector
- impact preview
- confirm CTA

## Mandatory states
- loading
- invalid quantity error
- success
- forbidden

## Critical invariants in UI
- return quantity must not exceed sold minus already returned
- RESTOCK and DISPOSE should be visibly different choices
- user should understand that DISPOSE implies loss path
- critical submit must be idempotent and protected from double tap

## Dependencies
- sale detail / lines
- return processing
- optional refund path
