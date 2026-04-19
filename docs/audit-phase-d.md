# Phase D — Аудит бэкенда и фронтенд-документации

**Дата:** 2026-04-19
**Ветка:** `vacuum-rework`
**Состояние Phase D:** PR-1..PR-9 закрыты, PR-10/11 (фронтенд) не начаты.
**Итоговая оценка соответствия vacuum-model:** **58%**

Этот документ — снапшот состояния проекта для передачи на внешний анализ.
Все находки сгруппированы по уровню риска. Рекомендации намеренно не включены —
они обсуждаются отдельно.

---

## 1. Сводка

| Область | Оценка | Комментарий |
|---|---|---|
| Модели данных | 72% | Ядро корректно, но legacy-модели физически живут в БД |
| Сервисный слой | 63% | Рабочий, но CREDIT без accrue_debt, JournalEntry не пишется |
| API (views/serializers/urls) | 68% | Tenant-фильтрация есть, но legacy `/receipts/` живой |
| Инварианты и безопасность | 55% | `IMMUTABLE_STATUSES` баг, Django groups не tenant-aware |
| Тесты | 42% | Lifecycle покрыт, но 4 крашера не покрыты, `test_role_matrix` тестирует мёртвые endpoints |
| Интеграции (Celery/FX/Outbox) | 38% | 4 крашера в analytics + race в outbox |

Ядро vacuum-model (Procurement → Lot → Sale → PartnerLedger) реализовано корректно
(~85%). Периметральные системы — analytics, journal integration, multi-currency,
CREDIT flow, outbox, permission model — содержат системные дефекты.

---

## 2. CRASH-уровень (рантайм падает при вызове)

### C-1. `analytics/tasks.py:~147` — ImportError на удалённой модели
```python
from apps.investors.models import InvestorProfitRecord
```
Модель удалена в PR-5. Задача `aggregate_daily_pnl` падает при первом же запуске.

### C-2. `analytics/tasks.py:~222` — ImportError на удалённой функции
```python
from apps.investors.services import record_investor_profit
```
Функция не существует. Задача `aggregate_investor_summary_for_sale` падает.

### C-3. `analytics/tasks.py:~175` — FieldError на удалённом поле
```python
sales.filter(payment_method='cash', ...)
```
Поле `Sale.payment_method` удалено в PR-4 (multi-payment).

### C-4. `analytics/tasks.py:~289` — FieldError на Python-property
```python
Customer.objects.filter(outstanding_balance__gt=0)
```
`outstanding_balance` — `@property`, не DB-поле. `compute_aging_reports` падает.

### C-5. `analytics/tasks.py:~229` — AttributeError на NoneType
```python
for line in sale.lines.select_related('lot__receipt'):
    receipt = line.lot.receipt      # None для vacuum-lots
    if receipt.receipt_type ...     # AttributeError
```
Все lot'ы через `receive_procurement` имеют `receipt=None`.

---

## 3. SILENT BUG (работает, но неправильно)

### B-1. CREDIT-продажа не начисляет долг
**Файл:** `apps/sales/services.py` (`create_sale`)
При `method='CREDIT'` создаётся `SalePayment(method=CREDIT)`, но
`customers.services.accrue_customer_debt()` не вызывается.
`Receivable` не обновляется. Продажа в долг зафиксирована, долг — нет.

### B-2. JournalEntry не создаётся при продаже/возврате
**Файлы:** `apps/sales/services.py`, `apps/finance/services.py`
Функции `record_sale_journal` и `record_return_journal` существуют,
но никогда не вызываются из сервисного слоя. Инвариант
"JournalEntry автоматически для каждой финансовой операции" нарушен.

### B-3. Касса никогда не обновляется
**Файлы:** `apps/sales/models.py:~194`, `apps/partnerships/models.py:~383`
`SalePayment.account_id` и `DividendPayment.paid_from_account_id` —
`IntegerField` без FK constraint. `CashEntry` при продаже/дивиденде
не создаётся. `CashAccount.balance` остаётся нулём независимо от оборота.

