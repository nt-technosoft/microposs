# SCN-OWN-001R2 / Reconciliation

## Route
- `/reports/reconciliation`

## Roles
- owner

## Goal
Дать owner инструмент сверки ключевых operational/financial цифр и выявления рассинхрона.

## Primary actions
- выбрать период
- просмотреть divergences
- перейти к связанному domain screen when mismatch found

## Mandatory states
- loading
- empty (нет completed reconcile batch)
- error
- forbidden

## Dependencies
- `/api/v1/core/excel/reconciliation/latest/`

## Acceptance criteria
- screen should explain mismatch meaning, not only show raw numbers
- reconciliation should act as diagnostic surface, not dense accounting table only
- 404 from backend (`No completed reconcile batch found`) mapped to explicit empty/cta state, not generic crash toast
- forbidden state shown for non-owner roles
- each divergence row has explicit navigation target or documented "no target yet" label

## Open decision
- Право доступа currently owner-only; расширение на finance-manager role возможно только после backend role policy change.
