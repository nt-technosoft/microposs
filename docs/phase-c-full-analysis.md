# Фаза C+ — Полный анализ и выбор стартовой точки

> Дополнение к [phase-c-diff.md](phase-c-diff.md). Здесь — анализ service-слоя, миграций, Excel-пайплайна, тестов, frontend, а также **ответ на вопрос: main или codex/bootstrap как основа для rework**.

---

## 1. Состояние веток

### `main` (коммит `afe039c`)
- **1 коммит** — baseline init.
- **Нет миграций** ни в одном app. Модели описаны, но схема не применена.
- **Нет services layer** (services.py либо отсутствует, либо минимален).
- **Нет bootstrap_demo.**
- **Нет тестов.**
- **Нет core инфраструктуры** уровня codex/bootstrap (TenantModel в зачаточном виде, OutboxEvent под вопросом).
- **Frontend** — только скелет.

### `codex/bootstrap` (коммит `d4ed756`, наш рабочий)
- **+2 коммита** после main: sprint1 stabilization + наши docs.
- **+73 файла изменено, +7110 строк.**
- **Полная backend инфраструктура:** 21 миграция, services.py во всех apps, тесты, bootstrap_demo, permissions, FX pipeline.
- **+Excel alignment pipeline** (1854 строки, 5 management commands, 4 design docs).
- **Frontend** — полнофункциональный: 22 view, 7 Pinia stores, 11 API клиентов, 9 base components.

---

## 2. Что на codex/bootstrap **точно оставляем** (не переделываем)

### ✅ Core инфраструктура (высокая ценность, переживает rework моделей)
| Компонент | Где | Почему оставляем |
|---|---|---|
| `TenantModel` | `apps/core/models.py` | Multi-tenant изоляция. Используется везде. |
| `ImmutableMixin` | `apps/core/models.py` | Шариатский инвариант #9 (запрет физ. удаления). |
| `OutboxEvent` + `publish_event()` | `apps/core` | Шариатский инвариант #11. |
| `SoftDeleteManager` / `SoftDeleteQuerySet` | `apps/core/managers.py` | `.alive()`/`.dead()`/`.hard_delete()`. |
| `BaseModel` (timestamps, soft-delete) | `apps/core/models.py` | Все модели наследуют. |
| Exception hierarchy (8 классов) | `apps/core/exceptions.py` | Доменные исключения. Переиспользуем. |
| Permissions (4 роли: owner/cashier/warehouse/investor) | `apps/core/permissions.py` | Готовый role matrix. |
| **FX pipeline** (`ExchangeRate` + `resolve_fx_rate_snapshot` + CBU fetch) | `finance/services.py`, `finance/tasks.py` | 745 строк продуман­ной логики. Vacuum-модель это требует. |
| JournalEntry / JournalLine / Chart of Accounts | `finance/` | Bookkeeping слой, не меняется. |
| JWT auth, token views, user profile | `apps/core/auth_views.py` | Инфраструктура. |

**Это ~2500 строк кода, которые стоит переписывать 2-3 недели.** Терять жалко.

### ✅ Frontend структура
| Компонент | Статус |
|---|---|
| Base components (9: Button, Input, Modal, Select, Badge, Chip, Card, Search, SkeletonLoader) | Полностью reusable. |
| Pinia stores pattern | Domain-agnostic. Переезжает на новые типы. |
| Router + layout (default / blank / investor) | Entity-agnostic. |
| Design tokens, responsive grid | Переносится 1:1. |
| auth.ts, session.ts, ui.ts stores | Чистые, не трогаем. |

---

## 3. Что на codex/bootstrap **переделываем**

### 🔧 Backend модели (per [phase-c-diff.md](phase-c-diff.md))
- Добавить 13 новых сущностей (Procurement, ProcurementBalance, SalePayment, LotStock, Receivable, PartnerLedger и т.д.).
- Переработать 7 (Receipt, Lot, Sale, SaleLine, SaleReturn, InvestorContract, InvestorProfitRecord).
- Удалить 5 (InvestorSummary, outstanding_balance скаляры, Sale.payment_method, ReceiptParticipant).

