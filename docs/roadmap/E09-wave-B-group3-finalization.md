# E09 Wave B — Group 3+4: Finalization (B-10 + B-11 + B-14)

**Batch:** три последних slice-а Wave B. Один документ, три коммита.
**Цель:** замкнуть AT_RECEIPT combined action, унифицировать readiness/conditional orchestration, polish-проход.

> Sonnet делает три последовательных коммита. STOP-points обрабатываются стандартно.

---

## Architectural baseline (общее)

- ≤300 строк на любой `.vue`
- View после всех trех slice ≤320 (текущий 266)
- KISS — никаких новых абстракций без необходимости

---

# B-10 — AT_RECEIPT combined receive+pay action

**Цель:** для timing=AT_RECEIPT сделать кнопку «Принять и оплатить» реальной — receive + payment в одной dispatched транзакции. Backend готов (Wave A S-1).

**Pre-flight reads:**
1. `apps/partnerships/workspace.py:receive_workspace_batch` — проверить
   что AT_RECEIPT branch принимает `payment_payload` в request payload
   и создаёт Payment атомарно.
2. `ReceiveBatchConfirmSheet.vue` (B-8) — текущая структура. Расширяем.
3. `PaymentMakeSheet.vue` (B-7) — pattern для payment fields (cash account
   picker для OWN_FUNDS, capital allocations для PARTNERSHIP).

**Контракт:**

В `ReceiveBatchConfirmSheet.vue` (uppercase budget +60 → ≤380):
- Detect `procurement.documents.settlement?.type === 'AT_RECEIPT'`
- Если AT_RECEIPT — рендерить **дополнительный block** «Оплата при получении»:
  - Для OWN_FUNDS: cash account picker + amount (pre-fill из cost_of_received)
  - Для PARTNERSHIP: per-partner allocation editor (pre-fill из planned shares × cost_of_received)
- На confirm — добавить в RECEIVE_BATCH payload поле `payment_payload`:
  ```
  payment_payload: {
    cash_account_id?: number      // OWN_FUNDS
    capital_allocations?: Array<{ partner_id, amount }>  // PARTNERSHIP
    amount: string
    currency: string
    fx_rate: string
  }
  ```
- Validation: amount должен быть >= cost_of_received. Если меньше → error.

Альтернатива (если sheet > 380): выделить `PaymentAtReceiveBlock.vue`
как nested компонент (≤150 строк).

**STOP-points:**
1. Backend `receive_workspace_batch` не принимает `payment_payload` — Wave A S-1 регрессия.
2. ReceiveBatchConfirmSheet > 380 после добавления — STOP, выделяем sub-block.
3. Cash account picker не существует — нужно создать минимальный (но B-7 видимо уже создавал внутри PaymentMakeSheet — переиспользуем pattern).

**Commit:** `feat(E09-wave-B-10): AT_RECEIPT combined receive+pay action`

---

# B-11 — Conditional matrix orchestration + readiness

**Цель:** унифицировать readiness/visibility логику. Сейчас каждая карточка
сама считает ⚠/✓ — переключаем на единый источник `procurement.readiness`
от backend.

**Pre-flight reads:**
1. `procurement.readiness` shape в `ProcurementWorkspacePayload`:
   ```
   readiness: Record<string, { ok, severity, message, missing }>
   ```
2. Какие keys backend отдаёт (например `source_ready`, `items_ready`,
   `settlement_ready`, `capital_ready`, `payment_ready`, `receive_ready`).
3. `procurement.policy.visible_sections` — какие секции backend разрешает
   отображать в принципе.

**Контракт:**

Опционально (если есть смысл) — новый composable
`useProcurementReadiness.ts` ≤80 строк:
```ts
export function useProcurementReadiness(procurement: Ref<ProcurementWorkspacePayload | null>) {
  const isSectionVisible = (key: string) => ...
  const sectionReadiness = (key: string) => procurement.value?.readiness[key] ?? null
  const sectionStatusIcon = (key: string) => 'ok' | 'warn' | 'info' | 'blocked'
  ...
}
```

Каждая карточка переключается на composable вместо своих local computed.
Card-header ⚠/✓ иконки тянутся из единого источника.

