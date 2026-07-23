# Архитектура системы

## Структура репозитория

```
microposs/
├── backend/          Django-монолит
│   ├── apps/         11 domain-приложений
│   ├── config/       settings (base / development / production)
│   └── manage.py
├── frontend/         Vue 3 SPA
│   └── src/
│       ├── api/      HTTP-клиенты (типизированные)
│       ├── stores/   Pinia-сторы
│       ├── modules/  domain-модули (views + components)
│       ├── components/ shared-компоненты
│       └── router/   маршруты + guard-ы
└── docs/             эта документация
```

---

## Backend — 11 Django-приложений

| Приложение | Назначение | Ключевые модели |
|---|---|---|
| `core` | Тенанты, партнёры, outbox, регистрации | `Business`, `Partner`, `OutboxEvent`, `BaseModel` |
| `catalog` | Товары, варианты, категории, атрибуты | `Product`, `ProductVariant`, `Category` |
| `inventory` | Склады, поступления, лоты, движение стока | `Warehouse`, `Lot`, `LotStock`, `StockMovement` |
| `sales` | POS-сессии, продажи, возвраты | `PosSession`, `Sale`, `SaleLine`, `SalePayment`, `Return` |
| `finance` | Двойная бухгалтерия, кэш, FX, отчёты | `Account`, `JournalEntry`, `CashAccount`, `ExchangeRate`, `DailySummary` |
| `partnerships` | Мударабá/Мушарáка, закупки, прибыль | `Procurement`, `InvestmentAgreement`, `PartnerLedgerEntry` |
| `customers` | Дебиторы, рассрочки | `Customer`, `Receivable`, `ReceivableEntry` |
| `suppliers` | Кредиторы, консигнация | `Supplier`, `SupplierPayment` |
| `investors` | Устаревший слой (мигрирует в `partnerships`) | — |
| `risk` | Инвентаризация, учёт потерь | `RiskEvent`, `StockDisposal` |
| `analytics` | Агрегированные метрики (Celery-задачи) | `DailySummary`, `CashFlowSummary`, `AgingReport` |

---

## Архитектурные паттерны

### Мультитенантность
Каждая бизнес-модель наследует `TenantModel(BaseModel)` с FK `tenant_id → Business`. Все ORM-запросы фильтруются по `tenant_id`. `OutboxEvent` несёт `tenant_id` для изолированной async-обработки.

### OutboxEvent (Event Sourcing)
```
Синхронная операция (create_sale, process_return, ...)
    └─ publish_event(event_type, payload, tenant_id)
           └─ INSERT OutboxEvent (processed_at=NULL)

Celery Beat (каждые 10 сек)
    └─ process_outbox_events()
           └─ для каждого OutboxEvent → _dispatch_event()
                  ├─ 'sale.completed'     → aggregate_daily_pnl.delay()
                  ├─ 'customer.payment'   → aggregate_daily_pnl.delay()
                  ├─ 'supplier.payment'   → aggregate_daily_pnl.delay()
                  └─ 'pos_session.closed' → aggregate_daily_pnl.delay()
```
**Назначение:** отделяет синхронную бизнес-логику от async side-эффектов. Бизнес-операция не ждёт агрегации — возвращает ответ сразу.

### Иммутабельность через `ImmutableMixin`
Модели `Sale`, `Receipt`, `Lot`, `JournalEntry` наследуют `ImmutableMixin`. После достижения статусов `confirmed / completed / closed / received`:
- `save()` бросает `ImmutableRecordError`
- `delete()` переходит в `soft_delete()` (физическое удаление запрещено)

### Soft Delete (`BaseModel`)
Все модели имеют `deleted_at: datetime | null`. Default-менеджер фильтрует `deleted_at__isnull=True`. Для доступа ко всем записям: `Model.all_objects`.

### Service Layer
Каждый app имеет `services.py` — единственная точка входа для бизнес-логики. Прямые импорты моделей между доменными приложениями допустимы, прямой вызов бизнес-логики — нет (только через services).

### Идемпотентность
Все POST-эндпоинты финансовых операций принимают `client_request_id`. При повторном запросе с тем же `client_request_id` возвращается существующая запись без повторного создания.

---

## Celery-задачи

| Задача | Триггер | Что делает |
|---|---|---|
| `process_outbox_events` | каждые 10 сек (Beat) | Обрабатывает до 100 OutboxEvent, роутит по типу |
| `aggregate_daily_pnl(tenant_id, date_str)` | из process_outbox_events или вручную | Upsert DailySummary + CashFlowSummary за дату |
| `compute_aging_reports(tenant_id)` | ночью (Beat) | Пересчёт дебиторской/кредиторской задолженности по срокам |

---

## Redis-кэширование

| Ключ | TTL | Назначение |
|---|---|---|
| `finance:agg:warm:{tenant}:{from}:{to}` | 3600 сек | Флаг «все агрегаты за диапазон готовы» |
| `finance:agg:lock:{tenant}` | 60 сек | Distributed lock на диспетчеризацию Celery-задач |
| `profitability:{md5}` | 300 сек | Кэш profitability-запросов (ключ = hash(params + версия)) |
| `profitability:v:{tenant}` | 86400 сек | Версия кэша; инкрементируется при sale.completed / receipt.confirmed |