### 🔧 Services layer — частично (~60% rewrite)
| Файл | Объём rework |
|---|---|
| `inventory/services.py` (`confirm_receipt`) | **Полный rework** — становится `confirm_procurement` с ProcurementBalance=0 инвариантом, расчётом landed_cost, создание LotStock. |
| `sales/services.py` (`create_sale`) | **Полный rework** — multi-SalePayment, FIFO per-warehouse, profit_distribution_snapshot. |
| `investors/services.py` | **Полный rework** — per-Procurement PartnerLedger, hybrid формула, DividendPayment. |
| `finance/services.py` | **60% оставить** — FX/COA/journal логика, добавить CashAccount/CashEntry/CurrencyExchange. |
| `customers/services.py` | **Rework** — `record_customer_payment` → `ReceivableEntry(REPAYMENT)`. |
| `suppliers/services.py` | **Заморозить** — Payable отложен. |
| `risk/services.py` | **Rework** — `create_writeoff` → StockDisposal + `LOSS_INCURRED` по `capital_share`. |
| `catalog/services.py` | **Оставить** — товарный каталог стабилен. |

### 🔧 Frontend (~40-50% rewrite API/store layer)
- `api/inventory.ts`, `api/sales.ts`, `api/investors.ts`, `api/customers.ts` — переписать под новые эндпоинты.
- Stores `cart.ts`, `sales.ts`, `customers.ts` — переписать payloads.
- Views `intake/*`, `investors/*`, `sales/Checkout*` — rework UX под новые сущности.
- Views `products/*`, `reports/*`, base components — почти не трогаем.

---

## 4. Что на codex/bootstrap **замораживаем** (не удаляем, но и не развиваем)

### 🧊 Excel alignment pipeline (~1854 строки)
Файлы:
- `apps/core/excel_alignment.py` (1321 строка)
- `apps/core/views_alignment.py`
- `apps/core/management/commands/excel_*.py` (3 команды)
- `apps/core/migrations/0002_excelimportbatch_excelimportrow.py`
- `apps/core/migrations/0003_*`
- `apps/core/tests/test_excel_alignment_*.py`
- `docs/excel-to-domain-mapping.md`, `excel-source-model.md`, `excel-gap-backlog.md`, `reconciliation-spec.md`
- `backend/import_snapshots/`

**Проблема:** код парсинга универсальный, но mapping на домен намертво привязан к старой схеме (Receipt, ReceiptParticipant, Sale.payment_method). При переходе на Procurement/SalePayment — 60% маппинга переписать.

**Решение:** оставить как есть, сейчас НЕ использовать. После того как новая доменная модель стабилизируется (PR-5..6 по плану), вернуться к Excel-импорту и переписать mapping layer на новые сущности. **Примерно 40% кода (парсинг листов, staging-таблицы `ExcelImportBatch`/`ExcelImportRow`, fingerprinting) переиспользуется.**

**Action:** ничего не удаляем, флаг в docs «Excel pipeline заморожен до v2 domain».

### 🧊 `ConsignmentAgreement` + `Receipt.CONSIGNMENT`
DISTRIBUTOR отложен в vacuum-модели → оставляем в коде, не развиваем.

### 🧊 `backend/import_snapshots/` + `Код.gs` + `логистика.gs`
Это артефакты клиента / скрипты Google Apps. Не влияют на код, `.gitignore` их уже ловит или можно игнорить.

---

## 5. Что **удаляем полностью** при rework

- `InvestorSummary` (derived, не храним).
- `Sale.payment_method`, `Sale.customer_has_existing_debt`, `Sale.operation_amount/fx_rate_snapshot/functional_amount_uzs` (дублируют SalePayment).
- `Customer.outstanding_balance` (derived из Receivable).
- `Supplier.outstanding_balance` (derived из Payable).
- `Receipt.MUDARABA` choice (покрывается PARTNERSHIP + mudaraba_ratio).
- `ReceiptParticipant` (заменяется ContractPartner + BalanceContribution).
- Тесты `test_api_smoke.py`, `test_financial_integrity.py`, `test_role_matrix.py` — переписать с нуля (старые жёстко завязаны на bootstrap_demo).

---

## 6. **Ответ: main или codex/bootstrap как основа?**

### Short answer: **codex/bootstrap.**

### Обоснование

| Критерий | main | codex/bootstrap |
|---|---|---|
| Core инфраструктура (Tenant, Immutable, Outbox, Soft-delete, Permissions) | ❌ нет / зачаток | ✅ ~800 строк готового кода |
| FX pipeline (ExchangeRate, CBU fetch, snapshot) | ❌ нет | ✅ 745 строк в finance/services.py |
| JournalEntry / Chart of Accounts | ❌ нет миграций | ✅ готов, переиспользуется |
| Services pattern (`publish_event`, immutability checks) | ❌ нет | ✅ устоялся |
| Миграции применены | ❌ | ✅ |
| bootstrap_demo | ❌ | ⚠️ сломается (но переписывать всё равно надо) |
| Frontend (stores, router, base components) | ❌ скелет | ✅ 22 views + 11 API + 9 base |
| Тесты | ❌ | ⚠️ 8 файлов, часть выбросим |
| Excel pipeline | ❌ | 🧊 заморожен, но 40% reusable позже |
| Документация (implementation-status, role-matrix, compliance) | ❌ | ✅ есть |

