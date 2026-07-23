# E09 Wave B — Slice B-2 Execution Plan (для Sonnet)

**Slice:** B-2 — Header + Bottom action bar
**Цель:** заменить placeholder header и placeholder action bar в
`ProcurementWorkspaceView.vue` на полноценные компоненты:
`ProcurementHeader.vue` (status badge + back + title + subtitle +
action menu) и `ProcurementBottomActionBar.vue` (primary action с
динамическим label из backend payload).

> Опус согласовал. Sonnet исполняет. Branch points → STOP.
>
> Связанные документы:
> - [`E09-wave-B-ui-design-detailed.md`](./E09-wave-B-ui-design-detailed.md)
> - Архитектурные правила: CLAUDE.md → «Frontend decomposition rules»

---

## Architectural baseline

Применяются те же правила что в B-1: ≤300 строк per .vue, KISS over
patterns, props down events up, store без UI logic. Конкретные размерные
budget-ы для B-2:

- `ProcurementHeader.vue` — ≤180 строк
- `ProcurementBottomActionBar.vue` — ≤120 строк
- `ProcurementWorkspaceView.vue` после интеграции — ≤140 строк (вынос
  placeholder-стилей в свои компоненты должен **уменьшить** view)

Если какой-то компонент пухнет — STOP, surface, обсуждаем декомпозицию.

---

## Pre-flight reads

1. `frontend/src/api/partnerships.ts` — найти `ProcurementWorkspacePayload`,
   убедиться что есть поля `display.title`, `display.subtitle`,
   `display.next_action.{key,label,reason}`, `status`. Точные имена нужны
   для типизации.
2. `frontend/src/utils/domainLabels.ts` — есть `procurementStatusLabel`
   и `procurementStatusMeta`. Используем эти helpers (не дублируем
   логику меток).
3. `frontend/src/i18n/locales/ru.ts` (или en.ts) — найти существующие
   i18n keys для status / actions. Все text strings через `t('...')`.
4. Если есть `BadgeStatus.vue` или похожий shared component в
   `components/` — переиспользуем. Если нет — рендерим inline в Header.

Если что-то из (1) отсутствует — STOP. Структуру не подменять.

---

## Контракт

### Новый файл: `ProcurementHeader.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementHeader.vue`

**Mockup (mobile, 375px):**

```
┌────────────────────────────────────────┐
│ ← Приход #1234        OPEN        ⋯    │  ← row 1
│ Дистрибьютор «Coca-Cola Узбекистан»    │  ← row 2 (subtitle)
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  procurementId: number | null
  status: string | null       // ProcurementStatus
  title: string               // display.title
  subtitle: string | null     // display.subtitle
}>()
defineEmits<{
  back: []
  'menu-action': [actionKey: string]   // attach / amend / cancel / reverse — wire-up в B-12/B-13
}>()
```

**Поведение:**
- Sticky на top экрана (через CSS из workspace).
- Back button — emit `back`, parent делает `router.back()`.
- Title — берём `title` prop (`display.title` из payload).
- Status badge — справа от title, использует `procurementStatusMeta[status].colorClass` для цвета и `procurementStatusLabel(status)` для label. Если status null/unknown — badge не рендерится.
- Action menu (⋯) — открывает popover/dropdown с placeholder-actions:
  - «Прикрепить документ» (key: `attach`)
  - «Изменить состав» (key: `amend`)
  - «Отменить приход» (key: `cancel`)
  - «Отменить приёмку» (key: `reverse_receive`)
  - На клик emit `menu-action` с соответствующим key.
  - В B-2 эти actions **не вызывают реальные операции** — parent на эмит просто `console.log` или `toast.info('будет реализовано')`. Wire-up в B-12/B-13.
- Subtitle — если есть, под title тонким текстом. Если null — row 2 не рендерится (header сжимается).

**Стили:**
- Sticky positioning перенесён из view-placeholder сюда.
- Использовать design tokens: `--color-bg-secondary`, `--color-border-subtle`, `--text-lg`, `--space-2/4`, `--header-height`, `--z-sticky`, `backdrop-filter`.
- Status badge стиль: компактный pill, цвет из `colorClass` (`.badge-status--gray|orange|green|blue`). Если эти классы отсутствуют — создать локальные `.status-badge.status-badge--<color>` правила.

### Новый файл: `ProcurementBottomActionBar.vue`

Расположение: `frontend/src/modules/intake/components/workspace/ProcurementBottomActionBar.vue`

**Mockup:**

```
┌────────────────────────────────────────┐
│ [ Подтвердить и оплатить → ]           │  ← primary button (full width)
│ Зафиксирует состав и спишет 1 250 000  │  ← optional hint (display.next_action.reason)
└────────────────────────────────────────┘
```

**Props/emits:**

```ts
defineProps<{
  actionKey: string | null    // display.next_action.key
  actionLabel: string | null  // display.next_action.label
  reason: string | null       // display.next_action.reason
}>()
defineEmits<{
  click: [actionKey: string]
}>()
```

**Поведение:**
- Sticky на bottom.
- Если `actionLabel` null — кнопка показывает default «Сохранить черновик», disabled, hint = reason или статичный («Заполни поставщика и товары»).
- Если `actionLabel` present — кнопка показывает label. Disabled только если `actionKey === null` (label есть но key нет — это «не готов»).
- Hint (`reason`) — под кнопкой мелким текстом. Если null — не рендерится.
- Click — emit `click` с `actionKey` (если не disabled).

