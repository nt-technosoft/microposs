# E09 Wave B — UI Rebuild Detailed Design

**Дата:** 2026-05-20
**Контекст:** детальная подготовка к UI пересборке `ProcurementWorkspace.vue`.
**Зависит от:** Wave A backend preconditions (8 slices).
**Под контролем:** founder. Sonnet/Codex может помогать в реализации, но
каждый Wave B slice стартует только с явного одобрения founder'а.

> Этот документ — **готовый детальный проект** UI пересборки. Содержит:
> ASCII-mockups каждой карточки на mobile, component contracts, slice
> breakdown, state management strategy. Цель — когда founder начинает
> UI работу, он не должен заново брейнштормить структуру; всё уже
> запроектировано.

---

## Pre-conditions (что должно быть в backend перед Wave B)

Все 8 Wave A slices завершены:
- AT_RECEIPT timing в enum + combined action
- Per-item goods_ownership refactor + MIXED state
- Discrepancy fields на ReceiveBatchLine
- Generic Attachment модель + endpoint
- Cancel procurement rule + action
- Reverse receive batch + inverse documents
- ProcurementAmendment модель + service
- PREPAID multi-payment coverage rule

Без них UI будет либо неполным, либо упрётся в отсутствующий backend.

---

## Page layout overview (mobile, 375px)

```
┌────────────────────────────────────────┐
│ ← Приход #1234        DRAFT       ⋯    │  ← Header (sticky top)
│ Дистрибьютор «Coca-Cola Узбекистан»    │
│ Свои деньги · Предоплата · 1 250 000   │
├────────────────────────────────────────┤
│                                        │
│ ┌─ Card 1: Поставщик и оплата ──────┐ │
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 2: Товары ──────────────────┐ │
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 3: Расходы ─────────────────┐ │  (hidden for CONSIGNED)
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 4: Финансирование ──────────┐ │  (PARTNERSHIP only)
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 5: Оплата ──────────────────┐ │  (varies by timing)
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 6: Приёмка ─────────────────┐ │  (after confirm)
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
│ ┌─ Card 7: История и документы ─────┐ │
│ │ ...                               │ │
│ └───────────────────────────────────┘ │
│                                        │
├────────────────────────────────────────┤
│ [ Подтвердить и оплатить → ]           │  ← Bottom action bar (sticky)
└────────────────────────────────────────┘
```

Все карточки скроллятся внутри Body. Header и Action bar — sticky.

---

## Header

```
┌────────────────────────────────────────┐
│ ← Приход #1234        DRAFT       ⋯    │
│ Дистрибьютор «Coca-Cola Узбекистан»    │
│ Свои деньги · Предоплата · 1 250 000   │
└────────────────────────────────────────┘
```

**Элементы:**
- Back arrow → возврат к списку procurements
- Title: «Приход #ID» (или «Новый приход» для нового DRAFT)
- Status badge: DRAFT / OPEN / PARTIALLY_RECEIVED / RECEIVED / CLOSED / CANCELLED
- Action menu (⋯):
  - «Прикрепить документ»
  - «Изменить состав» (только OPEN/PARTIALLY_RECEIVED, открывает amendment flow)
  - «Отменить приход» (только если разрешено правилом cancel)
  - «Отменить приёмку» (только если есть ReceiveBatch)
- Summary line под title: краткие параметры
  - Свой funding или Партнёрский (со ссылкой на договор)
  - Тип оплаты человеческим языком
  - Сумма обязательства

Для PARTNERSHIP — header **подсвечивается** (фон цветной + иконка):
```
┌────────────────────────────────────────┐
│ ← Приход #1234        OPEN        ⋯    │  ⓘ цветной фон
│ 🤝 Партнёрский · Договор #5            │
│ Инвестор: Анвар · 80% · 1 000 000 USD  │
└────────────────────────────────────────┘
```

Для CONSIGNED:
```
│ 📦 На реализации · Дистрибьютор X      │
```

Для MIXED:
```
│ 📦 Смешанный приход (свой + реализация)│
```

---

## Card 1 — Поставщик и оплата

### State: empty (новый DRAFT)

```
┌────────────────────────────────────────┐
│ Поставщик и оплата          ⚠         │
│                                        │
│ [ Выбрать поставщика → ]               │
│                                        │
│ Тип оплаты:                            │
│ ● Предоплата                           │
│ ○ По получению                         │
│ ○ Отсрочка                             │
│ ○ Рассрочка                            │
│ ○ Частичная                            │
│ ○ На реализации                        │
│                                        │
└────────────────────────────────────────┘
```

