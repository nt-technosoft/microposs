# Фаза D — План rework под Vacuum Model

> **Самодостаточный документ.** Если лимиты Claude Code кончились — можно продолжить в Codex / Cursor / другом LLM-инструменте, используя только этот файл + [vacuum-model.md](vacuum-model.md) + [phase-c-diff.md](phase-c-diff.md) + [phase-c-full-analysis.md](phase-c-full-analysis.md).
>
> **Ветка:** `vacuum-rework` (создана от `codex/bootstrap @ e7aac1f`). Страховочный тег: `pre-vacuum-rework`.
>
> **Принцип исполнения:** один PR = один PR-раздел этого документа. Каждый PR оставляет код в рабочем состоянии (тесты проходят, миграции катятся). Никаких «половинчатых» состояний между PR.

---

## 0. Предварительные архитектурные решения

Решены сейчас, чтобы не спотыкаться в каждом PR.

### 0.1. Partner абстракция

**Решение:** новая таблица `core.Partner` как общий супертип. `investors.Investor` становится 1:1 профилем поверх Partner с ролью `INVESTOR`. Оператор tenant'а создаётся автоматически как `Partner(role=OPERATOR)` при создании `Business`.

**Схема:**
```
core.Partner:
  tenant_id FK
  role: INVESTOR | OPERATOR
  display_name
  user FK auth.User (nullable — для не-юзер партнёров)
  is_active

investors.Investor (adjusted):
  partner: OneToOneField(Partner)   # PRIMARY KEY
  phone, email, notes
  # удаляются: user FK, name (через partner.display_name)
```

**Почему:** InvestmentContract ссылается на партнёров разных ролей одинаково. Без общей абстракции — constraint'ы и JOIN'ы становятся уродливыми.

### 0.2. Новый app `partnerships`

Создаём `backend/apps/partnerships/`. Туда переезжают:
- `Procurement` (был `inventory.Receipt`)
- `ProcurementItem` (был `inventory.ReceiptLine`)
- `ProcurementExpense` (новая)
- `ProcurementBalance`, `BalanceContribution`, `BalanceWithdrawal`
- `InvestmentContract`, `ContractPartner`
- `ProcurementPartnerLedger`, `PartnerLedgerEntry`
- `DividendPayment`

**Почему:** доменная связность высокая, смысловое ядро — партнёрский капитал. Выделение отдельного app делает границы явными.

`investors` остаётся справочником (Investor, его профиль). Бизнес-логика партнёрства — в `partnerships`.

### 0.3. JournalEntry vs CashEntry — порядок записи

**Решение:** CashEntry — первичный источник. JournalEntry автогенерируется в том же service call через явный вызов `record_journal_from_cash_entry(entry)`. Не через signal (непредсказуемость порядка в транзакциях).

```python
@transaction.atomic
def record_sale(...):
    sale = Sale.objects.create(...)
    for payment in payments:
        cash_entry = CashEntry.objects.create(...)
        record_journal_from_cash_entry(cash_entry, operation=sale)
    publish_event('sale.confirmed', sale_id=sale.id)
```

### 0.4. Migrations strategy

**Bootstrap stage — прямые миграции.** Локальную БД дропаем свободно. В каждом PR:
1. Меняем модели.
2. `python manage.py makemigrations <app>`.
3. Коммитим миграции вместе с кодом.
4. В README PR указываем: «потребуется `migrate --fake-initial` ИЛИ drop + recreate».

На этом этапе **не тратим время на reversibility / data migrations.**

### 0.5. Frontend порядок

Backend до PR-9 (включительно) → фронт не трогаем (старый UI сломается, но сервер работает через DRF browsable API). После PR-9 — фронтовая волна идёт последовательно через PR-10 → PR-11.

**Execution strategy for frontend:**
- **Reuse foundation**: app shell, router meta idea, auth/session backbone, design tokens, shared/base components, feedback primitives, i18n/theme/session controls.
- **Rewrite feature/domain**: page flows, domain views, orchestration-heavy stores, transport contracts tied to legacy Receipt / InvestorSummary era.
- **Не делаем full redesign**: PR-10/11 — это controlled migration под vacuum-model, а не визуальный снос продукта.
- **PR-12 не идёт в той же волне**: Excel/final cleanup выносится в отдельный discovery/design трек под личным контролем пользователя.

### 0.6. Что выключаем на время rework

