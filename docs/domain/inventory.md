# Inventory — Склад, Лоты, FIFO

## Ключевые модели

### Warehouse
Физическое место хранения или продажи.

| Поле | Тип | Назначение |
|---|---|---|
| `kind` | STORAGE / SHOP | STORAGE = склад, SHOP = точка продаж |
| `name` | str | Название |
| `is_active` | bool | Активность |

**Важно:** продажи ведутся только через `SHOP`-склады. PosSession привязана к `location (Warehouse.kind=SHOP)`.

---

### Lot (иммутабельный)
Снимок стоимости партии товара на момент приёмки. Создаётся при подтверждении Receipt или при `receive_procurement_batch`.

| Поле | Тип | Назначение |
|---|---|---|
| `product_variant` | FK | Вариант товара |
| `quantity_initial` | Decimal | Количество при создании |
| `unit_purchase_price` | Decimal | Цена поставщика (без landed costs) |
| `landed_cost_per_unit` | Decimal | Полная себестоимость (закупка + распределённые расходы) |
| `contract_snapshot` | JSON | Снимок контракта для распределения прибыли |
| `received_at` | datetime | Время получения (для FIFO-сортировки) |
| `is_active` | bool | False = весь сток списан |
| `receipt` | FK? | Ссылка на legacy Receipt (взаимоисключает procurement_batch) |
| `procurement_batch` | FK? | Ссылка на ProcurementReceiveBatch (новый путь) |

**Инварианты:**
- Физическое удаление запрещено
- Поля `contract_snapshot`, `received_at`, `landed_cost_per_unit` иммутабельны после создания
- `is_active` автоматически переключается в `False` когда суммарный `quantity_remaining` по всем складам = 0

**`contract_snapshot` — структура:**
```json
{
  "mudaraba_ratio": "0.7",
  "loss_rule": "BY_CAPITAL",
  "partners": [
    {"partner_id": 1, "role": "INVESTOR", "capital_share": "0.6", "profit_share": "0.42"},
    {"partner_id": 2, "role": "OPERATOR", "capital_share": "0.4", "profit_share": "0.58"}
  ]
}
```

---

### LotStock
Остаток конкретного лота на конкретном складе. Один уникальный (lot, warehouse).

| Поле | Тип | Назначение |
|---|---|---|
| `lot` | FK | Лот |
| `warehouse` | FK | Склад |
| `quantity_remaining` | Decimal | Текущий остаток |

**Инварианты:**
- `quantity_remaining` >= 0 всегда
- `sum(quantity_remaining по всем складам)` ≤ `Lot.quantity_initial`
- При достижении 0 по всем складам → `Lot.is_active = False` автоматически

---

### StockMovement (audit log, append-only)
Каждое изменение количества стока.

| Тип | Когда |
|---|---|
| `RECEIPT` | При создании лота (приёмка) |
| `SALE` | При продаже (отрицательное количество) |
| `TRANSFER` | При перемещении между складами |
| `RETURN` | При возврате на склад (RESTOCK) |
| `WRITEOFF` | При списании (RiskEvent) |
| `ADJUSTMENT` | При ручной корректировке |

---

### StockDisposal (append-only)
Необратимые потери товара (не возвращаются на полку).

| Поле | Тип | Назначение |
|---|---|---|
| `lot` | FK | Лот |
| `quantity` | Decimal | Количество |
| `reason` | DEFECT / EXPIRED / DAMAGED_RETURN / WRITEOFF / OTHER | Причина |
| `loss_amount` | Decimal | quantity × landed_cost_per_unit |

**Ключевое отличие от возврата:** `StockDisposal` уменьшает `Lot.quantity_initial` (товар физически уничтожен/потерян), а не `quantity_remaining`.

---

## Ключевые сервисные функции

### `allocate_lot(product_variant_id, warehouse_id, quantity, tenant_id) → list[dict]`
FIFO-выбор лотов для продажи. **Только читает, не изменяет.**

- Запрос: `LotStock` где `quantity_remaining > 0` и `lot.is_active=True`
- Сортировка: `(lot.received_at, lot.id)` — строгое FIFO
- Возвращает: `[{lot, lot_stock, quantity}, ...]` — может быть несколько слайсов если одного лота недостаточно
- Исключение: `InsufficientStockError` если склад не может удовлетворить запрос

### `deduct_lot_stock(lot_stock, quantity) → LotStock`
Атомарно уменьшает остаток. Вызывается из `create_sale`.

- Уменьшает `quantity_remaining`
- Если суммарный остаток по всем складам = 0 → `Lot.is_active = False`
- Исключение: `InsufficientStockError` если `quantity_remaining < quantity`

### `restore_lot_stock(lot_stock, quantity) → LotStock`
Обратная операция к `deduct_lot_stock`. Вызывается при возврате (RESTOCK).

- Увеличивает `quantity_remaining`
- `Lot.is_active = True` (может реактивировать)

### `transfer_lot_stock(tenant_id, lot, from_warehouse, to_warehouse, quantity) → LotStock`
Перемещение товара между складами.

**Side effects:**
- `from_warehouse.LotStock.quantity_remaining -= quantity`
- `to_warehouse.LotStock` (get_or_create) `+= quantity`
- Создаёт `StockMovement(type=TRANSFER)`
- Публикует `OutboxEvent('lot.transfer')`

**Инварианты:**
- `0 < quantity ≤ from_lot_stock.quantity_remaining`
- Контракт лота (участники, доли) не изменяется при перемещении

### `get_stock_summary(tenant_id, warehouse_id?) → list[dict]`
Агрегированный вид остатков по (вариант, склад).

- Только активные лоты с `quantity_remaining > 0`
- Возвращает: `product_variant_id`, `product_name`, `warehouse_id`, `warehouse_name`, `total_quantity`, `total_landed_cost`

---

## Жизненный цикл лота

```
Procurement.receive_batch() / Receipt.confirm()
    └─ Lot создан (is_active=True, quantity_initial=N)
         └─ LotStock создан (warehouse=destination, quantity_remaining=N)
              └─ StockMovement(type=RECEIPT)

Продажа:
    allocate_lot() → FIFO-слайсы
    deduct_lot_stock() для каждого слайса
        если sum(remaining) == 0 → Lot.is_active = False

Возврат (RESTOCK):
    restore_lot_stock()
        Lot.is_active = True (если был деактивирован)

Возврат (DISPOSE):
    StockDisposal создан
    Lot.quantity_initial -= qty (товар уничтожен)

Перемещение:
    deduct от from_warehouse.LotStock
    add к to_warehouse.LotStock
    Lot.contract_snapshot не трогается
```

---

## FIFO: почему SaleLine ссылается на Lot

При продаже 8 единиц одного товара из двух партий (первая — 5 ед., вторая — 3 ед.) создаётся **2 SaleLine** с разным `lot_id`. Это необходимо потому, что:
1. Разные партии могут иметь разную себестоимость (`landed_cost_per_unit`)
2. Разные партии могут иметь разный `contract_snapshot` (разные инвесторы)
3. Распределение прибыли считается **per-lot-slice**, не per-product

---

## Связи с другими доменами

- **Sales:** `create_sale` → `allocate_lot` + `deduct_lot_stock` + `StockMovement(SALE)`
- **Partnerships:** `Lot.contract_snapshot` используется для расчёта прибыли; `landed_cost_per_unit` = COGS
- **Finance:** `landed_cost_per_unit × quantity` = COGS для journal entry
- **Risk:** `StockDisposal` связан с `RiskEvent` через `risk_event_ref`
