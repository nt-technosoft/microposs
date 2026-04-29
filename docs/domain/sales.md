# Sales — Продажи и POS

## Обзор

Продажа создаётся **атомарно** («vacuum model»): нет черновиков, нет промежуточного состояния. При вызове `create_sale` одновременно выполняется выделение лотов, списание стока, проводки, начисление прибыли партнёрам — и возвращается завершённая `Sale.status=COMPLETED`.

---

## POS-сессия

### Модель PosSession

| Поле | Назначение |
|---|---|
| `location` | FK на Warehouse (kind=SHOP) |
| `opened_by` / `closed_by` | Кассир |
| `status` | OPEN / CLOSED |
| `opening_cash_by_currency` | JSON: сумма на старте по валютам |
| `expected_cash_by_currency` | JSON: расчётный остаток (вычисляется при закрытии) |
| `actual_cash_by_currency` | JSON: фактический остаток (вводит кассир при закрытии) |
| `cash_difference_by_currency` | JSON: расхождение |

**Инварианты:**
- Не более одной OPEN сессии на location
- Не более одной OPEN сессии на пользователя
- Продажи возможны только при открытой сессии

### Открытие сессии (`open_pos_session`)
- Валидирует что location.kind = SHOP
- Проверяет отсутствие другой открытой сессии
- Публикует `OutboxEvent('pos_session.opened')`

### Закрытие сессии (`close_pos_session`)
- Суммирует наличные продажи за сессию по валютам
- `expected = opening + cash_sales`
- `difference = actual - expected`
- Если `difference != 0` → создаёт `RiskEvent(type=CASH_MISMATCH)`
- Публикует `OutboxEvent('pos_session.closed')`

---

## Создание продажи (`create_sale`)

### Параметры
```python
create_sale(
    tenant_id,
    pos_session_id,
    location_id,
    sold_by_id,
    customer_id=None,       # обязателен для кредитной продажи
    lines=[{
        product_variant_id,
        quantity,
        unit_price,           # цена продажи в UZS
        operation_currency?,  # исходная валюта (если не UZS)
        operation_unit_price?,# цена в исходной валюте
        discount_reason_id?,
    }],
    payments=[{
        amount,
        currency,
        fx_rate,
        method,               # CASH / CARD / TRANSFER / CREDIT
        account_id?,          # CashAccount
    }],
    client_request_id=None,  # идемпотентность
    notes=None,
    date=None,
)
```

### Пошаговый процесс

**1. Идемпотентность**
Если `client_request_id` уже существует → возвращает существующую Sale без повторной обработки.

**2. Валидация сессии**
- Сессия OPEN
- `session.location_id == location_id`

**3. Обработка каждой строки**
- Проверка ценовой политики ProductVariant:
  - `FIXED` → `unit_price` должна соответствовать `base_price`
  - `ALWAYS_ASK` → `unit_price > 0` обязательно
- FX-конвертация: если `operation_currency != UZS` → вычисляется `unit_price` через `fx_rate`
- **FIFO-аллокация**: `allocate_lot()` → возвращает список слайсов
- Для каждого слайса:
  - Создаётся `SaleLine` с:
    - `profit_distribution_snapshot` = `calculate_profit_distribution(lot, unit_price, qty, landed_cost)`
    - Снимки: `unit_purchase_price`, `unit_landed_cost`
  - Вызывается `deduct_lot_stock()` → уменьшается остаток
  - Создаётся `StockMovement(type=SALE)`
  - Создаётся `PartnerLedgerEntry(type=PROFIT_ACCRUED)` для каждого партнёра

**4. Обработка каждого платежа**
- Создаётся `SalePayment` с fx_rate (снимок)
- `CREDIT`: `accrue_debt(customer_id, amount)` → создаёт `ReceivableEntry`
- `CASH/CARD/TRANSFER`: если `account_id` → `create_cash_entry(direction=IN)` → обновляется `CashAccount.balance`
- Создаётся journal entry (settlement)

**5. Балансировка платежей**
`Σ(payment functional amounts in UZS) == Sale.total_amount ± 0.01`

**6. Finalization**
- `create_journal_entry` COGS: Debit 5000, Credit 1100
- `Sale.status = COMPLETED`
- Публикуется `OutboxEvent('sale.completed')`

---

## Модель Sale

| Поле | Тип | Назначение |
|---|---|---|
| `status` | DRAFT / COMPLETED / RETURNED | Статус |
| `location` | FK Warehouse | Магазин продажи |
| `pos_session` | FK | Сессия кассира |
| `customer` | FK? | Клиент (обязателен для CREDIT) |
| `total_amount` | Decimal | Итого UZS |
| `total_cogs` | Decimal | Итого себестоимость UZS |
| `client_request_id` | str | Ключ идемпотентности |