Chips для тип оплаты — multi-row, scroll-horizontal.

### State: filled (own-funds, supplier выбран)

```
┌────────────────────────────────────────┐
│ Поставщик и оплата          ✓         │
│ ┌──────────────────────────────────┐  │
│ │ Coca-Cola Узбекистан        ›   │  │
│ │ Тел: +998 90 123 45 67           │  │
│ └──────────────────────────────────┘  │
│ ● Предоплата                          │
└────────────────────────────────────────┘
```

### State: PARTNERSHIP timing выбран

```
┌────────────────────────────────────────┐
│ Поставщик и оплата          ⚠         │
│ ┌──────────────────────────────────┐  │
│ │ Coca-Cola Узбекистан        ›   │  │
│ └──────────────────────────────────┘  │
│ ● Предоплата (партнёрский)            │
│                                        │
│ Инвестиционный договор:                │
│ ┌──────────────────────────────────┐  │
│ │ ⚠ Не выбран — обязательно для    │  │
│ │   партнёрского прихода           │  │
│ │   [ Выбрать договор → ]          │  │
│ └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

При нажатии «Выбрать договор» — bottom sheet со списком ACTIVE/OPEN
InvestmentAgreement + кнопка «Создать новый» → `InvestmentAgreementQuickForm.vue`.

### State: CONSIGNED ownership (выбрали ON_SALE timing)

```
┌────────────────────────────────────────┐
│ Поставщик и оплата          ✓         │
│ ┌──────────────────────────────────┐  │
│ │ Coca-Cola Узбекистан        ›   │  │
│ └──────────────────────────────────┘  │
│ ● На реализации                       │
│                                        │
│ ⓘ Все товары будут оформлены как     │
│   консигнация. Расходы недоступны.    │
└────────────────────────────────────────┘
```

Помечает дисабленность Card 3 (Расходы) подсказкой.

### Component contract

```typescript
// ProcurementCardSupplier.vue
defineProps<{
  procurement: ProcurementWorkspacePayload
  policy: PolicyPayload
}>()
defineEmits<{
  'supplier-selected': [supplierId: number]
  'timing-changed': [timing: PaymentTiming]
  'ownership-changed': [ownership: GoodsOwnership]
  'agreement-selected': [agreementId: number]
}>()
```

---

## Card 2 — Товары

### State: empty

```
┌────────────────────────────────────────┐
│ Товары                          0      │
│                                        │
│ Нет товаров. Добавь первый.            │
│                                        │
│ [ + Добавить товар ]                   │
└────────────────────────────────────────┘
```

### State: 3 товара, OWN_FUNDS PREPAID, OWNED

```
┌────────────────────────────────────────┐
│ Товары                          3      │
│ ─────────────────────────────────────  │
│ Кока-кола 0.5л                         │
│ 100 шт × 5 000 = 500 000 UZS    swipe→ │
│ ─────────────────────────────────────  │
│ Спрайт 0.5л                            │
│ 50 шт × 5 000 = 250 000 UZS     swipe→ │
│ ─────────────────────────────────────  │
│ Фанта 0.5л                             │
│ 80 шт × 6 250 = 500 000 UZS     swipe→ │
│ ─────────────────────────────────────  │
│ Итого: 1 250 000 UZS                   │
│                                        │
│ [ + Добавить товар ]                   │
└────────────────────────────────────────┘
```

Swipe-actions per line: Edit / Split / Delete.

### State: MIXED ownership (часть OWNED, часть CONSIGNED)

```
┌────────────────────────────────────────┐
│ Товары                          3      │
│ ─────────────────────────────────────  │
│ 🛍 Кока-кола 0.5л                      │
│ 100 шт × 5 000 = 500 000 UZS           │
│ ─────────────────────────────────────  │
│ 🛍 Спрайт 0.5л                         │
│ 50 шт × 5 000 = 250 000 UZS            │
│ ─────────────────────────────────────  │
│ 📦 Фанта 0.5л (на реализации)          │
│ 80 шт × 6 250 = 500 000 UZS            │
│ ─────────────────────────────────────  │
│ Итого: 750 000 UZS свои + 500 000 рез. │
│                                        │
│ [ + Добавить товар ]                   │
└────────────────────────────────────────┘
```

При добавлении товара через FAB — bottom sheet с переключателем
«свой / на реализации» (только если procurement.goods_ownership позволяет MIXED).

### State: после confirm (amendments only)

```
┌────────────────────────────────────────┐
│ Товары                          3      │
│ ─────────────────────────────────────  │
│ ...список без swipe actions...        │
│ ─────────────────────────────────────  │
│ Итого: 1 250 000 UZS                   │
│                                        │
│ ⓘ Состав зафиксирован после подтверж- │
│   дения. Правки через «Изменить       │
│   состав» в меню (⋯).                 │
└────────────────────────────────────────┘
```

### Component contract

```typescript
// ProcurementCardItems.vue
defineProps<{
  items: ProcurementItem[]
  isEditable: boolean  // false после confirm
  allowMixedOwnership: boolean
  totalAmount: string
  currency: string
}>()
defineEmits<{
  'item-add': []
  'item-edit': [itemId: number]
  'item-delete': [itemId: number]
  'item-split': [itemId: number]
}>()
```

---

## Card 3 — Расходы

### State: empty, allowed

```
┌────────────────────────────────────────┐
│ Расходы                          0     │
│                                        │
│ Нет дополнительных расходов.           │
│                                        │
│ [ + Добавить расход ]                  │
└────────────────────────────────────────┘
```

### State: один расход

```
┌────────────────────────────────────────┐
│ Расходы                          1     │
│ ─────────────────────────────────────  │
│ 🚚 Логистика                           │
│ 50 000 UZS · по стоимости              │
│ На все товары                          │
│ ─────────────────────────────────────  │
│                                        │
│ [ + Добавить расход ]                  │
└────────────────────────────────────────┘
```

### State: дисаблено для CONSIGNED

```
┌────────────────────────────────────────┐
│ Расходы                       disabled │
│                                        │
│ ⓘ Расходы недоступны для прихода      │
│   на реализации (консигнации).         │
│                                        │
└────────────────────────────────────────┘
```

### Component contract

```typescript
// ProcurementCardExpenses.vue
defineProps<{
  expenses: ProcurementExpense[]
  isEditable: boolean
  isDisabled: boolean  // true если procurement.goods_ownership=CONSIGNED
  disabledReason: string
}>()
defineEmits<{
  'expense-add': []
  'expense-edit': [expenseId: number]
  'expense-delete': [expenseId: number]
}>()
```

---

## Card 4 — Финансирование (PARTNERSHIP only)

### State: empty, agreement выбран

```
┌────────────────────────────────────────┐
│ Финансирование                  ⚠     │
│ ─────────────────────────────────────  │
│ Договор #5                             │
│ Баланс: 2 000 000 UZS                  │
│                                        │
│ Планируемое распределение:             │
│ ┌───────────────────────────────────┐ │
│ │ Инвестор Анвар   1 000 000 (80%) │ │
│ │ Бизнес            250 000 (20%)  │ │
│ └───────────────────────────────────┘ │
│                                        │
│ К покрытию закупки: 1 250 000          │
│ Доступно: 2 000 000 ✓                  │
│                                        │
│ [ Уточнить распределение ]             │
└────────────────────────────────────────┘
```

Кнопка «Уточнить распределение» → bottom sheet с editable amounts per partner.

### State: capital allocation подтверждено

```
┌────────────────────────────────────────┐
│ Финансирование                  ✓     │
│ ─────────────────────────────────────  │
│ Договор #5                             │
│                                        │
│ Распределение:                         │
│ Инвестор Анвар:  1 000 000  (80%)     │
│ Бизнес:            250 000  (20%)     │
│                                        │
│ К списанию из договора: 1 250 000     │
└────────────────────────────────────────┘
```

### Component contract

```typescript
// ProcurementCardFinancing.vue
defineProps<{
  agreement: InvestmentAgreementSummary
  plannedAllocation: PartnerAllocation[]
  actualAllocation: PartnerAllocation[] | null  // если уже подтверждено
  procurementCost: string
  isEditable: boolean
}>()
defineEmits<{
  'allocation-edit': []
}>()
```

---

## Card 5 — Оплата (variations по timing)

### PREPAID — empty

```
┌────────────────────────────────────────┐
│ Оплата                          ⚠     │
│ ─────────────────────────────────────  │
│ Обязательство: 1 250 000 UZS           │
│ Оплачено:           0 UZS              │
│ Остаток:    1 250 000 UZS              │
│                                        │
│ [ Оплатить полностью ]                 │
│ [ Оплатить частично ]                  │
└────────────────────────────────────────┘
```

### PREPAID — с multi-payment

```
┌────────────────────────────────────────┐
│ Оплата                          ⚠     │
│ ─────────────────────────────────────  │
│ Обязательство: 1 250 000 UZS           │
│ Оплачено:     400 000 UZS              │
│ Остаток:      850 000 UZS              │
│                                        │
│ ▼ Платежи (2)                          │
│   20 мая · 200 000 · наличные          │
│   21 мая · 200 000 · банк              │
│                                        │
│ [ Оплатить остаток ]                   │
│ [ Добавить платёж ]                    │
└────────────────────────────────────────┘
```

### AT_RECEIPT — Card 5 СКРЫТА

```
[Card 5 not rendered. Combined receive+pay в Card 6]
```

### DEFERRED

```
┌────────────────────────────────────────┐
│ Оплата (отсрочка)               ⚠     │
│ ─────────────────────────────────────  │
│ Обязательство: 1 250 000 UZS           │
│ Дедлайн: 15 июня 2026 (через 26 дней)  │
│ Оплачено: 0 UZS                        │
│                                        │
│ [ Совершить платёж ]                   │
└────────────────────────────────────────┘
```

### INSTALLMENT (со schedule)

```
┌────────────────────────────────────────┐
│ Оплата (рассрочка)              ⚠     │
│ ─────────────────────────────────────  │
│ Обязательство: 1 250 000 UZS           │
│ График: 5 платежей × 250 000           │
│                                        │
│ ▼                                       │
│ 1.  1 июня     250 000  [Оплатить]    │
│ 2.  1 июля     250 000   ожидает       │
│ 3.  1 авг.     250 000   ожидает       │
│ 4.  1 сент.    250 000   ожидает       │
│ 5.  1 окт.     250 000   ожидает       │
│                                        │
└────────────────────────────────────────┘
```

### PARTIAL

```
┌────────────────────────────────────────┐
│ Оплата (частичная)              ⚠     │
│ ─────────────────────────────────────  │
│ Обязательство: 1 250 000 UZS           │
│ Предоплата:    500 000 UZS (40%)       │
│ В долг:        750 000 UZS             │
│ Дедлайн долга: 15 июня                 │
│                                        │
│ [ Оплатить предоплату 500 000 ]        │
└────────────────────────────────────────┘
```

### ON_SALE (CONSIGNED procurement)

```
┌────────────────────────────────────────┐
│ Накопленные обязательства              │
│ (по продажам с реализации)             │
│ ─────────────────────────────────────  │
│ Долг поставщику: 240 000 UZS           │
│ За продажи: 12 шт.                     │
│ ▼ Детально                              │
│   18 мая · продажа 5 шт. · 100 000     │
│   19 мая · продажа 7 шт. · 140 000     │
│                                        │
│ [ Оплатить накопленное ]               │
└────────────────────────────────────────┘
```

### Component contract

```typescript
// ProcurementCardPayment.vue
defineProps<{
  timing: PaymentTiming  // PREPAID | PARTIAL | DEFERRED | INSTALLMENT | AT_RECEIPT | ON_SALE
  obligationAmount: string
  paidAmount: string
  remainingAmount: string
  currency: string
  payments: Payment[]
  schedule?: PaymentScheduleEntry[]  // для INSTALLMENT
  deadline?: string  // для DEFERRED
  consignmentObligations?: ConsignmentPayable[]  // для ON_SALE
}>()
defineEmits<{
  'pay-full': []
  'pay-partial': []
  'pay-schedule-entry': [entryId: number]
  'pay-consignment': []
}>()
```

Если `timing === 'AT_RECEIPT'` — компонент рендерит **null** (карточка скрыта).

---

## Card 6 — Приёмка

### State: ничего не принято (OPEN, ожидаем receive)

```
┌────────────────────────────────────────┐
│ Приёмка                                │
│ ─────────────────────────────────────  │
│ Запланировано: 230 шт. на 1 250 000   │
│ Принято: 0 шт.                         │
│                                        │
│ [ Принять товар ]                      │
└────────────────────────────────────────┘
```

### State: AT_RECEIPT combined action

```
┌────────────────────────────────────────┐
│ Приёмка и оплата                       │
│ ─────────────────────────────────────  │
│ Запланировано: 230 шт. на 1 250 000   │
│ Принято: 0 шт.                         │
│ Оплата: при приёмке (по получению)     │
│                                        │
│ [ Принять и оплатить ]                 │
└────────────────────────────────────────┘
```

Действие открывает sheet, где выбирается cash_account + qty per item +
автомат-payment в одной транзакции.

### State: после частичного приёма

```
┌────────────────────────────────────────┐
│ Приёмка                                │
│ ─────────────────────────────────────  │
│ Запланировано: 230 шт.                 │
│ Принято: 180 шт. (78%)                 │
│ Осталось: 50 шт.                       │
│                                        │
│ ▼ Приёмки (1)                          │
│ ┌───────────────────────────────────┐ │
│ │ 20 мая — Приёмка #1               │ │
│ │ ✓ Кока-кола: 100 из 100           │ │
│ │ ✓ Спрайт: 50 из 50                │ │
│ │ ⚠ Фанта: 30 из 80 — не привезли   │ │
│ │   📎 Накладная.pdf                │ │
│ └───────────────────────────────────┘ │
│                                        │
│ [ Принять оставшееся ]                 │
└────────────────────────────────────────┘
```

### State: 100% принято (RECEIVED)

```
┌────────────────────────────────────────┐
│ Приёмка                          ✓     │
│ ─────────────────────────────────────  │
│ Принято полностью.                     │
│                                        │
│ ▼ Приёмки (2)                          │
│ ┌───────────────────────────────────┐ │
│ │ 20 мая — Приёмка #1   180/230     │ │
│ ├───────────────────────────────────┤ │
│ │ 22 мая — Приёмка #2    50/50      │ │
│ └───────────────────────────────────┘ │
└────────────────────────────────────────┘
```

### Receive sheet (открывается по кнопке «Принять товар»)

```
┌────────────────────────────────────────┐
│ ← Приёмка товара              ✕        │
│                                        │
│ Склад: [ Главный склад ▼ ]            │
│ Дата приёма: [ 20 мая 2026 ]          │
│                                        │
│ ─────────────────────────────────────  │
│ Кока-кола 0.5л                         │
│ Заказано: 100  ▼ Принято: [100]       │
│ Причина расхождения: —                 │
│ ─────────────────────────────────────  │
│ Спрайт 0.5л                            │
│ Заказано: 50  ▼ Принято: [48]         │
│ Причина: [ Битые ▼ ]                  │
│   ○ Без расхождения                    │
│   ● Битые                              │
│   ○ Не привезли, ждём                  │
│   ○ Возврат по качеству                │
│   ○ Закрыть с недостачей               │
│ ─────────────────────────────────────  │
│ Фанта 0.5л                             │
│ Заказано: 80  ▼ Принято: [80]         │
│ ─────────────────────────────────────  │
│                                        │
│ Документы:                             │
│ [ 📎 Прикрепить накладную ]            │
│                                        │
│ [ Принять (180 из 230) ]               │
└────────────────────────────────────────┘
```

Для PARTNERSHIP — в этом же sheet перед confirm появляется блок
«Подтвердить распределение капитала» с editable per-partner amounts
(если planned shares не совпадут с actual money flow).

### Component contract

```typescript
// ProcurementCardReceive.vue
defineProps<{
  procurement: ProcurementWorkspacePayload
  receiveBatches: ReceiveBatch[]
  isAtReceipt: boolean  // for combined action label
  canReceive: boolean
}>()
defineEmits<{
  'receive-start': []
}>()

