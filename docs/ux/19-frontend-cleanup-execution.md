# Frontend Cleanup Execution Plan

## Purpose
Этот документ фиксирует практический шаг физической очистки frontend feature layer перед clean-slate rewrite.

## Keep now
- docs/ux layer
- Bootstrap target files from `05-frontend-restart-bootstrap.md` (recreate from scratch in empty `frontend/`)

Note: previous references to existing `frontend/src/*` files were valid before wipe; now frontend is intentionally empty and must be rebuilt from scratch.
## Remove / replace now
- Legacy feature views/components are already removed by wipe.
- New implementation must avoid restoring old feature architecture and should follow `05-frontend-restart-bootstrap.md`.
- If old files reappear from cherry-pick/merge, treat them as reference-only and do not use as base for new feature layer.

## Transitional shell rule
После удаления legacy feature screens routes и shell должны быть сведены к минимальному, buildable foundation state. Это временное состояние перед новым clean-slate rewrite.

## Expected result
- В файловой структуре не остаётся misleading legacy feature pages.
- build остаётся зелёным на минимальном foundation shell.
- следующая реализация идёт уже по `docs/ux` без адаптации старых screens.