Чтобы не поддерживать мёртвый код:
- `apps/core/excel_alignment.py` + все `excel_*` management commands + тесты — **не удаляем, но в PR-1 помечаем `_DISABLED_DURING_REWORK = True`** на входных точках. Импорты не ломаем.
- `Receipt.CONSIGNMENT` + `suppliers.ConsignmentAgreement` — оставляем модели, но в PR-2 помечаем `# frozen: DISTRIBUTOR is deferred, do not develop`.
- `risk.services.create_writeoff` — переписываем в PR-8 (как StockDisposal).

---

## 1. PR Sequence (12 PR)

Формат каждого PR:
- **Цель** — 1-2 строки.
- **Файлы** — какие создаём/меняем/удаляем.
- **Доменные действия** — модели, миграции, services.
- **Приёмка** — как убедиться что PR работает.
- **Риск отката** — что может пойти не так.

---

### PR-1: Core abstractions (Partner, Warehouse rename, enum alignment)

**Цель:** подготовить фундамент. Без этого PR ничего дальше не поедет.

**Файлы:**
- `backend/apps/core/models.py` — добавить `Partner`.
- `backend/apps/core/migrations/0004_partner.py` — миграция.
- `backend/apps/inventory/models.py` — переименовать `Location` → `Warehouse`, choice `warehouse/store` → `STORAGE/SHOP`.
- `backend/apps/inventory/migrations/0005_rename_location_warehouse.py`.
- `backend/apps/catalog/models.py` — pricing_mode choices: `ASK_EACH_SALE → ALWAYS_ASK`, `DEFAULT_EDITABLE → EDITABLE`, `FIXED_LOCKED → FIXED`.
- `backend/apps/catalog/migrations/0003_rename_pricing_modes.py`.
- Обновить все `services.py`, `serializers.py`, `views.py`, `admin.py`, которые ссылаются на `Location` / старые pricing_mode константы.

**Доменные действия:**
```python
# core/models.py
class Partner(TenantModel):
    class Role(models.TextChoices):
        INVESTOR = 'INVESTOR', 'Инвестор'
        OPERATOR = 'OPERATOR', 'Оператор'
    role = models.CharField(max_length=20, choices=Role.choices)
    display_name = models.CharField(max_length=255)
    user = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    class Meta:
        db_table = 'core_partner'
        indexes = [models.Index(fields=['tenant', 'role', 'is_active'])]
```

**Приёмка:**
- `python manage.py migrate` проходит на чистой БД.
- `python manage.py makemigrations --check` = no changes.
- Все существующие тесты либо проходят, либо помечены `@pytest.mark.skip(reason='awaits PR-N')`.

**Риск:** цепная реакция от rename Location. Mitigation: grep по коду + frontend на `'Location'` перед началом.

---

### PR-2: Procurement skeleton + InvestmentContract + ProcurementBalance

**Цель:** родить новый app `partnerships` с ядром партнёрского прихода.

**Файлы:**
- Создать `backend/apps/partnerships/` (`__init__.py`, `apps.py`, `models.py`, `services.py`, `admin.py`, `migrations/`).
- Зарегистрировать в `config/settings/base.py` → `INSTALLED_APPS`.
- `backend/apps/partnerships/models.py`:
  - `Procurement` (status OPEN/RECEIVED/CLOSED/CANCELLED, type OWN_FUNDS/PARTNERSHIP/MUSHARAKA/DISTRIBUTOR, supplier FK nullable)
  - `ProcurementItem` (product_variant FK, quantity, unit_purchase_price, currency, fx_rate)
  - `ProcurementExpense` (expense_type, amount, currency, fx_rate, allocation_method)
  - `InvestmentContract` (1:1 к Procurement, mudaraba_ratio, loss_rule='by_capital', planned_budget)
  - `ContractPartner` (contract FK, partner FK, role, planned_capital_share, profit_share)
  - `ProcurementBalance` (1:1 к Procurement, balances JSONField Map<currency, Decimal>)
  - `BalanceContribution` (balance FK, partner FK, amount, currency, fx_rate, date)
  - `BalanceWithdrawal` (balance FK, partner FK, amount, currency, fx_rate, date, reason)
- `backend/apps/partnerships/services.py` — stubs: `open_procurement`, `add_contribution`, `add_withdrawal`, `receive_procurement` (raise `NotImplementedError`).

