# Legacy Inventory

> Единый список всего, что помечено как **legacy / reference / устаревшее**
> в проекте MicroPOS. Цель — чтобы агенты (Claude, Codex) и люди-разработчики
> могли быстро отличить target-архитектуру от исторических артефактов.
>
> Источник правды: этот файл. Если что-то здесь не упомянуто и при этом не
> является явной частью target — добавь сюда. Создан в рамках E08 Фаза 0
> ([T-0.5](./roadmap/E08-architecture-cleanup.md)).

---

## Why this matters

В рамках E07 controlled radical reset старый код намеренно не удалён сразу —
он используется как reference для бизнес-правил и edge cases. Но без явного
списка агенты случайно опираются на legacy как на target, и проект уходит по
ложному следу. Этот документ исключает такую возможность.

При закрытии E08 (Фазы 1 и 2) большая часть позиций ниже будет удалена
физически. До тех пор они существуют, но не являются образцом для нового кода.

---

## Backend (`backend/apps/`)

### Полные модули и крупные файлы

| Путь | Размер / статус | Что делать |
|---|---|---|
| `apps/partnerships/services.py` | 4012 LoC, **мёртвый** — обращается к удалённым полям (`procurement.procurement_type`, `Procurement.Type.OWN_FUNDS`) | Удалить полностью в E08 Фаза 1 (T-1.4). Импорты из живого кода — переписать на новый модуль. |
| `apps/investors/` | Параллельная модель «инвестор», конкурирует с `core.Partner` | Мигрировать в `core.Partner` + `partnerships`. Деталь — отдельный эпик. |

### Модели

| Модель | Расположение | Что заменяет в target | Статус |
|---|---|---|---|
| `Receipt`, `ReceiptLine`, `ReceiptParticipant` | `apps/inventory/models.py` | `ProcurementReceiveBatch*` + `Lot.contract_snapshot` | Legacy путь прихода. `Lot.receipt` остаётся nullable FK для совместимости старых данных. Новый код не создаёт `Receipt`. |
| `InvestorContract`, `ContractPartner` | `apps/partnerships/models.py` | `InvestmentAgreement` + `AgreementPartner` | Старая модель партнёрства. Жива параллельно с новой; не использовать в новом коде. |
| `ProcurementBalance`, `BalanceContribution`, `BalanceWithdrawal`, `ProcurementBalanceExchange` | `apps/partnerships/models.py` | Прямой путь Agreement → `BatchCapitalSnapshot` | Промежуточный «пот денег per procurement». Используется в новом receive flow для UZS-учёта, но это лишний слой. Удалить в E08 Фаза 2 (T-2.6). |
| `ProcurementTerms` | `apps/partnerships/models.py` (имя), фактически контекст `apps/suppliers/` | target name — `SupplierSettlement` | Имя в коде; будет переименовано в E08 Фаза 2. Сейчас оба имени = одна сущность. |

### Поля

| Поле | Что не так | Что делать |
|---|---|---|
| `Lot.received_at` (`inventory/models.py:266`) | `null=True` | E08 Фаза 1 (T-1.6): миграция в `NOT NULL` + backfill. FIFO loophole. |
| `SupplierPayable.paid_amount`, `remaining_amount`, `status` | Денормализованы, мутируются напрямую мимо `finance.Payment` | E08 Фаза 2 (T-2.1): derived properties. |
| `Supplier.outstanding_balance` | Денормализовано | E08 Фаза 2 (T-2.2): derived. |
| `ProcurementTerms.paid_amount` | Денормализовано | E08 Фаза 2 (T-2.3): derived. |
| `InvestmentAgreement.balances` (JSON) | Параллельный источник правды с append-only событиями | E08 Фаза 2 (T-2.5): derived projection. |
| `SalePayment.account_id`, `DividendPayment.paid_from_account_id` | `IntegerField`, не FK | E08 Фаза 2 (T-2.9, T-2.10): FK на `finance.CashAccount`. |

