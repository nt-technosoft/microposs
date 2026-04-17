# Vacuum Model — идеальная доменная модель MicroPOS

> **Фаза B: «в вакууме».** Эта модель спроектирована **без оглядки на текущую кодовую базу** — только на основе:
> - реального Excel учёта клиента (`MUZORABA USTOZ VA BEKZOD AKA 2.xlsx`),
> - исламских финансовых принципов (Musharaka, Mudaraba, AAOIFI стандарты 12 и 13),
> - бизнес-диалога с потенциальным клиентом-инвестором (70/30 капитал → 40/60 прибыль).
>
> **Фаза C (diff с кодовой базой)** и **Фаза D (план миграции)** — отдельные документы, составляются позже.
>
> **Принцип**: без потери данных Excel. Все сущности и связи Excel имплементируются сюда, но структурированно — как БД, а не как таблицы.

---

## Индекс тезисов

1. [Контракт партнёрства (Musharaka + Mudaraba hybrid)](#тезис-1--контракт-партнёрства)
2. [Приход + Баланс прихода](#тезис-2--приход--баланс)
3. [Lot + Склад](#тезис-3--lot--склад)
4. [Продажа](#тезис-4--продажа)
5. [Мультивалютность, P&L, Cash Flow](#тезис-5--мультивалютность-pl-cash-flow)
6. [Дебиторка](#тезис-6--дебиторка)
7. [Возвраты и брак](#тезис-7--возвраты-и-брак)
8. [Касса, расходы, дивиденды](#тезис-8--касса-расходы-дивиденды)
9. [Отчёты](#тезис-9--отчёты)

---

## Шариатские инварианты (хардкод, применяются везде)

Эти правила не опциональны и не настраиваются пользователем — они enforced на уровне кода:

1. **Убытки всегда распределяются по `capital_share`**, не по `profit_share`. Независимо от договора, профиля риска, или желаний партнёров.
2. **Σ `profit_share` = 1.0**, все `profit_share[i] ≥ 0`. Гарантируется формулой Musharaka+Mudaraba hybrid (никогда не даёт отрицательных долей).
3. **Нельзя гарантировать фиксированную сумму прибыли инвестору** — только процент от фактической прибыли. Система не принимает ввод «гарантированная прибыль = X USD».
4. **Приход не может перейти в фазу продаж (RECEIVED), пока `ProcurementBalance` ≠ 0 в каждой валюте.** Капитал должен быть определён до начала торговли (AAOIFI: `ra'smal mu'ayyan`).
5. **Формула распределения прибыли фиксируется в `agreement` до первой продажи.** После первой продажи — immutable.
6. **Landed cost фиксируется на RECEIVED** и не меняется.
7. **Проценты/штрафы за просрочку дебиторки запрещены** (riba). Только статусы и напоминания.
8. **`OperatingExpense` изолирован от Partnership P&L.** Операционные расходы бизнеса (аренда, зарплаты, реклама) не касаются капитала и прибыли инвестора. Это ответственность оператора (mudarib).
9. **Физическое удаление `Sale`, `Receipt`, `JournalEntry`, `Lot` запрещено** (правило #12 из `CLAUDE.md`). Только soft-delete через статусы.
10. **Все финансовые операции пишут `JournalEntry` + `OutboxEvent`** (правила #10, #11 из `CLAUDE.md`).

---

## Тезис 1 — Контракт партнёрства

**Модель**: Musharaka + Mudaraba hybrid (канонический гибрид по AAOIFI Standard 12).

### Формула

Слой 1 (Musharaka): прибыль по доле капитала.
Слой 2 (Mudaraba): инвестор(ы) отдаёт часть своей прибыли оператору за управление.

```
profit_investor_i = capital_investor_i × mudaraba_ratio
profit_operator   = capital_operator + Σ(capital_investor_i × (1 − mudaraba_ratio))
```

`mudaraba_ratio ∈ [0, 1]` = доля, которую пассивный инвестор оставляет себе из своей musharaka-доли.

### Свойства формулы

- Σ profit_share = 1.0 автоматически (не требует нормализации).
- Ни одна доля не может быть отрицательной при любом распределении капитала ∈ [0, 1].
- Continuous: нет разрывов, не нужны пороги пересчёта.
- Вырождается в чистую Musharaka при `mudaraba_ratio = 1`.
- Вырождается в чистую Mudaraba при `capital_operator = 0`.
- Обобщается на N партнёров: каждый пассивный делегирует `(1 − mudaraba_ratio)` своей прибыли оператору.

### Текущий кейс Устоз/Бекзод (калибровка)

| Партнёр | Роль | Capital share (план) | Profit share (план) |
|---|---|---|---|
| Устоз | investor | 70% | 40% |
| Бекзод ака | operator | 30% | 60% |

Решаем: `70 × m = 40 → m = 4/7 ≈ 0.5714`.

Проверка: `30 + 70 × 3/7 = 30 + 30 = 60` ✓.

### UX модель

Пользователь вводит **интуитивные проценты**: пары `capital_share` и `profit_share`. `mudaraba_ratio` вычисляется автоматически, скрыт в секции «формула» для аудита.

На экране создания контракта — живой калькулятор с ползунками + live preview дрейфа:
> «Если капитал сместится с 70/30 до 75/25 — прибыль станет 42.86/57.14».

### Типы контракта на UX (внутри — одна сущность)

- **`OWN_FUNDS`** — только собственные средства оператора, контракт не нужен.
- **`MUSHARAKA`** — упрощённая форма (prof_share = capital_share, `mudaraba_ratio = 1`).
- **`PARTNERSHIP`** (default для клиента) — полная форма с mudaraba-компонентом.
- **`DISTRIBUTOR`** — консигнация / товар поставщика, особый режим собственности (разобрать отдельно в Фазе C).

Все они — одна сущность `InvestmentContract` с разными параметрами.

### Модель

```
InvestmentContract (встроен в Procurement):
  partners: [{
    partner_id: FK,
    role: INVESTOR | OPERATOR,
    planned_capital_share: Decimal,
    profit_share: Decimal,
  }]
  mudaraba_ratio: Decimal           # вычисляется из planned долей
  loss_rule: 'by_capital'           # хардкод
  planned_budget: Money             # для справки
```

### Пересчёт при дрейфе капитала

На закрытии фазы капитала (OPEN → RECEIVED):

```
actual_capital_share[partner] = net_contribution[partner] / Σ net_contribution[all]
profit_share[partner] = MushMud(actual_capital_share, mudaraba_ratio)
```

Дополнительно: система не требует порогов пересчёта — формула сама плавно перераспределяет.

---

## Тезис 2 — Приход + Баланс

### Концепция

**Единица инвестирования = «Приход» (procurement batch).** Каждый приход — отдельная мини-мушарака: свой капитал, свои участники, свои доли, свой P&L. Закрывается когда весь товар продан, но прибыль признаётся по каждой продаже.

### Модель

```
Procurement:
  id, tenant_id
  status: OPEN | RECEIVED | CLOSED | CANCELLED (DRAFT — техническое)
  type: OWN_FUNDS | PARTNERSHIP | MUSHARAKA | DISTRIBUTOR
  supplier_id: FK Supplier (nullable для DISTRIBUTOR)
  agreement: InvestmentContract (встроен, только для партнёрских типов)
  opened_at, received_at, closed_at
  
  # фиксируются при RECEIVED (snapshot):
  actual_capital_share: Map<partner_id, Decimal>
  actual_profit_share: Map<partner_id, Decimal>

ProcurementBalance (1:1 к Procurement):
  procurement_id: FK
  balances: Map<currency, Decimal>  # мультивалютный
  
BalanceContribution:
  balance_id: FK, partner_id: FK
  amount, currency, fx_rate, date

BalanceWithdrawal:
  balance_id: FK, partner_id: FK
  amount, currency, fx_rate, date
  reason: REFUND_SURPLUS | ADJUSTMENT

ProcurementItem:
  procurement_id: FK
  product_id: FK
  quantity, unit_purchase_price, currency, fx_rate
  # при RECEIVED → порождает Lot

ProcurementExpense:
  procurement_id: FK
  expense_type: CUSTOMS | FREIGHT | INSURANCE | STORAGE | OTHER
  amount, currency, fx_rate
  allocation_method: auto by type
    CUSTOMS → value-based
    FREIGHT/STORAGE/INSURANCE → qty-based
  description
```

### Жизненный цикл

**OPEN** — свободно:
- Contribution, Withdrawal в Balance от любого партнёра.
- Добавление ProcurementItem, ProcurementExpense.
- Баланс может быть любым (включая отрицательный).
- UI показывает текущие вклады и расчётные доли в реальном времени.

**OPEN → RECEIVED** (кнопка «Оприходовать»):
- Инвариант: `balance = 0` в каждой валюте.
- Если `balance > 0` (излишек) → распределение по плановым долям:
  - `target_net[p] = total_spent × planned_capital_share[p]`
  - `suggested_withdrawal[p] = actual_net[p] − target_net[p]`
  - Если все suggested ≥ 0 → автоматически, плановые доли сохраняются.
  - Если у кого-то suggested < 0 (недовнёс) → выбор: доплатить ИЛИ перерасчёт с новыми долями (превью).
- Если `balance < 0` (недостача) → обязательный Contribution.
- Расчёт `actual_capital_share`, применение Muš+Mud формулы → `actual_profit_share`.
- Размывка ProcurementExpense по позициям (value-based для customs, qty-based для остального).
- Создание Lot'ов со snapshot долей прибыли.

**RECEIVED** — баланс заморожен, идут продажи.

**RECEIVED → CLOSED** — все Lot'ы распроданы ИЛИ ручное закрытие с остатком.

### Общий котёл — ключевой принцип

`Spending` (авто-списание при оплате Item/Expense) **не помечается источником денег**. Все деньги в балансе — общий котёл. Доля партнёра = его нетто-вклад / сумма нетто-вкладов. Никакой per-transaction attribution не нужно.

### Объяснение партнёру (UX подсказка)

> «Приход — это общий кошелёк. Вы оба вкладываете в него деньги, когда удобно. Из кошелька оплачивается товар и расходы. Когда всё закуплено и завезено, вы закрываете этап: если в кошельке осталась сдача — она возвращается пропорционально вашим вкладам; если не хватило — кто-то дополняет. После этого ваши доли зафиксированы и начинаются продажи.»

---

## Тезис 3 — Lot + Склад

### Концепция

Lot = минимальная единица товара с полной историей. Lot неделим по идентичности, но разделён по количеству между складами через `quantity_by_location`. Перемещение меняет только распределение, не идентичность.

### Модель

```
Lot:
  id
  procurement_item_id: FK
  product_id: FK
  quantity_initial: Decimal
  quantity_by_location: Map<warehouse, Decimal>
    # default: { ASOSIY: qty, DOKON: 0 }
  unit_purchase_price: Money       # базовая закупочная
  landed_cost_per_unit: Money      # с размазкой ProcurementExpense
  contract_snapshot: {             # immutable на момент RECEIVED
    partners: [{partner_id, capital_share, profit_share}]
  }
  received_at: datetime            # для FIFO-сортировки
  status: ACTIVE | DEPLETED        # depleted при qty_remaining = 0

Warehouse:
  id, name, kind: STORAGE | SHOP
  # default: ASOSIY (STORAGE), DOKON (SHOP)

StockTransfer:
  from_warehouse, to_warehouse
  date
  lines: [{lot_id, quantity}]
  # FIFO по умолчанию при автовыборе lot_id; override логируется

StockDisposal:
  date, reason
  lines: [{lot_id, quantity}]
  # списание Lot'а, см. Тезис 7 для бракованного списания с распределением убытка
```

### Правила (финал, 9 пунктов)

1. Lot = `procurement_item × unit_purchase_price × landed_cost_per_unit × contract_snapshot`. Идентичность неизменяема после RECEIVED.
2. Один Lot живёт на всех складах через `quantity_by_location`. Сумма = `quantity_remaining`.
3. **FIFO по `received_at`** — единственный автоалгоритм подбора Lot при продаже/перемещении. Override возможен, логируется в audit.
4. `SaleLine` атомарен относительно Lot'а. Если FIFO задел несколько Lot'ов на одном складе — создаётся несколько SaleLine в одной Sale.
5. Прибыль считается per-SaleLine по `landed_cost_per_unit` и распределяется по `contract_snapshot.profit_share`.
6. Продажа по умолчанию с `DOKON`, override на `ASOSIY` возможен.
7. **Продажа строго с одного склада.** Недостаток на выбранном → блок + показ остатков по другим складам + ручное решение оператора (перенести, продать с другого, продать частично). Никаких автоматических mixed-sales или auto-transfer.
8. StockTransfer со смешиванием Lot'ов разных типов прихода (OWN + PARTNERSHIP или разные партнёрства) → **warning на UI, не блок**.
9. Возвраты/брак привязаны к конкретному Lot через SaleLine — гарантируется моделью.

### Пример FIFO-split SaleLine

Продажа 120 шт `Gul 50x80` с DOKON:
- L1 на DOKON = 50 (старше, Бекзод own) → SaleLine_A(L1, qty=50).
- L2 на DOKON = 100 (Устоз+Бекзод 40/60) → SaleLine_B(L2, qty=70).
- Одна Sale, две SaleLine. Прибыль по A идёт Бекзоду 100%, по B — Устозу 40%/Бекзоду 60%.

### Product и ценообразование

```
Product:
  base_price: Money                 # типичная розничная цена
  pricing_mode: FIXED | ALWAYS_ASK | EDITABLE   # default EDITABLE
```

- `FIXED` — цена жёстко `base_price`, редактирование заблокировано.
- `ALWAYS_ASK` — инпут пустой, обязательно ввести.
- `EDITABLE` — инпут = `base_price`, можно стереть и ввести другую.

Фактическая `unit_sale_price` всегда сохраняется в SaleLine независимо от режима.

---

## Тезис 4 — Продажа

### Модель

```
Sale:
  id, tenant_id, date
  customer_id: FK Customer          # nullable только если paid = total при CONFIRMED
  location: FK Warehouse            # default DOKON
  fx_rate                            # на момент CONFIRMED
  status: DRAFT | CONFIRMED | RETURNED | PARTIALLY_RETURNED
  client_request_id                 # идемпотентность (правило CLAUDE.md)

SaleLine (атомарна по Lot):
  sale_id: FK
  lot_id: FK
  product_id: FK
  quantity
  unit_sale_price                   # фактическая
  unit_landed_cost                  # snapshot из Lot
  unit_purchase_price               # snapshot из Lot (для валовой маржи)
  line_revenue, line_cogs, line_profit  (вычислимы)
  profit_distribution_snapshot: Map<partner_id, Money>

SalePayment (0..N на Sale):
  sale_id: FK
  date, amount, currency, fx_rate
  method: KASSA_SOM | KASSA_DOLLAR | PLASTIK_SOM
  role: INITIAL | DEBT_REPAYMENT
  account_id: FK CashAccount
```

### Статус оплаты — вычисляется, не хранится

```
paid_total = Σ SalePayment.amount (в валюте продажи)
debt = sale.total − paid_total
status: PAID | PARTIAL | UNPAID  (вычисление)
```

Это даёт единообразное покрытие:
- Чистый NAQD → 1 SalePayment на полную сумму.
- Мульти-валютная оплата (их реальный кейс 2026-04-07: сом + USD) → 2 SalePayment разных валют.
- Долг → 0 SalePayment при CONFIRMED + N SalePayment при погашениях.
- Смешанная (часть нал, часть долг) → 1 SalePayment + Receivable на остаток.

### Процесс CONFIRMED

1. Для каждой SaleLine — FIFO подбор Lot на `location`. Если не хватает — блок.
2. `Lot.quantity_by_location[location] -= qty` для каждой SaleLine.
3. Считается `line_profit` по каждой SaleLine, фиксируется `profit_distribution_snapshot` по `Lot.contract_snapshot.profit_share`.
4. Для каждого партнёра в `profit_distribution_snapshot` создаётся запись `PartnerLedger.PROFIT_ACCRUED`.
5. Сумма `SalePayment` проводится через `CashEntry` на соответствующий `CashAccount`.
6. Если `paid < total` → обновляется `Receivable(customer_id)` с `DEBT_ACCRUED`.
7. `JournalEntry` + `OutboxEvent`.

### PartnerLedger (per Procurement × Partner)

```
ProcurementPartnerLedger:
  procurement_id: FK
  partner_id: FK
  entries: [PartnerLedgerEntry]

PartnerLedgerEntry:
  date, amount, currency
  type: CAPITAL_IN | CAPITAL_OUT | PROFIT_ACCRUED | PROFIT_REVERSED 
      | DIVIDEND_PAID | LOSS_INCURRED
  ref: ссылка на первичную операцию

# Вычислимые метрики (для UI):
capital_invested      = Σ CAPITAL_IN − Σ CAPITAL_OUT
profit_accrued_total  = Σ PROFIT_ACCRUED − Σ PROFIT_REVERSED
loss_total            = Σ LOSS_INCURRED
dividends_paid        = Σ DIVIDEND_PAID
profit_pending_payout = profit_accrued_total − loss_total − dividends_paid
value_in_remaining_stock = Σ over Lots: qty_remaining × landed_cost × profit_share
```

Агрегат по всему tenant (общая сводка партнёра) — **computed view** поверх всех ProcurementPartnerLedger, не отдельная сущность.

### Авансовые дивиденды

Разрешены (у них в Excel: USTOZ DIVIDEND 477.3 USD 2026-04-12, при незакрытом приходе). Ограничения:
- Выплата ≤ `profit_pending_payout` на момент операции.
- Если позже прибыль партнёра уменьшится (возвраты/утилизация) ниже уже выплаченного → `PartnerOverpayment` (edge case, помечен к доработке в v2).

---

## Тезис 5 — Мультивалютность, P&L, Cash Flow

### Базовые принципы

1. **`Money` = (amount, currency).** Везде в системе. Никогда не «чистое число».
2. **Каждая транзакция пишет native amount + currency + исторический fx_rate.** Три поля, immutable.
3. **Balances per-currency.** Все счета хранят `Map<currency, Decimal>` или моно-валютные (как CashAccount).
4. **Конверсия валют — только явная операция `CurrencyExchange`.** Никаких неявных конверсий.

### Два контура отчётов

| Отчёт | Курс | Назначение |
|---|---|---|
| **P&L** (маржа, прибыль, распределение партнёрам) | Исторический (курс даты операции) | Контрактные цифры. Не меняются во времени. |
| **Cash Flow** | Исторический | По датам операций. |
| **PartnerLedger** | Исторический, в валюте капитала | Шариатски корректно. |
| **Balance** (текущий срез) | Native per-currency | Без автоматической конверсии. |
| **Snapshot в одной валюте** (опционально, v2) | Текущий, по явно указанному курсу с датой и пометкой | Кнопка «Показать в USD по курсу X на дату Y». |

### Вытекающие правила

5. Капитал Прихода фиксируется в валюте внесения; landed cost и прибыль считаются в той же валюте.
6. Инвариант `balance = 0` на RECEIVED проверяется **per-currency** (отдельно USD и UZS).
7. Дивиденды партнёру выплачиваются в валюте накопления по умолчанию. Другая валюта → явный `CurrencyExchange` перед выплатой.
8. Отчёты P&L/финансовой отчётности **всегда подписаны валютой**. Никаких безвалютных цифр.
9. `fx_rate` на транзакции — обязательное поле. Берётся из справочника `ExchangeRate(date, currency_pair, rate)` или вводится вручную.

### В MVP vs v2

**MVP:** native per-currency + исторический P&L в валюте капитала. Никаких консолидированных представлений в одной валюте.

**v2:** кнопка «Показать всё в USD по курсу на дату» с явной пометкой курса и даты.

---

## Тезис 6 — Дебиторка

### Модель

```
Receivable (агрегат per-customer):
  customer_id: FK (unique)
  balances: Map<currency, Decimal>

ReceivableEntry:
  receivable_id: FK
  date, amount, currency, fx_rate
  type: DEBT_ACCRUED | REPAYMENT | ADJUSTMENT | WRITE_OFF
  source_ref: Sale | SalePayment | ...
  due_date: date (nullable, только для DEBT_ACCRUED)
```

### Правила

1. Одна `Receivable` на клиента, мультивалютная. Детализация через `ReceivableEntry`.
2. Продажа в долг (`paid < total` при CONFIRMED) → `Sale.customer_id` обязателен. На UI — кнопка «Создать нового клиента» (минимум: имя + опционально телефон).
3. Частичные погашения разрешены. Каждый `SalePayment` с `role = DEBT_REPAYMENT` → `ReceivableEntry(REPAYMENT)`.
4. FIFO погашения при неуказании конкретной продажи: закрываются DEBT_ACCRUED по возрастанию `due_date`, потом по дате.
5. `due_date` — необязательное поле. Если заполнен → UI показывает «просрочено N дней».
6. **Никаких процентов/штрафов** (riba). Только статусы и напоминания.
7. Валюта долга = валюта продажи. Два долга разных валют → две строки в balances.
8. Статусы клиента (вычисляются): `CURRENT` / `OUTSTANDING` / `OVERDUE` / `WRITTEN_OFF`.

---

## Тезис 7 — Возвраты и брак

### Модель

```
Return:
  id, tenant_id
  sale_id: FK
  date, reason: DEFECT | CLIENT_REFUSE | OTHER
  resolution: RESTOCK | DISPOSE
  lines: [ReturnLine]

ReturnLine:
  return_id: FK
  sale_line_id: FK                  # однозначно определяет Lot и цену
  quantity

Refund (возврат денег):
  id, tenant_id
  return_id: FK (nullable)
  customer_id: FK
  date, amount, currency, fx_rate
  account_id: FK CashAccount        # из какой кассы
  method: CASH | PLASTIK | RECEIVABLE_OFFSET   # offset = закрытие долга вместо нала
```

### RESTOCK (качественный возврат)

1. `Lot.quantity_by_location[sale.location] += qty`.
2. SaleLine помечается как partially/fully returned (не удаляется).
3. В `PartnerLedger` для каждого затронутого партнёра → `PROFIT_REVERSED` на сумму его доли прибыли с возвращённого количества.
4. Если клиент оплатил → `Refund`. Иначе → уменьшение `Receivable`.
5. Возврат к тому же Lot с теми же `contract_snapshot` и `landed_cost`. Никакого «нового оприходования».

### DISPOSE (утилизация брака)

1. `Lot.quantity_remaining -= qty`, товар не возвращается на склад.
2. **Убыток распределяется по `capital_share`** (не `profit_share`):
   ```
   loss = qty × Lot.landed_cost_per_unit
   для каждого partner: LOSS_INCURRED = loss × Lot.capital_share[partner]
   ```
3. Если прибыль по этим qty уже была начислена (продажа прошла) → сначала `PROFIT_REVERSED` по `profit_share`, потом `LOSS_INCURRED` по `capital_share`. Две разные операции.
4. Клиенту — обычно полный `Refund`.

### Статусы Sale

- `CONFIRMED` → при первом Return переходит в `PARTIALLY_RETURNED`.
- Если Σ Return по всем SaleLine = Σ SaleLine.quantity → `RETURNED`.
- Статус — вычисляется, не хранится.

### Инварианты

- Σ Return по SaleLine ≤ SaleLine.quantity.
- Σ Refund по валюте ≤ Σ SalePayment по той же валюте.
- DISPOSE при недостаточном количестве на Lot → ошибка.

---

## Тезис 8 — Касса, расходы, дивиденды

### Модель

```
CashAccount:
  name                              # KASSA SOM, KASSA DOLLAR, PLASTIK SOM — default при tenant
  currency                          # моно-валютный
  balance: Decimal
  kind: CASH | CARD | BANK | OTHER

CashEntry:
  account_id: FK
  direction: IN | OUT
  amount (в валюте account)
  date
  source_ref: Sale | SalePayment | Refund | BalanceContribution | BalanceWithdrawal 
            | OperatingExpense | CurrencyExchange | DividendPayment | OwnerContribution

CurrencyExchange:                   # их PUL AYRIBOSHLASH
  from_account, to_account
  from_amount, from_currency
  to_amount, to_currency
  effective_rate, date

OperatingExpense:
  amount, currency, fx_rate
  paid_from: FK CashAccount
  category: RENT | SALARY | MARKETING | UTILITIES | BANK_FEE | OTHER
  description, date
  # НЕ привязан к Procurement. НЕ трогает Lot/PartnerLedger.

DividendPayment:
  partner_id, procurement_id        # источник прибыли
  amount, currency, fx_rate
  paid_from: FK CashAccount
  date
  # эффект: PartnerLedger.DIVIDEND_PAID, CashEntry OUT
  # инвариант: amount ≤ profit_pending_payout[partner, procurement]

OwnerContribution:
  amount, currency
  to_account: FK CashAccount
  date
  # пополнение кассы из личных средств оператора
  # НЕ инвестиция, НЕ касается Procurement/Contract
```

### Изоляция Operating vs Partnership (шариатский инвариант #8)

**Operating Expense НИКОГДА не влияет на:**
- `Lot.landed_cost`
- P&L Procurement (прибыль, которая распределяется партнёрам)
- `PartnerLedger` инвестора
- Доли капитала / прибыли контракта

**Почему:** инвестор вложил в конкретный проект. Его P&L ограничен границами Procurement (revenue − landed cost его Lot'ов). Операционная overhead — ответственность оператора, покрывается из его доли прибыли.

### Два контура P&L

```
Partnership P&L (per Procurement, для распределения):
  revenue              = Σ SaleLine.line_revenue по Lot'ам Procurement
  cogs                 = Σ SaleLine.line_cogs
  (procurement_expenses уже в landed_cost)
  partnership_profit   = revenue − cogs
  → распределяется по profit_share партнёров

Business P&L (per Period, для оператора):
  operator_share_of_partnerships  = Σ operator-доли по всем Procurement
  own_funds_profit                = прибыль с OWN_FUNDS приходов
  - operating_expenses
  = net_business_profit
```

### Таблица классификации расходов

| Расход | Куда |
|---|---|
| Растаможка партии | ProcurementExpense (CUSTOMS) → landed cost |
| Фрахт | ProcurementExpense (FREIGHT) |
| Страховка груза | ProcurementExpense (INSURANCE) |
| Аренда магазина | OperatingExpense (RENT) |
| Зарплата продавца | OperatingExpense (SALARY) |
| Реклама бренда | OperatingExpense (MARKETING) |
| Зарплата грузчика за разгрузку этого Прихода | Default OperatingExpense; если явно выделено — ProcurementExpense (решение оператора в момент ввода) |
| Утилизация брака | DISPOSE → убыток по `capital_share` (Тезис 7) |
| Комиссии банка при выплате дивиденда | OperatingExpense (BANK_FEE) |
| Курсовая разница при Exchange | Относится к тому счёту, где произошла; если на Procurement — туда, иначе OperatingExpense |

### Инвариант CI

```python
def assert_operating_expense_isolation(e: OperatingExpense):
    assert e.procurement_id is None
    assert not e.triggers_partner_ledger_entry()
    assert not e.changes_lot_landed_cost()
```

---

## Тезис 9 — Отчёты

### Три уровня

**1. Инвестор:**
- `/investor/procurement/:id` — детальная карточка прихода (капитал, товар на складе, прибыль, дивиденды, прогноз).
- `/investor/dashboard` — сводка по всем приходам.
- `/investor/dividends` — история выплат + pending.

**2. Оператор:**
- `/dashboard` — Business P&L + Cash Flow за период.
- `/cash` — CashAccount balances + журнал движений.
- `/receivables` — дебиторка по клиентам.
- `/payables` — кредиторка поставщикам.
- `/inventory` — остатки по складам.
- `/procurements` — все приходы, фильтры.

**3. Оперативные:**
- Остатки (per-warehouse, per-product, с FIFO Lot list).
- Просрочки дебиторки (без штрафов).
- Low-stock alerts для переноса ASOSIY → DOKON.
- Top selling products (по объёму / марже).
- OPEN Procurements (незакрытые).

### Правила построения

1. **Отчёты = computed views**, не хранимые сущности. Единственный источник истины — первичные сущности (Sale, Lot, PartnerLedger, CashEntry).
2. Каждый отчёт подписан валютой.
3. **P&L — только исторические курсы**, зафиксированные.
4. **Balance — native per-currency по умолчанию.**
5. Для инвестора — всегда в валюте его капитала, без конверсий. `OperatingExpense` не фигурирует.
6. Снэпшоты закрытых периодов можно кешировать (оптимизация).

### Scope доступа инвестора

**Прозрачность внутри его приходов — полная:**
- Все Sale / SaleLine по Lot'ам его приходов.
- Все ProcurementItem / ProcurementExpense.
- Все StockTransfer его Lot'ов.
- Все Return / Refund по его Lot'ам.
- Все Contribution / Withdrawal в его ProcurementBalance.
- Все DividendPayment ему.

**Вне scope (403):**
- Другие приходы (OWN_FUNDS, другие партнёрства).
- OperatingExpense.
- Касса бизнеса в целом.

**Режим:** read-only + export. Drill-down от агрегатов к первичке.

**Technical:** scope enforced на уровне Django queryset'а, не только UI.

### Периоды

- Пресеты: Сегодня / Эта неделя / Этот месяц / Прошлый месяц / Этот квартал / С начала года / Всё время.
- Custom range: любые границы.
- Один селектор в header → применяется ко всем отчётам страницы.
- Default: оператор — «Этот месяц»; инвестор — «Всё время» (scope по приходу).

### Экран инвестора — пример карточки

```
Приход #42 (PARTNERSHIP, статус RECEIVED)
├─ Капитал
│   вложил:     7 000 USD (план 7 000, факт 67.7%)
│   возвращено: 0
│   net:        7 000 USD
├─ Товар на складе
│   moя доля в остатках: 2 800 USD (по landed cost, не реализовано)
├─ Прибыль
│   начислено:         1 240 USD
│   выплачено:           900 USD
│   к выплате:           340 USD
├─ Убытки (DISPOSE)
│   списано:              50 USD
└─ Прогноз
│   ожидаемая итоговая прибыль: ~2 100 USD (по текущим base_price, не факт)
```

---

## Сводная карта сущностей

```
Partner ─┬─ InvestmentContract ─┬─ Procurement ─┬─ ProcurementItem ── Lot ──┬── SaleLine ── Sale ── SalePayment ── CashEntry
         │                      │               │                           │
         │                      │               ├─ ProcurementExpense       ├── Return ── Refund
         │                      │               │                           │
         │                      │               └─ ProcurementBalance ──┬── BalanceContribution
         │                      │                                        └── BalanceWithdrawal
         │                      │
         │                      └─ ProcurementPartnerLedger ── DividendPayment
         │
         └─ PartnerLedger (aggregate view)

Customer ── Receivable ── ReceivableEntry ── (← Sale, SalePayment)

Warehouse ── StockTransfer / StockDisposal

CashAccount ── CashEntry ── CurrencyExchange

OperatingExpense ── CashEntry  (изолирован от Partnership P&L)

Supplier ── Procurement
```

---

## Соответствие Excel-листам

| Excel Sheet | Наша модель |
|---|---|
| `SOTIB OLISH` | Procurement + ProcurementItem |
| `XARAJAT` (SOTIB OLISH тип) | ProcurementExpense |
| `XARAJAT` (DIVIDEND тип) | DividendPayment |
| `XARAJAT` (операционные) | OperatingExpense |
| `EXPENSES` | OperatingExpense (дубль XARAJAT — разобрать в Фазе C) |
| `OMBOR` | Lot + `quantity_by_location[ASOSIY]` + `quantity_by_location[DOKON]` |
| `STOCK TRANSFER` | StockTransfer |
| `SOTUV` | Sale + SaleLine |
| `TUSHUM` (CAPITAL) | BalanceContribution |
| `TUSHUM` (SOTUV) | SalePayment |
| `KASSA` | CashAccount балансы |
| `PUL AYRIBOSHLASH` | CurrencyExchange |
| `FOYDA TAQSIMOTI` | InvestmentContract.partners + вычисляемые доли |
| `QARZDORLAR` | Receivable + ReceivableEntry |
| `YETKAZIB BERUVCHILARDAN QARZ` | Payable (аналогично Receivable, разобрать в Фазе C) |
| `MALUMOTLAR` | Справочники: Customer, Product, Supplier, Warehouse, CashAccount |

---

## Отложенное (не включено в Фазу B)

- **Payable** (кредиторка поставщикам) — аналог Receivable для YETKAZIB BERUVCHILARDAN QARZ. Структурно симметрично.
- **DISTRIBUTOR (консигнация)** — особый режим собственности, отдельный разбор.
- **PartnerOverpayment** — edge case когда авансовый дивиденд больше итоговой прибыли.
- **AdvanceAgainstFutureProfit** — заём от бизнеса инвестору под будущую прибыль.
- **v2 агрегат в одной валюте** (кнопка «показать всё в USD по курсу X на дату Y»).
- **Глобальный PartnerWallet** (personal balance across all procurements) — только если клиенты попросят.
- **Снэпшоты отчётов** для кеширования закрытых периодов — оптимизация, не архитектура.

---

## Следующие фазы

### Фаза C — Diff с кодовой базой

1. Прочитать текущие Django-модели:
   - `backend/apps/catalog/models.py`
   - `backend/apps/inventory/models.py`
   - `backend/apps/finance/models.py`
   - `backend/apps/sales/models.py`
   - `backend/apps/investors/models.py`
   - `backend/apps/suppliers/models.py`
   - `backend/apps/customers/models.py`
2. Составить таблицу: что совпадает 1:1 / что переименовать / что переделать / что удалить / что добавить.
3. Оценить объём миграции.

### Фаза D — План миграции

1. Последовательность PR'ов с учётом зависимостей.
2. Приоритеты: критические сущности (Procurement, Lot, PartnerLedger) первыми.
3. Стратегия для data migration (если есть рабочие данные) — хотя для bootstrap stage это не проблема.
4. Риски: какие места потребуют frontend rework.

---

## История обсуждения (для контекста)

Эта модель — результат ~10 итераций с пользователем (17–18 апреля 2026) на основе:

1. **Excel файла клиента** `MUZORABA USTOZ VA BEKZOD AKA 2.xlsx` (13 листов, реальный учёт).
2. **Разговора с инвестором** — подтвердил musharaka+mudaraba hybrid (70/30 капитал → 40/60 прибыль).
3. **Шариатских стандартов** AAOIFI (Standard 12 — Mudaraba, Standard 13 — Musharaka).

Ключевые прорывные моменты:

- **Mudaraba-Musharaka hybrid формула** — найдена аналитически, при mudaraba_ratio = 4/7 воспроизводит кейс 70/30 → 40/60 точно. Никогда не даёт отрицательных долей. Не требует порогов пересчёта.
- **Общий котёл `ProcurementBalance`** без attribution на spending — заменил сложные «кошельки партнёров».
- **Инвариант `balance = 0` на RECEIVED** — единственное жёсткое правило, покрывает и излишки, и недостачи.
- **Изоляция Operating / Partnership** — критичный шариатский инвариант, делает отчёты инвестора стабильными.

---

*Документ составлен: 2026-04-18. Фаза B (Vacuum Model) закрыта. Ожидает перехода в Фазу C.*