**Действия:**
- НЕ трогаем старый `inventory.Receipt` в этом PR. Он остаётся рабочим параллельно (для bootstrap_demo, старых тестов).
- Новый домен живёт рядом.

**Приёмка:**
- Миграция проходит.
- В Django admin видны все новые модели.
- Ручной smoke: создать Procurement(status=OPEN) через shell, добавить Contribution, проверить balance update.

**Риск:** пересечение с `inventory.Receipt` в bootstrap_demo. Mitigation: bootstrap_demo не трогаем до PR-9.

---

### PR-3: Lot rework — LotStock, landed_cost, contract_snapshot

**Цель:** Lot становится соответствующим vacuum-модели (multi-warehouse через LotStock, 2 цены, immutable snapshot долей).

**Файлы:**
- `backend/apps/inventory/models.py`:
  - `Lot` — добавить `unit_purchase_price`, переименовать `cost_per_unit` → `landed_cost_per_unit`, добавить `contract_snapshot` (JSONField), добавить `received_at`, **удалить `location` FK, удалить `quantity_remaining`**.
  - Новая модель `LotStock(lot FK, warehouse FK, quantity_remaining)`.
- Миграция: `0006_lot_rework.py`.
- `backend/apps/inventory/services.py` — `confirm_receipt` временно сломан (raise `NotImplementedError('use partnerships.receive_procurement')`).
- `backend/apps/inventory/services.py` — новая функция `allocate_lot(lot, warehouse, qty)` для FIFO-подборки.

**Действия:**
- Заменить все запросы `Lot.objects.filter(location=X, is_active=True)` на `LotStock.objects.filter(warehouse=X, quantity_remaining__gt=0)`.
- Старый `receipt_line` FK в Lot сохраняется для обратной связи, **добавить** `procurement_item` FK (nullable, заполнится после PR-4/9).

**Приёмка:**
- Миграция катится.
- `LotStock.objects.sum('quantity_remaining')` == `Lot.quantity_initial` инвариант проверяется тестом.
- Старый test_api_smoke.py помечен skip.

**Риск:** `sales.services.create_sale` использует Lot.location — сломается. Mitigation: в этом PR `create_sale` тоже помечаем `raise NotImplementedError('awaits PR-4')`.

---

### PR-4: Sale rework — SalePayment, location, profit_distribution_snapshot

**Цель:** Sale становится multi-payment, привязан к warehouse, SaleLine хранит полное распределение прибыли.

**Файлы:**
- `backend/apps/sales/models.py`:
  - `Sale` — удалить `payment_method`, `customer_has_existing_debt`, `operation_amount`, `fx_rate_snapshot`, `functional_amount_uzs`. Добавить `location FK Warehouse`, `date DateTimeField`.
  - `SaleLine` — переименовать `cost_per_unit` → `unit_landed_cost`, добавить `unit_purchase_price`, `profit_distribution_snapshot` (JSONField Map<partner_id, Decimal>).
  - **Новая модель** `SalePayment(sale, date, amount, currency, fx_rate, method, role, account_id)`.
- Миграция: `0003_sale_rework.py`.
- `backend/apps/sales/services.py`:
  - Переписать `create_sale(data)`:
    1. Создать Sale (DRAFT).
    2. Для каждой line — FIFO по LotStock на `sale.location`, если не хватает → `InsufficientStockError`.
    3. На `confirm_sale(sale)`: списать LotStock, посчитать profit per SaleLine через `Lot.contract_snapshot`, зафиксировать `profit_distribution_snapshot`, записать SalePayment'ы, вызвать `record_journal_from_cash_entry`, записать PartnerLedgerEntry (PROFIT_ACCRUED), обновить Receivable если есть долг, publish `OutboxEvent`.
- `backend/apps/sales/serializers.py` — новый `SalePaymentSerializer`, SaleSerializer с nested payments.

**Приёмка:**
- Unit test: создать Procurement + LotStock → продажа 1 товар NAQD → JournalEntry + PartnerLedgerEntry + CashEntry созданы.
- Unit test: мульти-валютная оплата (1 SalePayment UZS + 1 SalePayment USD).
- Unit test: частичная оплата → Receivable создан.

**Риск:** interaction с PartnerLedger (которого ещё нет — PR-5). Mitigation: в PR-4 записываем в plain `InvestorProfitRecord` (старая модель), в PR-5 делаем миграцию данных.

---

