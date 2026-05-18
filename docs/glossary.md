# Glossary

> Базовый словарь терминов проекта MicroPOS / Sherik POS. Используется как
> справочник для агентов и людей: что означает каждое имя, и где
> target-имя отличается от того, что в коде сейчас.
>
> Создан в рамках E08 Фаза 0 ([T-0.6](./roadmap/E08-architecture-cleanup.md)).
> Источник правды: этот файл. Если ввели новый термин — добавь сюда.

---

## Партнёрство (Islamic finance)

| Термин | Значение |
|---|---|
| **Мудараба** (Mudaraba) | Партнёрский контракт: одна сторона (инвестор, *rabb-ul-mal*) даёт капитал, другая (оператор, *mudarib*) ведёт работу. Прибыль делится по заранее согласованному коэффициенту; убыток несёт **только инвестор** (если оператор не виноват в халатности). В коде: `InvestmentAgreement.legal_mode = MUDARABA`. |
| **Мушарака** (Musharaka) | Партнёрство, где **обе стороны** вкладывают капитал и могут участвовать в управлении. Прибыль — по согласованному коэффициенту; убыток — **пропорционально вкладам**. В коде: `InvestmentAgreement.legal_mode = MUSHARAKA`. |
| **Hybrid** | Смешанный контракт (Mudaraba + Musharaka элементы). `InvestmentAgreement.legal_mode = HYBRID`. |
| **legal_mode** | Только метка на `InvestmentAgreement`, влияющая на формулу распределения убытков. НЕ отдельный тип прихода. |
| **capital_share** | Доля капитала партнёра в конкретном договоре или лоте (0.0–1.0). Считается из `capital_amount`, не хранится независимо. |
| **profit_ratio** / **profit_share** | Доля прибыли партнёра. Может отличаться от `capital_share` (как в Mudaraba). `Σ profit_ratio == 1.0` всегда. |
| **mudaraba_ratio** | В Mudaraba — доля прибыли, идущая инвестору; остаток (`1 - ratio`) — оператору. |

---

## Procurement (приход товара)

