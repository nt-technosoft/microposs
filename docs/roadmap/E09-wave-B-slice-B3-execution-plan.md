# E09 Wave B — Slice B-3 Execution Plan (для Sonnet)

**Slice:** B-3 — Card 1 «Поставщик и оплата»
**Цель:** добавить в workspace первую содержательную карточку: supplier
picker + timing chips. Это «top» карточка, которая определяет shape
остального экрана (через `funding_source`, `payment_timing`,
`goods_ownership`).

> Опус согласовал. Sonnet исполняет. Branch points → STOP.
>
> Связанные документы:
> - [`E09-wave-B-ui-design-detailed.md`](./E09-wave-B-ui-design-detailed.md) — mockups
> - [`E09-procurement-completeness.md`](./E09-procurement-completeness.md) — 8 легальных комбинаций
> - CLAUDE.md → «Frontend decomposition rules»

---

## Architectural baseline

Размерные budget-ы для B-3:

- `ProcurementCardSupplier.vue` ≤250 строк (это большая карточка с несколькими секциями — supplier, timing, optional ownership toggle для CONSIGNED)
- `WorkspaceSupplierPickerSheet.vue` ≤200 строк
- `ProcurementWorkspaceView.vue` после интеграции ≤160 строк (минимальный рост — добавляется одна карточка)

Если что-то пухнет — STOP, surface, обсуждаем декомпозицию (например выделить TimingChips как отдельный компонент).

---

## Pre-flight reads

1. `frontend/src/components/feedback/AppBottomSheet.vue` — найти props и slots
   bottom-sheet helper-а. Использовать в picker.
2. `frontend/src/api/suppliers.ts:fetchSuppliers` — сигнатура
   `(params?, signal?)`, возвращает `PaginatedResponse<Supplier>`.
3. `frontend/src/api/partnerships.ts` — найти `WorkspaceActionKey`
   union; убедиться что `UPDATE_SOURCE`, `UPDATE_SETTLEMENT` существуют
   как ключи (уже видели — они есть).
4. `frontend/src/modules/intake/components/workspace/WorkspaceVariantPickerSheet.vue`
   — образец для написания нового picker sheet (как обращается с
   `AppBottomSheet`, как делает search, как эмитит выбор).
5. Существующие enum-типы для timing — в `frontend/src/types/enums.ts`
   или в `api/partnerships.ts`. Найти существующие или создать с
   точными значениями (`PREPAID`, `AT_RECEIPT`, `PARTIAL`, `DEFERRED`,
   `INSTALLMENT`, `ON_SALE`).

Если AppBottomSheet API сильно отличается от ожиданий — STOP.

---

## Контракт

### Новый файл: `WorkspaceSupplierPickerSheet.vue`

Расположение: `frontend/src/modules/intake/components/workspace/WorkspaceSupplierPickerSheet.vue`

**Mockup (open state):**

```
┌────────────────────────────────────────┐
│ Выберите поставщика              ✕    │
│ ──────────────────────────────────────│
│ [ Поиск… 🔍                       ]    │
│ ──────────────────────────────────────│
│ Coca-Cola Узбекистан              ›   │
│ Тел: +998 90 123 45 67                │
│ ──────────────────────────────────────│
│ Pepsi Bottlers                    ›   │
│ ──────────────────────────────────────│
│ ...                                   │
│                                       │
│ [ + Создать нового поставщика ]       │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  open: boolean
  selectedId?: number | null
}>()
defineEmits<{
  'update:open': [value: boolean]
  select: [supplierId: number]
  'create-new': []  // wire-up в B-4 или позже; в B-3 — placeholder toast
}>()
```

**Поведение:**
- Использует `AppBottomSheet` как контейнер. Header «Выберите поставщика» + close button (emit `update:open` с `false`).
- Search input с debounce 300ms (CLAUDE.md convention) → передаёт `search` параметр в `fetchSuppliers`.
- AbortController для re-fetch при изменении search или re-open.
- Список suppliers через `fetchSuppliers({ active: true, search })`.
- Click на supplier → emit `select` + закрытие.
- Click на «Создать нового» → emit `create-new` + закрытие. (Реальный quick-create supplier — отдельный slice, в B-3 toast «будет реализовано»).
- Selected supplier (если `selectedId` пришёл) — подсвечивается в списке (галочка/highlight).
- Loading state, empty state.

