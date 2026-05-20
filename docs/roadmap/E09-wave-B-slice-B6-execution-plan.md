# E09 Wave B — Slice B-6 Execution Plan (для Sonnet)

**Slice:** B-6 — Card 4 «Финансирование» (PARTNERSHIP only)
**Цель:** добавить четвёртую карточку — capital allocation per partner +
**закрыть agreement picker stub** из B-3. PARTNERSHIP-only: для
OWN_FUNDS карточка скрыта целиком.

> Опус согласовал. Sonnet исполняет. Branch points → STOP.

---

## Architectural baseline

- `ProcurementCardFinancing.vue` ≤280 строк (большая, capital + allocation visualization)
- `WorkspaceAgreementPickerSheet.vue` ≤200 строк (новый — выбор/создание агреемента)
- `CapitalAllocationEditSheet.vue` ≤220 строк (per-partner amounts editor)
- `ProcurementWorkspaceView.vue` после интеграции ≤240 строк

Если что-то пухнет — STOP.

---

## Pre-flight reads

1. `frontend/src/api/partnerships.ts` — изучить:
   - `documents.investment` shape: agreement_id, partners[], contributions[], allocations[]
   - `documents.source.investment_agreement_required` / `investment_agreement_id`
   - Actions: `LINK_INVESTMENT_AGREEMENT`, `CREATE_INVESTMENT_AGREEMENT`,
     `RECORD_CAPITAL_CONTRIBUTION`, `ALLOCATE_CAPITAL`
2. **Existing components** (изучить, **возможно reuse**):
   - `InvestmentAgreementQuickForm.vue` (641 строка) — форма создания
     агреемента. Большая, но self-contained. **Reuse как nested form
     внутри bottom sheet**.
   - `InvestmentAgreementDetailSheet.vue` (302 строки) — sheet для
     просмотра агреемента. Reuse для tap-to-view.
   - `WorkspaceInvestmentStartBlock.vue` (240 строк) — legacy block.
     **Не reuse**, написан под старый UX.
3. `frontend/src/api/partnerships.ts` — `fetchInvestmentAgreements`,
   `fetchInvestmentAgreement`, `createInvestmentAgreement`. API client готов.

Если payload `documents.investment.partners[]` не содержит `planned_capital_share`
и `profit_share` — STOP.

---

## Контракт

### Новый файл: `WorkspaceAgreementPickerSheet.vue`

Назначение: bottom sheet для выбора существующего агреемента или
создания нового.

**Mockup:**

```
┌────────────────────────────────────────┐
│ Инвестиционный договор           ✕    │
│ ──────────────────────────────────────│
│ [ Поиск… 🔍                       ]    │
│ ──────────────────────────────────────│
│ Договор #5 · Инвестор: Анвар          │
│ Бюджет: 2 000 000 UZS · Мудараба      │
│ Баланс: 1 500 000 UZS              ›  │
│ ──────────────────────────────────────│
│ Договор #3 · Инвестор: Бахром         │
│ ...                                   │
│                                       │
│ [ + Создать новый договор ]           │
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  open: boolean
  selectedAgreementId?: number | null
}>()
defineEmits<{
  'update:open': [value: boolean]
  select: [agreementId: number]
  'create-new': []  // открывает InvestmentAgreementQuickForm в отдельном sheet
}>()
```

**Поведение:**
- Использует `AppBottomSheet` как контейнер.
- Список через `fetchInvestmentAgreements()` (без params в MVP, фильтрация
  только клиентская через search).
- Search фильтрует по `display_name` / номеру / именам инвесторов
  (use case: «найти договор Анвара»).
- Click на агреемент → emit `select` + закрытие.
- Click «Создать новый» → emit `create-new`. Parent открывает
  `InvestmentAgreementQuickForm` в отдельном sheet (modal).
- AbortController при search/re-open.
- Loading / empty states.

### Новый файл: `CapitalAllocationEditSheet.vue`

Назначение: per-partner amount editor для текущего procurement-а. Запускается
кнопкой «Уточнить распределение» в Financing card.

**Mockup:**

