# MicroPOS — Excel Source Model (Iteration 1)

## Purpose
Этот документ фиксирует, как исходная Google Sheets модель трактуется в MicroPOS:
- что является первичными событиями,
- что является мастер-данными,
- что является производными отчетами (не импортируется как первичка).

## Data Classes

| Class | Sheets | Nature | Target in MicroPOS |
|---|---|---|---|
| `master/static` | `MALUMOTLAR` | Справочники, стабильные справочные значения | Каталог, контрагенты, склады, справочные типы |
| `transactional/dynamic` | `SOTIB OLISH`, `STOCK TRANSFER`, `SOTUV`, `TUSHUM`, `XARAJAT`, `PUL AYRIBOSHLASH` | Операции (изменяются по времени) | Доменные операции через сервисный слой |
| `derived/report-only` | `KASSA`, `OMBOR`, `QARZDORLAR`, `YETKAZIB BERUVCHILARDAN QARZ`, `FOYDA TAQSIMOTI` | Формульные витрины | Пересчет из БД (не импортируется как первичка) |

## Canonical Principles
1. Импортируются только первичные события и мастер-данные.
2. Производные листы используются для сверки, не для записи в домен.
3. Все доменные операции применяются через сервисы (`receipt/sale/transfer/payment/expense`) с сохранением `JournalEntry` и `OutboxEvent`.
4. Каждая staged-строка хранит source-trace:
   - `source_sheet`, `source_row_id`, `row_fingerprint`,
   - `operation_currency`, `operation_amount`, `fx_rate_snapshot`, `functional_amount`.
5. Excel-поля типа `HIDE/UNHIDE`, визуальные helper-колонки и повторяющиеся формулы не переносятся в доменную модель.

## Source Format for Import Command
Команда `excel_align_import` принимает JSON snapshot:

1. **Canonical**:
```json
{
  "sheets": {
    "SOTUV": [{ "...": "..." }],
    "SOTIB OLISH": [{ "...": "..." }]
  },
  "opening_balances": {},
  "expected": {}
}
```

2. **Connector shape** (output from Google Sheets connector `get_spreadsheet_cells`):
- `sheets[] -> properties.title + data[].rowData[]`.
- Первая строка трактуется как headers.

## Currency Canon (for import trace)
- `operation_currency`: валюта исходной операции (`USD`/`UZS`).
- `operation_amount`: сумма в исходной валюте.
- `fx_rate_snapshot`: курс на момент операции.
- `functional_amount`: сумма в функциональной валюте (`UZS`).
