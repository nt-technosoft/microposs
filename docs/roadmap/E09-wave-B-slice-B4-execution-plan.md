# E09 Wave B — Slice B-4 Execution Plan (для Sonnet)

**Slice:** B-4 — Card 2 «Товары»
**Цель:** добавить вторую содержательную карточку: список товаров +
кнопку добавления + per-line edit/delete + per-item goods_ownership
toggle (для MIXED procurements). Использует existing variant picker и
quick-product sheets.

> Опус согласовал. Sonnet исполняет. Branch points → STOP.
> Связанные документы: дизайн doc, эпик, CLAUDE.md.

---

## Architectural baseline

Размерные budget-ы:

- `ProcurementCardItems.vue` ≤300 строк (большая карточка, оправдано)
- `ProcurementItemRow.vue` ≤150 строк (view-style row, не editable inline)
- `ProcurementItemEditSheet.vue` ≤220 строк (sheet для add/edit одной line)
- `ProcurementWorkspaceView.vue` после интеграции ≤200 строк

Если что-то пухнет — STOP. Возможно стоит вынести FAB+totals в подкомпонент.

---

## Pre-flight reads

1. `frontend/src/modules/intake/components/workspace/WorkspaceItemRow.vue` —
   existing, **draft inline-edit стиль**. **Не переиспользовать целиком** —
   там tight coupling с `useGoodsExpensesWorkspace`. Только взгляд для
   понимания паттернов и стилистики.
2. `frontend/src/modules/intake/components/workspace/WorkspaceVariantPickerSheet.vue` —
   **переиспользуем как есть**. Props/emits — посмотреть и принять.
3. `frontend/src/modules/intake/components/workspace/WorkspaceQuickProductSheet.vue` —
   **переиспользуем как есть** для quick-create нового product.
4. `frontend/src/api/partnerships.ts` — payload `documents.items[]`
   shape (id, product_variant_id, product_variant_name, quantity,
   unit_purchase_price, currency, fx_rate, lifecycle_state,
   `goods_ownership`?). Проверить что Wave A добавила `goods_ownership`
   в ProcurementItem serializer payload — если нет, STOP.
5. `frontend/src/api/partnerships.ts` — actions `UPDATE_ITEMS`,
   `SPLIT_ITEM`. Понять payload shape для UPDATE_ITEMS — скорее всего
   массив items с id/variant/qty/price.

Если `goods_ownership` отсутствует в items payload — STOP, потому что
без него per-item ownership UI не работает.

---

## Контракт

### Новый файл: `ProcurementItemRow.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementItemRow.vue`

**Цель:** view-style строка одного item-а в списке карточки. **Не
inline-editable** — клик на строку открывает edit sheet.

**Mockup:**

```
┌────────────────────────────────────────┐
│ Кока-кола 0.5л                  📦 ›   │  ← badge "Реализация" (consigned)
│ 100 шт × 5 000 = 500 000 UZS           │
└────────────────────────────────────────┘
```

Для OWNED — без иконки, или с 🛍 (опционально). Для CONSIGNED — иконка 📦
и микро-label «Реализация» рядом.

**Props/emits:**

```ts
defineProps<{
  item: ProcurementItemPayload  // тип из api/partnerships.ts documents.items[N]
  isEditable: boolean  // false если procurement.status уже OPEN после confirm
}>()
defineEmits<{
  click: [itemId: number]
  delete: [itemId: number]
}>()
```

**Поведение:**
- Click on row → emit `click` (открывает edit sheet в parent).
- Иконка `Trash` справа (только если isEditable) → emit `delete` с
  confirmation dialog (можно простой `window.confirm` для MVP — нормально).
- Display: name, qty × unit_price = total в operation currency,
  ownership badge если CONSIGNED.

### Новый файл: `ProcurementItemEditSheet.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementItemEditSheet.vue`

**Цель:** bottom-sheet для add new item или edit existing. Использует
existing `WorkspaceVariantPickerSheet` и `WorkspaceQuickProductSheet`
как nested sheets (или просто triggers, открывающие отдельные sheets).

**Поля:**
- Variant picker (открывает WorkspaceVariantPickerSheet)
  - Если variant не выбран — кнопка «Выбрать товар»
  - Если выбран — отображение названия + ссылка «Изменить»
  - Кнопка «Создать новый товар» открывает WorkspaceQuickProductSheet
- Quantity (number input, min 1)
- Unit purchase price (MoneyCurrencyInput для amount + currency selector)
- FX rate (auto-fetched если currency ≠ UZS; editable)
- `goods_ownership` toggle:
  - Если timing = `ON_SALE` → locked на `CONSIGNED`, disabled toggle
  - Если timing = другой → toggle между `OWNED` и `CONSIGNED`
  - В edit-mode для existing item уже принятого partial-receive — locked
- Кнопка «Сохранить» (primary)
- Кнопка «Удалить» (только если edit existing item, secondary destructive)

**Props/emits:**

```ts
defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  editingItemId: number | null  // null = create new
}>()
defineEmits<{
  'update:open': [value: boolean]
  save: [payload: ItemEditPayload]
  delete: [itemId: number]
}>()
```

Sheet сам управляет внутренним state (variant, qty, price). При save —
emit с полным payload, parent отправляет в `UPDATE_ITEMS` action.