### PR-5: ProcurementPartnerLedger + DividendPayment + удаление InvestorSummary

**Цель:** Ledger партнёра по каждому приходу. Убираем хранимый InvestorSummary.

**Файлы:**
- `backend/apps/partnerships/models.py`:
  - `ProcurementPartnerLedger(procurement, partner)` — unique_together.
  - `PartnerLedgerEntry(ledger, date, amount, currency, type, source_ref)` — type: CAPITAL_IN/CAPITAL_OUT/PROFIT_ACCRUED/PROFIT_REVERSED/DIVIDEND_PAID/LOSS_INCURRED.
  - `DividendPayment(partner, procurement, amount, currency, fx_rate, paid_from FK CashAccount, date)`.
- Миграция: партнёрская `0002_ledger_and_dividend.py`.
- `backend/apps/partnerships/services.py`:
  - `append_ledger_entry(ledger, type, amount, source_ref)`.
  - `get_partner_aggregate(partner)` — computed view через raw SQL / annotations (заменяет InvestorSummary).
  - `pay_dividend(partner, procurement, amount, from_account)` с инвариантом `amount ≤ profit_pending_payout`.
- Удалить `investors.InvestorSummary` модель + миграция `0002_drop_summary.py`.
- Удалить `investors.InvestorProfitRecord` ПОСЛЕ миграции данных в `PartnerLedgerEntry` (но проще — на bootstrap stage просто дропаем без миграции).
- Обновить `sales.services.create_sale` — писать в `PartnerLedgerEntry(PROFIT_ACCRUED)` вместо `InvestorProfitRecord`.

**Приёмка:**
- Создать Procurement с 2 партнёрами, провести 3 продажи → `get_partner_aggregate` возвращает корректные суммы по каждому партнёру.
- DividendPayment с amount > pending → `ValidationError`.
- Computed aggregate view работает без InvestorSummary.

**Риск:** investor cabinet frontend ожидает InvestorSummary endpoint. Mitigation: endpoint остаётся, но отдаёт computed view — прозрачно для фронта (в PR-11 фронт переедет на новые поля).

---

### PR-6: Receivable + ReceivableEntry, убрать outstanding_balance

**Цель:** Дебиторка как ledger, не скаляр.

**Файлы:**
- `backend/apps/customers/models.py`:
  - Новая `Receivable(customer OneToOne, balances JSONField Map<currency, Decimal>)`.
  - Новая `ReceivableEntry(receivable, date, amount, currency, fx_rate, type, source_ref, due_date)` — type: DEBT_ACCRUED/REPAYMENT/ADJUSTMENT/WRITE_OFF.
  - Удалить `Customer.outstanding_balance`.
  - `CustomerPayment` — оставить (как historical), но сервис `record_customer_payment` теперь пишет `ReceivableEntry(REPAYMENT)` + `CashEntry`.
- Миграция `0003_receivable.py`.
- `backend/apps/customers/services.py` — обновить `record_customer_payment`, добавить `get_customer_debt_summary` (computed через ReceivableEntry).
- `backend/apps/sales/services.py` — при частичной оплате Sale → создать `Receivable` если нет и `ReceivableEntry(DEBT_ACCRUED)`.

**Приёмка:**
- Продажа в долг → Receivable создан + ReceivableEntry(DEBT_ACCRUED).
- Погашение → ReceivableEntry(REPAYMENT) + CashEntry IN.
- Две продажи в разных валютах одному клиенту → balances имеет 2 ключа.

**Риск:** frontend ожидает `Customer.outstanding_balance`. Mitigation: добавить `@property outstanding_balance` на Customer, computed.

---

### PR-7: Cash layer — CashAccount, CashEntry, CurrencyExchange, Refund, OwnerContribution

**Цель:** операционный слой касс. JournalEntry + COA остаются как bookkeeping поверх.

**Файлы:**
- Решение: эти модели в `finance/models.py` (не новый app — они тесно связаны с JournalEntry).
- `backend/apps/finance/models.py`:
  - `CashAccount(name, currency, balance, kind, linked_account FK finance.Account)` — моно-валютный.
  - `CashEntry(account, direction IN/OUT, amount, date, source_ref_type, source_ref_id)`.
  - `CurrencyExchange(from_account, to_account, from_amount, from_currency, to_amount, to_currency, effective_rate, date)`.
  - `Refund(customer, date, amount, currency, fx_rate, account FK CashAccount, method CASH/PLASTIK/RECEIVABLE_OFFSET, return_ref FK nullable)`.
  - `OwnerContribution(amount, currency, to_account, date)`.
