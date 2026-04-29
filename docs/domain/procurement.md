# Procurement — Закупка и Приход Товара

## Обзор

`Procurement` — основной путь поступления товара в систему (замена устаревшего `Receipt`). Охватывает весь цикл от создания заявки на закупку до фактической приёмки товаров на склад и создания `Lot`-ов.

---

## Жизненный цикл Procurement

```
OPEN
 ├─ Добавление ProcurementItem + ProcurementExpense
 ├─ Привязка InvestmentContract (для Partnership/Musharaka)
 ├─ Частичная приёмка → PARTIALLY_RECEIVED
 ├─ Полная приёмка → RECEIVED
 └─ Закрытие вручную → CLOSED / CANCELLED
```

**Статусы:**

| Статус | Значение |
|---|---|
| `OPEN` | Закупка создана, товар ещё не получен |
| `PARTIALLY_RECEIVED` | Часть позиций получена |
| `RECEIVED` | Все позиции получены |
| `CLOSED` | Финансово закрыта |
| `CANCELLED` | Отменена |

---

## Типы закупок

| Тип | Финансирование | Контракт нужен |
|---|---|---|
| `OWN_FUNDS` | Собственные средства бизнеса | Нет |
| `PARTNERSHIP` | Партнёрский капитал (InvestmentAgreement) | Да |
| `MUSHARAKA` | Прямой Мушарака-контракт | Да |
| `DISTRIBUTOR` | Заморожен, не реализован | — |

---

## Ключевые модели

### Procurement

| Поле | Тип | Назначение |
|---|---|---|
| `procurement_type` | OWN_FUNDS / PARTNERSHIP / MUSHARAKA | Тип финансирования |
| `status` | OPEN / ... | Текущий статус |
| `supplier` | FK? | Поставщик (опционально) |
| `agreement` | FK? | Родительский InvestmentAgreement |
| `reference_number` | str | Номер заказа/договора |
| `notes` | str | Комментарии |

### ProcurementItem
Позиция закупки (один вариант товара).

| Поле | Тип | Назначение |
|---|---|---|
| `product_variant` | FK | Вариант товара |
| `quantity` | Decimal | Количество |
| `unit_purchase_price` | Decimal | Цена поставщика |
| `currency` | str | Валюта (USD / UZS / ...) |
| `fx_rate` | Decimal | Курс на дату |
| `status` | DRAFT / PAID / RECEIVED | Статус позиции |

### ProcurementExpense
Посадочные расходы (перевозка, таможня, комиссии).

| Поле | Тип | Назначение |
|---|---|---|
| `expense_type` | LOGISTICS / CUSTOMS / FEE / OTHER | Тип |
| `amount` | Decimal | Сумма |
| `currency` | str | Валюта |
| `fx_rate` | Decimal | Курс |
| `allocation_method` | BY_VALUE / BY_QUANTITY / BY_WEIGHT | Метод распределения |
| `status` | DRAFT / PAID / RECEIVED | Статус |
| `targets` | M2M → ProcurementItem | Какие позиции несут этот расход |

### ProcurementReceiveBatch
Один акт физической приёмки товаров.

| Поле | Тип | Назначение |
|---|---|---|
| `received_at` | datetime | Время приёмки |
| `warehouse` | FK | Склад назначения |
| `items_count` | int | Количество позиций |
| `total_inventory_uzs` | Decimal | Итоговая стоимость в UZS |
| `contract_snapshot` | JSON | Снимок контракта (если партнёрство) |

---

## Посадочные расходы (Landed Costs)

Расходы распределяются по позициям закупки по выбранному методу:

| Метод | Формула |
|---|---|
| `BY_VALUE` | `expense × (item_value_uzs / total_items_value_uzs)` |
| `BY_QUANTITY` | `expense × (item_quantity / total_quantity)` |
| `BY_WEIGHT` | `expense × (item_weight / total_weight)` *(если есть вес)* |