### B-4. Multi-currency капитал складывается не-нормализованно
**Файл:** `apps/partnerships/services.py:~402-426` (`receive_procurement`)
`actual_capital[partner] = CAPITAL_IN - CAPITAL_OUT` без конвертации в UZS.
Если партнёр А внёс 70 USD, партнёр Б — 120 000 UZS, то суммы
складываются напрямую: `total_capital = 120070` → capital_share A ≈ 0.0006.
Комментарий в коде (services.py:~561) признаёт долг: "all in UZS (multi-currency
not yet normalised — PR-7 brings FX rates)".

### B-5. Multi-currency касса лжёт при cash reconciliation
**Файл:** `apps/sales/services.py:~697-709` (`close_pos_session`)
```python
SalePayment.objects.filter(method=CASH).aggregate(total=Sum('amount'))
```
`fx_rate` не применяется. $50 × 12650 = 632500 UZS, система посчитает 50.
`expected_cash` некорректен → ложные расхождения в `RiskEvent(CASH_MISMATCH)`.

### B-6. `close_investor_contract` не видит vacuum-lots
**Файл:** `apps/investors/services.py:~19-38` (`_resolve_contract_receipt_ids`)
Функция ищет Lot'ы через `Receipt.objects.filter(investor_contract_id=...)`
и `ReceiptParticipant`. Для лотов через `receive_procurement` возвращает
пустой список → контракты нельзя закрыть корректно для vacuum-схемы.

### B-7. `aggregate_investor_summary_for_sale` пропускает vacuum-lots
**Файл:** `apps/analytics/tasks.py:~227-266`
Итерирует `lot.receipt.receipt_type` — для vacuum-lots `lot.receipt = None`,
задача тихо пропускает все реальные продажи после C-5 crash fix.

### B-8. `Receivable.balance_uzs` суммирует разные валюты
**Файл:** `apps/customers/models.py:~63-66`
```python
return sum(Decimal(str(v)) for v in self.balances.values())
```
USD и UZS складываются напрямую → aging reports показывают неверные суммы.

### B-9. Сумма `profit_share` партнёров не валидируется
**Файл:** `apps/partnerships/services.py` (`open_procurement`)
Нет проверки `sum(profit_share for all ContractPartners) == 1.0`.
Можно создать нешариатский контракт без ошибки.

---

## 4. Безопасность и изоляция тенантов

### S-1. Django groups не tenant-aware
**Файл:** `apps/core/permissions.py:~116-123` (`resolve_user_role`)
Роли определяются через `user.groups.filter(name__in=[...])`. Django groups
глобальные — если пользователь в группе `cashier` для тенанта А, он
получит роль cashier для тенанта Б. Cross-tenant role leakage.

### S-2. Implicit tenant resolution для single-tenant deployment
**Файл:** `apps/core/permissions.py:~70-81` (`resolve_tenant_id_for_user`)
```python
active_ids = list(Business.objects.filter(is_active=True)...)
if len(active_ids) == 1:
    tenant_id = _coerce_tenant_id(active_ids[0])
```
В bootstrap-фазе логика корректна, но при добавлении второго тенанта
логин сломается для всех "implicit" пользователей без понятной ошибки.

### S-3. `IsInvestor` не пропускает owner
**Файл:** `apps/core/permissions.py:~202-206`
`InvestorDashboardView.permission_classes = [IsInvestor]`. Owner с ролью
`owner` получит 403. CLAUDE.md задаёт owner как "full access" — противоречие.

### S-4. `process_outbox_events` без tenant-фильтрации
**Файл:** `apps/analytics/tasks.py:~21-27`
Один worker обрабатывает события всех тенантов. Нет изоляции. При parametrized
payload с чужим `tenant_id` задача может обработать чужие данные.

### S-5. `Sale.objects.get(pk=sale_id)` без tenant_id в Celery task
**Файл:** `apps/analytics/tasks.py:~224`
Задача получает `sale_id` из OutboxEvent payload и читает Sale без
проверки `tenant_id`. Нарушение принципа наименьших привилегий.

---

## 5. Транзакционная целостность

