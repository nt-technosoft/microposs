# MicroPOS / Sherik POS — Roadmap

> Центральная карта крупных задач (эпиков) проекта.
> Каждая строка ниже — это **эпик** со своим документом, чек-листом задач, фазами и открытыми вопросами.
> Этот файл обновляется руками; детали — внутри файлов эпиков.

---

## Статусы

| Статус | Значение |
|---|---|
| ⚪ `NOT_STARTED` | Эпик создан, но работа не начата |
| 🟡 `IN_PROGRESS` | Активная разработка/обсуждение |
| 🔵 `IN_REVIEW` | Реализация завершена, проверяется |
| 🟢 `DONE` | Закрыт, дальнейших задач нет |
| ⏸️ `PAUSED` | Отложен (есть блокеры или зависимости) |

---

## Обзорная таблица

| # | Эпик | Статус | Прогресс | Зависит от | Документ |
|---|---|---|---|---|---|
| **E01** | Suppliers & Procurement (расширенная модель) | 🟢 DONE | 100% | — | [→](./roadmap/E01-suppliers-procurement.md) |
| **E02** | Product–Supplier Links (UX + модель) | 🟢 DONE | 100% | E01 (UX) | [→](./roadmap/E02-product-supplier-links.md) |
| **E03** | Real Value Reporting (Net Asset View) | ⚪ NOT_STARTED | 0% | E01, E02 | [→](./roadmap/E03-real-value-reporting.md) |
| **E04** | Contract Types Formalization | 🟡 IN_PROGRESS | 60% | — | [→](./roadmap/E04-contract-types.md) |
| **E05** | Zakat Calculation | ⏸️ PAUSED | 0% | E01, E02, E03 | [→](./roadmap/E05-zakat.md) |
| **E06** | Sharia Certification (institutional path) | 🟡 RESEARCH_DONE | ~15% | E04, E05 | [→](./roadmap/E06-sharia-certification.md) |
| **E07** | Procurement & Investment Workspace Re-architecture | 🟢 DONE | 100% | E01, E04 | [→](./roadmap/E07-procurement-workspace.md) |
| **E08** | Architecture Cleanup & Source-of-Truth Consolidation | 🟢 DONE | 100% | E07 | [→](./roadmap/E08-architecture-cleanup.md) |
| **E09** | Procurement Completeness (non-PREPAID, ON_SALE, returnability) | 🔵 IN_REVIEW | ~95% | E07, E08 | [→](./roadmap/E09-procurement-completeness.md) |
| **E10** | Frontend Design System & Screen Redesign | 🟡 IN_PROGRESS | ~35% | E07, E08, E09 | [→](./roadmap/E10-frontend-redesign.md) |
| **E11** | Partnership Capital as Real Agreement Account (money source-of-truth) | 🟢 DONE | 100% | E07, E08 | [→](./roadmap/E11-partnership-capital-pool.md) |
| **E12** | Multi-currency Capital (FIFO cost-basis) + Calc Precision | 🟢 DONE | 100% | E11 | [→](./roadmap/E12-multicurrency-capital-and-precision.md) |
| **E13** | ⚠️ Mixed-currency procurement (затраты в разных валютах в одном приходе) | ⏸️ BLOCKED | 0% | E11, E12 + verified приход | [→](./roadmap/E13-multicurrency-procurement.md) |
| **E14** | Сверка внесённого и договорного капитала (межпартнёрские авансы) | 🟡 IN_PROGRESS | 5% | E11, E12 | [→](./roadmap/E14-capital-reconciliation-advances.md) |

**⚠️ НЕ ЗАБЫТЬ — E13 (отложен намеренно):** система ОБЯЗАНА уметь
мультивалютный приход (товары/расходы в разных валютах в одном приходе; классика
импорта USD-товар + UZS-таможня). Сейчас заблокировано на фронте и бэке
(одновалютный `ProcurementTerms`), что частично обесценивает E11+E12. **Funding-
слой уже готов в E11/E12** (пул, конвертация, FIFO cost-basis,
`_receive_funding_breakdown` по валютам) — недостаёт obligation-слоя.
**Возвращаемся ТОЛЬКО после** того, как приход доведён и проверен end-to-end
(снапшоты долей, движение денег, отчёты, аналитика). См.
[E13](./roadmap/E13-multicurrency-procurement.md).

