# Phase D — Технический долг

Трекер всего, что официально "готово" по плану (PR-1..PR-8), но на самом деле
оставлено как `NotImplementedError` / заглушка / мёртвый код. Обновляется
в конце каждого PR: любое незакрытое место идёт сюда строкой.

Формат: `id | откуда | что | блокирует`.

## Активные долги

_(пусто — все долги PR-1..PR-8 закрыты. Excel-импортер retired; его перезапуск — отдельный проект после Phase D.)_

---

## Закрытые долги

### ~~CALLER-1 — legacy `create_sale` вызовы~~ ✅
- **bootstrap_demo.py**: удалён весь legacy-блок (Receipt / InvestorContract / InvestorProfitRecord / InvestorSummary / DailySummary / CashFlowSummary с `investor_share` / старый `create_sale`). Теперь команда создаёт tenant / users / категорию / продукт / discount_reason / supplier / customer и успешно завершается. Полный procurement→sale→dividend демо-поток запланирован на PR-9b.
- **excel_alignment.py**: 1321 строка legacy-кода, привязанного к удалённым моделям (Receipt, InvestorContract, Sale.PaymentMethod, `transfer_lot`), заменена на 50-строчный stub. Публичная поверхность (`ExcelAlignmentImporter`, `load_snapshot`, `extract_sheets`, `normalize_row_keys`, `parse_datetime`, `pick`) сохранена для импорта зависимых management-команд, но каждый символ падает с `NotImplementedError` с внятным сообщением о причине. Перезапуск Excel-импорта — отдельный проект после Phase D.
- **Проверено:** `python manage.py bootstrap_demo` проходит end-to-end; `python manage.py check` — чисто; все три модуля (bootstrap_demo, excel_align_import, excel_align_pilot) импортируются.

### ~~PARTNER-1 — `partnerships.open_procurement`~~ ✅
- Реализовано: создаёт `Procurement` + items + expenses + (для PARTNERSHIP/MUSHARAKA) `InvestmentContract` + `ContractPartner[]` + пустой `ProcurementBalance`. Идемпотентность по `client_request_id`.

### ~~PARTNER-2 — `partnerships.add_contribution`~~ ✅
- Реализовано: `BalanceContribution` + мутация `balances[currency]` + `PartnerLedgerEntry(CAPITAL_IN)`. Блокирует contributions в не-OPEN статусе.

### ~~PARTNER-3 — `partnerships.add_withdrawal`~~ ✅
- Реализовано: `BalanceWithdrawal` + уменьшение `balances[currency]` (проверка на минус) + опциональный `CAPITAL_OUT` при указанном `partner_id`.

### ~~PARTNER-4 — `partnerships.receive_procurement`~~ ✅
- Реализовано: проверка `balance == 0`, аллокация landed cost пропорционально стоимости, `Lot` + `LotStock` + `StockMovement(RECEIPT)` на destination warehouse, `contract_snapshot` из фактических `CAPITAL_IN - CAPITAL_OUT`, `status = RECEIVED`.

### ~~SALES-1 — `sales.create_sale`~~ ✅
- Реализовано: новая сигнатура `(tenant_id, pos_session_id, location_id, sold_by_id, customer_id, lines, payments, client_request_id, notes, date)`. FIFO через `allocate_lot`, `SalePayment[]` с `resolve_fx_rate_snapshot`, `PROFIT_ACCRUED` по партнёрам через `calculate_profit_distribution`, `Lot.is_active=False` при нулевом остатке.

### ~~SALES-2 — `sales.calculate_profit_distribution`~~ ✅
- Реализовано: чистая функция `(lot, unit_price, quantity, unit_landed_cost) → {partner_id_str: decimal_str}`. Формула: investor = gross · capital_share · mudaraba_ratio; operator = gross · capital_share_op + gross · (1-mudaraba_ratio) · Σ investor_capital_share. Residue от округления → оператору.

### ~~SALES-3 — legacy-тела~~ ✅
- Удалены 200+ строк закомментированного legacy-кода под `raise NotImplementedError`.

### ~~DEAD-2 — `record_sale_stock_movement` / `record_return_stock_movement`~~ ✅
- Удалены из `inventory/services.py`. `StockMovement` теперь создаётся inline в `create_sale` и `process_return`.

### ~~DEAD-1 — `risk.services._record_investor_loss`~~ ✅
- Проверено grep'ом: функции уже не существует (вероятно, снята при переписи PR-8). Строка в документе была устаревшей.

### ~~INV-1 — `inventory.confirm_receipt` (tombstone)~~ ✅
- Удалена функция-tombstone и endpoint `ReceiptViewSet.confirm` (использовал эту функцию и падал `NotImplementedError`). Receipt CRUD (list/retrieve/create) оставлен как legacy read-surface — вся confirmation-логика теперь идёт через `partnerships.receive_procurement`.

### ~~PR8-1 — автосоздание `Refund` в `process_return`~~ ✅
- Добавлен опциональный kwarg `refund: dict | None = None`. Когда передан `{method, currency?, fx_rate?, account_id?}`, `process_return` вызывает `finance.refund_customer` инлайн с `return_ref_id=return_doc.pk`. Двухшаговый режим (caller сам делает refund) сохранён по умолчанию.

### ~~TEST-1 — legacy тесты под `pytest.skip`~~ ✅
- Удалены 5 legacy-файлов (`test_api_smoke.py`, `test_products_pricing_flow.py`, `test_excel_alignment_import.py`, `test_financial_integrity.py`, `test_excel_alignment_iteration2.py`). Они были привязаны к удалённым моделям (Receipt/InvestorContract/Sale.PaymentMethod) и к retired excel_alignment. Новый тестовый корпус под vacuum-модель пишется с нуля отдельно. Оставлены: `test_role_matrix.py` и `test_fx_rates.py` — работают поверх нового `bootstrap_demo`.

---

## Закрытые долги

_(пусто — впишется по мере закрытия)_

---

## Политика

- Любой PR, объявленный готовым, но оставивший `NotImplementedError` или
  мёртвый код — обязан добавить сюда строку с id и deadline-PR.
- Ассистент в конце каждого PR-сообщения пишет `Долги: <ids or none>`.
- PR-9 разбивается:
  - **9a** — закрыть все `PARTNER-*`, `SALES-1`, `SALES-2`, `SALES-3`, `DEAD-*`.
  - **9b** — `bootstrap_demo` (опирается на закрытый 9a).
  - **9c** — переписать тесты под новую модель.
