# E09 Wave B — Slice B-15 Finishing Touches

**Slice:** B-15 — Finishing touches для функциональной полноты MVP
**Цель:** закрыть три блокирующие дыры, выявленные при manual verification
после Wave B closure. Без них golden-path тестирование невозможно.

> Это **последний** slice Wave B. После B-15 — comprehensive code review,
> затем golden-path testing, затем E03.

---

## Контекст

Manual verification после B-14 выявил три блокера:

1. **Supplier quick-create UI отсутствует.** API `createSupplier` есть, но
   `WorkspaceSupplierPickerSheet` имеет `+ Создать` как stub-toast (отложен в B-3).
2. **Partner (investor) quick-create нет ни в API frontend, ни в UI.**
   Backend `PartnerViewSet` — `ReadOnlyModelViewSet`. Без partners в БД нельзя
   создать InvestmentAgreement → нельзя протестировать PARTNERSHIP procurement.
3. **Bottom action button показывает «UPDATE_SOURCE»** вместо человеческого
   label. Backend `_display` (workspace.py:1736) ставит `label = next_action`
   (action key).

---

## Architectural baseline

- Стандартные правила (≤300 строк per .vue, KISS, decomposition).
- Backend изменения минимальные — только Partner CRUD + action labels.
- Frontend ≤2 новых маленьких компонента + extensions existing.

---

## Pre-flight reads

1. `apps/core/views.py:PartnerViewSet` (line 40) — текущий ReadOnly.
   Найти PartnerSerializer и какие fields требует Partner модель.
2. `apps/partnerships/workspace.py:_display` (line 1724) — функция
   которая ставит label.
3. `frontend/src/api/core.ts:fetchPartners` — для понимания Partner type.
4. `frontend/src/api/suppliers.ts:createSupplier` — sig для wire-up.
5. `WorkspaceSupplierPickerSheet.vue` — куда подключать quick-create.
6. `InvestmentAgreementQuickForm.vue` — для встраивания partner quick-create.

---

## Контракт

### TASK 1 — Backend: Partner create endpoint

`apps/core/views.py`:
- Расширить `PartnerViewSet` от `ReadOnlyModelViewSet` до `ModelViewSet`
  (или добавить `mixins.CreateModelMixin`).
- Добавить permission_classes если нужно (probably IsOwner).
- `PartnerSerializer` или новый `PartnerCreateSerializer` с обязательными
  полями: name, role (INVESTOR/OPERATOR), is_active (default true).

Проверить что create endpoint фильтрует по tenant_id (multi-tenant
isolation — обязательно).

### TASK 2 — Backend: action_key → human label

`apps/partnerships/workspace.py:_display` функция (line 1724-1739):

Добавить module-level `ACTION_LABELS` dict (или вынести в отдельный
файл если он используется ещё где-то):

```python
ACTION_LABELS = {
    'UPDATE_SOURCE': 'Выбрать поставщика',
    'UPDATE_ITEMS': 'Добавить товары',
    'UPDATE_EXPENSES': 'Добавить расходы',
    'UPDATE_SETTLEMENT': 'Выбрать условия',
    'CREATE_INVESTMENT_AGREEMENT': 'Создать договор',
    'LINK_INVESTMENT_AGREEMENT': 'Привязать договор',
    'RECORD_CAPITAL_CONTRIBUTION': 'Внести капитал',
    'ALLOCATE_CAPITAL': 'Распределить капитал',
    'PAY_COSTS': 'Оплатить',
    'PAY_SUPPLIER_PAYABLE': 'Оплатить поставщика',
    'GENERATE_INSTALLMENT_SCHEDULE': 'Сгенерировать график',
    'RECEIVE_BATCH': 'Принять товар',
    'AMEND_SETTLEMENT': 'Изменить условия',
    'RETURN_CONSIGNMENT': 'Вернуть консигнацию',
    'CLOSE_WORKSPACE': 'Закрыть приход',
    'CANCEL_WORKSPACE': 'Отменить приход',
}
```

В `_display` заменить `'label': next_action` на:
```python
'label': ACTION_LABELS.get(next_action, next_action) if next_action else None,
```

### TASK 3 — Frontend: Partner create API client

`frontend/src/api/core.ts` — добавить:

```ts
export interface PartnerCreatePayload {
  name: string
  role: 'INVESTOR' | 'OPERATOR'
  is_active?: boolean
}

export async function createPartner(payload: PartnerCreatePayload): Promise<Partner> {
  const { data } = await api.post<Partner>('/api/v1/core/partners/', payload)
  return data
}
```