### Новый файл: `ProcurementCardItems.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementCardItems.vue`

**Mockup (empty state):**

```
┌────────────────────────────────────────┐
│ Товары                          0   ⚠ │
│                                        │
│ Нет товаров. Добавь первый.            │
│                                        │
│ [ + Добавить товар ]                   │
└────────────────────────────────────────┘
```

**Mockup (filled):**

```
┌────────────────────────────────────────┐
│ Товары                          3   ✓ │
│ ─────────────────────────────────────  │
│ Кока-кола 0.5л                   ›    │
│ 100 шт × 5 000 = 500 000 UZS           │
│ ─────────────────────────────────────  │
│ Спрайт 0.5л                      ›    │
│ 50 шт × 5 000 = 250 000 UZS            │
│ ─────────────────────────────────────  │
│ Фанта 0.5л              📦 Реал. ›    │  ← CONSIGNED item
│ 80 шт × 6 250 = 500 000 UZS            │
│ ─────────────────────────────────────  │
│ Итого: 1 250 000 UZS                   │
│                                        │
│ [ + Добавить товар ]                   │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'update-items': [items: ItemPayload[]]  // full updated list
  'delete-item': [itemId: number]
  // SPLIT_ITEM пока не делаем — это для partial receive prep, ждёт B-8
}>()
```

**Поведение:**
- Читает `procurement.documents.items` — рендерит row-ы через `ProcurementItemRow`.
- Считает total (sum of qty × price в UZS через fx_rate, для UI).
- Local state: `editSheetOpen` (ref), `editingItemId` (ref).
- Click row → `editingItemId = item.id, editSheetOpen = true`.
- Click FAB → `editingItemId = null, editSheetOpen = true`.
- Sheet save → формирует новый items array (replace или add) → emit `update-items`.
- Sheet delete → emit `delete-item` с подтверждением.
- Header показывает count + status icon (✓ если есть >0 items, ⚠ если 0).

### Модификация View

В `ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardItems`.
- В `cards-container` после `ProcurementCardSupplier` добавить `<ProcurementCardItems>`.
- Handler `onUpdateItems(items)` → `store.dispatch('UPDATE_ITEMS', { items })`.
- Handler `onDeleteItem(id)` → строит новый items array без этого id и dispatch.

---

## Что НЕ делаем в B-4

- **SPLIT_ITEM** — отдельная операция для partial receive preparation,
  ждёт B-8 (Receive card). Кнопка split не показывается.
- **Amendments после confirm** — это B-12. Здесь только editable
  состояние (DRAFT/OPEN до первого receive).
- **Discrepancy on receive** — это B-8.
- **Quick-create supplier** stub из B-3 — здесь не трогаем.

---

## STOP-точки

1. **`goods_ownership` отсутствует в items payload** — Wave A не до конца
   проникла в serializer. STOP, surface, нужен backend fix.
2. **`UPDATE_ITEMS` payload shape неожиданный** — например ожидает не
   массив items, а отдельные actions add/update/delete. STOP, не угадываем.
3. **WorkspaceVariantPickerSheet API не подходит** — нужны другие props
   (например `productId` вместо `variantId`). STOP.
4. **Размерные budget превышены.** STOP — обсуждаем что выделить.
5. **MoneyCurrencyInput не работает с FX rate auto-fetch** или нужна
   external composable. STOP.

---

## Verification

После slice:
1. `/procurements/create` с заполненным supplier → карточка «Товары» рендерится empty state.
2. Tap «+ Добавить товар» → sheet открывается. Variant picker работает.
3. Создать новый product через quick-create → возвращается в edit sheet, variant заполнен.
4. Ввести qty + price → save → row появляется в карточке, total рассчитан.
5. Tap row → edit sheet с пред-заполненными значениями. Изменить qty → save → row обновляется.
6. Delete с подтверждением → row пропадает.
7. Для PARTNERSHIP procurement timing=AT_RECEIPT — добавить item, проверить что goods_ownership toggle доступен (OWNED по default).
8. Для ON_SALE timing — toggle locked на CONSIGNED, badge «Реал.» в row.
9. Mix OWNED + CONSIGNED в одном procurement (если allowed validator-ом) → procurement.goods_ownership = MIXED, оба типа rows видны.

---

## Commit

```
feat(E09-wave-B-4): items card + per-line edit + per-item ownership

Adds the items section of the workspace. ProcurementCardItems lists
the procurement's lines as view-only rows; tapping a row or the
"+ Добавить товар" button opens ProcurementItemEditSheet — a bottom
sheet that wraps the existing WorkspaceVariantPickerSheet and
WorkspaceQuickProductSheet for product selection and on-the-fly
creation.

Per-item goods_ownership (Wave A) gets its own toggle in the edit
sheet — auto-locked to CONSIGNED when procurement timing is ON_SALE,
otherwise defaults to OWNED with the user able to flip individual
items. Rows display a "Реал." badge for CONSIGNED items.

UPDATE_ITEMS action receives the full items array after each save /
delete; granular per-line actions are a future optimization.

SPLIT_ITEM (partial-receive prep) is deferred to B-8 where the
Receive card is built; amendments after confirm are B-12.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После B-4

Дальше **B-5 (карточка Расходы)** — близок по структуре к Items, использует
аналогичные паттерны row + edit sheet, плюс allocation logic.
