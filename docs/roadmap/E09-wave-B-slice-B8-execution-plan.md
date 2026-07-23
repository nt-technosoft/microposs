# E09 Wave B — Slice B-8 Execution Plan (для Sonnet)

**Slice:** B-8 — Card 6 «Приёмка»
**Цель:** карточка receive batches с per-line discrepancy capture
(qty_planned vs qty_received + reason_code) + история приёмок +
capital snapshot editor для PARTNERSHIP. Использует Wave A backend
(`quantity_planned`, `quantity_received`, `discrepancy_reason` —
S-3).

> Опус согласовал. Sonnet исполняет.

---

## Architectural baseline

- `ProcurementCardReceive.vue` ≤280 строк (orchestrator + history list)
- `ReceiveBatchHistoryRow.vue` ≤120 строк
- `ReceiveBatchConfirmSheet.vue` ≤320 строк (sheet с per-line UI, может быть большой)
- `CapitalAllocationReceiveBlock.vue` ≤200 строк (опционально, для PARTNERSHIP внутри receive sheet)
- `ProcurementWorkspaceView.vue` после интеграции ≤280 строк

ReceiveBatchConfirmSheet — самый большой компонент в B-8. Если пухнет
> 320 — STOP, выделить capital block или discrepancy block в отдельный.

---

## Pre-flight reads

1. `frontend/src/api/partnerships.ts`:
   - `documents.receive_batches[]` shape: id, received_at, warehouse_*,
     lines[], expenses[], capital_snapshot, journal_entry_id
   - `receive_batches.lines[N]` — нужны поля `quantity_planned`,
     `quantity_received`, `discrepancy_reason` (Wave A S-3 добавила).
     Если их нет — STOP.
2. Action: `RECEIVE_BATCH`. Payload shape (warehouse_id, received_at,
   per-line qty + reason, optional capital_allocations для partnership).
3. **Existing** `WorkspaceReceiveConfirmSheet.vue` — если есть, **взгляд для
   паттернов**. Скорее всего legacy, не reuse целиком.
4. `frontend/src/api/inventory.ts` или подобный — найти `fetchWarehouses`
   API. Если нет — surface.

Если `quantity_planned`/`quantity_received`/`discrepancy_reason` отсутствуют
в payload — STOP, Wave A S-3 не пробросила.

---

## Контракт

### `ReceiveBatchHistoryRow.vue`

Read-only row для существующей приёмки в history list.

**Mockup:**

```
┌────────────────────────────────────────┐
│ 20 мая — Приёмка #1   180/230  ⚠     │
│ Кока-кола: 100/100  Спрайт: 50/50     │
│ Фанта: 30/80 — не привезли, ждём       │
│ 📎 Накладная.pdf                       │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  batch: ReceiveBatchPayload
  items: ProcurementItemPayload[]  // для name lookup
}>()
defineEmits<{
  click: [batchId: number]  // open details
  reverse: [batchId: number]  // ⋯ menu action (опционально)
}>()
```

Show:
- Header: date, batch #, total received/planned, warning if discrepancies.
- Per-line summary: name + received/planned.
- For lines с reason ≠ NONE — показывать reason label inline.
- Attachments если есть (в B-9 wire-up, в B-8 placeholder badge).

### `ReceiveBatchConfirmSheet.vue`

Bottom sheet для создания **новой** приёмки.

**Mockup:**

```
┌────────────────────────────────────────┐
│ ← Приёмка товара              ✕        │
│ ──────────────────────────────────────│
│ Склад: [ Главный склад ▼ ]            │
│ Дата: [ 21 мая 2026 ]                 │
│ ──────────────────────────────────────│
│ Кока-кола 0.5л                         │
│ Заказано: 100  ▼ Принято: [ 100 ]     │
│ Причина: — без расхождения             │
│ ──────────────────────────────────────│
│ Спрайт 0.5л                            │
│ Заказано: 50   ▼ Принято: [ 48  ]     │
│ Причина: [ Битые ▼ ]                  │
│ ──────────────────────────────────────│
│ Фанта 0.5л                             │
│ Заказано: 80   ▼ Принято: [ 80  ]     │
│ ──────────────────────────────────────│
│ [Для PARTNERSHIP] Распределение        │
│ капитала на эту приёмку:               │
│ Инвестор Анвар:  500 000 UZS           │
│ Бизнес:          150 000 UZS           │
│ ──────────────────────────────────────│
│ [ Принять (178 из 230) ]               │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'update:open': [value: boolean]
  save: [payload: ReceiveBatchInput]
}>()
```

`ReceiveBatchInput`:
```ts
{
  warehouse_id: number
  received_at: string
  lines: Array<{
    item_id: number
    quantity_received: string
    discrepancy_reason: 'NONE' | 'MISSING_EXPECTED_LATER' | 'DAMAGED' | 'QUALITY_REJECT' | 'ACCEPT_AS_SHORTFALL'
  }>
  capital_allocations?: Array<{ partner_id: number; amount: string }>  // PARTNERSHIP only
}
```

**Поведение:**
- Pre-fill `quantity_received` каждой строки = remaining qty
  (qty_planned − Σ received_so_far across previous batches).
- Reason dropdown default: `NONE` если qty_received == remaining, иначе
  `MISSING_EXPECTED_LATER` (мягкий дефолт).
- Validation: if `qty_received < remaining` and reason `NONE` → error
  «укажите причину расхождения».
