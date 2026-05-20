# E09 Wave B — Slice B-7 Execution Plan (для Sonnet)

**Slice:** B-7 — Card 5 «Оплата и обязательства»
**Цель:** payment card с пятью вариантами timing-а (PREPAID, PARTIAL,
DEFERRED, INSTALLMENT, ON_SALE). AT_RECEIPT прячет карточку — receive
объединяет действие (B-10). Multi-payment history. Самая сложная
карточка из-за conditional content per timing.

> Опус согласовал. Sonnet исполняет.

---

## Architectural baseline

- `ProcurementCardPayment.vue` ≤300 строк (orchestrator card)
- `PaymentScheduleEditor.vue` ≤180 строк (только для INSTALLMENT)
- `PaymentMakeSheet.vue` ≤220 строк (sheet для нового платежа)
- `ConsignmentObligationsBlock.vue` ≤120 строк (только для ON_SALE)
- `ProcurementWorkspaceView.vue` после интеграции ≤260 строк

Если orchestrator card пухнет — выделить per-timing **subcomponents**
(PaymentPrepaidView, PaymentDeferredView, etc.). Решение принимаем
по ходу, в зависимости от насколько разная разметка между вариантами.

---

## Pre-flight reads

1. `frontend/src/api/partnerships.ts`:
   - `documents.settlement` — type / total_amount_due / paid_amount /
     remaining_amount / deadline_date / schedule[]
   - `documents.payables` — для DEFERRED/INSTALLMENT/PARTIAL view
   - `documents.payments` — для multi-payment history
   - `payment_status` block в payload (добавлен в Wave A-7) — derived
     view с obligation / paid / delta / state
2. Actions: `PAY_COSTS`, `PAY_SUPPLIER_PAYABLE`,
   `GENERATE_INSTALLMENT_SCHEDULE`.
3. `frontend/src/components/forms/MoneyCurrencyInput.vue` — reuse.
4. Cash account picker — найти существующий или создать минимальный.
   Cash account list через какой API — посмотреть `api/finance.ts`
   или `api/core.ts`.

Если `payment_status` block отсутствует в payload — STOP (Wave A
S-7 не пробросил его в workspace payload).

---

## Контракт

### `ProcurementCardPayment.vue` (orchestrator)

Один файл, шесть веток по timing-у. Если разрастается — расщепляем на
sub-components.

**Common header** (одинаковый во всех вариантах):

```
┌────────────────────────────────────────┐
│ Оплата                          ⚠/✓   │
│ ──────────────────────────────────────│
│ Обязательство: 1 250 000 UZS           │
│ Оплачено:     400 000 UZS              │
│ Остаток:      850 000 UZS              │
```

**Variation 1: PREPAID — empty:**

```
│ [ Оплатить полностью ]                 │
│ [ Оплатить частично ]                  │
└────────────────────────────────────────┘
```

**Variation 1: PREPAID — c history:**

```
│ ▼ Платежи (2)                          │
│   20 мая · 200 000 · наличные          │
│   21 мая · 200 000 · банк              │
│ [ Оплатить остаток ]                   │
│ [ Добавить платёж ]                    │
└────────────────────────────────────────┘
```

**Variation 2: AT_RECEIPT — карточка СКРЫТА** (через `v-if`).

**Variation 3: PARTIAL:**

```
│ Предоплата: 500 000 UZS (40%)          │
│ В долг:     750 000 UZS                │
│ Дедлайн долга: 15 июня                 │
│ ▼ Платежи (1)                          │
│ [ Оплатить предоплату 500 000 ]        │
└────────────────────────────────────────┘
```

**Variation 4: DEFERRED:**

```
│ Дедлайн: 15 июня 2026 (через 26 дней)  │
│ ▼ Платежи (0)                          │
│ [ Совершить платёж ]                   │
└────────────────────────────────────────┘
```

**Variation 5: INSTALLMENT — empty (no schedule):**

```
│ ⚠ Нет графика рассрочки                │
│ [ Сгенерировать график ]               │
└────────────────────────────────────────┘
```

**Variation 5: INSTALLMENT — со schedule:**

```
│ График: 5 платежей × 250 000           │
│ ▼                                       │
│ 1. 1 июня     250 000  [Оплатить]      │
│ 2. 1 июля     250 000   ожидает        │
│ 3. 1 авг.    250 000   ожидает        │
│ ...                                    │
└────────────────────────────────────────┘
```

**Variation 6: ON_SALE — CONSIGNED procurement:**

Использует отдельный `ConsignmentObligationsBlock.vue`:

```
│ Накопленные обязательства              │
│ (по продажам с реализации)             │
│ Долг поставщику: 240 000 UZS           │
│ За продажи: 12 шт.                     │
│ ▼ Детально (collapsed)                 │
│ [ Оплатить накопленное ]               │
└────────────────────────────────────────┘
```