**Вывод:** `main` чище, но «чище» здесь = беднее. На main почти нет полезного кода — только модели без миграций и пустые services. Откат на main означает **переписывать заново 2500+ строк готовой инфраструктуры** (Tenant/Immutable/Outbox/Permissions/FX/JournalEntry/auth), которые vacuum-модель **требует сохранить** (шариатские инварианты #9, #10, #11 прямо указывают на ImmutableMixin, JournalEntry, OutboxEvent).

Проблема codex/bootstrap не в «грязи», а в том, что **домен (Receipt/Lot/Sale) не соответствует vacuum-модели**. Это локальная проблема — 7 моделей переработать, 13 добавить, 5 удалить. Инфраструктурный слой (ниже доменного) — правильный.

### Страховка

Чтобы не потерять текущее состояние при rework, **делаем тег `pre-vacuum-rework`** прямо сейчас на `d4ed756`. Если rework пойдёт криво, сможем вернуться к этому состоянию, а не восстанавливать с main.

---

## 7. Дорожная карта (предварительно, для Фазы D)

**Порядок PR** (уточним в Фазе D):

| # | Содержание | Что затрагивает |
|---|---|---|
| 0 | Тег `pre-vacuum-rework` + docs freeze | git tag |
| 1 | `Partner` абстракция, `Warehouse` rename (Location→Warehouse), choice enums alignment | core, inventory |
| 2 | Procurement skeleton + InvestmentContract + ContractPartner + ProcurementBalance + Contribution/Withdrawal | new app `partnerships`, миграции |
| 3 | Lot rework: LotStock, unit_purchase_price, landed_cost_per_unit, contract_snapshot, received_at | inventory |
| 4 | Sale rework: SalePayment, убрать payment_method, SaleLine.profit_distribution_snapshot | sales |
| 5 | ProcurementPartnerLedger + PartnerLedgerEntry, DividendPayment, удалить InvestorSummary | investors, partnerships |
| 6 | Receivable + ReceivableEntry, убрать outstanding_balance | customers |
| 7 | CashAccount, CashEntry, CurrencyExchange, Refund, OwnerContribution | new app `cash` или finance |
| 8 | Return rework: RESTOCK/DISPOSE resolution, интеграция с PartnerLedger (PROFIT_REVERSED, LOSS_INCURRED) | sales, inventory, investors |
| 9 | bootstrap_demo под новую схему, новые тесты | core |
| 10 | Frontend API clients + stores + types — синхронизация | frontend/src/api, stores, types |
| 11 | Frontend views rework (intake, sales checkout, investor dashboard) | frontend/src/modules |
| 12 | Excel pipeline разморозка (mapping на новый домен, reuse staging слоя) | core/excel_alignment.py |

**Оценка:** 6-8 недель full-time для полного прохода, при этом после PR-9 уже есть рабочий бэкенд под vacuum-модель, frontend можно катить параллельно с PR-10+.

---

## 8. Риски и что обсудить перед Фазой D

1. **Partner абстракция** — две опции (vacuum #5.1 в phase-c-diff.md). Решить сразу.
2. **JournalEntry vs CashEntry порядок записи** — service-level hook или signal?
3. **Новый app `partnerships`** или расширение `investors`? Рекомендую новый app — семантика расходится.
4. **migrations strategy** — `makemigrations` и прямо катим (bootstrap, DB можно дропать) vs более аккуратно с reversibility?
5. **Frontend параллельно с backend** или строго после? Рекомендую backend до PR-9, потом фронт догонит одной волной.

---

## 9. Итог

- **Ответ на главный вопрос:** остаёмся на `codex/bootstrap`. На main нет ничего ценного — только модели без миграций. Откат = потеря 2500+ строк готовой инфры, которая vacuum-модели **нужна**.
- **Перед началом:** тег `pre-vacuum-rework` на `d4ed756`.
- **Заморозить:** Excel pipeline, Consignment, DISTRIBUTOR — возвращаемся к ним после стабилизации домена.
- **Готовы к Фазе D** — мне хватает контекста для детального плана по PR.

---

*Документ составлен: 2026-04-18. Фаза C (полный анализ) закрыта. Ожидает Фазу D.*