- Validation: if `qty_received > remaining` → error.
- For PARTNERSHIP — show CapitalAllocationReceiveBlock с pre-filled
  amounts. Editable до confirm.
- Total «(X из Y)» в primary action button — real-time count.

### `CapitalAllocationReceiveBlock.vue` (опционально, only if size budget tight)

Если ReceiveBatchConfirmSheet > 320 строк после добавления capital
section — выделить в отдельный компонент. Иначе оставить inline.

**Цель:** per-partner capital amounts editor для текущей приёмки.

Pre-fill из planned shares × cost_of_received_items. Editable user-ом.

### `ProcurementCardReceive.vue`

**Mockup — empty (OPEN, no batches):**

```
┌────────────────────────────────────────┐
│ Приёмка                                │
│ Запланировано: 230 шт. на 1 250 000   │
│ Принято: 0 шт.                         │
│ [ Принять товар ]                      │
└────────────────────────────────────────┘
```

**Mockup — AT_RECEIPT (combined action label):**

```
│ Приёмка и оплата                       │
│ ...                                    │
│ Оплата: при приёмке (по получению)     │
│ [ Принять и оплатить ]                 │
```

**Mockup — после partial receive:**

```
│ Приёмка                                │
│ Запланировано: 230 шт.                 │
│ Принято: 180 шт. (78%)                 │
│ Осталось: 50 шт.                       │
│ ▼ Приёмки (1)                          │
│   [ReceiveBatchHistoryRow]             │
│ [ Принять оставшееся ]                 │
└────────────────────────────────────────┘
```

**Mockup — 100% received:**

```
│ Приёмка                          ✓     │
│ Принято полностью.                     │
│ ▼ Приёмки (2)                          │
```

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'start-receive': []  // open ConfirmSheet
  'reverse-batch': [batchId: number]  // открывает confirmation для reverse — реальная реализация в B-13
}>()
```

**Поведение:**
- Считает aggregate from `procurement.documents.items[].quantity` (planned) и
  `documents.items[].received_quantity` (already received).
- Кнопка label dynamic: «Принять товар» если AT_RECEIPT — «Принять и
  оплатить» (но реальный wire-up combined action — это B-10; в B-8
  кнопка пока ведёт в стандартный receive sheet).
- Скрывается если procurement.status === CANCELLED or items empty.
- В RECEIVED state — кнопки нет, только история.

### Модификация View

`ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardReceive`, `ReceiveBatchConfirmSheet`.
- Local state: `receiveSheetOpen` (ref).
- Handler `onStartReceive()` → `receiveSheetOpen = true`.
- Handler `onReceiveSave(payload)` → `store.dispatch('RECEIVE_BATCH', payload)`.
- Reverse stub: emit toast «B-13».

---

## Что НЕ делаем в B-8

- **AT_RECEIPT combined action** — кнопка label показывает, но реальная
  логика combined receive+pay — B-10.
- **Reverse receive batch flow** — кнопка-stub, реальный flow в B-13.
- **Attachments inline в receive sheet** — реальный uploader в B-9, в
  B-8 placeholder.
- **Multi-warehouse split** — один warehouse на receive batch, без split.

---

## STOP-точки

1. **`quantity_planned` / `quantity_received` / `discrepancy_reason`
   отсутствуют** в `documents.receive_batches.lines[]` payload — Wave A
   S-3 регрессия. STOP, surface (нужен backend fix аналог 13c0829).
2. **`RECEIVE_BATCH` payload shape** не принимает per-line qty + reason
   массив — STOP.
3. **Warehouse API** — если `fetchWarehouses` или подобный недоступен,
   STOP.
4. **ReceiveBatchConfirmSheet > 320 строк** — STOP, выделить
   CapitalAllocationReceiveBlock.
5. **Items с `received_quantity` поле** — должен быть в payload (видели
   в pre-flight B-4). Если нет — STOP.

---

## Verification

1. OPEN procurement с items → карточка Приёмка с empty state.
2. Tap «Принять товар» → sheet с per-line inputs pre-filled = qty_planned.
3. Change qty одной line → меньше than planned → reason dropdown
   required, default «не привезли, ждём».
4. Save → batch создаётся, history row появляется, totals обновляются,
   procurement.status → PARTIALLY_RECEIVED.
5. Continue receive → второй batch covers оставшееся → status → RECEIVED.
6. PARTNERSHIP procurement → в sheet появляется capital allocation block
   pre-filled. Edit amounts → save → snapshot фиксируется per-batch.
7. AT_RECEIPT timing → кнопка label «Принять и оплатить» (логика combined
   = B-10).

---

## Commit

```
feat(E09-wave-B-8): receive card + discrepancy capture + partnership snapshot

Receive batches list with per-line discrepancy capture (Wave A S-3
fields: quantity_planned / quantity_received / discrepancy_reason).
ReceiveBatchConfirmSheet shows each item with a quantity input
defaulting to remaining-to-receive, plus a reason dropdown for
shortfalls (NONE / MISSING_EXPECTED_LATER / DAMAGED / QUALITY_REJECT /
ACCEPT_AS_SHORTFALL).

For PARTNERSHIP procurements the sheet adds a capital allocation
block — per-partner amounts pre-filled from planned shares times the
cost of items being received, editable before confirm. The resulting
Lot.contract_snapshot captures actual flow per batch.

AT_RECEIPT timing changes the primary action label to "Принять и
оплатить", but the actual combined transaction wire-up lands in B-10.
Reverse-receive button is a stub here; real flow in B-13.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