**Props/emits orchestrator:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  'pay-full': []
  'pay-partial': []
  'pay-schedule-entry': [entryId: number]
  'generate-schedule': []
  'pay-consignment': []
}>()
```

View handles dispatch:
- `pay-full` / `pay-partial` → open `PaymentMakeSheet` → on save → dispatch `PAY_COSTS` или `PAY_SUPPLIER_PAYABLE` (зависит от naличия payable)
- `generate-schedule` → open `PaymentScheduleEditor` → on save → dispatch `GENERATE_INSTALLMENT_SCHEDULE`
- `pay-schedule-entry` → open `PaymentMakeSheet` pre-filled с amount из entry → save → dispatch
- `pay-consignment` → for ON_SALE — aggregate-payment против consignment payables

### `PaymentMakeSheet.vue`

Один общий sheet для всех timing-вариантов.

**Поля:**
- Amount (MoneyCurrencyInput с currency picker)
- Cash account picker (для funding_source=OWN_FUNDS)
  ИЛИ Allocation per partner (для funding_source=PARTNERSHIP) — pre-fill из planned shares
- FX rate (auto если currency ≠ UZS)
- Notes (optional)

**Props/emits:**

```ts
defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  defaultAmount?: string
  paymentType: 'cost' | 'payable' | 'schedule-entry' | 'consignment'
  scheduleEntryId?: number  // если payment_type === 'schedule-entry'
}>()
defineEmits<{
  'update:open': [value: boolean]
  save: [payload: PaymentPayload]
}>()
```

Sheet сам выбирает action на save:
- `paymentType === 'cost'` → emit с действием PAY_COSTS
- `paymentType === 'payable'` → PAY_SUPPLIER_PAYABLE
- `paymentType === 'schedule-entry'` → специальный payload

### `PaymentScheduleEditor.vue` (только INSTALLMENT)

Sheet для генерации графика:
- Count of payments (input)
- Frequency: monthly / weekly chips
- First payment date
- Even split toggle (default true) — иначе manual per-entry amounts

**Props/emits:**

```ts
defineProps<{
  open: boolean
  totalAmount: string
  currency: string
}>()
defineEmits<{
  'update:open': [value: boolean]
  save: [schedule: Array<{ sequence_number: number; due_date: string; amount: string; currency: string }>]
}>()
```

### `ConsignmentObligationsBlock.vue` (только ON_SALE)

Внутри PaymentCard для CONSIGNED procurement. Показывает aggregate
накопленных consignment payables:

**Props/emits:**

```ts
defineProps<{
  procurement: ProcurementWorkspacePayload
}>()
defineEmits<{
  pay: []  // open PaymentMakeSheet с paymentType='consignment'
}>()
```

**Поведение:**
- Filters `documents.payables` для `reason === 'CONSIGNMENT_SALE'`
- Sum amounts, show count of underlying sales (через outbox events
  или payable count).
- На «Оплатить накопленное» — emit для aggregate payment, открывает
  PaymentMakeSheet с total amount.

### Модификация View

`ProcurementWorkspaceView.vue`:
- Импорт `ProcurementCardPayment`, `PaymentMakeSheet`,
  `PaymentScheduleEditor`, `ConsignmentObligationsBlock`.
- В cards-container после `ProcurementCardFinancing` (или `Expenses`
  если OWN_FUNDS) добавить:
  ```vue
  <ProcurementCardPayment
    v-if="procurement?.documents.settlement?.type !== 'AT_RECEIPT'"
    :procurement="procurement"
    ...
  />
  ```
- Sheets state: `paymentSheetOpen`, `scheduleEditorOpen`, sheet config refs.
- Handlers: `onPayFull`, `onPayPartial`, `onPayScheduleEntry`,
  `onGenerateSchedule`, `onPayConsignment`. Каждый opens соответствующий
  sheet или dispatches action.

---

## Что НЕ делаем в B-7

- AT_RECEIPT combined receive+pay action — B-10.
- Reverse payment — не часть MVP.
- Multi-cash payment split — backend поддерживает, но UI MVP — single cash
  account за платёж. Improvement в B-14 polish если будет приоритет.

---

## STOP-точки

1. **`payment_status` block отсутствует** в workspace payload — STOP (Wave A регрессия).
2. **Cash account API не найден** — нужна функция типа `fetchCashAccounts`
   в api/finance.ts. Если нет — STOP, surface.
3. **PAY_COSTS / PAY_SUPPLIER_PAYABLE payload shape неожиданный** — STOP.
4. **Capital allocation per payment** для PARTNERSHIP — backend ожидает
   ли `capital_allocations` в payment payload? Если да — выяснить shape.
   Если нет — derive автоматом из planned shares.
5. **Размер orchestrator card > 300 строк** — STOP, обсуждаем
   per-timing sub-components.

---

## Verification

1. PREPAID OWN_FUNDS, payment empty → 2 buttons «полностью» / «частично».
2. Tap «полностью» → PaymentMakeSheet с pre-filled remaining amount.
3. Save → payment появляется в history, totals обновляются.
4. DEFERRED → видно deadline + countdown days, кнопка платежа.
5. INSTALLMENT no schedule → CTA «Сгенерировать график».
6. Generate schedule (5 платежей monthly) → schedule rows появляются, кнопка «Оплатить» на первом.
7. PARTIAL → upfront block + payable block.
8. AT_RECEIPT → карточка скрыта (provided receive card в B-8 видна).
9. PARTNERSHIP + PREPAID → PaymentMakeSheet показывает per-partner allocation
   instead of cash account.
10. ON_SALE → ConsignmentObligationsBlock с aggregate.

---

## Commit

```
feat(E09-wave-B-7): payment card + 5 timing variations + multi-payment

The most variable card in the workspace. ProcurementCardPayment
orchestrates five visible variants (PREPAID / PARTIAL / DEFERRED /
INSTALLMENT / ON_SALE) and hides itself entirely for AT_RECEIPT —
that timing combines payment with receive in B-10.

Shared header shows obligation / paid / remaining derived from the
payment_status block added by Wave A S-7. PaymentMakeSheet is a
single bottom sheet covering cost payments, payable payments,
schedule-entry payments, and consignment aggregate payments — the
sheet picks the correct action on save. PaymentScheduleEditor
covers INSTALLMENT schedule generation; ConsignmentObligationsBlock
shows accrued debt for ON_SALE procurements.

For PARTNERSHIP procurements, the sheet swaps cash-account picker
for per-partner allocation pre-filled from planned shares. Multi-
cash split is deferred to B-14 polish.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