**Что меняется конкретно:**
- `ProcurementCardSupplier`: status icon из `readiness.source_ready` (или эквивалент).
- `ProcurementCardItems`: из `readiness.items_ready`.
- `ProcurementCardExpenses`: visibility из `policy.visible_sections`,
  status — derived (всегда ok когда видна).
- `ProcurementCardFinancing`: visibility из `policy.visible_sections`
  (вместо локального `isPartnership` check).
- `ProcurementCardPayment`: visibility из `policy.visible_sections`
  (вместо локального проверка timing !== AT_RECEIPT).
- `ProcurementCardReceive`: status из `readiness.receive_ready`.

Это **рефакторинг**, не новая функциональность. UI не должен заметно измениться, но единая точка истины упростит будущие правки.

**STOP-points:**
1. `procurement.readiness` keys отсутствуют или другие имена — STOP, surface.
2. `policy.visible_sections` пустой массив для всех — STOP (backend регрессия).
3. После рефакторинга — какая-то карточка ведёт себя по-другому, чем
   раньше → проверка визуально.

**Commit:** `refactor(E09-wave-B-11): unified readiness/visibility via single source`

---

# B-14 — Polish

**Цель:** мелкие улучшения visible-уровня. Не функциональность — UX.

**Pre-flight reads:**
1. `frontend/src/composables/useToast.ts` (если есть) — для error toast.
2. Существующие keyframes/transition utilities в `frontend/src/assets/styles/`.

**Чек-лист (Sonnet выбирает что важно, что отложить):**

### Transitions
- Все sheet-открытия — slide-up 200ms.
- Card collapse/expand — 150ms.
- Chip select / button hover — 100ms.
- `@media (prefers-reduced-motion: reduce)` — все длительности до 0.

### Error toasts
- В `procurementWorkspace store` обернуть `dispatch()` в try/catch.
- На ошибку — toast с error.message (если backend вернул `{detail: '...'}`,
  показать `detail`). Использовать существующий useToast если есть.
- Удалить локальные `console.error` в pages — централизованно в store.

### Empty / loading states
- Каждая карточка — loading skeleton placeholder когда `procurement === null`
  и `isLoading === true`.
- Empty states — отдельная visual treatment с иконкой и подсказкой.

### "Завести по факту" entry point
- В IntakeList.vue (или процкуремент-list) — добавить дополнительную
  кнопку «Завести по факту». Это same procurement create + redirect, но
  с UI hint: «Если приход уже произошёл и просто заносишь данные».
- Реально просто другая копка с другим label + опционально pre-filled timing=PREPAID.

### Mobile polish
- 48px минимальный tap target везде.
- Bottom-sheet swipe-down to close (если supports у AppBottomSheet).

**STOP-points:**
1. `useToast` отсутствует — создать минимальный composable ≤60 строк.
2. Полишинг ломает существующее поведение — STOP, revert.
3. Mobile swipe-down — если AppBottomSheet не поддерживает, skip.

**Commit:** `polish(E09-wave-B-14): transitions, error toasts, empty states, entry points`

---

## После Group 3+4

Wave B полностью закрыта. Состояние:
- Backend: Wave A + следующие follow-up fixes (13c0829, 87097cf)
- Frontend: 14 slice-ов выполнены, ProcurementWorkspaceView полностью переписан
- E09 эпик: ~95%+ progress

Дальше:
- Финальный коммит обновления документации (E09 epic % + ROADMAP)
- Тестирование golden path (8 легальных комбинаций procurement matrix)
- Старт E03 (Net Value) если приоритет

---

## Промпты для Sonnet (по одному, sequentially)

**B-10:**
```
Read /Users/aziztohirov/Desktop/Projects/microposs/docs/roadmap/E09-wave-B-group3-finalization.md
section B-10 (AT_RECEIPT combined action). Three STOP-points listed.
ReceiveBatchConfirmSheet budget extended to ≤380 — surface if it
crosses that.
```

**B-11 (после B-10):**
```
Continue same plan: section B-11 (Conditional matrix orchestration +
readiness). B-10 already committed. Three STOP-points. This is a
refactor — UI must not visually change after it.
```

**B-14 (после B-11):**
```
Continue same plan: section B-14 (Polish). B-10 and B-11 committed.
Three STOP-points. Pick items by impact, surface if any item turns
into rework rather than polish.
```