### T-1. `open_pos_session` без `transaction.atomic()`
**Файл:** `apps/sales/services.py:~653-678`
`PosSession.create()` и `publish_event()` не обёрнуты. При сбое между
ними — сессия создана, событие потеряно (или наоборот).

### T-2. `process_outbox_events` без `select_for_update(skip_locked=True)`
**Файл:** `apps/analytics/tasks.py:~21-27`
Два параллельных worker'а выберут одни и те же 100 unprocessed-событий
и выполнят `_dispatch_event` дважды → двойная агрегация в DailySummary,
двойные PartnerLedgerEntry.

### T-3. `pay_dividend` race condition
**Файл:** `apps/partnerships/services.py:~622-626`
Между чтением aggregate `PartnerLedgerEntry` и записью `DIVIDEND_PAID`
нет lock на ledger. При конкурентных транзакциях можно выплатить больше
`pending_payout`.

---

## 6. Инварианты из CLAUDE.md

### I-1. `IMMUTABLE_STATUSES` не содержит `'RECEIVED'`
**Файлы:** `apps/core/models.py:~52`, `apps/partnerships/models.py:~24-27`
`IMMUTABLE_STATUSES = {'confirmed', 'completed', 'closed'}` (lowercase).
`Procurement.Status.RECEIVED = 'RECEIVED'` (uppercase). После приёмки
Procurement можно изменить через `save()`.

### I-2. Physical delete не заблокирован
**Файлы:** `apps/sales/models.py:~155`, `apps/finance/models.py:~99`
```python
def delete(self, *args, **kwargs):
    self.soft_delete()
```
CLAUDE.md: "Physical delete forbidden for Sale, Receipt, JournalEntry, Lot"
→ ожидается `raise ValueError(...)`, не silent soft-delete. `queryset.delete()`
обходит instance-level метод.

### I-3. `ReceiptParticipant.capital_ratio` всегда 0
**Файл:** `apps/inventory/views.py:~133`
```python
capital_ratio=0,  # Will be calculated on confirm
```
Confirmation endpoint удалён (INV-1 закрыт). Поле навсегда 0.
Инвариант "capital_ratio auto-calculated from capital_amount" нарушен.

### I-4. `resolve_fx_rate_snapshot` без fallback
**Файл:** `apps/finance/services.py` (не проверен fallback)
При отсутствии курса на дату — `ValueError`. Продажа в USD невозможна,
если оператор забыл обновить курс. Нет fallback на последний доступный.

---

## 7. Legacy surface (мёртвый код)

### L-1. `inventory/models.py:~35-204` — Receipt/ReceiptLine/ReceiptParticipant
Классы живут в БД, таблицы создаются при migrate. Confirm — tombstone.

### L-2. `inventory/urls.py:~18` — `router.register('receipts', ReceiptViewSet)`
Живой эндпоинт для устаревшей модели. Нет Deprecation-заголовка.

### L-3. `inventory/urls.py:~16` — `router.register('locations', WarehouseViewSet)`
Дублирующий алиас `warehouses/`.

### L-4. `finance/services.py:~433-480` — `record_receipt_journal()`
Работает с Receipt-типами MUDARABA/MUSHARAKA/CONSIGNMENT. Не вызывается.

### L-5. `finance/models.py:~173-208` — `DailySummary.investor_share`
Поле завязано на удалённую `InvestorProfitRecord`.

### L-6. `investors/models.py` — `InvestorContract`
Одностороннее наследие. `_resolve_contract_receipt_ids` ссылается на Receipt.

### L-7. `finance/views.py:~20,~86` — `from apps.inventory.models import Receipt`
Используется в `_resolve_report_date_range()` для определения диапазона дат.

### L-8. `apps/core/excel_alignment.py` — stub с 6 `NotImplementedError`
Management-команды импортируются, но любой вызов падает.

### L-9. `ReceiptParticipant.entity_id`, `SalePayment.account_id`,
`DividendPayment.paid_from_account_id` — три `IntegerField` без FK.
Нарушение referential integrity.

---

## 8. Документация

### D-1. `docs/architecture.md` — критически устарел
Весь раздел "Data Flow: Sale Lifecycle" описывает Receipt → Lot и типы
MUDARABA/MUSHARAKA/CONSIGNMENT/SUPPLIER_PURCHASE как рабочие. В коде их нет.

