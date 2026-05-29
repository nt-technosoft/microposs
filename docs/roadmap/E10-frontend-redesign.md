# E10 — Frontend Design System & Screen Redesign

**Статус:** `IN_PROGRESS`
**Прогресс:** ~20% (Фаза 0 фундамент почти закрыта, остался T-0.5 шрифт)
**Зависит от:** E07, E08 (DONE), E09 (IN_REVIEW)
**Блокирует:** —

---

## Цель

Перевести экраны приложения на единый зрелый визуальный язык (`DESIGN.md`:
calm confidence, deep-emerald OKLCH, numbers-first) поверх связки Tailwind v4 +
shadcn-vue/Reka + lucide. Редизайн идёт screen-by-screen, начиная с детальной
страницы прихода, без глобального визуального reset живого приложения.

## Контекст и обоснование

После E07/E08/E09 функциональный procurement-трек собран как target
architecture, но **визуальный слой отстаёт** и фрагментирован:

- `DESIGN.md` (создан Claude Code) и `docs/frontend-design-system.md` (создан
  Codex) делались независимо и **разошлись**: первый описывает OKLCH /
  deep-emerald / calm confidence, второй фиксирует стек и объявляет `tokens.css`
  источником правды.
- `tokens.css` всё ещё содержит **legacy «Warm Minimal / Deep Teal» HEX-палитру**
  (`#1B8A6F`, amber, JetBrains Mono, `#FFFFFF`), противоречащую `DESIGN.md`
  (который сам помечен «seeded from vision, not scanned from code»).
- Workflow редизайна продублирован в трёх местах (`SKILL.md`,
  `frontend-design-system.md`, `CLAUDE.md`) — нарушение «one source per rule»,
  источник дрейфа.

Без выровненного фундамента первый же редизайненный экран разойдётся с
`DESIGN.md` и будет переделан.

### Источник правды (решено 2026-05-29)

- `PRODUCT.md` / `DESIGN.md` = **что** за дизайн (намерение, канон).
- `.agents/skills/microposs-frontend-design/SKILL.md` = **как** работает агент
  (метод редизайна).
- `docs/frontend-design-system.md` = стек + карта файлов + указатель на канон
  (без дублирования workflow).
- `tokens.css` = **рантайм-механизм**, не конкурент `DESIGN.md`: его значения
  приводятся к `DESIGN.md`. Старые токен-имена остаются для legacy-экранов и
  удаляются по факту миграции (аддитивный слой, не форк палитры).

### Метод пересборки экрана (решено 2026-05-29)

**«Сохранить контракт, пересобрать презентацию».** Логика — актив, разметка и
CSS — пассив.

1. **Extract & freeze contract** — по каждому блоку зафиксировать бизнес-правила,
   входы/выходы данных, состояния (loading/empty/error/edge), события,
   инварианты (Key Business Rules).
2. **IA-first shape** — заново вывести композицию экрана из workflow (mobile +
   desktop); решить границы блоков (часть старых выживает, сливается, делится,
   умирает — текущая декомпозиция не священна). 2–3 направления, выбрать одно.
3. **Rebuild per-block** — `<script setup>` логику переносим; `<template>` +
   `<style scoped>` пересобираем на shadcn-vue/Tailwind + доменных обёртках.
   По одному блоку, не вся страница разом.
4. **Verify** — mobile + desktop ширины, все состояния, контраст brand-green
   (165) vs positive-green (145) в плотных данных.

Это не «редактировать на месте» (тащит старую раскладку) и не «снести всё
включая логику» (риск нарушить инварианты).

## Сценарии (use cases)

- **US-1.** Владелец открывает детальную страницу прихода — за секунды читает
  состояние документа (статус, суммы по валютам, что требует действия), не
  продираясь через визуальный шум.
- **US-2.** Один визуальный язык: редизайн страницы A не ломает страницу B
  (аддитивные токены, screen-by-screen).
