# Customers & Suppliers — Дебиторы и Кредиторы

## Customers (Дебиторы)

### Модель Receivable
Один леджер задолженности на (клиент, тенант).

| Поле | Тип | Назначение |
|---|---|---|
| `customer` | FK | Клиент |
| `balances` | JSON | `{"UZS": "150000.00", "USD": "100.00"}` |

**Инвариант:** `balances` — мультивалютный словарь. Сумма считается из `ReceivableEntry` (исторически), `balances` — оперативный снимок.

### Модель ReceivableEntry (append-only)

| Поле | Тип | Назначение |
|---|---|---|
| `entry_type` | DEBT_ACCRUED / REPAYMENT / ADJUSTMENT | Тип |
| `amount` | Decimal | Положительное — долг, отрицательное — погашение |
| `currency` | str | Валюта |
| `fx_rate` | Decimal | Курс на момент операции (снимок) |
| `due_date` | date? | Дата погашения (для рассрочки) |
| `source_ref` | str? | Ссылка на операцию-источник (sale_id) |

---

### `accrue_debt(tenant_id, customer_id, amount, currency, ...)`
Вызывается из `create_sale` при кредитном платеже.

**Side effects:**
- `ReceivableEntry(type=DEBT_ACCRUED, amount=+amount)`
- `Receivable.balances[currency] += amount`
- `OutboxEvent('customer.debt_accrued')`

### `record_customer_payment(tenant_id, customer_id, amount, payment_method, ...)`
Регистрирует погашение долга клиентом.

**Side effects:**
- Создаёт `CustomerPayment`
- Если `account_id` → `CashEntry(direction=IN)` → `CashAccount.balance += amount`
- `ReceivableEntry(type=REPAYMENT, amount=-amount)`
- `Receivable.balances[currency] -= amount`
- Journal entry: Debit 1000, Credit 1200
- `OutboxEvent('customer.payment')`

**Инвариант:** Валюта платежа должна совпадать с `CashAccount.currency` если передан account_id.

### `get_customer_debt_summary(tenant_id) → list[dict]`
Активные клиенты с долгом > 0, отсортированные по убыванию. Используется в `reports/summary/`.

---

## Suppliers (Кредиторы)

### Модель Supplier

| Поле | Тип | Назначение |
|---|---|---|
| `name` | str | Название поставщика |
| `phone` | str | Контакт |
| `outstanding_balance` | Decimal | Текущий долг перед поставщиком в UZS |

**Инвариант:** `outstanding_balance` всегда в UZS (функциональная валюта).

### Модель SupplierPayment

| Поле | Тип | Назначение |
|---|---|---|
| `supplier` | FK | Поставщик |
| `amount` | Decimal | Функциональная сумма UZS |
| `operation_currency` | str | Исходная валюта платежа |
| `operation_amount` | Decimal | Исходная сумма |
| `fx_rate_snapshot` | Decimal | Курс на момент платежа |
| `payment_method` | CASH / CARD / TRANSFER | Метод |
| `date` | date | Дата |

### `record_supplier_payment(tenant_id, supplier_id, amount, payment_method, ...)`
Регистрирует оплату поставщику.

**Side effects:**
- `Supplier.outstanding_balance -= functional_amount_uzs`
- Создаёт `SupplierPayment`
- Journal entry: Debit 2000, Credit 1000
- `OutboxEvent('supplier.payment')`

### `get_supplier_payables_summary(tenant_id) → list[dict]`
Поставщики с `outstanding_balance > 0`. Используется в `reports/summary/parity`.

---

## AgingReport (аналитика задолженностей)

Рассчитывается ночью (`compute_aging_reports` Celery-задача).

**Бакеты (MVP):**
- `bucket_0_30` — задолженность 0–30 дней

*Примечание: Полная разбивка по срокам запланирована; сейчас всё помещается в bucket_0_30.*

| Поле | Тип |
|---|---|
| `receivable_type` | AR (дебиторка) / AP (кредиторка) |
| `counterparty_id` | ID клиента или поставщика |
| `counterparty_name` | Имя |
| `total_outstanding` | Итого |
| `bucket_0_30` | Долг до 30 дней |

---

## Связи с другими доменами

- **Sales:** `accrue_debt` вызывается из `create_sale` при CREDIT-платеже
- **Finance:** `CashEntry`, `CashAccount`, journal entries при погашении
- **Analytics:** `OutboxEvent` → `aggregate_daily_pnl` учитывает CustomerPayment в `cash_in_debt_payments`
