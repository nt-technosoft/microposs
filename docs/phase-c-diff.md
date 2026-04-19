# Фаза C — Diff Vacuum Model ↔ текущая кодовая база

> Источник: [vacuum-model.md](vacuum-model.md) vs `backend/apps/*/models.py` на момент коммита `3bc416f`.
>
> **Статус проекта:** bootstrap (до первого продакшн-клиента). Рабочих данных нет → миграция данных не требуется, только модельная.
>
> **Легенда:**
> - ✅ **MATCH** — есть 1:1 или с минимальными отличиями (переименования полей).
> - ✏️ **RENAME** — сущность есть, нужно переименование.
> - 🔧 **REWORK** — сущность есть, но семантика значительно расходится — переделка.
> - ➕ **ADD** — отсутствует, нужно создать.
> - ❌ **DROP** — есть в коде, не нужна в vacuum-модели (удалить или deprecate).
> - ⚠️ **DANGER** — модель хранит то, что vacuum-модель требует вычислять (источник расхождений).

---

## 1. Сводная таблица по сущностям

| Vacuum Model | Текущая модель | Вердикт | Комментарий |
|---|---|---|---|
| `Product` | `catalog.Product` | ✅ MATCH | `base_price`, `pricing_mode` совпадают (коды choices отличаются — `DEFAULT_EDITABLE` vs `EDITABLE`, привести к vacuum). |
| `Product.pricing_mode` choices | `ASK_EACH_SALE` / `DEFAULT_EDITABLE` / `FIXED_LOCKED` | ✏️ RENAME | Привести к vacuum: `ALWAYS_ASK` / `EDITABLE` / `FIXED`. |
| `ProductVariant` | `catalog.ProductVariant` | ✅ MATCH | Используется как целевой объект Lot — vacuum использует Product, но вариация нужна. Оставляем. |
| `Warehouse` (ASOSIY/DOKON) | `inventory.Location` | ✏️ RENAME | `Location` → `Warehouse`. Choices `warehouse/store` → vacuum `STORAGE/SHOP`. По содержанию совпадает. |
| `Procurement` | `inventory.Receipt` | 🔧 REWORK | См. блок «Receipt → Procurement» ниже. |
| `ProcurementItem` | `inventory.ReceiptLine` | ✏️ RENAME + добавить `currency`, `fx_rate`. |
| `ProcurementExpense` | отсутствует (частично `finance.Expense`) | ➕ ADD | Vacuum: `CUSTOMS/FREIGHT/INSURANCE/STORAGE/OTHER` с `allocation_method`. Сейчас расходы прихода не выделены в сущность. |
| `ProcurementBalance` | отсутствует | ➕ ADD | Новая сущность (общий котёл). |
| `BalanceContribution` | отсутствует | ➕ ADD | |
| `BalanceWithdrawal` | отсутствует | ➕ ADD | |
| `Lot` | `inventory.Lot` | 🔧 REWORK | См. блок «Lot» ниже. |
| `Lot.quantity_by_location` | нет (есть `location` FK + `quantity_remaining`) | 🔧 REWORK | Критично: текущая модель = Lot на одном складе. Vacuum: Lot живёт на всех складах через Map. Либо Map-поле, либо отдельная таблица `LotStock(lot, warehouse, qty)`. |
| `Lot.landed_cost_per_unit` | нет (есть `cost_per_unit`) | ➕ ADD | Нужно 2 цены: `unit_purchase_price` + `landed_cost_per_unit`. Текущее `cost_per_unit` = landed, нужно добавить purchase. |
| `Lot.contract_snapshot` | нет | ➕ ADD | Immutable snapshot долей прибыли на момент RECEIVED. |
| `StockTransfer` | `inventory.StockMovement(type=transfer)` | 🔧 REWORK | Сейчас — лог движений. Vacuum: отдельная сущность с `lines` (несколько Lot за одно перемещение). |
| `StockDisposal` | `inventory.StockMovement(type=writeoff)` | 🔧 REWORK | Аналогично: отдельная сущность с распределением убытка по `capital_share` (шариатский инвариант). |
| `Sale` | `sales.Sale` | 🔧 REWORK | См. блок «Sale» ниже. |
| `SaleLine` | `sales.SaleLine` | ✏️ RENAME + добавить `profit_distribution_snapshot`, `unit_purchase_price`, переименовать `cost_per_unit` → `unit_landed_cost`. |
| `SalePayment` | нет (есть `Sale.payment_method`) | ➕ ADD | Критично: vacuum требует 0..N SalePayment на Sale с `method`/`currency`/`role`. Сейчас — один enum на Sale. См. блок «Sale». |
| `Receivable` (per customer) | `customers.Customer.outstanding_balance` | ⚠️ DANGER + 🔧 REWORK | Сейчас хранимый скаляр. Vacuum: отдельная сущность `Receivable` + `ReceivableEntry` (мультивалютная). |
| `ReceivableEntry` | `customers.CustomerPayment` (частично) | 🔧 REWORK | `CustomerPayment` = только REPAYMENT. Нужны также `DEBT_ACCRUED`, `ADJUSTMENT`, `WRITE_OFF`. |
| `Return` + `ReturnLine` | `sales.SaleReturn` + `sales.SaleReturnLine` | ✏️ RENAME + расширение | Добавить `resolution: RESTOCK | DISPOSE` (сейчас — `condition: good/damaged` на строке). Поднять на уровень Return. |
| `Refund` | нет | ➕ ADD | Отдельная сущность возврата денег (`CASH | PLASTIK | RECEIVABLE_OFFSET`). |
| `CashAccount` | нет (есть `finance.Account` через COA) | ➕ ADD | Vacuum: моно-валютные кошельки KASSA SOM / KASSA DOLLAR / PLASTIK SOM. Сейчас — Chart of Accounts, а не реальные кассы. |
| `CashEntry` | нет (есть `finance.JournalLine` через COA) | ➕ ADD | Лог движений по CashAccount. Можно переиспользовать JournalLine через `finance.Account(kind=CASH)`. См. блок «Finance». |
| `CurrencyExchange` | нет | ➕ ADD | `PUL AYRIBOSHLASH`. Явная операция. |
| `OperatingExpense` | `finance.Expense` | ✅ MATCH | Семантика совпадает (отделён от Procurement). Возможно, добавить явный enum category + инвариант `procurement_id is None`. |
| `DividendPayment` | `investors.InvestorProfitRecord(type=capital_return)` (частично) | 🔧 REWORK | Отдельная сущность нужна: выплата ≠ начисление. Сейчас confused. |
| `OwnerContribution` | нет | ➕ ADD | Пополнение кассы из личных средств оператора. |
| `InvestmentContract` | `investors.InvestorContract` | 🔧 REWORK | См. блок «Contract» ниже. |
| `ProcurementPartnerLedger` + `PartnerLedgerEntry` | `investors.InvestorProfitRecord` | 🔧 REWORK | Нужен per-Procurement ledger с типизированными entries (`CAPITAL_IN/OUT`, `PROFIT_ACCRUED/REVERSED`, `DIVIDEND_PAID`, `LOSS_INCURRED`). Сейчас — плоский список с грубыми типами. |
| `Partner` (abstract: investor ИЛИ operator) | `investors.Investor` + ничего для оператора | ➕ ADD | Vacuum: партнёр = любой участник (инвестор ИЛИ оператор). Нужна общая абстракция `Partner` или использовать `Investor` + виртуальный оператор tenant. |
| `Supplier` | `suppliers.Supplier` | ✅ MATCH | `outstanding_balance` скаляр → будущая замена на `Payable` (отложено). |
| `ExchangeRate` | `finance.ExchangeRate` | ✅ MATCH | Подходит как источник `fx_rate` в транзакциях. |
| `JournalEntry`/`JournalLine` | `finance.JournalEntry`/`JournalLine` | ✅ MATCH | Остаются инфраструктурой (шариатский инвариант #10). |
| `OutboxEvent` | есть в `apps.core` (предположительно) | ✅ MATCH | Оставляем. |

---

## 2. Проблемные блоки (деталь)

### 2.1. `Receipt` → `Procurement`

**Расхождения:**

| Поле | Receipt (сейчас) | Procurement (vacuum) | Действие |
|---|---|---|---|
| `receipt_type` | `BUSINESS_OWNED / MUDARABA / MUSHARAKA / SUPPLIER_PURCHASE / CONSIGNMENT` | `OWN_FUNDS / PARTNERSHIP / MUSHARAKA / DISTRIBUTOR` | Переименовать/консолидировать: `BUSINESS_OWNED + SUPPLIER_PURCHASE` = `OWN_FUNDS`; `MUDARABA` удаляется (покрывается `PARTNERSHIP` с mudaraba_ratio < 1); `CONSIGNMENT` → `DISTRIBUTOR` (отложено). |
| `status` | `draft / confirmed` | `OPEN / RECEIVED / CLOSED / CANCELLED` | Расширить: `confirmed → RECEIVED`. Добавить `OPEN` (фаза капитала) и `CLOSED` (все Lot распроданы). |
| `investor_contract` FK | глобальный контракт | `agreement` **встроен в Procurement** | Разорвать FK-к-глобальному-контракту. Контракт per-Procurement. |
| `operation_amount / fx_rate_snapshot` | snapshot общей суммы | не нужно на Procurement | Суммы хранятся в `ProcurementBalance` и `ProcurementItem`. На Procurement убираем. |
| `ImmutableMixin` | есть (после confirmed) | есть (после RECEIVED) | Semantics совпадает. |
| `client_request_id` | ✅ | ✅ | Оставить. |

**Action:** переименовать таблицу `inventory_receipt` → `partnerships_procurement` (новый app `partnerships`), полный rework.

### 2.2. `Lot`

**Самый критичный блок.** Текущая модель: один Lot на один склад. Vacuum: Lot — единая идентичность с распределением по складам.

**Варианты:**

- **A. `LotStock(lot, warehouse, qty_remaining)`** — реляционная декомпозиция, индексы простые, миграции чистые. Рекомендую.
- **B. `JSONField quantity_by_location`** — ближе к vacuum, но индексирование под FIFO-выборку хуже.

**Рекомендую A.** Добавить в Lot:
- `unit_purchase_price` (новое, из ProcurementItem)
- `landed_cost_per_unit` (переименовать `cost_per_unit`)
- `contract_snapshot` JSONField
- `received_at` для FIFO
- Удалить прямой `location` FK → перенести в `LotStock`

**`StockMovement`** в текущем виде (лог всех движений) можно **оставить как audit log**, но высшего уровня операции (`StockTransfer`, `StockDisposal`) должны быть отдельными сущностями поверх движений.

### 2.3. `Sale` / `SaleLine` / `SalePayment`

**Критическое расхождение:** текущая `Sale.payment_method` = один из `cash/card/credit`. Vacuum — 0..N `SalePayment` на Sale, мультивалютные.

**Рекомендую:**

1. Удалить `Sale.payment_method`, `customer_has_existing_debt`, `operation_amount`, `fx_rate_snapshot`, `functional_amount_uzs`.
2. Оставить `Sale`: `status / customer / pos_session / sold_by / total_amount / total_cogs / client_request_id / notes`.
3. Добавить `location FK Warehouse` на Sale (vacuum: продажа привязана к складу).
4. Создать `SalePayment(sale, amount, currency, fx_rate, method, role, account, date)`.
5. Статус оплаты (PAID/PARTIAL/UNPAID) — вычисляемый.
6. `SaleLine`: добавить `unit_purchase_price`, `unit_landed_cost` (переименовать `cost_per_unit`), `profit_distribution_snapshot` (JSONField, Map<partner_id, amount>).

**`PosSession`** — не в vacuum-модели, но это оперативная сущность (смена кассира). Оставить; интегрировать SalePayment с PosSession через `CashEntry`.

### 2.4. `InvestorContract` → `InvestmentContract` (встроенный)

**Текущая модель:**
- Глобальный контракт с `default_profit_ratio` на investor.
- Один `contract_type`: `MUDARABA` или `MUSHARAKA` (неверно — это не взаимоисключающее; vacuum использует hybrid).

**Vacuum модель:**
- Контракт **per-Procurement** (встроен).
- Параметры: `partners[{partner, role, planned_capital_share, profit_share}]` + `mudaraba_ratio` + `loss_rule='by_capital'`.
- `mudaraba_ratio` вычисляется.

**Action:**
1. Сохранить `Investor` как сущность партнёра (справочник).
2. Заменить `InvestorContract` на `InvestmentContract` (встроенная в Procurement как 1:1 или как JSON).
3. Добавить таблицу `ContractPartner(contract, partner, role, planned_capital_share, profit_share)`.
4. Разорвать текущий FK `Receipt.investor_contract` (глобальный) → контракт теперь локален к Procurement.

### 2.5. `InvestorProfitRecord` → `ProcurementPartnerLedger`

**Текущее:** плоский список с `record_type: profit / loss / capital_return`.

**Vacuum:** per-Procurement × Partner ledger с 6 типами: `CAPITAL_IN / CAPITAL_OUT / PROFIT_ACCRUED / PROFIT_REVERSED / DIVIDEND_PAID / LOSS_INCURRED`.

**Action:** полная переделка. Из текущих данных (в bootstrap нет) ничего не мигрируется.

### 2.6. `InvestorSummary`

⚠️ **DANGER.** Хранит `total_invested / total_profit / total_losses / business_owes`. Vacuum требует: **все агрегаты — computed view, не храним**.

**Action:** удалить `InvestorSummary` как модель. Заменить на ORM-level computed (annotation/view). Если нужно кешировать — делать materialized view или periodic refresh, но не хранить как истину.

То же касается `finance.DailySummary` и `finance.CashFlowSummary` — это кеш, не источник истины. Оставить с пометкой «derived, rebuild-safe».

### 2.7. `Customer.outstanding_balance`

⚠️ **DANGER.** Скаляр на клиенте. Нужно: `Receivable` + `ReceivableEntry`.

**Action:**
1. Создать `Receivable(customer, balances=Map<currency, Decimal>)`.
2. Создать `ReceivableEntry(receivable, date, amount, currency, type, source_ref, due_date)`.
3. Миграция `CustomerPayment` → `ReceivableEntry(type=REPAYMENT)`.
4. Удалить `Customer.outstanding_balance` (вычисляется из Receivable).

### 2.8. `finance.Account` + `CashAccount`

**Конфликт:** сейчас есть Chart of Accounts (`finance.Account`) с типами `asset/liability/equity/income/expense`. Vacuum вводит `CashAccount` (KASSA SOM, PLASTIK SOM) как физические кошельки.

**Решение:**
- Оставить `finance.Account` как COA для JournalEntry (bookkeeping слой).
- Создать `CashAccount` как **операционный** слой (реальные кассы/счета).
- Связь: каждая `CashAccount` мэпится на соответствующий `finance.Account(type=asset)`.
- `CashEntry` — операционный лог движений по CashAccount; параллельно пишется `JournalEntry` для бухгалтерии.

---

## 3. Что удалить полностью

| Модель | Причина |
|---|---|
| `inventory.Receipt.MUDARABA` choice | Покрывается `PARTNERSHIP` + `mudaraba_ratio`. Не нужен отдельный тип. |
| `inventory.ReceiptParticipant` | Заменяется на `ContractPartner` + `BalanceContribution`. Другая семантика. |
| `sales.Sale.payment_method` | Заменяется на `SalePayment`. |
| `sales.Sale.customer_has_existing_debt` | Вычисляется из `Receivable`. |
| `investors.InvestorSummary` | Derived, не храним. Заменить на view. |
| `customers.Customer.outstanding_balance` | Derived из Receivable. |
| `suppliers.Supplier.outstanding_balance` | Derived из Payable (когда появится). |
| `investors.InvestorContract.default_profit_ratio` | Контракт теперь per-Procurement, с полной структурой partners. |
| `investors.InvestorContract.final_settlement` | Derived из PartnerLedger. |

---

## 4. Объём изменений

### Модели: 27 vacuum entities vs ~22 текущих

- **Добавить новые:** 13 (ProcurementBalance, BalanceContribution, BalanceWithdrawal, ProcurementExpense, LotStock, StockTransfer, StockDisposal, SalePayment, Refund, CashAccount, CashEntry, CurrencyExchange, OwnerContribution, DividendPayment, ContractPartner, Receivable, ReceivableEntry, ProcurementPartnerLedger, PartnerLedgerEntry).
- **Переработать:** 7 (Receipt→Procurement, Lot, Sale, SaleLine, SaleReturn, InvestorContract, InvestorProfitRecord).
- **Удалить:** 5 (InvestorSummary, ReceiptParticipant, outstanding_balance поля, Sale.payment_method, др.).
- **Переименовать:** 4 (Location→Warehouse, ReceiptLine→ProcurementItem, pricing_mode choices, Return fields).

### Миграции данных
- **Не нужны** (bootstrap, нет рабочих данных).
- `bootstrap_demo` management command придётся переписать под новую схему.

### Frontend
- API клиенты (`src/api/*`) — переписать под новые эндпоинты для всех изменённых сущностей.
- Экраны intake/investors/sales/finance — затронуты все. Серьёзный rework UX.

### Тесты
- Сервисный слой (`services.py`) каждого app — переписать под новые сущности.
- Фикстуры/фабрики — все обновить.

---

## 5. Риски и открытые вопросы

1. **Partner абстракция.** Vacuum оперирует `partner_id` в контракте — и инвестор, и оператор. Как представить «оператора» в БД? Варианты: (a) каждый tenant имеет виртуального Investor-`OPERATOR`; (b) новая таблица `Partner`, Investor становится её подтипом. **Рекомендую (b)** — чище семантика.

2. **JournalEntry source of truth vs CashEntry.** Нужно чёткое правило: CashEntry — операционный источник, JournalEntry — автогенерируется из CashEntry (через сигнал или service-layer hook). Или наоборот. Решение влияет на порядок реализации.

3. **Consignment (DISTRIBUTOR)** отложен в vacuum-модели → текущий код `Receipt.CONSIGNMENT` + `ConsignmentAgreement` пока заморозить (не удалять, не развивать).

4. **Tenant isolation.** Vacuum не обсуждает, но все новые модели должны наследовать `TenantModel` (как текущие). Проверить в Фазе D.

5. **app разбиение.** Новые сущности просятся в новый app `partnerships` (Procurement, ProcurementBalance, ProcurementPartnerLedger, ContractPartner, DividendPayment). Текущий `investors` останется как справочник `Investor`/`Partner`.

---

## 6. Следующий шаг — Фаза D

План миграции (PR sequence) с учётом зависимостей. Предварительный порядок (будет детализирован в Фазе D):

1. **PR-1 Core abstractions:** Partner model, Warehouse (rename), core enums.
2. **PR-2 Procurement skeleton:** Procurement, ProcurementItem, ProcurementExpense, InvestmentContract, ContractPartner, ProcurementBalance + Contribution/Withdrawal.
3. **PR-3 Lot rework:** новый Lot + LotStock, ContractSnapshot, landed_cost pipeline.
4. **PR-4 Sale rework:** SalePayment, Sale без payment_method, SaleLine с profit_distribution_snapshot.
5. **PR-5 Ledger rework:** ProcurementPartnerLedger + entries, DividendPayment, удаление InvestorSummary.
6. **PR-6 Receivable:** Receivable + ReceivableEntry, удаление outstanding_balance.
7. **PR-7 Cash layer:** CashAccount, CashEntry, CurrencyExchange, Refund, OwnerContribution, OperatingExpense polish.
8. **PR-8 Returns:** Return + ReturnLine + resolution, интеграция с PartnerLedger (PROFIT_REVERSED, LOSS_INCURRED).
9. **PR-9 bootstrap_demo + фикстуры** переписать.
10. **PR-10 Frontend API/types/stores** — reuse foundation (tokens, shared/base components, app shell, router meta idea), rewrite contracts and state tied to legacy Receipt/InvestorSummary model.
11. **PR-11 Frontend feature/views** — controlled migration of domain screens and flows under vacuum-model, not a full visual redesign.
12. **PR-12 Excel/final cleanup** — separate discovery/design track under user control; not part of the ordinary frontend implementation wave.

---

*Документ составлен: 2026-04-18. Фаза C (Diff) закрыта. Ожидает Фазу D (план миграции) и согласования.*
