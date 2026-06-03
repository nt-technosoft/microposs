# Procurement Cost — Single Source of Truth Consolidation

> **For agentic workers:** superpowers:executing-plans / subagent-driven-development,
> task-by-task, verification-before-completion перед коммитами. UI — через
> impeccable + PRODUCT.md/DESIGN.md. Деньги: CLAUDE.md Key Business Rules,
> project_e07_money_discipline, vision-принцип «derived > stored, single source».

**Goal:** Устранить корневую причину рассинхрона между этапами прихода
(financing «к покрытию», payment «обязательство», receive «запланировано»,
capital allocation): стоимость прихода считается в 5+ местах независимо, с
непоследовательным `× fx` и фильтром CANCELLED. Свести к ОДНОМУ источнику
правды на backend и ОДНОМУ на frontend.

**Architecture:** Один backend-расчёт `procurement_cost_by_currency()` (валюта
обязательства, без fx, исключает CANCELLED/RECEIVED) — все секции читают из него.
Один frontend-composable `useActiveLines()` — все карты читают из него. `× fx`
живёт ТОЛЬКО в явно reporting-only функции.

**Tech Stack:** Django/DRF backend; Vue 3 `<script setup>` + Pinia.

---

## Контекст (что уже сделано — НЕ переделывать)

Точечные фиксы #24 уже в working tree (Opus, verified на #24):
- `compute_capital_requirement` / `build_workspace_capital_allocation_preview` —
  financing в валюте обязательства без UZS round-trip ($862 → $100).
- `_payment_status_block` — убран `× fx` (миллионы USD → $100).
- `ProcurementCardReceive.vue` — фильтр CANCELLED (254 → 1 шт).
- `ProcurementCardPayment.vue` — кнопка «Оплатить из партнёрского капитала».

Эта консолидация делает те фиксы **системными** (один источник вместо
повторения фильтра/формулы в каждом месте), чтобы класс багов не возвращался.
Закоммить текущие фиксы ПЕРВЫМ коммитом (baseline), затем рефакторинг.

## Дублирование сейчас (корень)

Backend (все считают «стоимость прихода» по-своему):
- `_draft_cost_total_uzs` (workspace.py) — `Σ qty×price×fx` (UZS) — reporting.
- `_draft_cost_total_in_obligation_currency` — `Σ qty×price` (obligation cur).
- `_payment_status_block` — inline `Σ qty×price` (после фикса).
- `build_workspace_capital_allocation_preview` — после фикса в obligation cur.
- `_resync_draft_terms_total` (workspace.py) + `_normalize_terms_values`
  (workspace_support.py) — terms.total_amount_due sync.
- receive planned / `_check_prepaid_coverage`.

Frontend (каждая карта сама фильтрует CANCELLED + суммирует):
- `ProcurementCardItems` (`totalsByCurrency`), `ProcurementCardExpenses`,
  `ProcurementCardPayment` (`allTotalsByCurrency`, `selectionTotal`),
  `ProcurementCardReceive`, `ProcurementCardFinancing`, `ReceiveBatchConfirmSheet`.

---

## Phase 1 — Backend: единый `procurement_cost_by_currency`

**Решение:** Одна функция — источник правды для стоимости прихода. Валюта
обязательства (валюта товаров), БЕЗ fx, исключает CANCELLED/RECEIVED, группирует
по валюте (обычно одна; mixed → ValueError через существующий
`_derive_items_currency`). Отдельная reporting-функция для UZS (`× fx`),
помеченная как ИСКЛЮЧИТЕЛЬНО для отчётов.

**Files:**
- Create в `apps/partnerships/workspace.py` (рядом с cost-функциями):
  ```python
  def procurement_cost_by_currency(items, expenses) -> dict[str, Decimal]:
      """Single source of truth: procurement obligation cost grouped by currency.
      Σ(qty × unit_purchase_price) for items + Σ(amount) for expenses, in their
      own currency. NO × fx (fx is reporting-only). Caller passes ACTIVE lines
      (exclude CANCELLED/RECEIVED)."""
      totals: dict[str, Decimal] = {}
      for it in items:
          cur = str(it.currency or 'UZS').upper()
          totals[cur] = totals.get(cur, Decimal('0')) + Decimal(str(it.quantity)) * Decimal(str(it.unit_purchase_price))
      for ex in expenses:
          cur = str(ex.currency or 'UZS').upper()
          totals[cur] = totals.get(cur, Decimal('0')) + Decimal(str(ex.amount))
      return {c: v.quantize(Decimal('0.01')) for c, v in totals.items()}

  def active_procurement_lines(procurement) -> tuple[list, list]:
      """ACTIVE (non-CANCELLED, non-RECEIVED) draft items + expenses."""
      items = [i for i in procurement.items.all() if i.lifecycle_state not in ('CANCELLED', 'RECEIVED')]
      expenses = [e for e in procurement.expenses.all() if e.lifecycle_state not in ('CANCELLED', 'RECEIVED')]
      return items, expenses
  ```
