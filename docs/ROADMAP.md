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
| **E14** | Сверка внесённого и договорного капитала (межпартнёрские авансы) | 🟡 IN_PROGRESS | 95% | E11, E12 | [→](./roadmap/E14-capital-reconciliation-advances.md) |
| **E15** | Partner Distributions & Capital Return (исходящие партнёрские деньги) | 🟡 IN_PROGRESS | 90% | E11, E12, E14 | [→](./roadmap/E15-partner-distributions-capital-return.md) |
| **E16** | Procurement Venture Settlement & Partner Proceeds | 🟡 IN_PROGRESS | 95% | E07, E11, E12, E14, E15 | [→](./roadmap/E16-procurement-venture-settlement.md) |
| **E17** | Production Lifecycle Readiness: Venture Close, Single Truth & UI Flow | ✅ DONE | 100% | E16 | [→](./roadmap/E17-production-lifecycle-readiness.md) |
| **E18** | Money Model Consolidation | 🔵 IN_REVIEW | ~100% core | E11–E17 | [→](./roadmap/E18-money-model-consolidation.md) |
| **E19** | POS Integration Platform | 🟡 IN_PROGRESS | 15% | E08 | [→](./roadmap/E19-integration-platform.md) |
| **E20** | Multi-Party Investment, Closed Funds & Contract Lifecycle | 🔵 IN_REVIEW | 100% implementation | E04, E18 | [→](./roadmap/E20-multi-party-investment-and-managed-funds.md) |
| **E21** | Business Context, Investor-Led Funds & Settlement UX Hardening | 🔵 IN_REVIEW | follow-ups implemented | E18, E20 | [→](./roadmap/E21-business-context-investor-funds-settlement-ux.md) |
| **E22** | Investor-Owned Funds + E21 UX Correction | 🔵 IN_REVIEW | 100% implementation | E18, E20, E21 | [→](./roadmap/E22-investor-owned-funds-e21-correction.md) |

**Future item — full business switcher:** не входит в E22/MVP. Текущий MVP
остаётся `one owner -> one business`; полноценный multi-business switcher нужен
отдельным эпиком, когда появится реальный multi-business операторский сценарий.

**⚠️ НЕ ЗАБЫТЬ — E13 (отложен намеренно):** система ОБЯЗАНА уметь
мультивалютный приход (товары/расходы в разных валютах в одном приходе; классика
импорта USD-товар + UZS-таможня). Сейчас заблокировано на фронте и бэке
(одновалютный `ProcurementTerms`), что частично обесценивает E11+E12. **Funding-
слой уже готов в E11/E12** (пул, конвертация, FIFO cost-basis,
`_receive_funding_breakdown` по валютам) — недостаёт obligation-слоя.
**Возвращаемся ТОЛЬКО после** того, как приход доведён и проверен end-to-end
(снапшоты долей, движение денег, отчёты, аналитика). См.
[E13](./roadmap/E13-multicurrency-procurement.md).

**⚠️ ОТКРЫТЫЙ ВОПРОС — FX на строках товара/расхода в черновике прихода (2026-07-03):**
обсуждали, что обязательный `fx_rate` на `ProcurementItem/ProcurementExpense`
может быть историческим компромиссом, а не правильной domain-границей. Сейчас
код использует его для UZS-себестоимости, `total_inventory_uzs`, landed cost,
FIFO COGS и отчётов, поэтому просто удалить нельзя. Целевая гипотеза для
следующего проектного прохода: в draft хранить native сумму+валюту; obligation
и payment показывать/проводить по валютам без `× fx`; курс/стоимость фиксировать
на реальном lifecycle-gate — оплата, приёмка/lot, реальная конвертация или
E12 FIFO cost-basis пула. Нужно отдельно решить, что честнее для own-funds и
partnership: исторический курс строки, курс оплаты, курс приёмки/market report
или cost-basis фактически потраченной валюты. Пока быстрый UX-fix: FX грузится
асинхронно/кэшируется и не должен блокировать ввод предупреждением до реального
сбоя загрузки курса.