### D-2. `docs/data-models.md` — критически устарел
ER-схема полностью на старой модели: `Receipt → ReceiptLine → Lot`,
`Investor → InvestorContract → InvestorProfitRecord → InvestorSummary`.
Последние две модели удалены.

### D-3. `docs/compliance-matrix.md` — устарел
Инварианты в терминах `confirm_receipt()`, `ReceiptParticipant`,
`validate_participant_ratios()`. Ссылается на удалённые тест-файлы.

### D-4. `docs/implementation-status.md` — частично устарел
Экран "intake" → давно `/procurements`. Раздел "Excel Alignment" описывает
работающий `ExcelImportBatch`, который теперь stub.

### D-5. `docs/role-matrix.md` — устарел
Описывает endpoints `/investors/summaries/` и `/investors/profit-records/`
как investor-only. Эти endpoints удалены в PR-5.

### D-6. `docs/frontend-architecture.md` — устарел (40% актуально)
- Модуль `modules/intake/` (legacy Receipt flow) вместо `modules/procurements/`
- Роутинг `/intake/*` вместо `/procurements/*`
- Investor routes `/investor/contracts/:id` вместо `/investor/procurements/*`
- `api/` не включает `partnerships.ts`
- `types/enums.ts` упоминает `ReceiptType`
- Ссылки на Axios/VeeValidate/Zod/Lucide/PWA/i18n, которых в коде нет

### D-7. `docs/phase-d-plan.md` — чеклисты не обновлены
PR-1..PR-9 показаны `[ ]` (не начато), хотя работа выполнена.

### D-8. Актуальные документы
- `docs/vacuum-model.md` — целевая модель, соответствует коду
- `docs/phase-d-debts.md` — корректно отражает закрытие долгов
- `docs/design-system.md` — 85% актуально (сильный документ)
- `docs/ux/00-foundation.md` — актуален
- `docs/ux/10-navigation-and-roles.md` — актуален
- `docs/ux/16-open-decisions-and-conflicts.md` — честно фиксирует конфликты
- `docs/ux/20-pages/*` — ~60% экранов достаточно для старта
- `docs/ux/30-components/*` — concept-level, недостаточно для implementation

### D-9. Структурно
18 .md-файлов на проекте в bootstrap-фазе. 6-7 — исторические артефакты.
Полезная тройка: `vacuum-model.md`, `phase-d-plan.md`, `phase-d-debts.md`.

---

## 9. Фронтенд-документация: оценка готовности

### Что есть
- Design tokens (design-system.md) — полная спецификация, готово к реализации
- Navigation и role map — достаточно
- Page specs — ~60% покрытия (P0 большинство покрыто, P1 частично)
- Component specs (ux/30-components) — concept level
- i18n direction (40-copy-i18n.md) — 4 примера, нет таблицы переводов
- State/API contracts (50-state-api-contracts.md) — 38 строк, нет TS-интерфейсов

### Чего нет
- TypeScript types/interfaces для API responses
- Полный список i18n keys с переводами
- Детальные component props спецификации
- Мобильные layout wireframes для всех P0 экранов
- PWA/offline specификация
- Error message taxonomy
- Navigation contract (entry/exit/back) для каждого экрана

### Может ли новый разработчик построить фронт по этим докам?
- По foundation (design tokens, layout, navigation) — **да**
- По бизнес-экранам P0 — для ~8 из 15 **достаточно**
- По компонентам — **нет**, нужна доп. спецификация props/emits
- По API интеграции — **нет**, нет TS-контрактов → придётся лезть в бэкенд
- По i18n — **нет**, нужна отдельная работа

---

## 10. Test coverage gaps

### Что покрыто
- `test_procurement_lifecycle.py` — open/contribute/receive
- `test_musharaka_mudaraba_formula.py` — profit distribution formula
- `test_sale_multi_payment.py` — multi-payment sale + ledger
- `test_returns_shariah.py` — RESTOCK/DISPOSE + PROFIT_REVERSED/LOSS_INCURRED
- `test_fx_rates.py` — manual rate + historical expense