- `backend/apps/finance/services.py`:
  - `record_journal_from_cash_entry(cash_entry, operation_type, operation_id)` — автогенерация JournalEntry.
  - `exchange_currency(from_account, to_account, from_amount, rate)` — атомарная операция.
  - `refund_customer(customer, amount, method, account)` с инвариантом `Σ Refund per currency ≤ Σ SalePayment per currency` на уровне Sale.
- Default CashAccounts создаются в `bootstrap_tenant` при Business create: `KASSA_SOM`, `KASSA_DOLLAR`, `PLASTIK_SOM`.

**Приёмка:**
- Sale с CashEntry → JournalEntry автоматически.
- CurrencyExchange из SOM в USD → оба account balance меняются.
- Refund превышающий SalePayment → rejected.

**Риск:** OperatingExpense (`finance.Expense`) теперь должен идти через CashEntry. Обновить сервис `record_expense` — делегирует в CashEntry.

---

### PR-8: Return rework — RESTOCK/DISPOSE + интеграция с PartnerLedger

**Цель:** возвраты и утилизация с правильным шариатским распределением.

**Файлы:**
- `backend/apps/sales/models.py`:
  - `SaleReturn` → переименовать в `Return`. Добавить `resolution: RESTOCK | DISPOSE`, `reason: DEFECT/CLIENT_REFUSE/OTHER`.
  - Удалить `SaleReturnLine.condition` (решение поднято на Return).
  - Переименовать `SaleReturnLine` → `ReturnLine`.
- `backend/apps/sales/services.py`:
  - `process_return(sale_id, lines, resolution, reason)`:
    - Для каждой ReturnLine берём SaleLine → Lot → contract_snapshot.
    - **Если RESTOCK:**
      1. `LotStock.quantity_remaining += qty` на `sale.location`.
      2. Для каждого партнёра в `profit_distribution_snapshot` → `PartnerLedgerEntry(PROFIT_REVERSED)`.
      3. Refund или ReceivableEntry(ADJUSTMENT).
    - **Если DISPOSE:**
      1. `Lot.quantity_initial -= qty` (реально — `LotStock` не меняется, учитывается через StockDisposal).
      2. Если прибыль была начислена → `PROFIT_REVERSED` по `profit_share`.
      3. `loss = qty × landed_cost_per_unit`. Для каждого партнёра → `PartnerLedgerEntry(LOSS_INCURRED, amount = loss × capital_share[partner])`.
      4. Refund клиенту.
- `backend/apps/risk/services.py`:
  - `create_writeoff` → теперь вызывает `StockDisposal` service с тем же механизмом (DISPOSE без Return, чистый брак).
- Новая модель `StockDisposal` в `inventory/models.py` — для брака без продажи.

**Приёмка:**
- Тест: продажа 10 шт @ 100 (capital 70/30, profit 40/60) → возврат 3 шт RESTOCK → PROFIT_REVERSED у Устоза 3×100×40%, у Бекзода 3×100×60%.
- Тест: тот же сценарий DISPOSE → PROFIT_REVERSED + LOSS_INCURRED распределён 70/30.
- Инвариант: `Σ ReturnLine.qty ≤ SaleLine.qty`.

**Риск:** `SaleReturn` → `Return` rename затрагивает API. Mitigation: в DRF viewset сохранить старый URL `/api/sales/returns/` через алиас, фронт не ломается.

---

### PR-9: bootstrap_demo + тесты под новую схему

**Цель:** рабочая demo-data + минимальный test suite, без которых нельзя тестить дальше.

**Файлы:**
- `backend/apps/core/management/commands/bootstrap_demo.py` — полная переписка под новую схему:
  1. Business + User'ы.
  2. Partners: оператор Бекзод + инвестор Устоз.
  3. CashAccounts: KASSA_SOM, KASSA_DOLLAR, PLASTIK_SOM.
  4. Warehouses: ASOSIY (STORAGE), DOKON (SHOP).
  5. Customer (IN_HOUSE anonymous + 1 debt customer).
  6. Supplier, Category, Product, ProductVariant, DiscountReason.
  7. Procurement (type=PARTNERSHIP):
     - InvestmentContract с партнёрами 70/30, profit 40/60, mudaraba_ratio=4/7.
     - BalanceContribution: Устоз 700 USD, Бекзод 300 USD.
     - ProcurementItem: 50 шт Gul @ 10 USD.
     - ProcurementExpense: CUSTOMS 50 USD.
     - `receive_procurement` → balance=0 → Lot + LotStock + contract_snapshot.
  8. Sale (NAQD, 5 шт @ 20 USD) через новый `create_sale` + `confirm_sale`.