Инвалидация кэша profitability — через «tenant version counter»: инкремент версии делает все старые MD5-ключи устаревшими автоматически.

---

## Схема БД и связи между доменами

```
Business (tenant)
├── Warehouse ──────────────────── физические склады/магазины
├── Lot (иммутабельный) ─────────── cost snapshot при приёмке
│    ├── LotStock (per-warehouse)
│    └── StockMovement (audit log)
├── Procurement ─────────────────── новый путь прихода товара
│    ├── ProcurementItem
│    ├── ProcurementExpense (landed costs)
│    ├── ProcurementReceiveBatch
│    └── InvestmentContract (shariah contract)
├── Receipt (legacy, replaced)
├── Sale (иммутабельный после COMPLETED)
│    ├── SaleLine → Lot
│    ├── SalePayment
│    └── Return → ReturnLine
├── Customer → Receivable → ReceivableEntry
├── Supplier → SupplierPayment
├── Partner → PartnerLedgerEntry
├── Account (COA) → JournalEntry → JournalLine
├── CashAccount → CashEntry
├── ExchangeRate (snapshot by date)
├── Expense
├── DailySummary (pre-aggregated)
├── CashFlowSummary (pre-aggregated)
├── OutboxEvent (async events)
└── InvestmentAgreement → AgreementPartner
```

---

## API-структура

```
/api/v1/
├── auth/               аутентификация
├── catalog/            товары, варианты, категории
├── inventory/          склады, лоты, сток, перемещения, инвентаризация
├── sales/              продажи, POS-сессии, возвраты
├── finance/
│   ├── reports/summary/    combined: P&L + cashflow + debt + parity (1 запрос)
│   ├── reports/analytics/  combined: sales + products + procurements profitability
│   ├── daily-summaries/
│   ├── cash-flow/
│   ├── journal-entries/
│   ├── cash-accounts/
│   ├── expenses/
│   ├── fx-rates/
│   ├── sales-profitability/
│   ├── product-profitability/
│   └── procurement-profitability/
├── partnerships/       закупки, соглашения, партнёры
├── customers/          клиенты, дебиторка
├── suppliers/          поставщики, кредиторка
├── investors/          (legacy investor layer)
└── platform/           регистрации бизнеса (platform_admin)
```

---

## Валютная дисциплина (Currency Discipline)

**Правило:** Реальное движение денег (оплата, перевод, списание, зачисление) возможно
только между счетами **одной валюты** (USD↔USD, UZS↔UZS).

- Cross-currency операция — только через явный `CurrencyExchange` (`record_currency_exchange`).
  Это осознанная, атомарная, двусторонняя операция с фиксацией курса.
- Авто-конвертация по `fx_rate` (умножение суммы × курс) допустима **исключительно в
  отчётах/аналитике** — для отображения «эквивалента» в одной валюте. Никогда — при
  записи фактического движения денег.
- Итоги к оплате (procurement obligation, payment card) отображаются **раздельно по
  валютам**: `$200 + 1 200 000 UZS`, а не свёрнуто в одно значение.

**Backend enforcement** (начиная с commit `2fbb71b`): `pay_workspace_costs` и
`pay_workspace_supplier_payable` выбрасывают `ValueError`, если валюта кассы ≠ валюта
обязательства. `total_amount_due` рассчитывается раздельно по валютам товаров без ×fx.

**Frontend enforcement**: Payment card проверяет совпадение валюты кассы и
обязательства до отправки dispatch; при несовпадении — предупреждение + кнопка
конвертации (CurrencyExchange flow с pre-fill).

---

## Приёмка партии и Lot.contract_snapshot (Receive Batch Gate)

**Инвариант:** `Lot.contract_snapshot` — immutable сразу после создания лота (`RECEIVE_BATCH`).
Изменение `InvestmentAgreement` после приёмки не переписывает уже созданные лоты — только будущие.

**Confirmation gate (frontend):** Для PARTNERSHIP закупок пользователь **обязан подтвердить
доли партии** («Подтвердить доли») перед тем как нажать «Принять товар». Кнопка «Принять» заблокирована
до `sharesConfirmed === true`. После подтверждения — доли переходят в readonly; «Изменить»
возвращает в режим редактирования, сбрасывая `sharesConfirmed`.

**Рекомендация долей:** `capital_allocations[i].amount = batchObligationTotal × partner.profit_share`,
ограниченное `available_by_partner[partnerId][currency]`. Если кепируется — показывается
флаг «↓ лимит» (`isCorrected`). Пользователь может изменить вручную до подтверждения.

**PREPAID gate:** Приходуются только позиции с `lifecycle_state === 'READY_FOR_RECEIVE'`
(т.е. только те, за которые уже прошла оплата). Позиции в других состояниях показываются
в блоке «Ожидают оплаты» — не для приёмки.

**Capital allocation currency:** Распределение всегда в валюте обязательства партии
(`batchObligationCurrency` = валюта первого товара). Никогда не конвертировать в UZS
автоматически — см. Валютная дисциплина выше.

---

## Конфигурация

| Среда | Settings | Особенности |
|---|---|---|
| Development / Tests | `config.settings.development` | `CELERY_TASK_ALWAYS_EAGER=True` — задачи синхронны |
| Production | `config.settings.production` | Celery worker обязателен; Redis как брокер |

Переменные окружения: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `DATABASE_URL`, `REDIS_URL`.