- Keep `_draft_cost_total_uzs` ТОЛЬКО для reporting; переименовать в
  `procurement_cost_uzs_for_reporting` + docstring «reporting only, never for
  obligation». Найти все вызовы — оставить только там, где нужен UZS-эквивалент
  для отчёта, не для обязательства.
- Replace `_draft_cost_total_in_obligation_currency` — сделать тонкой обёрткой
  над `procurement_cost_by_currency` (single-currency → одно значение; mixed →
  ValueError).
- Переключить потребителей на единый источник:
  - `_payment_status_block` (obligation = `procurement_cost_by_currency` для
    единственной валюты).
  - `build_workspace_capital_allocation_preview` (required = то же).
  - `pay_workspace_costs` (total selection — то же по валюте).
  - `_resync_draft_terms_total` + `_normalize_terms_values`
    (terms.total_amount_due = единый источник; убрать дублирующую формулу).
  - receive planned qty / coverage — те же active lines.

**Acceptance:** Для #24 financing.required, payment.obligation,
terms.total_amount_due, capital required — ВСЕ возвращают `{USD: 100.00}` из
одной функции. Нет ни одного `× fx` в obligation-расчётах (только в
reporting-функции).

---

## Phase 2 — Frontend: composable `useActiveLines`

**Решение:** Один composable — источник активных строк и итогов по валютам.
Все карты читают из него, никто не фильтрует CANCELLED и не суммирует сам.

**Files:**
- Create `frontend/src/modules/intake/composables/useActiveLines.ts`:
  ```ts
  export function useActiveLines(procurement: Ref<ProcurementWorkspacePayload | null>) {
    const items = computed(() =>
      (procurement.value?.documents.items ?? []).filter(i => i.lifecycle_state !== 'CANCELLED'))
    const expenses = computed(() =>
      (procurement.value?.documents.expenses ?? []).filter(e => e.lifecycle_state !== 'CANCELLED'))
    const itemTotalsByCurrency = computed(() => groupByCurrency(items.value, i =>
      (parseFloat(i.quantity)||0) * (parseFloat(i.unit_purchase_price)||0), i => i.currency))
    const expenseTotalsByCurrency = computed(() => groupByCurrency(expenses.value, e =>
      (parseFloat(e.amount)||0), e => e.currency))
    const allTotalsByCurrency = computed(() => mergeTotals(itemTotalsByCurrency.value, expenseTotalsByCurrency.value))
    return { items, expenses, itemTotalsByCurrency, expenseTotalsByCurrency, allTotalsByCurrency }
  }
  ```
  (Helpers `groupByCurrency` / `mergeTotals` — в том же файле. NO × fx.)
- Переключить на него (убрать локальные фильтры/суммирования):
  `ProcurementCardItems`, `ProcurementCardExpenses`, `ProcurementCardPayment`
  (`allTotalsByCurrency`, `selectionTotal` строит из `items`/`expenses`
  composable), `ProcurementCardReceive`, `ProcurementCardFinancing`,
  `ReceiveBatchConfirmSheet`.
- Quantity — integer формат везде (если ещё не везде после Phase 14).

**Acceptance:** Ни одна карта не содержит собственного `.filter(CANCELLED)` или
`× fx` для итогов. Все суммы берутся из `useActiveLines`. Итоги совпадают между
карточками товаров, оплаты, приёмки, финансирования.

---

## Phase 3 — Consistency guard test (страж рассинхрона)

**Решение:** Тест, который ловит будущее расхождение источников. Если кто-то
снова заведёт параллельный расчёт — тест падает.

**Files:**
- Create `apps/core/tests/test_procurement_cost_consistency.py`:
  - Procurement (PARTNERSHIP, USD items + USD expenses, + один CANCELLED item):
    проверить, что `procurement_cost_by_currency(active)`,
    `_payment_status_block.obligation_amount`,
    `build_workspace_capital_allocation_preview.required`,
    `terms.total_amount_due` — ВСЕ равны и в USD, CANCELLED исключён.
  - fx-independence: меняем `item.fx_rate` — obligation НЕ меняется (fx только
    для reporting).
  - mixed currency → ValueError.

**Acceptance:** Тест зелёный; при искусственном расхождении (вернуть `× fx` в
один путь) — падает.

---

## Verification

- `pytest apps/core/tests/ -q` зелёный (особенно test_procurement_currency,
  test_procurement_cost_consistency, test_e07_*, test_e09_*, test_partnerships_api).
- `npx vue-tsc --noEmit` без новых ошибок (pre-existing WorkspaceSupplierPickerSheet — игнор).
- Ручной smoke на #24: financing / payment / receive / capital — одинаковые
  суммы в USD, целые количества.
- superpowers:verification-before-completion перед коммитами.
