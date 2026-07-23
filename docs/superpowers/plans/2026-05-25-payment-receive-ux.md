# Payment & Receive UX Rework — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans or
> subagent-driven-development, task-by-task, verification-before-completion
> перед коммитами. UI — через `impeccable` + PRODUCT.md/DESIGN.md (green primary,
> calm confidence, tabular numbers, anti-slop). Деньги: CLAUDE.md Key Business
> Rules + project_e07_money_discipline. Продолжение
> `2026-05-25-procurement-workspace-rework.md` (Phases 1-13 реализованы) —
> здесь Phases 14-17, нашли после UI-проверки.

**Goal:** Сделать оплату и оприходование партнёрского/обычного прихода понятными
и быстрыми: integer-количества, capital в валюте обязательства, оплата с быстрым
дефолтом «всё» + опциональная выборочная, оприходование с долями партии
(рекомендация + коррекция + подтверждение) по образцу старой версии (7 мая).

**Architecture:** `ProcurementCardPayment` / `ReceiveBatchConfirmSheet` /
`ProcurementCardReceive` + backend `pay_workspace_costs` / `receive_workspace_batch`
/ partnership capital allocation. Доли фиксируются в `Lot.contract_snapshot`.

**Tech Stack:** Vue 3 `<script setup>` + Pinia; Django/DRF.

---

## Контекст багов (test-кейс: партнёрский приход #24, ветка vacuum-rework-claude)

- Capital allocation отображается/считается в UZS (`2541332000`) хотя товары в USD
  — нарушение валютной дисциплины (Phase 10 правило не применено к partnership capital).
- Quantity рендерится дробным («10.000», «222,000») — нужен integer формат.
- Старый receive-UX (7 мая) — референс: ветка `vacuum-rework` (origin, 7 мая) и
  фото в обсуждении. Sonnet может посмотреть `git show vacuum-rework:<path>` для
  сравнения, НЕ копировать дословно (там есть свои неудобства).

---

## Phase 14 — Integer-формат количества (глобально)

**Решение:** Количество товара/приёмки — всегда целое число, на отображение И на
ввод. Никаких `.000` / `,000`. Цена и суммы — отдельный формат (могут иметь
дробную часть), количество — строго integer.

**Files:**
- Найти все места рендера `quantity` / `Заказано` / `Принято` / «шт»:
  `ProcurementItemRow.vue`, `ProcurementCardItems.vue`, `ReceiveBatchConfirmSheet.vue`,
  `ProcurementCardReceive.vue`, split sheet, и т.п.
- Ввод: `<input type="number" step="1">` + parse как int; отображение —
  `Math.round(qty).toLocaleString('ru-RU')` без дробной части (или `Intl`
  с `maximumFractionDigits: 0`).
- Backend `ProcurementItem.quantity` — DecimalField; не менять схему, но
  принимать/возвращать целые; фронт не показывает дроби.

**Acceptance:** «Заказано: 10», «Принято: 222» — без `.000`. Ввод количества
не допускает дробей.

---

## Phase 15 — Capital allocation в валюте обязательства

**Решение:** Авто-распределение капитала и его отображение/ввод — в **валюте
обязательства прихода** (USD если товары/расходы в USD), не в UZS. Применить
Phase 10 правило к partnership capital allocation. Capital pool взаимодействует
в своей валюте; если валюта pool ≠ валюта обязательства — конвертация (explicit),
не авто-пересчёт по fx.

**Files:**
- Modify: `ProcurementCardPayment.vue` (PARTNERSHIP branch) + любой
  allocation-компонент — суммы по партнёрам в валюте обязательства, метка валюты
  верная (USD), без × fx.
- Backend: partnership allocation (`ALLOCATE_CAPITAL` /
  `_pre_allocate_at_receipt_partnership_capital`) — суммы в валюте обязательства;
  проверка валюты pool vs обязательства.

**Acceptance:** Для USD-прихода #24 распределение капитала показано в USD
(напр. «399 USD», «171 USD»), не «2541332000 UZS».

---

## Phase 16 — Оплата PREPAID: быстрый дефолт + опциональная выборочная

**Решение:** Карточка оплаты: primary-кнопка **«Оплатить всё»** + общий чек
раздельно по валютам (один тап — 90% сценариев). Вторичная ссылка «Оплатить
выборочно» раскрывает чекбоксы товаров/расходов (по умолчанию все отмечены) →
«Оплатить выбранное» с пересчётом чека. Источник средств в валюте позиций; не
хватает → конвертация (Phase 7/10). Split НЕ здесь — он на списке товаров (Phase 13).