- Удалить старые тесты:
  - `test_api_smoke.py` → переписать минимально.
  - `test_financial_integrity.py` → переписать под новый JournalEntry flow.
  - `test_role_matrix.py` → обновить под новые endpoints.
  - Оставить `test_fx_rates.py`, `test_products_pricing_flow.py` (мин. изменения).
  - Оставить как skip: `test_excel_alignment_*`.
- Новые тесты:
  - `test_procurement_lifecycle.py` — open/receive/close + balance invariants.
  - `test_musharaka_mudaraba_formula.py` — формула на 3-5 кейсах.
  - `test_sale_multi_payment.py` — SalePayment сценарии.
  - `test_returns_shariah.py` — RESTOCK vs DISPOSE capital_share loss.
  - `test_partner_ledger.py` — computed aggregate корректность.

**Приёмка:**
- `python manage.py migrate --run-syncdb` на пустой БД + `bootstrap_demo` → всё до конца без ошибок.
- `python manage.py test` зелёный.
- В Django admin видна полная картина: Procurement с Ledger'ами, Sale с SalePayment'ами.

**Риск:** самый объёмный PR. Mitigation: можно разбить на 9a (bootstrap_demo) и 9b (tests).

---

### PR-10: Frontend — API clients + types + stores

**Цель:** синхронизация TypeScript слоя с новым backend без сноса foundation-слоя frontend.

**Scope strategy:** shared UI, tokens, app shell и базовые паттерны переиспользуем; меняем только contracts/types/api/stores, которые завязаны на старую доменную модель.

**Файлы:**
- `frontend/src/types/models.ts` — переписать под новые сущности:
  - Удалить: Receipt, ReceiptParticipant, InvestorSummary.
  - Добавить: Procurement, ProcurementItem, ProcurementExpense, ProcurementBalance, InvestmentContract, ContractPartner, BalanceContribution, BalanceWithdrawal, Lot (обновлённый), LotStock, SalePayment, Receivable, ReceivableEntry, PartnerLedgerEntry, DividendPayment, CashAccount, CashEntry, CurrencyExchange, Refund, Return, ReturnLine.
  - Обновить: Sale (без payment_method, с SalePayment[] nested), SaleLine (profit_distribution_snapshot), Customer (outstanding_balance → computed).
- `frontend/src/api/*.ts`:
  - Переименовать `inventory.ts` → `inventory.ts` (без изменений) + новый `partnerships.ts` для Procurement endpoints.
  - Обновить `sales.ts` — multi-payment payload.
  - Обновить `investors.ts` — per-procurement ledger endpoints.
  - Обновить `customers.ts` — Receivable drill-down.
  - Новый `cash.ts` — CashAccount, CurrencyExchange.
- `frontend/src/stores/*.ts`:
  - `cart.ts` — warehouse selector в state.
  - `sales.ts` — multi-SalePayment draft state.
  - `customers.ts` — computed outstanding.
  - Новый `partnerships.ts` — Procurement lifecycle state.

**Приёмка:**
- `pnpm typecheck` зелёный.
- Dev server запускается без runtime ошибок на главной странице.

**Риск:** часть views временно разойдётся с обновлёнными contracts/stores. Это ожидаемо, но не означает полный rewrite фронта: PR-11 фиксит только feature/domain слой, foundation остаётся.

---

### PR-11: Frontend views — intake → procurements, sales checkout, investor dashboard

**Цель:** UX под vacuum-модель без полного visual redesign всего продукта.

**Scope strategy:** переписываем доменные экраны, навигацию и пользовательские сценарии под новую модель данных; shared components, tokens и app shell не сносим, а используем как foundation.

**Файлы:**
- `frontend/src/modules/intake/` → переименовать в `procurements/`:
  - `ProcurementList.vue` — статусы OPEN/RECEIVED/CLOSED.
  - `ProcurementCreate.vue` — wizard: тип → партнёры → контракт (live калькулятор mudaraba_ratio) → товар → расходы → receive с balance=0 check.
  - `ProcurementDetail.vue` — balance, items, expenses, contract, ledger per partner.