```
┌────────────────────────────────────────┐
│ Распределение капитала            ✕   │
│ ──────────────────────────────────────│
│ К покрытию: 1 250 000 UZS              │
│ ──────────────────────────────────────│
│ Инвестор Анвар (планируется 80%)       │
│ Доступно: 1 200 000 UZS                │
│ Выделить: [1 000 000      ]   UZS      │
│ ──────────────────────────────────────│
│ Бизнес (планируется 20%)               │
│ Доступно: 800 000 UZS                  │
│ Выделить: [250 000        ]   UZS      │
│ ──────────────────────────────────────│
│ Итого: 1 250 000 UZS ✓ совпадает       │
│ ──────────────────────────────────────│
│ [ Сохранить распределение ]            │
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
  save: [allocations: Array<{ partner_id: number; amount: string }>]
}>()
```

**Поведение:**
- На open: pre-fill amounts с planned shares × required cost.
- Inline edit per-partner amount. Real-time валидация:
  - Sum must equal required cost (показывать «совпадает ✓» / «не совпадает ⚠»).
  - Per-partner amount ≤ available (показывать «доступно»).
- Save: emit allocations array. Save disabled пока sum mismatch или any
  partner exceeds available.

### Новый файл: `ProcurementCardFinancing.vue`

**Mockup — empty (нет привязки агреемента):**

```
┌────────────────────────────────────────┐
│ Финансирование                  ⚠     │
│                                        │
│ Партнёрский приход требует              │
│ инвестиционный договор.                │
│                                        │
│ [ Выбрать договор → ]                  │
└────────────────────────────────────────┘
```

**Mockup — agreement linked, нет allocation:**

```
┌────────────────────────────────────────┐
│ Финансирование                  ⚠     │
│ ──────────────────────────────────────│
│ Договор #5 · Мудараба             ›   │
│ Баланс: 2 000 000 UZS                  │
│ ──────────────────────────────────────│
│ Распределение капитала:                │
│ Инвестор Анвар    Планируется 80%     │
│ Бизнес            Планируется 20%     │
│ ──────────────────────────────────────│
│ К покрытию: 1 250 000 UZS              │
│ Доступно: 2 000 000 ✓                  │
│                                        │
│ [ Уточнить распределение ]             │
└────────────────────────────────────────┘
```

**Mockup — allocated:**

```
┌────────────────────────────────────────┐
│ Финансирование                  ✓     │
│ ──────────────────────────────────────│
│ Договор #5                        ›   │
│                                        │
│ Распределение:                         │
│ Инвестор Анвар:  1 000 000 (80%)      │
│ Бизнес:            250 000 (20%)      │
│ ──────────────────────────────────────│
│ К списанию из договора: 1 250 000      │
└────────────────────────────────────────┘
```

**Mockup — capital shortage:**

