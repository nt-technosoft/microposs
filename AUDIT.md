# MicroPOS — Технический Аудит
**Дата:** 29 апреля 2026  
**Ветка:** `vacuum-rework`  
**Scope:** Backend (Django) + Frontend (Vue 3)

---

## 1. Общая оценка

Проект архитектурно грамотно выстроен: мультитенантность, outbox pattern, immutable records, append-only ledgers, double-entry бухгалтерия — всё это на месте. Основная проблема не в структуре, а в **слое отчётов и аналитики**: именно там сосредоточены почти все узкие места производительности. Функциональная логика (расчёты долей, FIFO, FX, контракты) надёжна и трогать её не нужно.

**Вердикт:** ~80% кодовой базы в хорошем состоянии. Критические правки нужны в ~5 местах, высокоприоритетные — ещё в ~8.

> Статус после оптимизаций CloudCode: часть пунктов ниже уже реализована в текущем dirty tree (`reports/summary`, `reports/analytics`, AbortController/debounce, category count annotate, procurement expense target prefetch, profitability cache). Разделы 3–5 оставлены как исходная карта аудита, а не как список полностью открытых дефектов.

---

## 2. Архитектура (быстрый обзор)

### Backend — 11 приложений, ~80 моделей

| Приложение | Назначение |
|---|---|
| `core` | Бизнес-тенанты, партнёры, outbox events, регистрации |
| `catalog` | Товары, варианты, категории, атрибуты |
| `inventory` | Склад, поступления, лоты, движение стока |
| `sales` | POS-сессии, продажи, возвраты |
| `finance` | Двойная бухгалтерия, кэш, FX, профитабилити-отчёты |
| `partnerships` | Mudaraba/Musharaka контракты, закупки, распределение прибыли |
| `customers` | Дебиторы, рассрочки |
| `suppliers` | Кредиторы, консигнация |
| `investors` | Устаревший слой (мигрирует в partnerships) |
| `risk` | Инвентаризация, учёт потерь |
| `analytics` | Агрегированные метрики (ProductPerformance, AgingReport) |

### Frontend — 8 модулей

`auth`, `sales`, `products`, `intake`, `inventory`, `reports`, `investors`, `finance/more`

Структура: `src/api/` → `src/stores/` → `src/modules/<domain>/views/` — чёткое разделение ответственности.

---

## 3. Критические проблемы 🔴

### 3.1 Синхронная агрегация в обработчике запроса (Backend)

**Файл:** `backend/apps/finance/views.py`, строки 127–173  
**Функция:** `_ensure_finance_aggregates()`

```python
# ПРОБЛЕМА: .run() = синхронный вызов Celery-задачи прямо в API-запросе
for cursor in date_range:
    aggregate_daily_pnl.run(tenant_id, cursor.isoformat())
```

`DailySummaryViewSet` и `CashFlowSummaryViewSet` вызывают эту функцию при каждом list-запросе. Если кэш Redisa промазал (новый период, первый запрос) — агрегация за весь диапазон блокирует ответ на **5–30 секунд**.

**Исправление:** Перевести агрегацию в фоновую задачу (Celery). При cache miss — вернуть `HTTP 202 Accepted` с task_id, фронт polling-ом забирает результат. Либо агрегировать ночью по расписанию и кэшировать.

---

### 3.2 ReportsDashboard — 10 API-запросов на mount (Frontend)

**Файл:** `frontend/src/modules/reports/views/ReportsDashboard.vue`, строка 593

```
onMounted → loadAll()
  ├── loadSummary()    → 1 запрос: fetchDailySummaries
  ├── loadCashFlow()   → 1 запрос: fetchCashFlow
  ├── loadDebt()       → 1 запрос: fetchDebtSummary
  ├── loadParity()     → 4 запроса: payables + stock + trial + cashAccounts
  └── loadAnalytics()  → 3 запроса: salesProfit + productProfit + procurementProfit
                                                              = 10 запросов
```