**Результат:** для каждой позиции вычисляется `landed_cost_per_unit_uzs`:
```
landed_cost_per_unit = (unit_purchase_price × fx_rate + allocated_expense / quantity)
```

Это значение сохраняется в `Lot.landed_cost_per_unit` при приёмке — **иммутабельно**.

---

## Процесс приёмки (`receive_procurement_batch`)

1. Определяется список позиций для приёма (PAID-items или все DRAFT если нет PAID)
2. Рассчитываются landed costs для выбранных позиций
3. Если тип партнёрства: валидируется и фиксируется капитальное распределение по партнёрам
4. Для каждой позиции создаётся **Lot**:
   - `quantity_initial = item.quantity`
   - `unit_purchase_price = item.unit_purchase_price`
   - `landed_cost_per_unit` = рассчитанное значение
   - `contract_snapshot` = снимок контракта (из batch)
   - `received_at` = batch.received_at
5. Для каждого Lot создаётся **LotStock** (warehouse = batch.warehouse)
6. Создаётся `StockMovement(type=RECEIPT)`
7. Статус позиций обновляется → RECEIVED
8. Статус Procurement → PARTIALLY_RECEIVED / RECEIVED
9. Публикуется `OutboxEvent('receipt.confirmed')`

---

## Партнёрская приёмка: капитальное распределение

При приёмке с типом PARTNERSHIP или MUSHARAKA:

**Preview (`_batch_capital_preview`):**
- Рассчитывает требуемую сумму в валюте контракта
- Предлагает распределение по партнёрам пропорционально `planned_capital_share`
- Проверяет доступный баланс каждого партнёра в InvestmentAgreement
- Возвращает статус: `READY` или `CAPITAL_SHORTAGE`

**Фиксация (`_resolve_batch_capital_snapshot`):**
- Валидирует что сумма по всем партнёрам = требуемая сумма
- Проверяет доступный баланс
- Возвращает `(contract_snapshot, allocation_rows)` — записывается в batch

---

## Предпросмотр стоимости (`build_procurement_cost_preview`)

```
{
  "receive_basis": "PAID_ONLY",          // PAID_ONLY или ALL_DRAFT
  "if_all_current_lines_paid": {
    "items": [...],
    "total_uzs": "...",
    "landed_cost_per_unit": "..."
  },
  "reallocation_pending": true,          // если есть DRAFT расходы поверх PAID позиций
  "message": "..."
}
```

---

## Legacy Receipt (устаревший путь)

`Receipt` — старая модель прихода товара, используется только для исторических данных. Все новые закупки идут через `Procurement`.

| Тип Receipt | Аналог Procurement |
|---|---|
| `BUSINESS_OWNED` | `OWN_FUNDS` |
| `MUDARABA` | `MUSHARAKA` (старый термин) |
| `MUSHARAKA` | `MUSHARAKA` |
| `SUPPLIER_PURCHASE` | с `supplier` |
| `CONSIGNMENT` | с `consignment_rule` |

**Инвариант:** `Receipt.status = confirmed` → иммутабельно навсегда. Нельзя ни изменить, ни физически удалить.

---

## Консигнация

Consignment-товар имеет `consignment_rule` на Receipt:
```json
{
  "mode": "margin",    // или "commission"
  "value": "0.2"       // 20% маржа или комиссия
}
```
При продаже консигнационного товара поставщику начисляется соответствующая сумма как кредиторская задолженность.

---

## Связи с другими доменами

- **Inventory:** Lot + LotStock создаются при приёмке; `contract_snapshot` определяет FIFO-снимок
- **Finance:** Journal entry `Debit 1100 (Inventory) / Credit 2000 (Payables)` или `3100 (Investor Capital)` при подтверждении
- **Partnerships:** `InvestmentAgreement` предоставляет партнёрский капитал; `PartnerLedgerEntry` фиксирует вложение
- **Analytics:** `OutboxEvent('receipt.confirmed')` → инвалидирует profitability-кэш
