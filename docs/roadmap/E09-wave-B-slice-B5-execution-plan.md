# E09 Wave B — Slice B-5 Execution Plan (для Sonnet)

**Slice:** B-5 — Card 3 «Расходы»
**Цель:** добавить карточку landed expenses с per-row edit и
allocation method picker. Структурно близка к B-4 (items), но с
особенностью: для CONSIGNED procurement карточка disabled целиком
(OPEN-4 guard из Wave A).

> Опус согласовал. Sonnet исполняет. Branch points → STOP.
> Связанные документы: дизайн doc, эпик, CLAUDE.md.

---

## Architectural baseline

- `ProcurementCardExpenses.vue` ≤250 строк
- `ProcurementExpenseRow.vue` ≤120 строк
- `ProcurementExpenseEditSheet.vue` ≤220 строк
- `ProcurementWorkspaceView.vue` после интеграции ≤220 строк

Структура близка к B-4 — переиспользуй стилистику и паттерны (row +
edit sheet + card wrapper).

---

## Pre-flight reads

1. `frontend/src/api/partnerships.ts` — `documents.expenses[]` shape
   (есть `id`, `expense_type`, `amount`, `currency`, `fx_rate`,
   `allocation_method`, `target_item_ids[]`, `lifecycle_state`,
   `payment_state`, `locked_reason`).
2. `frontend/src/api/partnerships.ts` — `UPDATE_EXPENSES` action.
   Скорее всего payload — массив expenses, как `UPDATE_ITEMS`.
3. `frontend/src/types/enums.ts` или `domainLabels.ts` — найти
   существующие label maps для `expense_type` (`logistics`,
   `customs`, `tax`, etc.) и `allocation_method` (`by_value`,
   `by_quantity`, `global`, `per_item`). Если их нет — создать.
4. `frontend/src/modules/intake/components/workspace/WorkspaceExpenseCard.vue`
   (existing legacy, 294 строк) — посмотреть **только для понимания
   домена**, не для прямого переиспользования. Там legacy-coupling.
5. `ProcurementCardItems.vue` (B-4) — образец структуры карточки +
   row + edit sheet, копируй паттерны (стилистика, decomposition).

Если `UPDATE_EXPENSES` action не существует или payload shape
неожиданный — STOP.

---

## Контракт

### Новый файл: `ProcurementExpenseRow.vue`

**Mockup:**

```
┌────────────────────────────────────────┐
│ 🚚 Логистика                      ›    │
│ 50 000 UZS · по стоимости              │
│ На все товары                          │
└────────────────────────────────────────┘
```

Для `allocation_method='per_item'` с конкретными targets:
```
│ На: Кока-кола 0.5л, Спрайт 0.5л       │
```

**Props/emits:**

```ts
defineProps<{
  expense: ProcurementExpensePayload
  items: ProcurementItemPayload[]  // нужны для display targets names
  isEditable: boolean
}>()
defineEmits<{
  click: [expenseId: number]
  delete: [expenseId: number]
}>()
```

**Поведение:**
- Иконка по `expense_type` (можно lucide: Truck для logistics, FileText для documents, etc., либо просто emoji-prefixes без иконок). Минимум — текстовый label типа.
- Display: `expense_type_label` + amount + currency + allocation summary.
- Allocation summary:
  - `by_value` → «по стоимости»
  - `by_quantity` → «по количеству»
  - `global` → «глобально (на все товары)»
  - `per_item` → если 1-2 target — список имён; если 3+ — «На N товаров»
- Click → emit click → parent открывает edit sheet.
- Trash icon (только isEditable) → emit delete с window.confirm.

### Новый файл: `ProcurementExpenseEditSheet.vue`

**Поля:**
- Expense type — select (logistics / customs / tax / commission / other).
  Если в проекте уже есть chip-group для choice — используем.
- Amount (MoneyCurrencyInput с currency).
- FX rate (auto если currency ≠ UZS).
- Allocation method chips:
  - «По стоимости» (`by_value`)
  - «По количеству» (`by_quantity`)
  - «На все» (`global`)
  - «На выбранные» (`per_item`)
- Если `per_item` выбран — показывается checkbox-list items procurement-а
  (название + qty), пользователь отмечает целевые. Если other allocation_method
  — этот блок скрыт, `target_item_ids = []`.
- Save / Delete кнопки.

**Props/emits:**

```ts
defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  editingExpenseId: number | null
}>()
defineEmits<{
  'update:open': [value: boolean]
  save: [payload: ExpenseEditPayload]
  delete: [expenseId: number]
}>()
```

### Новый файл: `ProcurementCardExpenses.vue`

**Mockup (empty, OWN_FUNDS):**

