# E08 — Architecture Cleanup & Source-of-Truth Consolidation

**Статус:** 🟡 IN_PROGRESS
**Прогресс:** 55% (Phase 0 + Phase 1 закрыты)
**Зависит от:** E07 (целевая архитектура procurement workspace)
**Блокирует:** E03 (Net Value), E05 (Zakat), E06 (Sharia certification) — все нуждаются в чистом источнике правды

---

## Цель

Устранить архитектурные долги, накопившиеся за период controlled radical reset
E07: убрать мёртвый код, ликвидировать дублирование источников правды для
партнёрского капитала и денежных обязательств, привести документацию к
единой карте. Без этой чистки последующие эпики (E03/E05/E06) будут строиться
на нестабильном фундаменте.

## Контекст и обоснование

В рамках E07 параллельно работают старая (intake) и новая (workspace) ветки.
Старая не до конца удалена, новая не до конца достроена. Параллельный аудит
backend + frontend + документации (сессия 2026-05-18, ветка
`vacuum-rework-claude`) выявил 7 критических точек:

1. **`apps/partnerships/services.py` (4012 LoC) — мёртвый код.** Обращается к
   удалённым полям (`procurement.procurement_type`, `Procurement.Type.OWN_FUNDS`),
   но импортируется живым кодом из `partnerships/views.py`, `investors/views.py`,
   `investors/services.py`, `risk/services.py`, `core/management/commands/bootstrap_demo.py`,
   `bootstrap_deploy_baseline.py`, `excel_workflow_audit.py`. При случайном
   вызове → `AttributeError` в проде. Live trap.
2. **`Lot.received_at` nullable** (`inventory/models.py:266`) + FIFO ordering по
   `(lot.received_at, lot.id)` (`inventory/services.py:39`). NULL в Postgres
   может встать first → продажа из неправильной партии → неправильный
   `contract_snapshot` → чужие деньги в `profit_distribution_snapshot`. Прямое
   нарушение шариатского учёта при ЛЮБОЙ продаже, не только партнёрской.
3. **Источник правды для капитала партнёра в 4–6 представлениях одновременно:**
   `AgreementContribution/Withdrawal/Allocation` (правильный append-only) +
   `InvestmentAgreement.balances` JSON + `ProcurementBalance.balances` JSON +
   `PartnerLedgerEntry` + табличный `ProcurementReceiveBatchCapitalAllocation` +
   JSON `Lot.contract_snapshot`. Шесть путей на одну сумму.
4. **Денежные обязательства на денорм-полях:** `SupplierPayable.paid_amount`/
   `remaining_amount` (`suppliers/services.py:392-397`), `Supplier.outstanding_balance`
   (`suppliers/services.py:99-100, 196-197, 411-413`), `ProcurementTerms.paid_amount`
   (`workspace.py:996-1008`) мутируются напрямую, мимо `finance.Payment`.
5. **`ProcurementTerms` не `ImmutableMixin`** (`partnerships/models.py:1080`) —
   договор-обязательство мутируется без amendment-trail, хотя
   `ProcurementTermsAmendment` существует.
6. **`SalePayment.account_id`, `DividendPayment.paid_from_account_id`** —
   `IntegerField`, не FK (`sales/models.py:215-216`, `partnerships/models.py:1063-1064`).
   Orphan-риск для immutable финансовых записей.
7. **Расхождения в документации:** прогресс E07 = 52% в `ROADMAP.md` vs 70% в
   эпике; `Receipt`-инвариант в Key Business Rules при пометке «`Receipt` is
   legacy» в `CLAUDE.md`; `SupplierSettlement` vs `ProcurementTerms` в разных
   файлах; `Key Business Rules` в 3 файлах с разной нумерацией.

Из этих семи: #1 и #2 — глобальные риски (не только про приход). #3–#6
сконцентрированы в партнёрско-procurement слое. #7 — документационный.

## Сценарии (use cases)

- **US-1.** Любой агент (Claude/Codex) открывает проект → читает
  `CLAUDE.md` + `ROADMAP` + соответствующий эпик → ясно понимает текущее
  состояние без противоречий между файлами.
- **US-2.** Разработчик удаляет `apps/partnerships/services.py` или импорт из
  него → проект компилируется и работает; нет hidden imports «на всякий случай».
- **US-3.** Партнёрская продажа (FIFO) гарантированно берёт лот с правильным
  `contract_snapshot`; нет шанса попасть на NULL `received_at`.
- **US-4.** Запрос «сколько мы должны поставщику X» возвращает один и тот же
  ответ независимо от источника (`SupplierPayable`, агрегат `Payment`,
  `Supplier.outstanding_balance`).
- **US-5.** Партнёр-инвестор открывает свой dashboard → видит баланс,
  совпадающий с суммой его append-only contributions − withdrawals −
  allocated; нет вариантов «по выбору источника».

## Текущее состояние

