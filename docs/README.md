# MicroPOS — Документация

Мобильная POS-система для малого ритейла с поддержкой исламского партнёрского финансирования (Мударабá, Мушарáка), консигнационной торговлей и мультискладским учётом.

**Стек:** Python 3.12 / Django 5.x / DRF / PostgreSQL 16 / Redis / Celery + Vue 3 / TypeScript / Pinia / Vite

---

## Навигация

### 🗺️ Roadmap и активные задачи
| Документ | Что описывает |
|---|---|
| **[ROADMAP.md](./ROADMAP.md)** | **Центральная карта эпиков и их статусов** — открывай в первую очередь |
| [roadmap/](./roadmap/) | Детали по каждому эпику (фазы, чек-листы, открытые вопросы) |

**Текущий P0:** [E07 — Procurement & Investment Workspace Re-architecture](./roadmap/E07-procurement-workspace.md)

### Архитектура и устройство системы
| Документ | Что описывает |
|---|---|
| [architecture.md](./architecture.md) | Модули, паттерны, мультитенантность, OutboxEvent, кэширование |
| [frontend.md](./frontend.md) | Vue 3 структура, модули, сторы, API-слой |
| [roles.md](./roles.md) | Роли пользователей и матрица доступа |
| [testing-data-workflow.md](./testing-data-workflow.md) | Принципы тестового заполнения базы и Excel workflow-аудита |
| [stage-deploy-checklist.md](./stage-deploy-checklist.md) | Проверки перед stage/prod-like деплоем |

### Бизнес-домены (backend)
| Документ | Что описывает |
|---|---|
| [domain/inventory.md](./domain/inventory.md) | Склады, лоты, FIFO, движение стока |
| [domain/procurement.md](./domain/procurement.md) | Закупка: приход товара, посадочные расходы, партнёрский капитал |
| [domain/sales.md](./domain/sales.md) | Продажи: vacuum model, POS-сессия, возвраты |
| [domain/partnerships.md](./domain/partnerships.md) | Мударабá/Мушарáка, распределение прибыли, партнёрский леджер |
| [domain/finance.md](./domain/finance.md) | Двойная бухгалтерия, кэш-слой, FX, отчётность |
| [domain/customers-suppliers.md](./domain/customers-suppliers.md) | Дебиторы, кредиторы, задолженности |

---

## Ключевые инварианты (никогда не нарушать)

1. Товары поступают ТОЛЬКО через Procurement / Receipt (кроме начального ввода остатков)
2. `Receipt.status = confirmed` → иммутабельно навсегда
3. `SaleLine` всегда ссылается на `Lot`, не на `ProductVariant` напрямую
4. FIFO по умолчанию при выборе лота
5. `Σ profit_ratio` всех участников контракта == 1.0
6. Кредитная продажа требует `customer_id`
7. `InvestorContract` закрывается только если нет активных лотов
8. Перемещение лота меняет только местоположение, не участников/доли
9. `JournalEntry` создаётся автоматически при каждой финансовой операции
10. Все значимые операции пишут `OutboxEvent`
11. Физическое `delete()` запрещено для `Sale`, `Receipt`, `JournalEntry`, `Lot`