Все запросы параллельны (Promise.all) — это хорошо. Но каждый несёт полный HTTP overhead + авторизацию на бэке. На слабом соединении страница ощущается медленной.

Дополнительно: переключение валюты запускает ещё 3 запроса **без debounce** — быстрый клик UZS → USD → UZS = 6+ запросов.

**Исправление:** Создать 2 агрегированных endpoint на бэке:
- `GET /api/v1/finance/reports/summary/` — возвращает daily + cashflow + debt + parity (4 → 1)
- `GET /api/v1/finance/reports/analytics/` — возвращает все три profitability в одном ответе (3 → 1)

Итого: 10 запросов → **4 запроса**. Добавить debounce 300ms на смену валюты.

---

### 3.3 Нет отмены запросов (Frontend)

**Файл:** `frontend/src/api/client.ts`

Ни один API-вызов не использует `AbortController`. При навигации со страницы все 10 запросов ReportsDashboard продолжают выполняться — лишняя нагрузка на бэк, расход батареи на мобильных.

**Исправление:** Добавить AbortController в базовый клиент, отменять при `onBeforeUnmount` компонента или при смене маршрута.

---

## 4. Высокоприоритетные проблемы 🟠

### 4.1 N+1 запрос — count() на категориях (Backend)

**Файл:** `backend/apps/catalog/serializers.py`, строки 73–74

```python
def get_products_count(self, obj):
    return obj.products.count()  # +1 запрос на каждую категорию в списке
```

20 категорий = 21 SQL-запрос вместо 1.

**Исправление:**
```python
# В CategoryViewSet.get_queryset():
queryset.annotate(products_count=Count('products', distinct=True))

# В сериализаторе:
products_count = serializers.IntegerField(read_only=True)
```

---

### 4.2 N+1 запрос — target_item_ids в расходах (Backend)

**Файл:** `backend/apps/partnerships/serializers.py`, строки 79–80

```python
def get_target_item_ids(self, obj):
    return list(obj.targets.values_list('item_id', flat=True))  # +1 на каждый расход
```

Procurement с 5 расходами = 6 запросов вместо 1.

**Исправление:** `prefetch_related('expenses__targets')` в `ProcurementViewSet.get_queryset()`.

---

### 4.3 Отключена пагинация на финансовых views (Backend)

**Файл:** `backend/apps/finance/views.py`, строки 440, 468

```python
class DailySummaryViewSet(...):
    pagination_class = None  # ← опасно!

class CashFlowSummaryViewSet(...):
    pagination_class = None  # ← опасно!
```

При большом диапазоне дат (год+) — неограниченный resultset летит на фронт.

**Исправление:** Убрать `pagination_class = None`, добавить `?date_from`/`?date_to` как обязательные параметры или ограничить максимальный диапазон 90 днями.

---

### 4.4 Агрегация AgingReport в Python вместо БД (Backend)

**Файл:** `backend/apps/analytics/tasks.py`, строки 287–291

```python
customers = [c for c in Customer.objects.filter(...) if c.outstanding_balance > 0]
# Загружает ВСЕХ клиентов в память, фильтрует в Python
```

**Исправление:** Если `outstanding_balance` — поле модели:
```python
Customer.objects.filter(..., outstanding_balance__gt=0)
```
Если вычисляемое — добавить `annotate()` с SubQuery.

---

### 4.5 5 отдельных aggregate() для нахождения диапазона дат (Backend)

**Файл:** `backend/apps/finance/views.py`, строки 89–111

```python
Sale.objects.filter(...).aggregate(min_dt=Min(...), max_dt=Max(...))
Receipt.objects.filter(...).aggregate(...)
CustomerPayment.objects.filter(...).aggregate(...)
SupplierPayment.objects.filter(...).aggregate(...)
Expense.objects.filter(...).aggregate(...)
```