| Термин | Значение |
|---|---|
| **Procurement** | Документ-корень закупки: «мы планируем/приняли товар от поставщика X». Может быть OWN_FUNDS или PARTNERSHIP. Статусы: `OPEN`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CLOSED`, `CANCELLED`. |
| **ProcurementItem** | Строка товара в procurement. Имеет `lifecycle_state` (DRAFT/READY/RECEIVED/CANCELLED). Payment-статус — derived, не storage. |
| **ProcurementExpense** + **ProcurementExpenseTarget** | Landed costs (логистика, упаковка) и таргетирование расходов на конкретные товары/строки. |
| **SupplierSettlement** (target) / **ProcurementTerms** (current code) | Условия расчёта с поставщиком: PREPAID, PARTIAL, DEFERRED, INSTALLMENT, CONSIGNMENT. В E07-доках — `SupplierSettlement`; в коде пока `ProcurementTerms`. Будет переименовано в E08 Фаза 2. |
| **SettlementType** | Значения: `PREPAID` (всё оплачено upfront) / `PARTIAL` (часть upfront, остаток в долг) / `DEFERRED` (одной отсроченной выплатой) / `INSTALLMENT` (по графику) / `CONSIGNMENT` (товар на реализацию). |
| **CONSIGNMENT** | Подвиды: `FIXED_SUPPLIER_PRICE` (поставщик называет фикс-цену) или `COMMISSION` (бизнес платит комиссию с продажи). |
| **FundingSource** | Бинарная ось: `OWN_FUNDS` vs `PARTNERSHIP`. Ортогональна `SettlementType` в target-архитектуре. |
| **Policy matrix** | Какие комбинации `FundingSource × SettlementType` разрешены. В MVP: `PARTNERSHIP × PREPAID` only; `OWN_FUNDS × всё`. |

---

## Receive (приёмка)

| Термин | Значение |
|---|---|
| **ReceiveBatch** | Документ фактической приёмки на склад. Append-only (`POSTED` / `REVERSED`). Один procurement → несколько batch'ей (partial receive). |
| **ReceiveBatchLine** / **ReceiveBatchExpense** | Snapshot полученных строк и расходов в момент batch'а. |
| **BatchCapitalSnapshot** + **BatchCapitalSnapshotPartner** | Immutable снимок фактических долей партнёров на этот batch. План агрямента может быть 70/30, первый batch фиксируется 68/32, второй — 72/28. Существующие batch'ы не переписываются. |
| **Receipt** (legacy) | Старый путь прихода. Не использовать в новом коде; см. `legacy-inventory.md`. |

---

## Inventory (склад)

| Термин | Значение |
|---|---|
| **Lot** | Партия товара. Immutable после создания. Хранит `landed_cost_per_unit`, `received_at`, `contract_snapshot`. |
| **contract_snapshot** | Immutable JSON на `Lot`: фиксирует партнёров, их `capital_share` и `profit_share` **на момент receive batch**. При sale FIFO читает этот snapshot, не текущее состояние агрямента. |
| **LotStock** | Сколько единиц лота осталось на конкретном складе. |
| **StockMovement** | Append-only лог движений склада. Типы: RECEIVE, SALE, TRANSFER, DISPOSAL, CONSIGNMENT_RETURN_OUT и т.д. |
| **FIFO slice** | При продаже `SaleLine` создаётся **по одной** на каждый «срез» лота, который понадобился (если 1 sale потребовала 3 разных лота — 3 SaleLine'а). |
| **FIFO ordering** | По `(lot.received_at, lot.id)`. `received_at` ДОЛЖЕН быть NOT NULL (см. E08 T-1.6). |

---

## Investment (инвестиционный слой)

| Термин | Значение |
|---|---|
| **InvestmentAgreement** | Договор между сторонами (инвестор + бизнес-оператор). Статусы: DRAFT/PROPOSED/ACCEPTED/REJECTED/ACTIVE/CLOSED. |
| **AgreementPartner** | Сторона договора (FK на `core.Partner`, role = INVESTOR/OPERATOR). |
| **CapitalCommitment** | **Планируемый** вклад партнёра в договор. План, не факт. |
| **CapitalContribution** | **Фактическое** движение капитала в pool договора. Append-only, native currency, `fx_rate` snapshot. |
| **CapitalAllocation** (InvestmentAllocation) | Выделение капитала из договора на конкретный procurement или receive batch. Состояния: RESERVED / POSTED / REVERSED. |
| **AgreementEvent** | Append-only audit log уровня договора. Содержит `source` (BUSINESS_RECORDED / INVESTOR_SUBMITTED / SYSTEM), actor, payload. |
| **PartnerLedgerEntry** | Append-only ledger движений капитала. Типы: CAPITAL_COMMITTED, CAPITAL_IN, CAPITAL_ALLOCATED, CAPITAL_RETURNED, PROFIT_ACCRUED, PROFIT_REVERSED, LOSS_INCURRED, DIVIDEND_PAID. |
| **Money discipline** | Партнёрские деньги ВСЕГДА проходят через договор: `CapitalCommitment → CapitalContribution → CapitalAllocation → Payment`. Прямой оплаты «мимо договора» в partnership flow нет. |
| **InvestorContract** (legacy) | Старая модель партнёрства. Не использовать в новом коде. |

---

## Finance (деньги)

| Термин | Значение |
|---|---|
| **Payment** | Append-only документ движения денег. `source_type ∈ {CASH_ACCOUNT, CAPITAL_POOL, EXTERNAL_PARTNER}`, `target_type ∈ {PROCUREMENT_COST, SUPPLIER_PAYABLE, CAPITAL_CONTRIBUTION, DIVIDEND}`. Reversal — отдельный документ. |
| **PaymentAllocation** | Для split-allocation одного `Payment` на несколько целей. |
| **JournalEntry** + **JournalLine** | Immutable двойная бухгалтерия. Каждая финансовая операция создаёт минимум одну `JournalEntry`. |
| **CashAccount** | Касса/счёт. Имеет валюту и баланс (denorm, обновляется атомарно вместе с `CashEntry`). |
| **CashEntry** | Append-only движение по кассе. |
| **ExchangeRate** | Снимок курса валют per `rate_date`, с `source` (CBU / MANUAL). Исторические факты не переоцениваются. |
| **fx_rate snapshot** | Курс, зафиксированный на момент операции, и хранящийся на самой операции. Используется для исторической точности. |

---

## Suppliers & Customers

| Термин | Значение |
|---|---|
| **Supplier** | Поставщик. `outstanding_balance` (UZS, target — derived из `Payment`). |
| **SupplierPayable** | Кредиторское обязательство перед поставщиком. Возникает из `SupplierSettlement` при non-PREPAID. |
| **SupplierPayment** | Документ оплаты поставщику. С `allocations` (мульти-касса/мульти-валюта). |
| **PaymentSchedule** | График платежей для INSTALLMENT-settlement. |
| **ConsignmentAgreement** + **ConsignmentReturn** + **ConsignmentReturnLine** | Консигнация: соглашение, возврат, построчный disposition (RETURN_TO_SUPPLIER / DISPOSE_SUPPLIER_LOSS / DISPOSE_BUSINESS_LOSS / CONVERT_TO_OWN). |
| **Receivable** + **ReceivableEntry** | Дебиторка клиентов: агрегат + append-only события. |

---

## Cross-cutting (общие)

| Термин | Значение |
|---|---|
| **idempotency** / **client_request_id** | Каждый POST финансовой операции принимает `client_request_id`. Повтор с тем же id не создаёт дубль операции. |
| **ImmutableMixin** | Базовый mixin: после терминальных статусов (`confirmed`, `completed`, `closed`, `received`) запрещает `save()`/`delete()` критичных полей. |
| **soft-delete** | `BaseModel.is_active = False` вместо физического `delete()`. Физический `delete()` запрещён для финансовых записей. |
| **OutboxEvent** | Async-сообщение для downstream (analytics, integrations). Все значимые domain-операции пишут outbox. |
| **tenant_id** | Multi-tenancy: каждая бизнес-сущность принадлежит тенанту. |
| **TenantModel** | Базовая модель с `tenant_id` FK. |
| **CELERY_TASK_ALWAYS_EAGER** | В dev/test = True — `.delay()` выполняется синхронно, worker не нужен. |
| **Functional currency** | UZS — функциональная валюта проекта. Все internal-балансы и отчёты — в UZS, native-валюта операции хранится на каждом факте отдельно. |

---

## Source-of-truth principles

- **Один факт — один источник.** Дублирование (например, `paid_amount` на `SupplierPayable` + на `ProcurementTerms` + в `Payment`) — анти-паттерн. См. E08 Фаза 2.
- **Append-only события первичны, агрегаты вторичны.** `balances` JSON на `InvestmentAgreement` должен быть derived из `AgreementContribution/Withdrawal/Allocation`, не writable.
- **Партнёрский капитал — только через договор.** См. `money discipline` выше.
- **Lot.contract_snapshot — иммутабельный источник для FIFO profit distribution.** Изменения в `InvestmentAgreement` не переписывают существующие lots.

---

## See also

- [Key Business Rules](../CLAUDE.md#key-business-rules-never-violate) — нерушимые инварианты.
- [legacy-inventory.md](./legacy-inventory.md) — что устарело и где живёт.
- [E07 target backend core](./roadmap/E07-target-backend-core.md) — детальная спецификация модели.
- [E07 policy matrix](./roadmap/E07-policy-matrix.md) — funding × settlement разрешённые комбинации.