**Files:**
- Modify: `ProcurementCardPayment.vue` — режим по умолчанию: «Оплатить всё»
  (показывает per-currency total). Toggle «Оплатить выборочно» → selection UI
  (чекбоксы, default all checked) → dispatch `PAY_COSTS` с `item_ids`/`expense_ids`.
  Расходы выбираются поштучно (split для расходов не нужен).
- Backend: `pay_workspace_costs` уже принимает подвыборку — убедиться, что
  остаток и статусы считаются по валютам и per-item.

**Acceptance:** Дефолт — одна кнопка «Оплатить всё» + чек по валютам. Выборочная
оплата доступна, но не доминирует. Можно оплатить 8 из 10 товаров + 2 из 3 расходов.

---

## Phase 17 — Оприходование: позиции + доли партии (рекомендация/коррекция/подтверждение)

**Решение:** Receive по образцу старой версии (7 мая), но чище. Sheet:
1. Список позиций к приёмке. Для PREPAID — только **оплаченные** (READY_FOR_RECEIVE);
   неоплаченные показаны заблокированными с пояснением «ожидает оплаты».
2. «Принять всё» (дефолт) + per-position «Разделить», если приехала часть
   (dispatch `SPLIT_ITEM`, затем принять отделённое).
3. Выбор склада.
4. Частичное / полное оприходование (частичное → `PARTIALLY_RECEIVED`).
5. **Доли партии (только PARTNERSHIP):** блок с рекомендованным распределением
   стоимости партии по партнёрам. Кнопки «Изменить» / «Подтвердить доли».
   Оприходование заблокировано пока доли не подтверждены. После подтверждения →
   `Lot.contract_snapshot` (immutable).

**Логика рекомендации долей:**
- База = договорные доли (`profit_share`/`planned_capital_share`, напр. 70/30) ×
  стоимость принимаемой партии (в валюте обязательства).
- Коррекция под бюджет: если доступный капитал партнёра в pool < его договорной
  доли — рекомендовать максимально близкое к договору, что позволяет фактический
  баланс (напр. 80/20). Показать что это коррекция от договора.
- Корректируемо руками в пределах доступного бюджета. Σ долей = стоимость партии
  (инвариант Σ capital_share = 1.0 в snapshot).

**Files:**
- Modify: `ReceiveBatchConfirmSheet.vue` — структура: позиции (integer qty,
  Phase 14) + split per-position + warehouse picker + доли партии блок
  (recommendation + edit + confirm gate).
- Modify: `ProcurementCardReceive.vue` — частичное/полное, статус.
- Backend: `receive_workspace_batch` — приёмка подвыборки/частично; доли из
  подтверждённого распределения → `contract_snapshot`; PREPAID gate (только
  оплаченные позиции); recommendation-расчёт (договор × бюджет) как сервис-функция.
- Доли партии: НЕ авто-применять без подтверждения пользователя — рекомендация,
  затем explicit confirm.

**Acceptance:** PREPAID: видны только оплаченные позиции к приёмке. Партию можно
принять частично (split) или полностью, выбрать склад. Для партнёрского —
рекомендованные доли (с учётом бюджета), редактируемые, обязательное
подтверждение перед оприходованием; после — зафиксированы в Lot snapshot.

---

## Новые зафиксированные правила (в docs/architecture.md)

1. **Количество — integer** везде (ввод + отображение). Цена/суммы — отдельно.
2. **Capital allocation — в валюте обязательства**, не UZS; pool взаимодействует
   в своей валюте, cross-currency только через конвертацию (расширение Phase 10).
3. **Доли партии при оприходовании — рекомендация, не автомат:** база договор,
   коррекция под фактический бюджет pool, ручная корректировка, обязательное
   подтверждение → immutable `Lot.contract_snapshot`.

## Verification

- Backend: `pytest apps/core/tests/ -q` зелёный; добавить тесты:
  capital allocation currency = obligation currency; receive shares recommendation
  (договор × бюджет, коррекция при нехватке); PREPAID receive gate (неоплаченное
  отклоняется); integer quantity.
- Frontend: `npx vue-tsc --noEmit` без новых ошибок.
- Ручной smoke на #24: оплата «всё» в USD, оприходование с долями в USD,
  integer количества.
- superpowers:verification-before-completion перед коммитами.