- ✅ **Что уже есть:** аудит зафиксирован (сессия 2026-05-18, ветка
  `vacuum-rework-claude`); checkpoint Codex-работы по E07 закоммичен
  (`vacuum-rework: e0997c1`); target-архитектура E07 в основном спроектирована
  правильно (`finance.Payment`, append-only ledgers, immutable snapshots,
  idempotency через `client_request_id`).
- ⚠️ **Что начато, но не завершено:** новый `ProcurementWorkspace` + новые
  модели (`InvestmentAgreement`, `CapitalCommitment`, `AgreementEvent`)
  живут рядом со старым кодом, не заменили его.
- ❌ **Чего нет вообще:** единой документ-карты, защищающей от ложного следа
  в будущих сессиях; чистого удаления legacy `services.py`; DB-constraint на
  `Lot.received_at`; derived properties для денежных балансов.

## План реализации

### Фаза 0 — Foundation map (документ-карта)

Минимальная документация, которая нужна как карта для всех последующих фаз.
Без этого следующие правки будут опираться на противоречивые источники, и
при сжатии контекста между сессиями появится ложный след.

### Фаза 1 — Global hygiene (глобальные риски)

Закрывает live trap (`services.py`) и FIFO loophole (`Lot.received_at`).
Удаляет мёртвый frontend legacy. Делается без UI-правок (UI остаётся под
контролем founder'а).

### Фаза 2 — Source-of-truth consolidation

Сердце эпика. Превращает 6 представлений каждого факта в одно: денежные
обязательства считаются из `finance.Payment`, балансы агрямента — из
append-only событий, `ProcurementBalance` уходит, `ProcurementTerms`
становится immutable.

### Фаза 3 — Frontend workspace closure

Формально остаётся внутри [E07 Phase D](./E07-procurement-workspace.md).
E08 не дублирует её, а указывает: после Фазы 2 цикл продолжается в E07. UI-шаги
прихода — под прямым контролем founder'а, без инициативы агентов.

## Задачи (чек-лист)

### Фаза 0 — Foundation map ✅

- [x] T-0.1 Свести `Key Business Rules` в `CLAUDE.md` как canonical;
      `AGENTS.md` и `docs/README.md` — ссылки.
- [x] T-0.2 Синхронизировать прогресс E07 в `docs/ROADMAP.md` (52% → 70%).
- [x] T-0.3 Резолвить `Receipt`-инвариант: переформулировать Key Business
      Rules через `ReceiveBatch`; `Receipt` явно отмечен как legacy + 2
      новых правила (#13, #14) про money discipline и snapshot immutability.
- [x] T-0.4 Резолвить `SupplierSettlement` vs `ProcurementTerms`: header
      note добавлен в `docs/domain/customers-suppliers.md` и
      `docs/roadmap/E01-suppliers-procurement.md`; target имя =
      `SupplierSettlement`, code rename → E08 Фаза 2.
- [x] T-0.5 `docs/legacy-inventory.md` создан — единое место для всего
      legacy (backend модули, frontend файлы, docs, tests).
- [x] T-0.6 `docs/glossary.md` создан — базовые термины (Мудараба,
      Мушарака, Procurement, ReceiveBatch, contract_snapshot, money
      discipline, idempotency и т.д.) с явным указанием target vs legacy
      имён.

### Фаза 1 — Global hygiene ✅

- [x] T-1.1 Аудит всех импортов `apps/partnerships/services.py` — список
      мест-вызовов, что нужно сохранить.
- [x] T-1.2 Перенести `pay_dividend`, `get_partner_aggregate`,
      `append_ledger_entry`, `get_or_create_ledger` в новый
      `apps/partnerships/agreement_services.py`.
- [x] T-1.3 Обновить все импорты в `partnerships/views.py`,
      `investors/views.py`, `investors/services.py`, `risk/services.py`,
      `core/management/commands/bootstrap_demo.py`,
      `bootstrap_deploy_baseline.py`, `excel_workflow_audit.py`.
- [x] T-1.4 Удалить `apps/partnerships/services.py`.
- [x] T-1.5 Удалить тесты, опирающиеся на удалённый код
      (`test_procurement_lifecycle.py`, `test_e01_e02_services.py`,
      `test_e01_wave5_consignment.py` и ещё 4 файла с той же зависимостью).
      `test_partner_ledger.py` и `test_audit_batch_one.py` сохранены —
      обновлены на `agreement_services`.
- [x] T-1.6 Миграция `Lot.received_at` → `NOT NULL` + backfill из `created_at`.
- [x] T-1.7 Удалить frontend legacy: `IntakeCreate.vue`, `IntakeDetail.vue`,
      `stores/intake.ts`, `components/ProcurementTermsHistory.vue`,
      `modules/intake/types.ts`.
- [x] T-1.8 Удалить «болтающуюся строку 406» в `ProcurementWorkspace.vue`.

### Фаза 2 — Source-of-truth consolidation

- [ ] T-2.1 `SupplierPayable.paid_amount`, `remaining_amount` → derived
      property из агрегата `finance.Payment`.
- [ ] T-2.2 `Supplier.outstanding_balance` → derived property.
- [ ] T-2.3 `ProcurementTerms.paid_amount` → derived property.
- [ ] T-2.4 Management command `validate_payable_consistency` для
      переходного периода (логирует расхождения).
- [ ] T-2.5 `InvestmentAgreement.balances` → derived (или явная projection
      `recompute_from_events`). Убрать `_mutate_agreement_balance`.
- [ ] T-2.6 Удалить `ProcurementBalance`, `BalanceContribution`,
      `BalanceWithdrawal`, `ProcurementBalanceExchange`.
- [ ] T-2.7 `allocate_workspace_capital` переходит на прямой путь Agreement
      → BatchCapitalSnapshot (без посредника `ProcurementBalance`).
- [ ] T-2.8 `ProcurementTerms` → `ImmutableMixin` после первого `Payment` или
      `receive_batch`.
- [ ] T-2.9 `SalePayment.account_id` → FK `finance.CashAccount`.
- [ ] T-2.10 `DividendPayment.paid_from_account_id` → FK `finance.CashAccount`.

## Открытые вопросы

- ? Куда переносить `pay_dividend`, `get_partner_aggregate` —
  `workspace_support.py` уже большой (761 LoC), стоит ли выделить
  `agreement_services.py`?
- ? Как поступить с тестами `test_procurement_lifecycle.py` (~1600 LoC) —
  переписать под E07 или удалить целиком? По правилу «не писать тесты ради
  тестов» склоняемся к удалению, но финальное решение за founder'ом.
- ~~`Lot.received_at` backfill источник~~ — Закрыто 2026-05-19: выбран
  `created_at`. В новом коде `received_at` всегда = `timezone.now()` в
  момент `RECEIVE_BATCH`. Для legacy лотов `created_at` — лучшее из доступных.
- ? Какие именно тесты-инварианты написать как страховку для шариатского
  учёта (`sum(profit_ratio) == 1.0`, FIFO ordering, append-only ledger,
  immutable snapshots, sum partner capital_share == 1.0 в snapshot)?

## Решённые вопросы (история)

- ✓ 2026-05-18: **Phase 0 закрыта.** Foundation map установлена: Key
  Business Rules canonical в `CLAUDE.md` (14 правил, target-имена
  `ReceiveBatch`/`InvestmentAgreement` вместо legacy `Receipt`/`InvestorContract`,
  добавлены правила money discipline и snapshot immutability), AGENTS.md и
  docs/README.md — ссылками. `docs/legacy-inventory.md` и `docs/glossary.md`
  созданы как единые источники для «что устарело» и «что что означает».
  E07 progress синхронизирован 52% → 70%.
- ✓ 2026-05-18: новый эпик E08 создан как отдельный от E07. E08 фокусируется
  на cleanup и source-of-truth, E07 продолжает focus на procurement workspace
  re-architecture (Phase D frontend closure). Решение принято после
  параллельного аудита backend + frontend + docs.
- ✓ 2026-05-18: документация делится на «foundation map» (Фаза 0, делается
  первой) и «deep domain rewrite» (отдельный трек после Фазы 2). Foundation
  map — минимум, защищающий от ложного следа в будущих сессиях. Глубокий
  rewrite `domain/*.md` отложен до стабилизации Фазы 2 (иначе документируем
  то, что сами через неделю меняем).
- ✓ 2026-05-18: подход к тестам зафиксирован — тесты пишем только на
  шариатские инварианты (assertion-tests), не на UI-сценарии в брейншторме.
  TDD как догма отвергнут для текущей стадии стартапа.
- ✓ 2026-05-18: senior-partner collaboration principles зафиксированы в
  `CLAUDE.md` и в `AGENTS.md` (короткой ссылкой) → workflow живёт между
  сессиями, не только в текущей.
- ✓ 2026-05-19: **Phase 1 закрыта.** `apps/partnerships/services.py` (4012 LoC)
  удалён. 4 live-функции перенесены в `agreement_services.py`. 7 legacy тестов
  удалены; `test_partner_ledger.py` и `test_audit_batch_one.py` обновлены на
  новый путь импорта и зелёные (4/4 passed). `Lot.received_at` — миграция
  0003 NOT NULL с backfill из `created_at`. Frontend: `IntakeCreate.vue`,
  `IntakeDetail.vue`, `stores/intake.ts`, `ProcurementTermsHistory.vue`,
  `intake/types.ts` удалены; стройная строка 406 в `ProcurementWorkspace.vue`
  убрана. Bootstrap/audit команды застабированы с TODO E07 Phase D.
  `Lot.received_at` backfill источник: `created_at` выбран как наиболее
  точное приближение для legacy лотов (открытый вопрос закрыт).