// WorkspaceReceiveConfirmSheet.vue (existing — extend)
// + new fields for qty_received per line, discrepancy_reason,
// + capital allocation editor for PARTNERSHIP,
// + cash account picker for AT_RECEIPT
```

---

## Card 7 — История и документы

```
┌────────────────────────────────────────┐
│ История и документы                    │
│ ─────────────────────────────────────  │
│ Документы (2):                         │
│ ┌───────────────────────────────────┐ │
│ │ 📎 Накладная.pdf  (Приёмка #1)    │ │
│ │ 📎 Договор.pdf  (Procurement)     │ │
│ └───────────────────────────────────┘ │
│ [ + Прикрепить документ ]              │
│                                        │
│ ▼ События (7)                          │
│   18 мая  Создан                       │
│   18 мая  + 3 товара                   │
│   19 мая  Подтверждено                 │
│   20 мая  Оплата 400 000               │
│   20 мая  Приёмка #1 — 180/230         │
│   21 мая  + 1 расход                   │
│   22 мая  Приёмка #2 — 50/50           │
│                                        │
└────────────────────────────────────────┘
```

Свёрнута по умолчанию (показывается только заголовок и счётчики). Тап →
разворот.

### Component contract

```typescript
// ProcurementCardHistory.vue
defineProps<{
  attachments: Attachment[]
  events: ProcurementEvent[]
  procurementId: number
}>()
defineEmits<{
  'attachment-upload': []
  'attachment-view': [attachmentId: number]
  'attachment-delete': [attachmentId: number]
}>()
```

---

## Bottom action bar (sticky)

**Один primary action**, label меняется по состоянию:

| Состояние procurement | Primary action label |
|---|---|
| DRAFT, empty | «Сохранить черновик» (disabled) |
| DRAFT, has data | «Сохранить черновик» |
| DRAFT, ready to confirm | «Подтвердить и оплатить» (PREPAID) / «Подтвердить» (DEFERRED, etc.) |
| OPEN, нужна оплата (PREPAID) | «Оплатить полностью» |
| OPEN, ожидает приёма | «Принять товар» |
| OPEN, AT_RECEIPT | «Принять и оплатить» |
| PARTIALLY_RECEIVED | «Принять оставшееся» |
| RECEIVED 100% | «Закрыть приход» |
| CLOSED | bar скрыт |

Под кнопкой — небольшая контекстная подсказка (что произойдёт):
```
┌────────────────────────────────────────┐
│ [ Подтвердить и оплатить → ]           │
│ Зафиксирует состав и спишет 1 250 000  │
└────────────────────────────────────────┘
```

### Component contract

```typescript
// ProcurementBottomActionBar.vue
defineProps<{
  primaryAction: {
    label: string
    description?: string
    disabled: boolean
  }
  status: ProcurementStatus
}>()
defineEmits<{
  'primary-click': []
}>()
```

---

## Conditional rendering matrix (для всех 8 комбинаций)

| # | Combination | Card 1 timing chip | Card 3 (Расходы) | Card 4 (Финансирование) | Card 5 (Оплата) | Card 6 (Приёмка) |
|---|---|---|---|---|---|---|
| 1 | OWN_FUNDS × PREPAID × OWNED | Предоплата | ✓ Доступна | ✗ Скрыта | Multi-payment, primary=«Оплатить остаток» | Receive после оплаты |
| 2 | OWN_FUNDS × AT_RECEIPT × OWNED | По получению | ✓ Доступна | ✗ Скрыта | ✗ Скрыта | «Принять и оплатить» |
| 3 | OWN_FUNDS × PARTIAL × OWNED | Частичная | ✓ Доступна | ✗ Скрыта | Upfront + payable preview | Receive в любой момент |
| 4 | OWN_FUNDS × DEFERRED × OWNED | Отсрочка | ✓ Доступна | ✗ Скрыта | Payable + deadline | Receive до платежей |
| 5 | OWN_FUNDS × INSTALLMENT × OWNED | Рассрочка | ✓ Доступна | ✗ Скрыта | Schedule builder | Receive до платежей |
| 6 | OWN_FUNDS × ON_SALE × CONSIGNED | На реализации | ✗ Disabled | ✗ Скрыта | Накопленные обязательства | Receive с CONSIGNED stock |
| 7 | PARTNERSHIP × PREPAID × OWNED | Предоплата (партнёрский) | ✓ Доступна | ✓ Capital allocation | Single payment из договора | Receive после оплаты |
| 8 | PARTNERSHIP × AT_RECEIPT × OWNED | По получению (партнёрский) | ✓ Доступна | ✓ Capital allocation | ✗ Скрыта | «Принять и оплатить» из договора |

Для MIXED procurement (OWN_FUNDS только):
- Card 3: disabled с подсказкой (landed expenses запрещены если есть CONSIGNED items)
- Card 5: для OWNED части — обычная по timing; для CONSIGNED части — отдельный блок «Накопленные обязательства»

---

## State management (Pinia)

**Single store** `useProcurementWorkspaceStore` (один procurement в памяти):

```typescript
// frontend/src/modules/intake/stores/procurementWorkspace.ts
export const useProcurementWorkspaceStore = defineStore('procurementWorkspace', () => {
  const procurement = ref<ProcurementWorkspacePayload | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const abortController = ref<AbortController | null>(null)

  // ───── Lifecycle ─────
  async function load(procurementId: number): Promise<void> {
    abortController.value?.abort()
    abortController.value = new AbortController()
    isLoading.value = true
    try {
      const data = await fetchProcurementWorkspace(procurementId, {
        signal: abortController.value.signal,
      })
      procurement.value = data
    } finally {
      isLoading.value = false
    }
  }

  // ───── Actions ─────
  async function dispatch(action: string, payload: object): Promise<void> {
    const result = await dispatchWorkspaceAction(
      procurement.value!.id, action, payload
    )
    procurement.value = result  // backend returns full updated workspace
  }

  // Specific actions wrap dispatch:
  async function selectSupplier(supplierId: number) {
    return dispatch('UPDATE_SOURCE', { supplier_id: supplierId })
  }
  async function changeTiming(timing: string) {
    return dispatch('UPDATE_SETTLEMENT', { terms: { type: timing } })
  }
  // ... etc for all actions

  // ───── Computed ─────
  const primaryActionLabel = computed(() => {
    // logic based on status + timing + state
  })

  return {
    procurement, isLoading, error,
    load, dispatch,
    selectSupplier, changeTiming, // ...
    primaryActionLabel,
  }
})
```

**AbortController** на каждой `load()` — отмена предыдущего запроса при
быстрой навигации. Pattern из CLAUDE.md.

**Дебаунс 300ms** на input-driven actions (currency switch, search, etc.) —
тоже из CLAUDE.md.

---

## API client extension

Файл `frontend/src/api/partnerships.ts` уже содержит много нужного. Добавить:

```typescript
// New endpoints needed by Wave B:

export async function reverseReceiveBatch(
  procurementId: number,
  batchId: number,
  reason: string,
): Promise<ProcurementWorkspacePayload> { ... }

export async function cancelProcurement(
  procurementId: number,
  reason: string,
): Promise<ProcurementWorkspacePayload> { ... }

export async function applyItemsAmendment(
  procurementId: number,
  newItems: ProcurementItemInput[],
  reason: string,
): Promise<ProcurementWorkspacePayload> { ... }

export async function applyExpensesAmendment(
  procurementId: number,
  newExpenses: ProcurementExpenseInput[],
  reason: string,
): Promise<ProcurementWorkspacePayload> { ... }

// Combined for AT_RECEIPT:
export async function receiveAndPayBatch(
  procurementId: number,
  receivePayload: ReceiveBatchInput,
  paymentPayload: PaymentInput,
): Promise<ProcurementWorkspacePayload> { ... }
```

Attachments через новый `frontend/src/api/attachments.ts`:

```typescript
export async function uploadAttachment(
  attachableType: string,
  attachableId: number,
  file: File,
  kind: string,
  caption?: string,
): Promise<Attachment> { ... }

export async function listAttachments(
  attachableType: string,
  attachableId: number,
): Promise<Attachment[]> { ... }

export async function deleteAttachment(attachmentId: number): Promise<void> { ... }
```

---

## Slice plan для Wave B

14 slices. Каждый — отдельная сессия (или 2-3 ходки если делегировано). После каждого slice — review founder'ом перед следующим.

| # | Slice | Что входит | Зависимости |
|---|---|---|---|
| **B-1** | Shell + routing + store | Удалить старый ProcurementWorkspace.vue; создать новый shell (страница + layout); pinia store с load/dispatch; routing wire-up | Wave A complete |
| **B-2** | Header + Bottom action bar | Header с status badge / action menu / summary; bottom action bar с primary action; state-dependent labels | B-1 |
| **B-3** | Card 1 — Поставщик и оплата | Supplier picker (использовать существующий sheet); timing chips; agreement picker для PARTNERSHIP | B-1, B-2 |
| **B-4** | Card 2 — Товары | Список items; quick-create sheet (existing); variant picker (existing); swipe actions; FAB +; для MIXED — переключатель ownership на add | B-3 |
| **B-5** | Card 3 — Расходы | Список expenses; bottom sheet редактирования; allocation method picker; disabled state для CONSIGNED | B-4 |
| **B-6** | Card 4 — Финансирование (PARTNERSHIP) | Capital allocation preview; editable amounts per partner; show agreement balance | B-3 |
| **B-7** | Card 5 — Оплата (variations) | Все варианты timing-карточки (PREPAID/PARTIAL/DEFERRED/INSTALLMENT/ON_SALE); payment sheet; multi-payment history | B-3, Wave A-1 (AT_RECEIPT) |
| **B-8** | Card 6 — Приёмка | Receive sheet с per-line qty + reason codes; ReceiveBatch history list; partnership capital snapshot editor | Wave A-3 (discrepancy fields) |
| **B-9** | Card 7 — История и документы | Event timeline; attachment uploader / viewer; integration с Wave A-4 attachments | Wave A-4 (attachments) |
| **B-10** | AT_RECEIPT combined action | Receive+Pay sheet в одной транзакции; cash account picker; partnership variant | Wave A-1 |
| **B-11** | Conditional matrix wire-up | Readiness indicators на карточках; show/hide логика по всем 8 комбинациям; primary action state machine | Все Card slices |
| **B-12** | Amendment flow | UI для AMEND_ITEMS / AMEND_EXPENSES; before/after preview; reason input | Wave A-7 |
| **B-13** | Cancel + Reverse receive flows | UI для CANCEL_PROCUREMENT и REVERSE_RECEIVE_BATCH; confirmation dialogs | Wave A-5, A-6 |
| **B-14** | Polish + responsive | Animations 150-300ms; reduced-motion support; loading states; error states; empty states; «завести по факту» entry point | Все предыдущие |

---

## Что НЕ в Wave B (отложено)

- **Desktop variant** — отдельный design+build cycle после MVP. Wave B = mobile-first.
- **Templates / clone procurement** — после MVP.
- **Multi-editor conflict protection** — после MVP.
- **Excel import** — после MVP.
- **AT_RECEIPT для CONSIGNED** — невалидная комбинация (CONSIGNED это ON_SALE).
- **Returnability UI** — E09 Phase 3 (после MVP).

---

## Component файлы (новая структура)

```
frontend/src/modules/intake/
├─ views/
│  └─ ProcurementWorkspaceView.vue          ← главная страница
├─ components/
│  └─ workspace/
│     ├─ ProcurementHeader.vue              ← B-2
│     ├─ ProcurementBottomActionBar.vue     ← B-2
│     ├─ ProcurementCardSupplier.vue        ← B-3
│     ├─ ProcurementCardItems.vue           ← B-4
│     │  ├─ ProcurementItemRow.vue
│     │  └─ ProcurementItemAddSheet.vue
│     ├─ ProcurementCardExpenses.vue        ← B-5
│     │  └─ ProcurementExpenseEditSheet.vue
│     ├─ ProcurementCardFinancing.vue       ← B-6
│     │  └─ CapitalAllocationEditSheet.vue
│     ├─ ProcurementCardPayment.vue         ← B-7
│     │  ├─ PaymentMakeSheet.vue
│     │  ├─ PaymentScheduleEditor.vue       (для INSTALLMENT)
│     │  └─ ConsignmentObligationsBlock.vue (для ON_SALE)
│     ├─ ProcurementCardReceive.vue         ← B-8
│     │  ├─ ReceiveBatchHistoryRow.vue
│     │  └─ ReceiveBatchConfirmSheet.vue   (extend existing)
│     ├─ ProcurementCardHistory.vue         ← B-9
│     │  ├─ AttachmentList.vue
│     │  ├─ AttachmentUploader.vue
│     │  └─ EventTimeline.vue
│     ├─ AmendmentSheet.vue                 ← B-12
│     ├─ ProcurementCancelDialog.vue        ← B-13
│     └─ ReverseReceiveBatchDialog.vue      ← B-13
└─ stores/
   └─ procurementWorkspace.ts               ← B-1
```

Existing reusable components сохранить (не переделывать):
- `WorkspaceVariantPickerSheet.vue`
- `WorkspaceQuickProductSheet.vue`
- `WorkspaceSupplierPickerSheet.vue` (если есть; иначе создать)
- `MoneyCurrencyInput.vue`
- `InvestmentAgreementQuickForm.vue`
- `InvestmentAgreementDetailSheet.vue`

---

## Design tokens (CSS custom properties)

Все стили через design tokens из `frontend/src/styles/`:

- Spacing: `--space-1` ... `--space-6`
- Radius: `--radius-sm/md/lg`
- Typography: `--text-xs/sm/base/lg/xl`
- Colors: `--color-brand-*`, `--color-text-*`, `--color-bg-*`, `--color-border-*`
- Animation: 150-300ms transitions, `prefers-reduced-motion` respected
- Icons: Lucide (никаких эмодзи как структурных иконок — только в подсказках/badge)

Mobile-first: дизайнить на 375px, расширять breakpoints для 768/1024/1440.

---

## Test strategy

Frontend tests **отложены** (см. vision и architecture-first policy — не пишем тесты ради тестов). Архитектурные инварианты живут в backend invariants suite (`test_e08_sharia_invariants.py`, `test_e09_*`).

Когда после MVP появится регрессионная боль — поставим vitest и напишем смоук-сценарии. Сейчас — пропускаем.

---

## Что от founder'а нужно по ходу Wave B

Перед каждым slice:
- Просмотр mockup-а конкретной карточки (этот документ — anchor)
- Согласие на старт slice
- Возможность правки mockup-а (этот документ может обновляться)

После каждого slice:
- Демонстрация работающей карточки в браузере
- Решение «следующий slice» или «исправить что-то здесь»

---

## Связанные документы

- [`E09-procurement-completeness.md`](./E09-procurement-completeness.md) — эпик, MVP scope
- [`E09-procurement-ui-design.md`](./E09-procurement-ui-design.md) — UI design anchor (mental model, IA, conditional matrix)
- [`E09-wave-A-execution-plan.md`](./E09-wave-A-execution-plan.md) — backend preconditions
- [`vision.md`](../vision.md) — продуктовый контекст