- `frontend/src/modules/sales/views/CheckoutView.vue`:
  - Warehouse selector.
  - Multi-payment UI (добавить SalePayment кнопкой).
  - Мульти-валютные суммы.
- `frontend/src/modules/investors/views/InvestorDashboard.vue`:
  - Список Procurement'ов инвестора.
  - Агрегат (computed) по всем.
- `frontend/src/modules/investors/views/ProcurementDetail.vue` (investor scope):
  - Drill-down: балансы, товар на складе, ledger entries.
- `frontend/src/modules/more/views/CustomersView.vue`:
  - Receivable drill-down вместо скалярной суммы.
- `frontend/src/router/routes.ts` — обновить пути (`/intake/*` → `/procurements/*`).

**Приёмка:**
- Manual walkthrough: open procurement → add contributions → add items → receive → sale with partial payment → dividend payment → all flows работают.
- Investor login видит только свои Procurement'ы (403 на чужие).

**Риск:** UX сложный (Procurement wizard). Mitigation: сначала минимальный CRUD, потом wizard отдельно.

---

### PR-12: Excel pipeline разморозка + финальная чистка

**Статус подхода:** не обычный следующий implementation PR, а отдельный discovery/design трек под личным контролем пользователя.

**Цель:** вернуть Excel-импорт под новую схему + удалить временные stubs, но только после отдельной проработки mapping principles, source-of-truth rules, ambiguity handling и dry-run/mismatch reporting.

**Файлы:**
- `backend/apps/core/excel_alignment.py` — переписать mapping layer:
  - SOTIB OLISH → Procurement + ProcurementItem.
  - XARAJAT (по типу) → ProcurementExpense | DividendPayment | OperatingExpense.
  - TUSHUM (CAPITAL) → BalanceContribution.
  - TUSHUM (SOTUV) → SalePayment.
  - SOTUV → Sale + SaleLine.
  - FOYDA TAQSIMOTI → данные для валидации InvestmentContract (не источник).
  - QARZDORLAR → Receivable + ReceivableEntry.
  - KASSA → CashAccount initial balances.
  - PUL AYRIBOSHLASH → CurrencyExchange.
- `backend/apps/core/tests/test_excel_alignment_*.py` — обновить под новые маппинги.
- Удалить stub'ы `_DISABLED_DURING_REWORK`.
- Удалить старые модели: окончательно дропнуть `inventory.Receipt`, `inventory.ReceiptLine`, `inventory.ReceiptParticipant`, `investors.InvestorProfitRecord` (после миграции PR-5), `investors.InvestorSummary`. Миграция `drop_legacy_receipt.py`.

**Приёмка:**
- `python manage.py excel_align_import --snapshot client_snapshot_full_from_xlsx.json` → не падает, создаёт Procurement'ы в правильных статусах.
- Валидация: FOYDA TAQSIMOTI из Excel совпадает с computed агрегатом.

**Риск:** mapping сложный, ошибки в данных клиента. Mitigation: первый прогон в dry-run mode, отчёт несоответствий, ручной разбор.

---

## 2. Текущий статус PR

Обновлять после каждого merged PR. Формат: `[ ]` = not started, `[~]` = in progress, `[x]` = done, `[!]` = blocked.

- [ ] PR-1 Core abstractions
- [ ] PR-2 Procurement skeleton
- [ ] PR-3 Lot rework
- [ ] PR-4 Sale rework
- [ ] PR-5 PartnerLedger + Dividend
- [ ] PR-6 Receivable
- [ ] PR-7 Cash layer
- [ ] PR-8 Returns rework
- [ ] PR-9 bootstrap_demo + tests
- [ ] PR-10 Frontend API/types/stores
- [ ] PR-11 Frontend views
- [ ] PR-12 Excel pipeline + final cleanup

---

## 3. Правила работы на ветке `vacuum-rework`

1. **Один PR = один коммит merge в `vacuum-rework`.** Внутри PR можно несколько коммитов, но сливаем squash.
2. **Каждый PR должен оставлять код рабочим.** Тесты проходят (или явно skipped с указанием «awaits PR-N»).
3. **Миграции коммитим с кодом PR.** Не копим.
4. **Не начинаем PR-N, пока не закрыт PR-(N-1).** Зависимости слишком плотные.
5. **Frontend не трогаем в PR-1..9.** Бэкенд сначала.
6. **После PR-9** — можно merge в `main` как новый baseline, дальше фронт параллельно.
7. **Если что-то пошло криво** — `git reset --hard pre-vacuum-rework` возвращает baseline. Не стесняться.