5 отдельных `SELECT MIN/MAX` вместо одного.

**Исправление:** Объединить в один запрос через `UNION ALL` или вынести логику в raw SQL / database view.

---

### 4.6 Memory leak — debounce таймер в Pinia store (Frontend)

**Файл:** `frontend/src/stores/products.ts`, строки 103–114

```typescript
_searchDebounceTimer: ReturnType<typeof setTimeout> | null
// Таймер хранится в state, никогда не очищается при unmount
```

**Исправление:** Вынести таймер из state в локальную переменную модуля, добавить `$dispose()` hook.

---

## 5. Среднеприоритетные проблемы 🟡

### 5.1 Нет визуального feedback при смене валюты (Frontend)

Файлы: `AgreementProfitabilityView.vue`, `ProcurementProfitabilityView.vue`

Пользователь кликает переключатель валюты → 2–3 запроса летят → UI не реагирует. Кажется что кнопка сломана.

**Исправление:** Добавить `isReloading` флаг + оверлей или spinner поверх таблицы.

---

### 5.2 Router guard повторяет `loadCurrentSession()` на каждый переход (Frontend)

**Файл:** `frontend/src/router/index.ts`

При неудаче `loadCurrentSession()` нет backoff — каждый переход по маршруту = новый запрос к API.

**Исправление:** Добавить флаг `sessionLoadFailed` + exponential backoff или cooldown 30 секунд.

---

### 5.3 Нет отображения загрузки на CustomersView / SuppliersView (Frontend)

Пустой список пока идёт запрос — пользователь видит пустоту.

**Исправление:** Добавить skeleton-лоадер или spinner. Однострочная правка.

---

### 5.4 Profitability views — live-вычисление без кэша (Backend)

**Файл:** `backend/apps/finance/views.py`, строки 491–585

`SaleProfitabilityView`, `ProductProfitabilityView`, `ProcurementProfitabilityView` вычисляют данные синхронно при каждом запросе. Нет ETag, нет кэшироования.

**Исправление краткосрочное:** Добавить `cache_page(60 * 5)` или Redis-кэш с ключом `(tenant_id, date_from, date_to, currency)`.
**Исправление долгосрочное:** Предвычислять при OutboxEvent (аналогично `aggregate_daily_pnl`).

---

### 5.5 Устаревший код — investor summary task (Backend)

**Файл:** `backend/apps/analytics/tasks.py`, строки 265–272

```python
# Retired/no-op — функция вызывается, но ничего не делает
def aggregate_investor_summary_for_sale(...):
    pass  # migrate to partnerships
```

Мёртвый код. Можно удалить если миграция в `partnerships` завершена.

---

## 6. Низкоприоритетные наблюдения 🟢

| # | Наблюдение | Файл | Действие |
|---|---|---|---|
| 6.1 | `fetchCategories()` вызывается из нескольких модулей независимо | `api/catalog.ts` | Добавить простой request-cache (Map + TTL) |
| 6.2 | Нет глобального обработчика ошибок 5xx | `api/client.ts` | Добавить interceptor → toast "Ошибка сервера" |
| 6.3 | Часть watchers без сохранения stop-функции | несколько views | `const stop = watch(...)` + onBeforeUnmount |
| 6.4 | `toList()` в `api/catalog.ts` — хрупкая нормализация | `catalog.ts:30-42` | Унифицировать типы ответа на бэке |
| 6.5 | `outstanding_balance` у Supplier не индексирован | `suppliers/models.py` | Добавить `db_index=True` |

---

## 7. Что работает хорошо ✅

- **Архитектура бэка**: mixin-based модели, outbox pattern, immutable records — production-grade
- **Индексирование**: 129+ индексов, составные и partial — хорошо проработано
- **Redis + Celery**: async tasks, beat scheduler, lock механизм в агрегации
- **Мультивалютность**: FX snapshot на каждой транзакции — надёжно
- **JWT**: 12-часовой access token, refresh logic на клиенте
- **Router**: полный lazy loading всех компонентов
- **Параллельные запросы**: фронт уже использует `Promise.all` там где возможно
- **TypeScript**: последовательное использование на всём фронте
- **Мобильный первый**: токены, адаптивная вёрстка