### Что не покрыто
- CREDIT sale → accrue_debt (B-1) — нет ни теста, ни кода
- Multi-currency capital в receive_procurement (B-4)
- Multi-currency cash reconciliation в close_pos_session (B-5)
- pay_dividend race condition (T-3)
- `compute_aging_reports` с Customer.outstanding_balance (C-4)
- `aggregate_daily_pnl` с InvestorProfitRecord (C-1)
- Idempotency для return / dividend / contribution
- FX rate missing → resolve_fx_rate_snapshot в sale path
- `test_role_matrix.py` тестирует удалённые endpoints

---

## 11. Priority matrix

| № | Находка | Риск | Блокирует PR-10? |
|---|---|---|---|
| C-1 | analytics/tasks.py: InvestorProfitRecord ImportError | Критический | Нет, но ломает Celery Beat |
| C-2 | analytics/tasks.py: record_investor_profit ImportError | Критический | Нет, но ломает Celery Beat |
| C-3 | analytics/tasks.py: payment_method FieldError | Критический | Нет, но ломает Celery Beat |
| C-4 | analytics/tasks.py: outstanding_balance FieldError | Критический | Нет, но ломает aging reports |
| C-5 | analytics/tasks.py: lot.receipt AttributeError | Критический | Нет, но ломает investor aggregates |
| B-1 | CREDIT sale без accrue_debt | Критический | Да — долги теряются |
| B-2 | JournalEntry не создаётся при sale/return | Высокий | Да — бухгалтерия сломана |
| B-3 | CashEntry не создаётся при оплате | Высокий | Да — касса не обновляется |
| S-1 | Django groups не tenant-aware | Высокий | Зависит от MT deployment |
| D-5 | role-matrix.md описывает удалённые endpoints | Средний | Да — ложный контекст для фронта |
| D-6 | frontend-architecture.md legacy на 60% | Средний | Да — разработчик реализует legacy |
| B-4 | Multi-currency capital_share | Средний | Нет (можно отложить до PR-7-fix) |
| B-5 | close_pos_session multi-currency cash | Средний | Нет (single-currency cash OK) |
| T-2 | process_outbox_events двойная обработка | Средний | Нет (single worker OK) |
| I-1 | IMMUTABLE_STATUSES не защищает RECEIVED | Средний | Нет |
| I-2 | Sale.delete() = soft_delete вместо raise | Низкий | Нет |
| L-1..L-9 | Legacy Receipt surface | Низкий | Нет |

---

## 12. Общий вывод

**Ядро vacuum-model работает корректно.** Procurement lifecycle, контракт
partnership, FIFO allocation, PartnerLedgerEntry, RESTOCK/DISPOSE возвраты,
shariah-инварианты (capital_share при убытках, immutable contract_snapshot,
balance=0 на receive) — всё реализовано и покрыто тестами.

**Периметр ядра содержит системные дефекты.** Analytics Celery-задачи
нерабочие (5 крашеров). Финансовая интеграция не замкнута (JournalEntry
и CashEntry не создаются при продаже). CREDIT-продажа не начисляет долг.
Permission-модель не tenant-aware. Multi-currency капитал и касса считаются
некорректно.

**Документация в двойном состоянии.** Новые документы (vacuum-model, phase-d-*,
design-system, ux/*) актуальны и хороши. Старые (architecture, data-models,
compliance-matrix, role-matrix, frontend-architecture) описывают удалённую
реальность и при прочтении создают ложный контекст.

**Фронтенд-доки достаточны для начала работы над P0-экранами, но
недостаточны для независимой реализации.** Нет TypeScript-контрактов API,
нет таблицы i18n, нет детальных props-спецификаций компонентов. Разработчик
будет неизбежно обращаться к бэкенду.

**Итог 58%** отражает разрыв между корректным ядром и сломанным периметром.
Чтобы двигаться к PR-10 без риска, нужно закрыть минимум 3 блокера
(C-1..C-5 как пакет, B-1, B-2+B-3) и обновить 2 документа (D-5, D-6).