### Новый файл: `ProcurementCardSupplier.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementCardSupplier.vue`

**Mockup — state: empty:**

```
┌────────────────────────────────────────┐
│ Поставщик и оплата                ⚠   │
│                                        │
│ [ Выбрать поставщика → ]               │
│                                        │
│ Тип оплаты:                            │
│ ● Предоплата                           │
│ ○ По получению                         │
│ ○ Частичная                            │
│ ○ Отсрочка                             │
│ ○ Рассрочка                            │
│ ○ На реализации                        │
└────────────────────────────────────────┘
```

**Mockup — state: filled:**

```
┌────────────────────────────────────────┐
│ Поставщик и оплата                ✓   │
│ ┌──────────────────────────────────┐  │
│ │ Coca-Cola Узбекистан        ›   │  │
│ │ Тел: +998 90 123 45 67           │  │
│ └──────────────────────────────────┘  │
│ ● Предоплата                          │
└────────────────────────────────────────┘
```

**Mockup — state: PARTNERSHIP funding (agreement stub):**

```
┌────────────────────────────────────────┐
│ Поставщик и оплата                ⚠   │
│ ...                                    │
│ ● Предоплата (партнёрский)            │
│                                        │
│ Инвестиционный договор:                │
│ ⓘ Будет реализовано в Card «Финансир.»│
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'update-source': [payload: { supplier_id?: number | null; funding_source?: string }]
  'update-settlement': [payload: { type: string; goods_ownership?: string }]
  'open-supplier-picker': []
  // agreement picker — stub в B-3, real в B-6
}>()
```

**Поведение:**

- Читает текущее состояние из `procurement.documents.source` (supplier_id,
  funding_source, ...) и `procurement.documents.settlement` (terms.type).
  Точные пути — посмотреть в payload type.
- Supplier row: если выбран — показывает имя + телефон. Если нет — кнопка
  «Выбрать поставщика». Tap → emit `open-supplier-picker`.
- Timing chips: 6 опций. Single-select (radio-style). Active chip — фон
  brand-цвет. Click → emit `update-settlement` с `type`.
- Implicit goods_ownership: если timing = `ON_SALE` → ownership = `CONSIGNED`
  автоматически. Если другой timing → `OWNED`. Это backend handles в
  `validate_procurement_combination` (правило: ON_SALE может быть только с
  CONSIGNED). UI просто эмитит timing, backend подтянет ownership правило.
  В B-3 НЕ показываем отдельный ownership toggle — это сложность для MIXED
  procurement (per-item ownership), которая придёт в B-4 (карточка
  «Товары»).
- Funding source toggle (если хочется) — пока не делаем явно. Funding
  определяется через выбор timing: если PARTNERSHIP-only timings — UI
  предлагает PARTNERSHIP, иначе OWN_FUNDS. **Проще: timing chips
  показывают все 6 значений; если пользователь выбрал PREPAID или
  AT_RECEIPT — открывается возможность переключить funding source через
  chip ниже или через дополнительный selector.** STOP HERE — это
  усложняет UX. Альтернатива:
  - **Вариант A (упрощённый, в B-3):** Timing chips показывают только
    значения, легальные для **текущего funding_source**. Default
    funding = `OWN_FUNDS`. Для переключения на PARTNERSHIP — отдельный
    toggle/chip «Партнёрский приход» вверху карточки, который меняет
    funding и пере-фильтрует timing chips (остаются только PREPAID и
    AT_RECEIPT).
  - **Вариант B:** Показывать все 6 chips, при выборе CONSIGNED-related
    timing — авто-set funding=OWN_FUNDS; при «Партнёрский» — авто-restrict
    timing до PREPAID/AT_RECEIPT.

  **Реализуем Вариант A** — чище UX, явный funding toggle.

- Stub agreement picker для PARTNERSHIP: показываем info-блок «Будет
  реализовано в карточке Финансирование» — никакого emit. Реальная
  привязка — в B-6.

