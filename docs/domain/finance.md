# Finance — Бухгалтерия, Кэш, FX, Отчётность

## Двойная бухгалтерия

### Модель Account (План счетов)

| Поле | Тип | Назначение |
|---|---|---|
| `code` | str | Уникальный код счёта в рамках тенанта |
| `name` | str | Название счёта |
| `account_type` | ASSET / LIABILITY / EQUITY / INCOME / EXPENSE | Тип |
| `parent` | FK self? | Родительский счёт (иерархия) |
| `is_system` | bool | Системный счёт (нельзя удалить) |

**Нормальное сальдо:**
- ASSET / EXPENSE → дебетовое (debit − credit)
- LIABILITY / EQUITY / INCOME → кредитовое (credit − debit)

**Системные счета (используются в автоматических проводках):**

| Код | Название | Тип |
|---|---|---|
| 1000 | Касса | ASSET |
| 1010 | Банк / POS-терминал | ASSET |
| 1100 | Товары на складе | ASSET |
| 1200 | Дебиторская задолженность | ASSET |
| 2000 | Кредиторская задолженность (поставщики) | LIABILITY |
| 2200 | Консигнационные обязательства | LIABILITY |
| 3000 | Капитал владельца | EQUITY |
| 3100 | Инвесторский капитал (Мударабá) | EQUITY |
| 3110 | Инвесторский капитал (Мушарáка) | EQUITY |
| 4000 | Выручка | INCOME |
| 5000 | Себестоимость | EXPENSE |
| 5300 | Операционные расходы | EXPENSE |

---

### JournalEntry (иммутабельная проводка)

| Поле | Тип | Назначение |
|---|---|---|
| `operation_type` | SALE / RECEIPT / PAYMENT / RETURN / WRITEOFF / TRANSFER / DEBT_PAYMENT | Тип операции |
| `operation_id` | int | ID исходной операции для трассировки |
| `date` | date | Дата |
| `is_reversal` | bool | Является ли сторнирующей проводкой |
| `reversed_entry` | FK self? | Ссылка на оригинал (для сторно) |
| `status` | str | Всегда `confirmed` |

**Инвариант:** `Σ debits == Σ credits`. Нарушение → `ValueError`. Физическое удаление запрещено; исправление только через сторно (`create_reversal_entry`).

### JournalLine

| Поле | Тип | Назначение |
|---|---|---|
| `account` | FK Account | Счёт |
| `debit` | Decimal | Дебет (0 если кредитовая строка) |
| `credit` | Decimal | Кредит (0 если дебетовая строка) |
| `description` | str | Описание строки |

---

## Автоматические проводки при операциях

### Продажа
```
CASH:   Debit 1000 (Касса)     Credit 4000 (Выручка)
CARD:   Debit 1010 (Банк)      Credit 4000 (Выручка)
CREDIT: Debit 1200 (Дебиторка) Credit 4000 (Выручка)
        Debit 5000 (СС)        Credit 1100 (Товары)    ← COGS
```

### Приёмка товара
```
BUSINESS_OWNED:   Debit 1100 (Товары) Credit 1000 (Касса)
SUPPLIER_PURCHASE:Debit 1100 (Товары) Credit 2000 (Поставщики)
CONSIGNMENT:      Debit 1100 (Товары) Credit 2200 (Консигнация)
MUDARABA:         Debit 1100 (Товары) Credit 3100 (Инв. Капитал М)
MUSHARAKA:        Debit 1100 (Товары) Credit 3110 (Инв. Капитал Ш)
```

### Оплата поставщику
```
Debit 2000 (Кредиторка) Credit 1000 (Касса)
```

### Погашение дебиторки
```
Debit 1000 (Касса) Credit 1200 (Дебиторка)
```

### Расход
```
Debit 5300 (Расходы) Credit 1000 (Касса / счёт)
```

### Внесение капитала владельца
```
Debit 1000 (Касса) Credit 3000 (Капитал владельца)
```

### Возврат (RESTOCK)
```
Debit 4000 (Выручка)   Credit 1000/1010/1200 (по методу оплаты)
Debit 1100 (Товары)    Credit 5000 (СС)
```

---

## Кэш-слой

### CashAccount
Операционный кассовый счёт (один тенант, одна валюта).

| Поле | Тип | Назначение |
|---|---|---|
| `currency` | str | Валюта счёта |
| `kind` | CASH / CARD_TERMINAL / BANK | Тип |
| `balance` | Decimal | Текущий баланс (поддерживается автоматически) |
| `linked_account` | FK Account? | Ссылка на счёт COA для journal entries |

**Инвариант:** `balance` — производная от `CashEntry`-журнала. Никогда не устанавливается напрямую — только через `create_cash_entry`.

### CashEntry (append-only)
| Поле | Тип | Назначение |
|---|---|---|
| `direction` | IN / OUT | Приход/расход |
| `amount` | Decimal | Сумма |
| `source_ref_type` | str | Тип источника ('sale', 'payment', ...) |
| `source_ref_id` | int | ID источника |

### `create_cash_entry(tenant_id, account, direction, amount, ...)`
- Создаёт `CashEntry`
- Атомарно обновляет `CashAccount.balance` через `F()`-выражение: `+= amount` (IN) или `-= amount` (OUT)
- **Вызывается внутри `transaction.atomic()`**

---

## FX-курсы

### ExchangeRate
История курса на дату для конкретного тенанта.