---

## 4. Ключевые нюансы для продолжения в Codex (если закончатся лимиты Claude Code)

Если возвращаешься в Codex или другой агент — этот раздел даёт контекст для продолжения без чата.

### 4.1. Что нужно прочитать в первую очередь
1. [docs/vacuum-model.md](vacuum-model.md) — целевая доменная модель (9 тезисов).
2. [docs/phase-c-diff.md](phase-c-diff.md) — что меняется в схеме.
3. [docs/phase-c-full-analysis.md](phase-c-full-analysis.md) — анализ веток + blast radius.
4. **Этот файл** — пошаговый план.

### 4.2. Домен-специфичные инварианты (не упустить)
- `sum(profit_share) == 1.0`, достигается формулой Mush+Mud hybrid: `profit_investor = capital × m`, `profit_operator = capital_op + capital_inv × (1 − m)`.
- `mudaraba_ratio` вычисляется из планового соотношения `capital_share` ↔ `profit_share`. Для кейса Устоз/Бекзод (70/30 → 40/60) ratio = 4/7.
- **Убытки ВСЕГДА распределяются по `capital_share`**, никогда не по profit_share (шариат).
- **Проценты/штрафы за просрочку запрещены** (riba).
- `OperatingExpense` **никогда** не касается PartnerLedger.
- `balance = 0` **per-currency** при RECEIVED.
- Landed cost: CUSTOMS value-based, FREIGHT/STORAGE/INSURANCE qty-based.
- FIFO по `received_at` — единственный автоалгоритм выбора Lot.
- Продажа — **строго с одного склада** (нет auto-mixed).

### 4.3. Технический стек
- Python 3.12, Django 5.x, DRF, PostgreSQL 16, Redis, Celery.
- Vue 3 + TypeScript + Pinia + Vite (pnpm).
- Все backend модели наследуют `apps.core.models.TenantModel` (soft-delete + tenant FK).
- Все финансовые операции пишут `JournalEntry` (через `record_journal_from_cash_entry`) + `OutboxEvent` (через `publish_event`).
- Идемпотентность POST через `client_request_id: UUID`.

### 4.4. Как запускать
```bash
# Backend
cd backend
python manage.py migrate
python manage.py bootstrap_demo
python manage.py runserver

# Frontend
cd frontend
pnpm install
pnpm dev

# Tests
cd backend && python manage.py test
cd frontend && pnpm typecheck
```

### 4.5. Фикс если застрял
- Сбросить БД: `dropdb micropos && createdb micropos && python manage.py migrate && python manage.py bootstrap_demo`.
- Вернуться к baseline: `git reset --hard pre-vacuum-rework`.
- Пересмотреть план: этот документ — source of truth.

### 4.6. Договорённости по стилю (из /Users/aziztohirov/.claude/rules/common/coding-style.md)
- Immutability: не мутировать, создавать новые объекты.
- Много маленьких файлов (200-400 строк, max 800).
- Validation на границах системы (DRF serializers).
- Ошибки обрабатывать явно, не глотать.
- Функции < 50 строк, файлы < 800, вложенность ≤ 4.

### 4.7. Что НЕ делать
- Не трогать Excel pipeline до PR-12 (он помечен `_DISABLED_DURING_REWORK`).
- Не трогать frontend до PR-10.
- Не удалять `inventory.Receipt` до PR-12 (он нужен как legacy reference во время rework).
- Не ломать соседние PR'ы ради оптимизации одного.
- Не пытаться мигрировать данные из старых моделей — bootstrap stage, данные пересоздаются через `bootstrap_demo`.

---

## 5. Чеклист перед стартом PR-1

- [x] Вся работа закоммичена на `codex/bootstrap`.
- [x] Тег `pre-vacuum-rework` поставлен.
- [x] Ветка `vacuum-rework` создана.
- [x] Документы Фаз B, C, C+, D закоммичены (этот файл — последний из серии).
- [ ] Подтверждено от пользователя: начинаем PR-1.

---

*Документ составлен: 2026-04-18. Фаза D (план) закрыта. Ожидает старт PR-1.*