- **US-3.** Любой агент в новой сессии знает текущий канон дизайна и метод
  редизайна без археологии (консолидированные доки).

## Текущее состояние

- ✅ **Что есть:** shadcn-vue установлен (`src/components/ui/`, 17 компонентов),
  Tailwind v4 подключён (`tailwind.css`, `@theme inline`), `components.json`
  (style `reka-nova`, baseColor `stone`, lucide), `DESIGN.md` + `PRODUCT.md`
  как design-намерение, общий список приходов слегка улучшен.
- ⚠️ **Начато, но не завершено:** `tokens.css` на legacy teal-HEX, не на
  `DESIGN.md` OKLCH; доки workflow продублированы в 3 местах.
- ❌ **Чего нет вообще:** OKLCH-токены в рантайме, доменные обёртки под новый
  язык, редизайненная детальная страница прихода.

## План реализации

### Фаза 0 — Foundation (источник правды)
Портировать `DESIGN.md` OKLCH/типографику в `tokens.css` аддитивным слоем +
shadcn-bridge переменные (`--primary`/`--background`/`--accent`/`--ring`).
Консолидировать доки по иерархии выше. Проверить tailwind config (v3 vs v4
артефакты, `tailwind.config.cjs`). Дописать в `SKILL.md` метод пересборки и
поправку про Reka↔shadcn. Определиться с mono-шрифтом (Geist Mono vs
JetBrains Mono) и проверить tabular-nums.

### Фаза 1 — Детальная страница прихода
Применить метод пересборки: extract contract по текущим блокам →
IA-first shape (mobile + desktop) → per-block rebuild → verify. Это
шаблонный экран, задаёт язык для последующих.

### Фаза 2+ — Остальные операционные экраны
Список приходов, продажи/POS, finance, inventory, отчёты — по приоритету,
тем же методом.

## Задачи (чек-лист)

### Фаза 0
- [x] T-0.1 Портировать DESIGN.md OKLCH → tokens.css (аддитивно) + shadcn-bridge + Tailwind `@theme` utilities; build verified
- [x] T-0.2 Консолидировать доки (DESIGN.md канон / SKILL.md метод / frontend-design-system.md = стек+карта)
- [x] T-0.3 Проверить tailwind config — v4 CSS-first чист; `tailwind.config.cjs` = shadcn-CLI заглушка, сборкой не читается
- [x] T-0.4 Дописать метод пересборки + Reka↔shadcn в SKILL.md
- [ ] T-0.5 Решить mono-шрифт (Geist vs JetBrains) + проверить tabular-nums — открыто

### Фаза 1
- [ ] T-1.1 Extract & freeze contract по блокам детальной страницы прихода
- [ ] T-1.2 IA-first shape (mobile + desktop), выбрать направление
- [ ] T-1.3 Per-block rebuild на shadcn-vue/Tailwind + доменные обёртки
- [ ] T-1.4 Verify (ширины, состояния, контраст зелёных)

## Открытые вопросы

- ? Mono-шрифт: Geist Mono (DESIGN.md) vs JetBrains Mono (tokens.css) — что
  реально шипим и грузим.
- ? Детальная страница прихода на desktop: split workspace + inspector vs
  stage-панели — решается в T-1.2 shape.

## Решённые вопросы (история)

- ✓ 2026-05-29: источник правды дизайна → `DESIGN.md` канон, `tokens.css`
  механизм (значения приводятся к канону, аддитивно); workflow-доки
  консолидированы по иерархии what/how/stack.
- ✓ 2026-05-29: метод редизайна → «сохранить контракт, пересобрать презентацию»
  + IA-first, per-block; не edit-in-place и не полный rip.
- ✓ 2026-05-29: редизайн выделен в отдельный эпик E10 (был ошибочно скрыт за
  устаревшим «E07 = Active P0» в CLAUDE.md, из-за чего новые сессии стартовали
  с E07).
