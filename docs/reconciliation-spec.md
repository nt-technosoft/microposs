# MicroPOS — Reconciliation Spec (Iteration 1/2)

## Goal
Подтвердить, что после импорта первичных событий система воспроизводит контрольные цифры, которые в Excel считаются формулами.

## Reconcile Command
`python manage.py excel_align_import --tenant-id <id> --mode reconcile --source-file <snapshot.json>`

## Sandbox Pilot Command (Iteration 2)
`python manage.py excel_align_pilot --source-file <snapshot.json> --days 14 --tenant-name "MicroPOS Sandbox Pilot"`

Pilot command выполняет этапы строго по порядку:
1. `dry-run`
2. `load-master`
3. `load-transactions` (срез последних N дней)
4. `reconcile`

Для owner-dashboard доступен endpoint последней сверки:
- `GET /api/v1/core/excel/reconciliation/latest/`
- возвращает `computed / expected / deltas + gap_summary`

Результат записывается в `ExcelImportBatch.totals`:
- `computed`
- `expected`
- `deltas`

## Computed Metrics
1. **Cash balance by account**
- `1000` (cash UZS)
- `1010` (bank/card/USD cash-equivalent)
- formula: `SUM(debit) - SUM(credit)` in journal lines

2. **Inventory by location**
- active lots only (`quantity_remaining > 0`)
- per location:
  - quantity
  - value (`quantity_remaining * cost_per_unit`)

3. **Receivables / Payables**
- `receivables_total_uzs = SUM(Customer.outstanding_balance)`
- `payables_total_uzs = SUM(Supplier.outstanding_balance)`

4. **Sales economics**
- `sales_revenue_uzs = SUM(Sale.total_amount, completed)`
- `sales_cogs_uzs = SUM(Sale.total_cogs, completed)`
- `gross_profit_uzs = revenue - cogs`

## Expected Metrics Input
Optional `expected` block in source snapshot:
```json
{
  "expected": {
    "receivables_total_uzs": "1230000.00",
    "payables_total_uzs": "980000.00",
    "gross_profit_uzs": "456700.00"
  }
}
```

For scalar expected values, command computes numeric delta:
- `delta = computed - expected`.

## Acceptance Baseline
- Quantity parity: exact match required (`100%`).
- Money parity: deviations only within agreed rounding threshold.
- Any non-rounding delta is logged as import gap for follow-up in `excel-gap-backlog.md`.