### Модификация View

`ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardSupplier` + `WorkspaceSupplierPickerSheet`.
- В `cards-container` вставить `<ProcurementCardSupplier>`.
- Локальный state: `supplierPickerOpen` (ref).
- Handlers:
  - `onUpdateSource(payload)` → `store.dispatch('UPDATE_SOURCE', payload)`
  - `onUpdateSettlement(payload)` → `store.dispatch('UPDATE_SETTLEMENT', payload)`
  - `onOpenSupplierPicker()` → `supplierPickerOpen = true`
  - `onSupplierSelect(id)` → `onUpdateSource({ supplier_id: id })`, picker автозакрывается
  - `onCreateNewSupplier()` → toast placeholder (B-4+ задача)
- Удалить card-placeholder из cards-container.

---

## Что НЕ делаем в B-3

- Реальный quick-create supplier — `create-new` emit ведёт в toast.
  Создание новых suppliers — отдельный slice (можно в B-4 если найдём
  место, или дополнительный B-3.5).
- Agreement picker для PARTNERSHIP — stub info-блок. Реализация в B-6
  «Карточка Финансирование» где capital allocation тоже живёт.
- Per-item ownership toggle — этого не существует на уровне
  procurement, это атрибут ProcurementItem. Будет в B-4 «Товары».
- Items / expenses / payment / receive — другие slice-ы.

---

## STOP-точки

1. **`AppBottomSheet` API сильно отличается** — props/slots не
   совпадают с ожиданиями (header, body, footer slots; open prop;
   close emit). STOP.
2. **`fetchSuppliers` не работает** с params `{ active, search }`
   или возвращает не paginated structure. STOP.
3. **Action `UPDATE_SOURCE` или `UPDATE_SETTLEMENT` падает** с
   payload `{ supplier_id }` / `{ type }` (например backend ожидает
   nested `{ terms: { type } }`). STOP, не угадывать payload shape.
4. **Размерные budget превышены.** STOP, обсуждаем декомпозицию
   (например TimingChips вынести как отдельный компонент).
5. **Существующий timing enum не содержит `AT_RECEIPT`** — это
   значит Wave A не до конца проникла в frontend types. STOP.

---

## Verification

После slice — посетить:

1. `/procurements/create` → создан новый draft. Карточка «Поставщик и
   оплата» рендерится с пустым состоянием — кнопка «Выбрать
   поставщика», default timing chip (PREPAID).
2. Tap «Выбрать поставщика» → открывается bottom sheet с реальным
   списком из API. Search работает. Select → sheet закрывается,
   карточка показывает выбранного supplier-а.
3. Tap по другому timing chip → дispatch отправляется, после ответа
   backend payload обновляется (если backend разрешил), UI отражает
   новый active chip.
4. Tap «Партнёрский приход» toggle → funding меняется на PARTNERSHIP,
   timing chips перефильтровываются (только PREPAID и AT_RECEIPT
   видимы), показывается info-stub про агреемент.
5. Bottom action bar (из B-2) обновляется по `display.next_action`
   из payload — должен сменить label на следующее действие после
   заполнения supplier+timing (например «Добавить товары»).

---

## Commit

```
feat(E09-wave-B-3): supplier picker card + bottom sheet

First content card in the procurement workspace. Combines supplier
selection (via new WorkspaceSupplierPickerSheet with debounced search
against fetchSuppliers) and payment_timing chips (six values:
PREPAID, AT_RECEIPT, PARTIAL, DEFERRED, INSTALLMENT, ON_SALE) on a
single card.

Funding source has its own toggle at the top of the card — defaults
to OWN_FUNDS, switching to PARTNERSHIP restricts timing chips to
PREPAID and AT_RECEIPT (the only legal combinations).

Agreement picker for PARTNERSHIP is intentionally a stub here — the
real wire-up lands in B-6 alongside capital allocation in the
Financing card.

Per-item goods_ownership is NOT on this card — it's an item-level
attribute that comes in B-4 (items card).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После B-3

Sonnet возвращает founder'у commit + STOP findings. Founder проверяет
визуально + я ревью кода. Дальше B-4 (Карточка «Товары»).