---

## 8. План действий — по приоритету

### Быстрые победы (1–4 часа каждая)

| # | Задача | Эффект |
|---|---|---|
| Q1 | Fix N+1: `annotate(products_count=Count(...))` в CategoryViewSet | −20 запросов на список категорий |
| Q2 | Fix N+1: `prefetch_related('expenses__targets')` в ProcurementViewSet | −5 запросов на закупку |
| Q3 | Включить пагинацию в DailySummaryViewSet и CashFlowSummaryViewSet | защита от unbounded results |
| Q4 | Добавить debounce 300ms на переключение валюты + loading оверлей | UX fix |
| Q5 | Fix AgingReport: фильтр `outstanding_balance__gt=0` в SQL | меньше памяти на задачу |
| Q6 | Вынести `_searchDebounceTimer` из Pinia state | закрыть memory leak |
| Q7 | Добавить loading skeleton в CustomersView/SuppliersView | UX fix |

### Средние задачи (день–два)

| # | Задача | Эффект |
|---|---|---|
| M1 | Создать 2 агрегированных endpoint для ReportsDashboard | 10 → 4 запроса при загрузке |
| M2 | Добавить AbortController в `api/client.ts` | нет лишних запросов при навигации |
| M3 | Redis-кэш на profitability views (TTL 5 мин) | мгновенный ответ при повторе |
| M4 | Объединить 5 aggregate() в `_resolve_operation_window` | −4 запроса |
| M5 | Backoff в router guard для `loadCurrentSession` | нет retry-шторм при падении сессии |

### Долгосрочные (требуют проектирования)

| # | Задача | Эффект |
|---|---|---|
| L1 | Вынести `_ensure_finance_aggregates()` из request path в Celery | убрать 5–30с блокировку при cache miss |
| L2 | Pre-aggregate profitability через OutboxEvent (аналог daily_pnl) | profitability views — чтение готового результата |
| L3 | Завершить миграцию `investors` → `partnerships`, удалить dead code | меньше путаницы, чище кодовая база |

---

## 9. Оценка текущего состояния документации

`CLAUDE.md` описывает правила хорошо, но **детальная функциональная документация** по следующим областям отсутствует или устарела:

- Алгоритм распределения прибыли (Mudaraba/Musharaka) — формулы нигде не описаны
- Жизненный цикл Procurement (статусы, переходы, ограничения)
- FX pipeline — как и когда обновляются курсы, как snapshot'ируются
- Outbox → Analytics pipeline — какие события что триггерят
- Отчёты — какие данные откуда берутся (daily summary vs profitability vs aging)

**Рекомендация:** Не переписывать CLAUDE.md — дополнить его разделами по бизнес-логике. Создать отдельный `docs/ARCHITECTURE.md` с диаграммами потоков данных.

---

## 10. Итог

| Категория | Статус |
|---|---|
| Бизнес-логика (формулы, расчёты) | ✅ Работает корректно |
| Архитектура бэка | ✅ Хорошая база |
| Архитектура фронта | ✅ Чистая структура |
| Производительность отчётов | 🔴 Требует внимания |
| N+1 запросы | 🟠 2 критических места |
| UX отзывчивость | 🟠 Пробелы в loading state |
| Отмена запросов | 🟠 Не реализована |
| Документация | 🟡 Устарела в деталях |

**Быстрые победы Q1–Q7 закроют ~60% ощущаемых проблем производительности при минимальных затратах.** Задачи M1 (агрегированный endpoint) и L1 (async агрегация) — ключевые для ощутимого ускорения страницы отчётов.