**Стили:**
- Sticky bottom, использует те же tokens что текущий placeholder.
- Минимальная высота кнопки 48px (mobile tap target).

### Модифицированный файл: `ProcurementWorkspaceView.vue`

**Что меняется:**

1. Импорт двух новых компонентов.
2. Удалить inline placeholder-разметку header и action bar.
3. Удалить соответствующие стили (`.workspace-header-placeholder`,
   `.workspace-action-bar-placeholder`, `.back-btn`, `.action-btn`,
   `.workspace-header-placeholder h1`) — они переехали в компоненты.
4. Передать props компонентам из store payload.
5. Обработать события: `back` → `router.back()`, `menu-action` →
   placeholder toast, primary `click` → `store.dispatch(actionKey, {})`.

**Шаблонная разметка (примерная):**

```vue
<template>
  <div class="workspace">
    <ProcurementHeader
      :procurement-id="procurement?.id ?? null"
      :status="procurement?.status ?? null"
      :title="procurement?.display.title ?? 'Новый приход'"
      :subtitle="procurement?.display.subtitle ?? null"
      @back="router.back()"
      @menu-action="handleMenuAction"
    />

    <main class="workspace-body">
      <div v-if="isLoading" class="state state-loading">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state state-empty">Нет данных</div>
      <div v-else class="cards-container">
        <div class="card-placeholder">Карточки появятся в следующих slice-ах</div>
      </div>
    </main>

    <ProcurementBottomActionBar
      :action-key="procurement?.display.next_action.key ?? null"
      :action-label="procurement?.display.next_action.label ?? null"
      :reason="procurement?.display.next_action.reason ?? null"
      @click="handlePrimaryAction"
    />
  </div>
</template>
```

`handleMenuAction` и `handlePrimaryAction` — короткие функции в `<script setup>`. После клика menu — `console.log` или `toast.info` (если в проекте есть toast composable — используем). После click primary — `store.dispatch(actionKey, {})` с базовым error toast.

---

## Что НЕ делаем в этом slice

- НЕ имплементируем реальные menu actions (attach/amend/cancel/reverse) — это B-12/B-13.
- НЕ имплементируем `handlePrimaryAction` для всех timing-вариантов — пока просто `dispatch(actionKey, {})`. Конкретные payload-ы для разных actions появятся когда соответствующие карточки будут готовы (B-7, B-8, B-10).
- НЕ строим popover/dropdown с нуля если в проекте уже есть shared
  компонент (типа `BasePopover`, `BaseDropdown`, `AppMenu`). Сначала grep:
  `grep -rn "BasePopover\|BaseDropdown\|AppMenu\|AppBottomSheet" frontend/src/components/`.
  Если есть — используем. Если нет — простой dropdown через `<details>` или
  inline `v-if`-меню с overlay.
- НЕ трогаем routing/store/API — они уже работают из B-1.

---

## STOP-точки

1. **`ProcurementWorkspacePayload` не содержит нужных полей**
   (`display.next_action`, `display.subtitle` etc.) — сигнатура изменилась
   с тех пор как я писал план. STOP, surface.
2. **`procurementStatusMeta` отсутствует или поменялся** — STOP, surface.
3. **CSS-токены для badge** (`badge-status--gray|orange|green|blue`)
   отсутствуют в global styles — STOP, спрашиваем создавать локально или
   ждать дизайн-токены.
4. **Любой компонент пухнет > его budget-а** (Header > 180, Bar > 120,
   View > 140) — STOP, surface, обсуждаем декомпозицию.
5. **i18n keys для status / next_action отсутствуют** — STOP, выясняем
   создавать новые keys или использовать литералы пока (для MVP литералы
   допустимы, но согласовать).

---

## Verification

После slice — посетить три URL:
1. `/procurements/create` → должен открыться header с «Новый приход»,
   subtitle если payload отдаёт, bottom bar с label из payload или
   disabled «Сохранить черновик».
2. `/procurements/:existing_id` → header с реальным title, status
   badge, subtitle. Bottom bar с primary action label из payload.
3. Тап на ⋯ → меню из 4 placeholder actions появляется. Клик на любой
   → console.log/toast «будет реализовано» (без реального изменения).

---

## Commit

```
feat(E09-wave-B-2): procurement workspace header + bottom action bar

Replaces the placeholder header and action bar in
ProcurementWorkspaceView with two dedicated components: a sticky
ProcurementHeader (back button, title, status badge, subtitle, action
menu) and a sticky ProcurementBottomActionBar (primary action driven
by display.next_action from the backend payload).

The view shrinks as styles move into the components. Menu actions
are placeholder emits — they'll be wired to real flows in B-12
(amendments) and B-13 (cancel / reverse receive). The primary
action dispatch is real: clicking it calls
store.dispatch(next_action.key, {}) which the backend already
supports.

Status badge reuses the existing procurementStatusMeta helper from
utils/domainLabels.ts; no duplicate label logic.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## После B-2

Sonnet возвращает founder'у commit hash + любые STOP-точки. После
ревью — переходим к B-3 (карточка «Поставщик и оплата»).