**Иммутабельность:** физическое удаление запрещено; `ImmutableMixin` блокирует изменение после COMPLETED.

---

## Модель SaleLine

| Поле | Тип | Назначение |
|---|---|---|
| `lot` | FK | Лот (FIFO-слайс) |
| `quantity` | Decimal | Количество |
| `unit_price` | Decimal | Цена продажи UZS |
| `unit_landed_cost` | Decimal | Снимок себестоимости |
| `unit_purchase_price` | Decimal | Снимок закупочной цены |
| `operation_currency` | str | Исходная валюта |
| `operation_unit_price` | Decimal | Цена в исходной валюте |
| `fx_rate_snapshot` | Decimal | Курс на момент продажи |
| `profit_distribution_snapshot` | JSON | `{partner_id_str: decimal_str}` |

**profit_distribution_snapshot** — иммутабельный снимок расчёта прибыли на момент продажи.

---

## Модель SalePayment

| Поле | Тип | Назначение |
|---|---|---|
| `method` | CASH / CARD / TRANSFER / CREDIT | Метод |
| `role` | INCOMING / REFUND | Входящий или возвратный |
| `amount` | Decimal | Сумма |
| `currency` | str | Валюта |
| `fx_rate` | Decimal | Курс (снимок) |
| `account_id` | FK? | CashAccount |

---

## Возвраты (`process_return`)

### Разрешения возврата

| Resolution | Что происходит с товаром |
|---|---|
| `RESTOCK` | Товар возвращается на склад |
| `DISPOSE` | Товар уничтожается/списывается |

### RESTOCK-процесс
1. `restore_lot_stock()` → `LotStock.quantity_remaining += qty`
2. Если Lot был деактивирован → `Lot.is_active = True`
3. `PartnerLedgerEntry(type=PROFIT_REVERSED)` для каждого партнёра (пропорционально возвращённому qty)
4. Создаётся `StockMovement(type=RETURN)`

### DISPOSE-процесс
1. `StockDisposal` создаётся с `reason=DAMAGED_RETURN`
2. `Lot.quantity_initial -= qty` (товар физически уничтожен)
3. `PartnerLedgerEntry(type=PROFIT_REVERSED)` для каждого партнёра
4. `PartnerLedgerEntry(type=LOSS_INCURRED)` по доле капитала: `loss × capital_share`

### Денежный возврат
Если передан `refund = {method, amount, currency, account_id?}`:
- `finance.refund_customer(...)` обрабатывает возврат денег
- Инвариант: `Σ refunds ≤ Σ sale payments` по каждой валюте

### Инварианты возврата
- `Σ(ReturnLine.qty) ≤ SaleLine.qty` (включая предыдущие возвраты)
- Одна Return на одну Sale

---

## Ценовая политика ProductVariant

| Политика | Правило |
|---|---|
| `FIXED` | `unit_price` должна == `base_price`; отклонение запрещено |
| `ALWAYS_ASK` | `unit_price > 0`; продавец вводит цену свободно |

Если цена изменена от базовой → требуется `discount_reason_id`. Если не передан — автоматически создаётся причина «Торг» (переговор о цене).

---

## Мультивалютность

Продажи и платежи ведутся в любой валюте. FX-курс фиксируется на момент операции:
- `SaleLine.fx_rate_snapshot` — курс для строки
- `SalePayment.fx_rate` — курс для платежа
- Итоговая сумма продажи всегда в UZS (`total_amount`)

Балансировка: `Σ(payment.amount × payment.fx_rate)` в UZS должна равняться `total_amount ± 0.01`.

---

## Журнальные проводки при продаже

**Для каждого платежа (settlement):**
```
CASH:     Debit 1000 (Касса)      Credit 4000 (Выручка)
CARD:     Debit 1010 (Банк/POS)  Credit 4000 (Выручка)
CREDIT:   Debit 1200 (Дебиторка) Credit 4000 (Выручка)
```

**Один раз за продажу (COGS):**
```
Debit 5000 (Себестоимость)  Credit 1100 (Товары на складе)
```

---

## Связи с другими доменами

- **Inventory:** `allocate_lot` + `deduct_lot_stock` + `StockMovement`
- **Finance:** journal entries (settlement + COGS), `CashEntry`, `refund_customer`
- **Partnerships:** `calculate_profit_distribution`, `PartnerLedgerEntry(PROFIT_ACCRUED/REVERSED/LOSS)`
- **Customers:** `accrue_debt` при CREDIT-платеже
- **Analytics:** `OutboxEvent('sale.completed')` → `aggregate_daily_pnl.delay()`