| Поле | Тип | Назначение |
|---|---|---|
| `base_currency` | str | Базовая валюта |
| `quote_currency` | str | Котируемая валюта |
| `rate_date` | date | Дата курса |
| `rate` | Decimal | Курс |
| `source` | CBU / MANUAL | Источник |
| `is_manual` | bool | Ручной ввод |

**Инвариант:** уникальный `(tenant, base_currency, quote_currency, rate_date)`. Сама строка курса может быть обновлена ручным вводом или official CBU sync (`overwrite_manual=true`). Иммутабельность финансовой операции обеспечивается не строкой `ExchangeRate`, а сохранённым `fx_rate_snapshot` в продаже, расходе, платеже, леджере или обмене.

### Валютный контракт отчётности
- `UZS` — functional currency: journal, P&L, COGS, сверка и `Sale.total_amount` считаются в UZS.
- `USD` и другие валюты — native/operation currency: кассы, платежи и взносы хранят реальные суммы в валюте операции.
- `report_currency` — display/report currency: отчёт может показать UZS-эквивалент в USD по выбранному курсу, не меняя бухгалтерские записи.
- Для USD-продаж `SaleLine.unit_price` хранит UZS-эквивалент, а `operation_currency`, `operation_unit_price`, `fx_rate_snapshot` хранят исходную цену.

### `exchange_currency(tenant_id, from_account_id, to_account_id, from_amount, rate, ...)`
Атомарный обмен валюты между двумя CashAccount.
- `from_account.balance -= from_amount`
- `to_account.balance += from_amount × rate`
- Создаёт `CurrencyExchange` запись
- Публикует `OutboxEvent('finance.currency_exchange')`

---

## Отчётность

### DailySummary (pre-aggregated)
Ежедневный P&L-снимок. Создаётся/обновляется Celery-задачей `aggregate_daily_pnl`.

| Поле | Назначение |
|---|---|
| `date` | Дата |
| `total_revenue` | Выручка |
| `total_cogs` | Себестоимость |
| `gross_profit` | Валовая прибыль |
| `investor_share` | Доля инвесторов (из PartnerLedgerEntry.PROFIT_ACCRUED) |
| `net_business_profit` | Чистая прибыль бизнеса (gross − investor − writeoffs − expenses) |
| `total_sales_count` | Количество продаж |
| `total_returns_count` | Количество возвратов |

### CashFlowSummary (pre-aggregated)

| Поле | Назначение |
|---|---|
| `cash_in_sales` | Наличные от продаж |
| `cash_in_debt_payments` | Погашения дебиторки |
| `cash_out_purchases` | Расходы на закупки |
| `cash_out_supplier_payments` | Оплаты поставщикам |
| `cash_out_expenses` | Операционные расходы |
| `net_cash_flow` | Чистый кэш-поток |

---

## Profitability-отчёты

Все три эндпоинта кэшируются на 5 минут. Ключ кэша = hash(tenant + params + версия). Версия инвалидируется при каждой новой продаже или закупке.

### `get_sales_profitability_rows(tenant_id, date_from?, date_to?, location_id?, report_currency?)`
Прибыльность по каждой продаже. Колонки: выручка, COGS, валовая прибыль, доля инвестора, прибыль бизнеса, маржа%, наценка%.

### `get_product_profitability_rows(tenant_id, date_from?, date_to?, location_id?, warehouse_id?, report_currency?)`
Прибыльность по варианту товара. Включает прогнозируемую прибыль на оставшийся сток (`projected_revenue`, `projected_gross_profit`).

### `get_procurement_profitability_rows(tenant_id, date_from?, date_to?, report_currency?)`
Прибыльность по закупке (агрегат по всем позициям и лотам).

---

## Combined API эндпоинты (оптимизация)

### `GET /api/v1/finance/reports/summary/`
Объединяет в 1 запрос: daily_summary + cash_flow + debt + parity (trial_balance + cash_accounts + payables + stock).

Ответ:
```json
{
  "is_computing": false,
  "daily_summary": [...],
  "cash_flow": [...],
  "debt": [...],
  "parity": {
    "payables": [...],
    "stock": [...],
    "trial_balance": [...],
    "cash_accounts": [...]
  }
}
```

**`is_computing: true`** — означает что фоновые Celery-задачи ещё работают над агрегацией. Фронтенд должен делать polling каждые 5 секунд (максимум 12 попыток = 60 секунд).

### `GET /api/v1/finance/reports/analytics/`
Объединяет в 1 запрос: sales profitability + products profitability + procurements profitability.

---

## Функция `_ensure_finance_aggregates`

Вызывается при каждом запросе к daily-summaries, cash-flow и reports/summary.

1. Определяет диапазон дат через `_resolve_operation_window()` (UNION-запрос по 5 таблицам)
2. Проверяет `warmup_key` в Redis (кэш «всё прогрето»)
3. Проверяет какие даты диапазона уже есть в `DailySummary`
4. Для отсутствующих дат → `aggregate_daily_pnl.delay()` (неблокирующий)
5. Возвращает `(date_from, date_to, is_computing)`

`is_computing=True` если задачи были задиспатчены (данных ещё нет).

---

## Связи с другими доменами

- **Sales:** journal entries создаются из `create_sale` и `process_return`
- **Customers:** `record_debt_payment_journal` при погашении дебиторки
- **Suppliers:** `record_supplier_payment_journal` при оплате поставщику
- **Partnerships:** `PartnerLedgerEntry.PROFIT_ACCRUED` → `investor_share` в DailySummary
- **Analytics:** Celery-задача строит DailySummary / CashFlowSummary
