# Traceability Matrix

## Purpose
Связать роли, сценарии, экраны, widgets, требования и тестирование, чтобы ничего не потерять при PR-10/11.

## Initial mapping

| Role | Journey | Screen | Widgets | Critical requirements |
|---|---|---|---|---|
| owner | Procurement lifecycle | SCN-OWN-003 / SCN-OWN-004 | WGT-003, WGT-006, WGT-005 | balance must be zero before receive; operator required; mobile-first progressive disclosure |
| owner | Partner settlement | SCN-OWN-005 | WGT-005 | payout <= pending; ledger transparency |
| owner | Finance operations | SCN-OWN-006 | cards + lists (TBD) | mobile launcher, not dense mega-screen |
| cashier | Browse and sell | SCN-CSH-001 / SCN-CSH-004 | WGT-001, WGT-002, WGT-003, WGT-004 | one warehouse sale; credit requires customer; idempotent submit |
| cashier | Return goods | SCN-CSH-006 | WGT-003 | quantity limit; RESTOCK vs DISPOSE clarity |
| cashier | Customer debt flow | SCN-CSH-007 | receivable cards (TBD) | no scalar-only debt magic; drill-down required |
| warehouse | Receive goods | SCN-WHS-001 / SCN-OWN-004 | WGT-006 | blocked/ready state visible; operational clarity |
| warehouse | Track stock | SCN-WHS-003 | stock cards/tables (TBD) | mobile card-first readability |
| investor | Portfolio visibility | SCN-INV-001 / SCN-INV-002 / SCN-INV-003 | WGT-005 | trust/transparency; read-focused shell |

## Usage
- Каждый новый spec должен привязываться к этой таблице.
- Если экран/виджет не попадает ни в один primary workflow, он должен быть явно обоснован.