```
┌────────────────────────────────────────┐
│ Расходы                          0     │
│                                        │
│ Нет дополнительных расходов.           │
│                                        │
│ [ + Добавить расход ]                  │
└────────────────────────────────────────┘
```

**Mockup (disabled, CONSIGNED procurement):**

```
┌────────────────────────────────────────┐
│ Расходы                       disabled │
│                                        │
│ ⓘ Расходы недоступны для прихода      │
│   на реализации (консигнация).         │
│                                        │
└────────────────────────────────────────┘
```

**Mockup (filled):**

```
┌────────────────────────────────────────┐
│ Расходы                          2     │
│ ─────────────────────────────────────  │
│ 🚚 Логистика                      ›    │
│ 50 000 UZS · по стоимости              │
│ ─────────────────────────────────────  │
│ 📋 Таможня                        ›    │
│ 30 000 UZS · на 2 товара               │
│ ─────────────────────────────────────  │
│ Итого расходов: 80 000 UZS             │
│                                        │
│ [ + Добавить расход ]                  │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'update-expenses': [expenses: ExpensePayload[]]
  'delete-expense': [expenseId: number]
}>()
```

**Поведение:**
- Если `procurement.goods_ownership === 'CONSIGNED'` (или derived MIXED с любым
  CONSIGNED item — TODO проверить semantics): рендерить disabled state с
  объяснением, без add/edit. NB: backend OPEN-4 guard отвергнет UPDATE_EXPENSES
  для CONSIGNED — UI просто отражает это правило.
- Иначе — стандартный список с FAB.
- Считает total в UZS (sum × fx_rate).
- Click row → editing sheet; FAB → editing sheet (создание).
- Sheet save → формирует полный массив expenses, emit `update-expenses`.

### Модификация View

`ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardExpenses`.
- В `cards-container` после `ProcurementCardItems` добавить
  `<ProcurementCardExpenses>`.
- Handler `onUpdateExpenses(expenses)` → `store.dispatch('UPDATE_EXPENSES', { expenses })`.
- Handler `onDeleteExpense(id)` → стрOIT new array без этого id и dispatch.

---

## Что НЕ делаем в B-5

- Pay expenses (это часть оплаты, в B-7).
- Expense lifecycle states (DRAFT/READY_FOR_RECEIVE/RECEIVED/CANCELLED) — backend сам управляет, UI просто отражает через locked_reason.
- Amendments после confirm — B-12.

---

## STOP-точки

1. **`UPDATE_EXPENSES` payload shape неожиданный** — STOP.
2. **`allocation_method` enum значения отличаются** от ожидаемых
   (`by_value` / `by_quantity` / `global` / `per_item`). Sonnet
   найдёт фактические значения в коде. STOP если рассогласование.
3. **`expense_type` enum значения** — найти фактический список,
   создать label-map.
4. **Размер компонентов > budget** — STOP.
5. **`isCONSIGNED` derived condition** — если procurement.goods_ownership
   API уже не строка а нечто другое (например объект с MIXED) — выяснить.

---

## Verification

1. `/procurements/:id` с OWN_FUNDS PREPAID — карточка Расходы рендерится empty.
2. Tap «+ Добавить расход» → sheet открывается.
3. Выбрать тип, ввести сумму, allocation `by_value` → save → row появляется.
4. Allocation `per_item` → появляется список items с чекбоксами, выбрать 2, save → row показывает «На 2 товара».
5. Edit row → sheet с pre-filled, изменить allocation → save.
6. Delete → confirm → row пропадает, total пересчитан.
7. Переключить timing на ON_SALE (или goods_ownership CONSIGNED) → карточка
   становится disabled с info-блоком.
8. Попытка отправить expense на CONSIGNED через прямой dispatch → backend
   отказ с понятной ошибкой (это backend, UI просто не даёт).

---

## Commit

```
feat(E09-wave-B-5): expenses card + per-item allocation picker

Third content card. ProcurementCardExpenses lists landed expenses
with allocation summary; tapping opens
ProcurementExpenseEditSheet for add/edit. Expense allocation method
chips (by_value / by_quantity / global / per_item) drive an inline
target items checklist when per_item is selected.

The card is disabled for CONSIGNED procurement (matching the
backend OPEN-4 guard from Wave A) with an explanatory info block.
The two-line addition to backend serializer in 13c0829 isn't needed
here — expenses already exposed.

UPDATE_EXPENSES receives the full expenses array, same pattern as
UPDATE_ITEMS in B-4.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После B-5

Дальше **B-6 (Финансирование)** — единственная PARTNERSHIP-only карточка.
Здесь же закрывается agreement picker stub из B-3.