---

## Frontend (`frontend/src/`)

### Полные файлы — удалить в E08 Фаза 1 (T-1.7)

| Путь | Размер | Роль |
|---|---|---|
| `modules/intake/views/IntakeCreate.vue` | ~1656 LoC | Старый wizard создания прихода. Отключён от router'а, но в репо. |
| `modules/intake/views/IntakeDetail.vue` | ~4395 LoC | Старый экран детального прихода с partial receive UX. Reference UX-приёмов. |
| `stores/intake.ts` | 185 LoC | Pinia store старого wizard'а (localStorage, contractRows, plannedBudget). Не используется новым workspace, дрейфует source of truth. |
| `modules/intake/components/ProcurementTermsHistory.vue` | — | Legacy компонент истории условий. |

### Частично legacy

| Путь | Что legacy |
|---|---|
| `modules/intake/types.ts` | Типы `ContractRow`, `ExpenseRow`, `LineRow`, `PaymentTermsDraft` — старые. Новые типы — в `components/workspace/types.ts`. |
| `modules/intake/views/ProcurementWorkspace.vue` | «Болтающаяся строка 406» после `</style>` — удалить (E08 Фаза 1, T-1.8). |

### Router

Маршруты `/intake/*` сохранены как redirects на `/procurements/*` — это правильно (backward-compat), не legacy. Не трогать.

---

## Documentation (`docs/`)

### Не помечены как legacy, но фактически таковые

| Путь | Что делать |
|---|---|
| `AUDIT.md` (в корне репо) | Технический аудит 2026-04-29 на старой архитектуре. Перенести в `docs/audits/2026-04-29-technical-audit.md` либо добавить banner-header «ARCHIVED». |
| `docs/source-inputs/MicroPOS_Claude_Code_Playbook.md` | 28 KB исходного playbook'а. Помечен только в README папки — добавить prominent banner в сам файл. |

### Pre-reset E07 документы (помечены, но не явно)

В `docs/roadmap/E07-*.md` есть 3 файла, описывающих **pre-reset** состояние.
Они полезны для понимания истории, но не для текущей работы. Кандидаты на
перенос в `docs/roadmap/archive/` после стабилизации E08:

- `E07-phase2-backend-plan.md` (232 LoC pre-reset)
- `E07-phase3-data-strategy.md` (180 LoC, специфика миграции на дату 2026-05-13)
- `E07-procurement-workspace-unification.md` (126 LoC pre-reset UI plan)

### Терминологические артефакты в живых документах

| Документ | Что артефакт |
|---|---|
| `docs/domain/customers-suppliers.md` | Использует `ProcurementTerms` (current code name). Header note добавлен. |
| `docs/roadmap/E01-suppliers-procurement.md` | Использует `ProcurementTerms` (legacy doc, исторически). Header note добавлен. |

---

## Tests

Legacy-набор, который ссылается на удалённый/устаревший код:

| Файл | LoC (≈) | Состояние |
|---|---|---|
| `apps/partnerships/tests/test_procurement_lifecycle.py` | ~1600 | Опирается на `apps/partnerships/services.py` (мёртвый). По правилу «не писать тесты ради тестов» — переписать или удалить (E08 Фаза 1, T-1.5). |
| `apps/.../test_e01_e02_services.py` | — | Та же зависимость. |
| `apps/.../test_e01_wave5_consignment.py` | — | Та же зависимость. |

Точечное решение по каждому файлу — открытый вопрос E08.

---

## See also

- [E07 — Procurement & Investment Workspace Re-architecture](./roadmap/E07-procurement-workspace.md) — target архитектура.
- [E08 — Architecture Cleanup](./roadmap/E08-architecture-cleanup.md) — план удаления legacy в коде.
- [E07 architecture audit](./roadmap/E07-architecture-audit.md) — детальный аудит на момент 2026-05-18.
- [glossary](./glossary.md) — терминология (target vs legacy имена).
