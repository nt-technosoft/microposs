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
| **E07** | Procurement & Investment Workspace Re-architecture | 🟡 IN_PROGRESS | 70% | E01, E04 | [→](./roadmap/E07-procurement-workspace.md) |
| **E08** | Architecture Cleanup & Source-of-Truth Consolidation | 🟡 IN_PROGRESS | 90% | E07 | [→](./roadmap/E08-architecture-cleanup.md) |

**🔥 Активный спринт / P0:** E07 (Procurement Workspace Phase D) + E08 (Architecture Cleanup).
Стратегия E07: controlled radical reset — новый procurement/investment/payment core и новый frontend workspace, старый intake/procurement код используется только как reference до switch-over.
E08 параллельно с E07: устраняет архитектурные долги (мёртвый код, дублирование источников правды для денежных балансов, FIFO loophole с `Lot.received_at`), не дублирует Phase D.
E04 продолжается как связанный архитектурный контекст, E03/E05/E06 зависят от завершения E07 + E08.
**E01/E02 завершены**: backend, frontend wizard, поставщики/оплаты, консигнационные возвраты, история связей товар↔поставщик.

---

## Логика приоритетов

**Текущая последовательность работы:**

```
E07 (новая архитектура Procurement + Investment Workspace) ──┐
                                                              ├─→ E03 → E05 → E06
E08 (cleanup, source-of-truth, гигиена legacy) ──────────────┘
```

E07 и E08 идут параллельно/чередуясь: E08 устраняет долги, накопившиеся в
controlled radical reset, E07 продолжает Phase D frontend workspace под
прямым контролем founder'а. E03/E05/E06 не запускаются, пока E08 Фаза 2 не
закрыта (без чистого источника правды Net Value / Zakat / Sharia
сертификация не построятся).

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