Предварительная рекомендация после обсуждения: для own-funds фиксировать курс
в момент оплаты; для partnership брать cost-basis денег из пула — историческую
ценность, зафиксированную при взносе/конвертации/пополнении соответствующей
валюты, а не курс черновой строки товара. `report_currency`/current-rate не
должен менять историческую себестоимость — это только слой отображения: например,
историческая себестоимость хранится как 1 200 000 UZS, а отчёт может показать
эквивалент в USD на выбранную дату/текущий курс для читаемости и сравнения.

**⚠️ НЕ ЗАБЫТЬ — Precision & Distribution Fairness (отложено 2026-06-17, без номера):**
аудит округлений бэкенда зафиксирован в [`docs/rounding-precision-audit.md`](./rounding-precision-audit.md).
Суть: суммы хранятся/считаются в копейках (~84 поля + ~145 quantize в venture.py), а
остаток распределения долей **дампится на оператора** (`formulas.py`) → суб-копеечный
дрейф + систематическая асимметрия. **На корректность сегодня НЕ влияет** (conservation
уже exact-0), но важно под **шариатскую сертификацию** (честность до доли). Принцип:
округлять только на границе движения денег/отображения, в расчётах — полная точность;
распределение — largest-remainder, не дамп на оператора. Малый первый слайс (когда возьмём):
fair-residue в `formulas.py`. **Не сейчас** — впереди приоритетнее закрыть E18-трек.

**🔥 Активный P0 (frontend, с 2026-05-29):** E10 — Frontend Design System &
Screen Redesign. Единый визуальный язык (`DESIGN.md` OKLCH) поверх
Tailwind v4 + shadcn-vue; редизайн screen-by-screen, старт с детальной
страницы прихода. Фаза 0 — выровнять источник правды (tokens.css → DESIGN.md).

**Backend P0 — ЗАКРЫТО (2026-06-16):** E17 (Production Lifecycle Readiness,
acceptance 11/11) → **E18 (Money Model Consolidation, Ф1–Ф8 IN_REVIEW)**. E18
консолидировал денежную модель: единый материализованный `PartnerPositionReadModel`
с независимым tag-источником (доказано == легаси байт-в-байт + property-based),
дисплей-дивергенция S1/S4 устранена, conservation exact-0 по UZS, мёртвый код/дубли
снесены. Всё на ветке `vacuum-rework-claude` (не в main), backend-сьют 368 зелёный;
ждёт UI-верификацию. **Следующий backend P0 — E03 (Real Value Reporting)**: теперь
есть чистый read-model, на который ему опираться. Вынесено за E18 (отдельные задачи):
ретайр `AgreementAllocation` (не дубль), split `get_partner_aggregate` (cross-app),
functional-currency (UZS захардкожен → будущий эпик под не-UZS бизнес).

**E20 (IN_REVIEW):** Multi-Party Investment, Closed Funds & Contract Lifecycle
реализован как отдельный partnership-layer: несколько прямых инвесторов,
простой закрытый фонд и payout/review/dispute lifecycle. Использует E18 как
единственный money read-side; series/reinvestment, redemption и PDF намеренно
отложены.

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

E17 — production-readiness слой поверх E16. Это не новая математика, а закрытие
рисковых швов перед пилотным клиентом: нельзя оставлять два источника прибыли,
legacy-взаиморасчёты рядом с net-position, незакрываемые приходы/договоры и
операции без idempotency.

E19 — параллельный ecosystem-layer трек. Он строит provider-neutral integration
runtime и не зависит от внутренней реализации E18: gateway вызывает доменные
команды Sherik Core, а не пишет в GL, partner read-model или domain tables.

E20 опирается на E18 как на единственный денежный read-side и на E04 как на
явную классификацию договора. Он не заменяет текущую FIFO-экономику и не вводит
второй ledger: добавляет contract/fund lifecycle над фактическими событиями.

E21 — корректирующий продуктово-архитектурный слой после E20 review. Он не
меняет денежную основу E18/E20, а доводит границы user/business/fund, investor-led
fundraising UX, net paid-in display и procurement-bound payout semantics до
pilot-ready состояния. Follow-up hardening фиксирует правило: `FACTUAL`
не допускает partial receive, чтобы один procurement не распадался на несколько
share-profile/tranches; для partial receive и быстрых продаж используется
`AGREED`.

E22 supersedes tenant-scoped fund ownership из E21: фонд принадлежит глобальному
`InvestmentProfile`, а business получает только synthetic holder `Фонд: X` в
момент deployment.

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