Точный URL — проверить через router (`/api/v1/core/partners/` vs другой).

### TASK 4 — Frontend: Supplier quick-create UI

`WorkspaceSupplierPickerSheet.vue` (≤200 budget):

- Сейчас `+ Создать нового поставщика` emit-ит placeholder. Заменить на:
  inline mini-form в том же sheet (раскрывается по кнопке) ИЛИ открыть
  nested `WorkspaceQuickSupplierSheet.vue` (новый компонент ≤140 строк).
- Минимальные поля: name (required), phone (optional).
- На save → `createSupplier({ name, phone })` → emit `select` с новым id.

Рекомендация: nested sheet (новый файл) — чище decomposition, picker не пухнет.

### TASK 5 — Frontend: Partner quick-create в agreement flow

`InvestmentAgreementQuickForm.vue` сейчас 641 строк — переиспользуется.
Внутри есть partner picker. Добавить туда «+ Создать нового инвестора»
кнопку рядом с picker-ом → открывает `WorkspaceQuickPartnerSheet.vue`
(новый компонент ≤130 строк).

Минимальные поля: name (required), role (INVESTOR — pre-filled).

На save → `createPartner({ name, role: 'INVESTOR' })` → возвращается в
QuickForm с pre-selected новым investor.

Если `InvestmentAgreementQuickForm` сильно сопротивляется встраиванию
— это OK добавить кнопку отдельным entry-point в
`WorkspaceAgreementPickerSheet.vue`.

### TASK 6 — Frontend: defensive label fallback (опционально)

В `ProcurementBottomActionBar.vue` или в shared util — fallback на
human label если backend всё ещё возвращает action key:

```ts
const ACTION_LABELS_RU: Record<string, string> = {
  // same map as backend ACTION_LABELS
}

const displayLabel = computed(() => {
  if (!props.actionLabel) return null
  return ACTION_LABELS_RU[props.actionLabel] ?? props.actionLabel
})
```

Это защита если backend не релизнулся одновременно с frontend.

---

## STOP-точки

1. **`PartnerSerializer` requires fields я не знаю** — STOP, surface.
2. **`InvestmentAgreementQuickForm` не позволяет встроить partner quick-create** без
   серьёзной переделки — surface, переключаемся на entry-point в picker sheet.
3. **Backend Partner create endpoint requires tenant context** — multi-tenant
   isolation должна работать. Если view не handle-ит request.tenant_id —
   STOP.
4. **Размеры новых компонентов > budgets** — STOP.

---

## Verification

После slice:
1. Открываем `/procurements/create` пустого пользователя без suppliers и partners.
2. В timing chips → tap «Выбрать поставщика» → opens picker → tap «+ Создать
   нового поставщика» → mini-form → save → новый supplier выбран.
3. Tap «Партнёрский» → opens agreement picker → tap «+ Создать новый договор»
   → opens QuickForm → tap «+ Создать инвестора» (NEW button) → mini-form →
   save → новый investor pre-selected в QuickForm.
4. Bottom button показывает человеческий label («Выбрать поставщика»,
   «Добавить товары», etc.) а не «UPDATE_SOURCE».
5. Все 8 легальных combinations procurement matrix теперь testable.

---

## Commit

```
feat(E09-wave-B-15): finishing touches — quick-create supplier/partner + action labels

Closes three gaps surfaced during post-Wave-B manual verification:

  Supplier quick-create UI now lives in a nested
  WorkspaceQuickSupplierSheet inside the picker (was a toast stub
  from B-3). Uses the existing createSupplier API.

  Partner (investor) quick-create requires both a backend extension
  and new frontend infrastructure. PartnerViewSet upgraded from
  ReadOnly to full ModelViewSet with multi-tenant isolation. New
  api/core.ts createPartner client. WorkspaceQuickPartnerSheet
  component plugs into InvestmentAgreementQuickForm.

  Bottom action bar showed raw action keys like "UPDATE_SOURCE"
  because _display set label = action_key. New ACTION_LABELS map
  in workspace.py supplies human-readable labels. Frontend also
  has a defensive fallback in case the two deploy out of sync.

Closes E09 Wave B fully — golden-path testing across the 8 legal
procurement combinations is now actually possible without seeding
data through admin.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После B-15

1. Visual check от founder — 5 пунктов выше.
2. Я делаю comprehensive code review pass (skill `review`) по всей Wave B.
3. После review — golden-path testing 8 комбинаций.
4. После testing OK — E09 → DONE, переходим к E03.