**🔥 Активный P0 (frontend, с 2026-05-29):** E10 — Frontend Design System &
Screen Redesign. Единый визуальный язык (`DESIGN.md` OKLCH) поверх
Tailwind v4 + shadcn-vue; редизайн screen-by-screen, старт с детальной
страницы прихода. Фаза 0 — выровнять источник правды (tokens.css → DESIGN.md).

**Активный P0 (backend):** E03 — Real Value Reporting (Net Asset View).
Разблокирован завершением E09 Wave B. E09 остаётся в IN_REVIEW (golden-path
верификация 8 комбинаций матрицы, Phase 3 returnability намеренно deferred).

**Предыдущий P0 (2026-05-19 — 2026-05-21):** E09 — Procurement Completeness.
Wave A (backend, 8 slices) + Wave B (frontend rebuild, 14 slices) завершены.
~95%, остаток — верификация и Phase 3 returnability (after-MVP).

**Закрыто (2026-05-19):** E07 (controlled radical reset партнёрского трека +
canonical workspace flow) + E08 (cleanup, source-of-truth consolidation,
FIFO loophole). Партнёрский приход, append-only ledger, derived balances,
immutable lot snapshot, finance.Payment как универсальный документ —
работают как target-архитектура.

E04 — связанный архитектурный контекст. E03/E05/E06 ждут завершения E09.
**E01/E02 завершены**: backend, frontend wizard, поставщики/оплаты,
консигнационные возвраты, история связей товар↔поставщик.

---

## Логика приоритетов

**Текущая последовательность работы:**

```
E07 + E08 (DONE 2026-05-19) ──→ E09 (Procurement Completeness) ──→ E03 → E05 → E06
                                         │
                                         └──→ E10 (Frontend Redesign, parallel track)
```

E10 идёт параллельным frontend-треком: не блокирует backend-последовательность,
переводит экраны на единый визуальный язык начиная с приходов.

E07 + E08 закрыли controlled radical reset партнёрского трека и
source-of-truth consolidation. E09 достраивает остальные комбинации
procurement matrix (non-PREPAID кредитные, ON_SALE для консигнации,
returnability), без этого Net Value / Zakat / Sharia certification
не построятся корректно.

E01/E02 завершены и теперь считаются историческим фундаментом, который может быть пересобран внутри E07. E04 идёт как связанный контекст для investment/contract layer.

---

## Принципы работы с roadmap

1. **Один эпик = один файл** в `roadmap/`. Не плодим документы внутри документов — детализация ставится **как ссылки** на отдельные техдоки, если она реально большая.
2. **Чек-листы внутри эпиков** — это truth source прогресса. Прогресс в этой таблице обновляется после изменений в чек-листах.
3. **Открытые вопросы** в эпике — это место для незакрытых обсуждений. Перед началом фазы открытые вопросы должны быть резолвнуты.
4. **Решённые вопросы (история)** — короткие записи: «дата → вопрос → решение». Это важнее, чем кажется: через 3 месяца ты не вспомнишь, почему выбрал тот или иной подход.
5. **Не торопись закрывать эпик** — после имплементации должен быть период `IN_REVIEW`: пилотные клиенты, обкатка, фиксы. Только потом `DONE`.
6. **Новый эпик** появляется, когда обсуждение выявляет крупную тему, не покрытую текущими. Не пихаем всё в один эпик, не делаем 30 мелких.

---

## Связь с другими документами

- [architecture.md](./architecture.md) — техническая архитектура (модули, паттерны)
- [domain/](./domain/) — бизнес-домены (что они делают сейчас)
- [README.md](./README.md) — навигация по всей документации
- `../AGENTS.md` — entrypoint для LLM-инструментов
- `../CLAUDE.md` — Claude-специфичные инструкции
- `../presentation/` — pitch-материалы для Billz (контекст и оффер)
- `../presentation/sharia-certification-research.md` — research-документ, источник для E06

---

## Шаблон для нового эпика

См. [`roadmap/_template.md`](./roadmap/_template.md).