```
│ К покрытию: 1 250 000                  │
│ Доступно: 800 000                      │
│ ⚠ Не хватает 450 000 UZS — нужен      │
│   contribution инвестора               │
│ [ Запросить вклад инвестора ]          │
```

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'link-agreement': [agreementId: number]
  'open-agreement-picker': []
  'open-allocation-edit': []
  'open-agreement-detail': [agreementId: number]
  'record-contribution': [partnerId: number, amount: string]  // optional, для shortage flow
}>()
```

**Поведение:**
- Виден ТОЛЬКО если `procurement.documents.source.funding_source === 'PARTNERSHIP'`
  (parent View управляет видимостью).
- Если `procurement.documents.investment` null → empty state с CTA «Выбрать договор».
- Если agreement linked, no allocations → show partners + planned shares +
  CTA «Уточнить распределение».
- Если allocations есть → show actual amounts + percentages.
- Capital shortage detection: если sum(planned amounts at planned shares) >
  agreement balance → show warning + CTA «Запросить contribution» (stub в
  B-6, реальная реализация в B-7 или отдельная задача).
- Agreement label clickable → emit `open-agreement-detail` →
  `InvestmentAgreementDetailSheet` showing.

### Модификация View

`ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardFinancing`, `WorkspaceAgreementPickerSheet`,
  `CapitalAllocationEditSheet`, **reuse** `InvestmentAgreementQuickForm`,
  `InvestmentAgreementDetailSheet`.
- В `cards-container` после `ProcurementCardExpenses` (B-5) добавить:
  ```vue
  <ProcurementCardFinancing
    v-if="isPartnership"
    :procurement="procurement"
    ...
  />
  ```
- Local state refs:
  - `agreementPickerOpen`
  - `agreementCreateFormOpen` (для InvestmentAgreementQuickForm в sheet)
  - `agreementDetailSheetOpen` (для view)
  - `allocationEditOpen`
- Handlers:
  - `onOpenAgreementPicker()` → `agreementPickerOpen = true`
  - `onAgreementSelect(id)` → `store.dispatch('LINK_INVESTMENT_AGREEMENT', { agreement_id: id })`
  - `onCreateNewAgreement()` → `agreementPickerOpen = false`, `agreementCreateFormOpen = true`
  - `onAgreementCreated(newAgreement)` → `store.dispatch('LINK_INVESTMENT_AGREEMENT', { agreement_id: newAgreement.id })`, close form
  - `onOpenAllocationEdit()` → `allocationEditOpen = true`
  - `onAllocationSave(allocations)` → `store.dispatch('ALLOCATE_CAPITAL', { allocations })`
  - `onOpenAgreementDetail(id)` → `agreementDetailSheetOpen = true` (view-only)

`isPartnership` computed:
```ts
const isPartnership = computed(() =>
  procurement.value?.documents.source.funding_source === 'PARTNERSHIP'
)
```

---

## Что НЕ делаем в B-6

- **Запрос contribution инвестора** — это inter-cabinet flow, отдельная фича.
  В B-6 кнопка показывается на shortage warning, но click → toast «будет реализовано».
- **Pay из allocated capital** — это B-7 (Payment card), здесь только allocation.
- **Edit/cancel agreement** — это отдельные actions, не в B-6.
- **InvestmentAgreementQuickForm refactor** — используем как есть (641 строка).
  Если нужны изменения — отдельный slice.

---

## STOP-точки

1. **`documents.investment` shape отличается** — STOP.
2. **`LINK_INVESTMENT_AGREEMENT` или `ALLOCATE_CAPITAL` payload неожиданный** — STOP.
3. **`InvestmentAgreementQuickForm` API не поддерживает `@created` emit** для
   получения нового агреемента — STOP, возможно нужна adapter prop.
4. **Размер компонентов > budget** — STOP.
5. **`available` per-partner computation** — если backend не отдаёт «available»
   суммы, нужна client-side derivation из contributions[] минус allocations[].
   Это не STOP, а **derive в компоненте**, но если структура данных не
   позволяет — STOP.

---

## Verification

1. OWN_FUNDS procurement → Финансирование карточка скрыта.
2. Switch на PARTNERSHIP → карточка появляется с empty state.
3. Tap «Выбрать договор» → AgreementPickerSheet с реальным списком.
4. Select agreement → linked, карточка обновляется с partners + planned shares.
5. Tap «+ Создать новый» в picker → закрывается, открывается QuickForm.
6. Save QuickForm → agreement created + auto-linked.
7. Tap «Уточнить распределение» → CapitalAllocationEditSheet с pre-filled amounts.
8. Edit amounts → validation работает (sum match, per-partner ≤ available).
9. Save → allocation сохраняется, карточка показывает actual amounts.
10. Tap agreement label → DetailSheet открывается с info.

---

## Commit

```
feat(E09-wave-B-6): financing card + agreement picker integration

PARTNERSHIP-only card that closes the agreement picker stub from B-3.
Three new components: ProcurementCardFinancing (visualizes partners,
planned shares, allocations), WorkspaceAgreementPickerSheet (bottom
sheet with list + search + create-new), CapitalAllocationEditSheet
(per-partner amount editor with sum/availability validation).

Existing InvestmentAgreementQuickForm and InvestmentAgreementDetailSheet
are reused as nested sheets for create / view flows. Shortage detection
shows a warning and a "Запросить вклад инвестора" CTA — wired as
placeholder toast for now (real inter-cabinet flow is a separate slice).

The View's isPartnership computed gates card visibility; OWN_FUNDS
procurements never see this card at all.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
