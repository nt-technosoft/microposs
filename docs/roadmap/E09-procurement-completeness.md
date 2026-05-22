# E09 — Procurement Completeness (non-PREPAID, ON_SALE, returnability)

**Статус:** `IN_REVIEW`
**Прогресс:** ~95%
**Зависит от:** E07, E08 (DONE)
**Блокирует:** E03 (Net Value требует корректного учёта CONSIGNED inventory), частично E05

---

## Цель

Завершить procurement matrix: расщепить `payment_timing` и `goods_ownership`
на независимые оси, реализовать ON_SALE-обязательство для консигнации
(автоматический payable при продаже), добавить returnability как
cross-cutting attribute. Без этого Net Value считается некорректно
(консигнационный товар не наш, но сейчас он попадает в стоимость инвентаря),
а полноценная POS-для-ритейла поддержка «в долг / в отсрочку / на реализацию»
у поставщика не закрыта.

## Контекст и обоснование

После E07 (controlled radical reset) и E08 (source-of-truth consolidation)
партнёрский трек и базовая архитектура зацементированы. Vacuum-сессия от
2026-05-19 показала, что procurement matrix лучше моделировать через 3
независимые оси (расширены 2026-05-20 после уточнения семантики
AT_RECEIPT):

- **funding_source** — `OWN_FUNDS | PARTNERSHIP`
- **payment_timing** — `PREPAID | AT_RECEIPT | PARTIAL | DEFERRED | INSTALLMENT | ON_SALE`
- **goods_ownership** — `OWNED | CONSIGNED`

Из 36 теоретических комбинаций легально **8** (расширилось с 6 после
добавления AT_RECEIPT в обе legitimate-партнёрские точки). Сейчас в коде:

- Ось `funding_source` есть как `Procurement.funding_source` ✓
- Ось `payment_timing` живёт внутри `ProcurementTerms.type`, но **CONSIGNMENT
  смешивает timing (ON_SALE) и ownership (CONSIGNED) в одном enum-значении** —
  категориальная ошибка, которую нужно расщепить.
- Ось `goods_ownership` отсутствует как явное поле.
- ON_SALE-обязательство (автомат-payable при продаже CONSIGNED Lot) не
  дописан до конца.
- Returnability работает только для CONSIGNED через `ConsignmentReturn`;
  generic возврат поставщику (просрочка, брак, сезонный возврат с
  OWNED-Lot) — отсутствует.

## Сценарии (use cases)

- **US-1.** Бизнесмен берёт товар на реализацию у дистрибьютора (CONSIGNED),
  продаёт через POS — система автоматически генерирует обязательство
  поставщику в размере себестоимости проданного. Кассир ничего лишнего не
  делает.
- **US-2.** Бизнес видит «к оплате поставщику X: 2 350 000 UZS» (накопленный
  debt из консигнационных продаж), делает один платёж — оплата корректно
  гасит payable.
- **US-3.** Возврат поставщику просроченного товара (OWNED, не консигнация) —
  отдельный документ, корректирует payable или генерирует обратный платёж.
- **US-4.** UI создания procurement показывает три флага (источник × timing ×
  ownership) как независимые элементы, не смешивая их в один selector.
  Невалидные комбинации блокируются на бэке.
- **US-5.** Отчёт Net Value корректно различает: OWNED-товар на полке входит
  в стоимость инвентаря, CONSIGNED — нет.

## Текущее состояние

- ✅ **Что есть:** `Procurement.funding_source`, `ProcurementTerms.Type`
  (со смешанным CONSIGNMENT), `ConsignmentReturn` + `ConsignmentReturnLine`,
  `ConsignmentAgreement` (suppliers), `AgreementPartner.Role` (INVESTOR/OPERATOR
  → мушарака уже поддержана), policies.py с `PARTNERSHIP_SETTLEMENTS = (PREPAID,)`.
- ⚠️ **Начато, но не завершено:** CONSIGNMENT существует как enum в
  `ProcurementTerms.Type`, но логика «продажа CONSIGNED Lot → автомат payable»
  не дописана.
- ❌ **Чего нет вообще:** `Procurement.goods_ownership`, `Lot.is_owned`,
  `ProductVariant.is_returnable_default`, `Lot.is_returnable`, `SupplierReturn`
  (generic, не консигнационный), `validate_procurement_combination()` валидатор
  легальных точек матрицы.

## План реализации

### Фаза 1 — Refactor matrix axes

Backend-only рефакторинг без новой функциональности: расщепить CONSIGNMENT
на две оси, добавить `goods_ownership` и `Lot.is_owned`, чистка legacy.
Не трогает UI. План пригоден для делегирования Сонету.

### Wave B — Frontend workspace rebuild (DONE 2026-05-21)

- [x] B-1: Shell + routing + store — новый `ProcurementWorkspaceView.vue` + Pinia store; заменил 405-строчный монолит
- [x] B-2: `ProcurementHeader` + `ProcurementBottomActionBar` — status badge, back nav, action menu, динамический CTA из backend payload
- [x] B-3: `ProcurementCardSupplier` — supplier picker, funding toggle, settlement timing chips; PARTNERSHIP chip откладывает dispatch до выбора agreement; preconditions на timing chips (supplier required)
- [x] B-4: `ProcurementCardItems` + `ProcurementItemRow` — список товаров, per-item goods_ownership, add/edit/delete
- [x] B-5: `ProcurementCardExpenses` — landed expenses с allocation method picker; заблокирована целиком для CONSIGNED (OPEN-4 guard)
- [x] B-6: `ProcurementCardFinancing` (PARTNERSHIP only) + `WorkspaceSupplierPickerSheet` + `WorkspaceAgreementPickerSheet`
- [x] B-7: `ProcurementCardPayment` + `PaymentMakeSheet` — multi-timing payment card; AT_RECEIPT прячет карточку полностью
- [x] B-8: `ProcurementCardReceive` + `ReceiveBatchConfirmSheet` — приёмка с discrepancy capture (qty + reason code) + capital snapshot для PARTNERSHIP
- [x] B-9: `ProcurementCardHistory` + `AttachmentList` + `AttachmentUploader` — collapsible история + вложения (Wave A S-4 backend)
- [x] B-10: AT_RECEIPT combined receive+pay — OWN_FUNDS cash account picker + payment block встроены в `ReceiveBatchConfirmSheet`
- [x] B-11: `useProcurementReadiness` composable — единый источник readiness/visibility; `items_ready` и capital section переключены на backend source
- [x] B-12: `AmendmentSheet` — inline амендмент items/expenses с обязательным reason; cancel rows через `_cancel` flag
- [x] B-13: `ProcurementCancelDialog` + `ReverseReceiveBatchDialog` + консолидация `dispatch()` helper в view (−7× try/catch, view ≤262 строк)
- [x] B-14: Polish — expand-transition на `CardHistory` (150ms), извлечение `{detail}` из Axios errors в dispatch, entry point «Завести по факту» в `IntakeList`

### Фаза 2 — ON_SALE механика

Реализация автомат-генерации payable при продаже CONSIGNED Lot. Это новая
функциональность, влияет на sale.completed flow. Backend + минимальный UI
(отображение накопленного консигнационного долга, action оплаты).

### Фаза 3 — Returnability

Возврат поставщику как cross-cutting функциональность для OWNED-Lot. Новые
поля + новая модель `SupplierReturn` + service + UI. Может быть отложена
если приоритет — Net Value (E03) сначала.

## Задачи (чек-лист)

### Wave A — Backend preconditions for UI rebuild (DONE 2026-05-20)

- [x] S-1: AT_RECEIPT timing — combined receive+pay action + policies guard + legal combinations expanded to 8; PARTNERSHIP×AT_RECEIPT draws from capital pool (explicit or derived from planned shares, OPEN-S1.1 resolved 2026-05-20)
- [x] S-2: Per-item goods_ownership — `Procurement.goods_ownership` → `@property`, field moved to `ProcurementItem`; MIXED derived
      → superseded 2026-05-21: MIXED убран целиком, `Procurement.goods_ownership` теперь derived из `terms.type` (ON_SALE → CONSIGNED, иначе OWNED), `ProcurementItem.goods_ownership` остаётся denormalized cache для Lot creation. Per-item toggle убран из UI.
- [x] S-3: Discrepancy reason codes on `ProcurementReceiveBatchLine` — `quantity_planned`, `quantity_received`, `discrepancy_reason`
- [x] S-4: Generic `apps/attachments/` app — `Attachment` model, `attach_file`/`list_attachments`/`detach` services, API endpoints
- [x] S-5: Cancel procurement action — `cancel_workspace_procurement` + `CANCEL_PROCUREMENT` action dispatch; blocked if payments or batches exist
- [x] S-6: Reverse receive batch — `reverse_workspace_receive_batch` + `Lot.reversed` field + FIFO filter update; STRICT reject if lots sold (OPEN-S6.1 resolved)
- [x] S-7: Amendment model — `ProcurementAmendment` (append-only), `apply_items_amendment`, `apply_expenses_amendment`; `payment_status` block in workspace payload (OPEN-S7.1 resolved: amendments don't touch payments)
- [x] S-8: PREPAID receive coverage constraint — `_check_prepaid_coverage` in `receive_workspace_batch`; other timings exempt

### Фаза 1 — Refactor (backend-only)

- [x] T-1.1 Добавить `Procurement.goods_ownership` поле (`OWNED | CONSIGNED`,
      default `OWNED`) + миграция.
- [x] T-1.2 Переименовать `ProcurementTerms.Type.CONSIGNMENT` → `ON_SALE`;
      data migration (если есть CONSIGNMENT строки — выставить
      `Procurement.goods_ownership=CONSIGNED` для родительского procurement).
- [x] T-1.3 Добавить `Lot.is_owned` boolean; в `receive_workspace_batch`
      устанавливать из `procurement.goods_ownership` при создании.
- [x] T-1.4 Создать `validate_procurement_combination(funding_source,
      payment_timing, goods_ownership)` в `policies.py`. Таблица легальных
      6 точек явно зафиксирована в коде.
- [x] T-1.5 Удалить MUSHARAKA legacy-нормализацию из `policies.py` +
      связанный тест-страж.
- [x] T-1.6 Переименовать `ProcurementPolicyContext.has_procurement_balance`
      → `has_partnership_capital_activity` (имя устарело после Phase 2).
- [x] T-1.7 Обновить тесты: `test_e07_procurement_policy.py` под новые
      имена, добавить invariant-тест на матрицу комбинаций.

### Фаза 2 — ON_SALE механика

- [x] T-2.1 Решить: trigger в `sales/services.py` синхронно (Variant A). Outbox
      только для audit, не как primary mechanism.
- [x] T-2.2 Реализовать trigger: при `sale.completed` для каждого
      `SaleLine` с `Lot.is_owned=false` создаётся `SupplierPayable(reason=CONSIGNMENT_SALE)`.
      Модуль `apps/suppliers/consignment_obligations.py`. Journal: CR A/P (2000) не CR Inventory (1100).
      OPEN-2 guards: CONSIGNED receive не создаёт payable и не пишет inventory-journal.
      OPEN-4 guard: landed expenses запрещены для CONSIGNED procurement.
- [x] T-2.3 Service оплаты — Variant A (без отдельного service). Существующий
      `pay_supplier_payable` достаточен; UI фильтрует по `reason=CONSIGNMENT_SALE`.
- [x] T-2.4 Invariant-тесты: `ConsignmentObligationInvariants` + `OwnedSaleNoConsignmentPayableInvariant`
      в `test_e08_sharia_invariants.py`. 6 новых тестов.
- [ ] T-2.5 UI (под контролем founder'а): отображение накопленного debt по
      консигнации, action оплаты, история консигнационных обязательств.

### Фаза 3 — Returnability

- [ ] T-3.1 Добавить `ProductVariant.is_returnable_default` boolean,
      default false.
- [ ] T-3.2 Добавить `Lot.is_returnable` boolean (override per-batch);
      `ReceiveBatch.returnable_until` optional date.
- [ ] T-3.3 Создать модель `SupplierReturn` + `SupplierReturnLine` —
      generic возврат для OWNED-Lot (аналог `ConsignmentReturn` но для
      не-консигнации).
- [ ] T-3.4 Service `record_supplier_return(lot_id, qty, reason)` — снижает
      `Lot.stock`, корректирует payable или генерирует обратный Payment.
- [ ] T-3.5 UI (под контролем founder'а): возврат поставщику.

## Открытые вопросы

- ~~**? ON_SALE trigger architecture.**~~ → решено 2026-05-19: Variant A — синхронно в `sales/services.py`, не через OutboxEvent. Модуль `apps/suppliers/consignment_obligations.py`. Outbox остаётся только для audit.
- ~~**? Payable per sale or per lot?**~~ → решено 2026-05-19: per-SaleLine payable (не накопительный). Аудитная точность важнее UX-компактности. Агрегат «всего к оплате» — query `Σ open CONSIGNMENT_SALE payables for supplier X`.
- ~~**? Миграция существующих CONSIGNMENT.**~~ → решено 2026-05-19: в dev DB 0 строк в `Procurement` и `ProcurementTerms`, поэтому migration тривиальная — `RemoveField`/`AddField` без backfill. Применено в T-1.2.
- **? SupplierReturn vs ConsignmentReturn — разделить или обобщить?**
  Архитектурно: оставить `ConsignmentReturn` для CONSIGNED-Lot returns
  (там consignment-specific логика), добавить отдельный `SupplierReturn`
  для OWNED-Lot returns. Два разных бизнес-кейса. **Решение в Фазе 3.**
- **? UI для Фазы 1 нужен?** Backend-only рефакторинг технически не
  требует UI-изменений, но если поле `goods_ownership` теперь явное —
  логично дать пользователю отдельный селектор «свой / на реализации»
  вместо смешанного с типом оплаты. **Решение после демо Фазы 1.**

## MVP UX scope (зафиксировано 2026-05-19)

Полноценный UI procurement должен покрыть 6 легальных комбинаций матрицы.
Ниже — функциональный scope, отделяющий MVP от after-MVP, чтобы при
проектировании карточек/секций не упереться в потолок и не делать лишнего.

### В MVP (обязательно в первой реализации UI)

- **Per-item ownership.** `goods_ownership` переносится с Procurement на
  ProcurementItem. Реальный кейс: дистрибьютор шлёт 80% OWNED + 20%
  CONSIGNED (free samples) в одной поставке. Архитектурный сдвиг —
  влияет на `validate_procurement_combination` и legal-combinations
  matrix. **Делать ДО основной UI работы.**
- **Amendment items/expenses mid-receive.** Backend поддерживает
  `ProcurementTermsAmendment` для terms; расширить для items/expenses.
  UX — явный режим «амендмент» с записью before/after, иначе
  пользователи начнут пересоздавать procurement-ы при любой
  корректировке.
- **Reverse receive batch.** Backend append-only, реверсал = новый
  документ. UX — явный action «зафиксировать ошибку приёма» с
  генерацией обратного движения и инверсией snapshot-а.
- **Cancel procurement в OPEN после первого платежа.** Отдельное от
  `terms.lifecycle` правило: запрет если есть `finance.Payment` или
  ReceiveBatch, иначе можно. Чёткое правило в state machine.
- **Discrepancy on receive с reason codes.** `damaged` / `missing` /
  `quality_reject`. Поле на ReceiveBatchLine. Без reason codes данные
  грязные, аудит невозможен.
- **Document attachments на receive batch.** Минимум одно фото
  накладной. Новая модель `ReceiveBatchAttachment` (или generic
  attachment). Audit trail + supplier-trust.

### After MVP (намеренно отложено)

- **Returnability** (E09 Phase 3) — ~95% товаров невозвратные; делаем
  когда появится реальная бизнес-боль.
- **Cash-flow inline** — идёт пакетом с E03 Net Value.
- **Templates / clone procurement** — quality-of-life, не блокер.
- **Multi-editor conflict protection** — badge «кто редактирует»,
  soft-lock. Текущая база уже позволяет нескольким пользователям
  редактировать; защита от конфликтов — слой поверх, добавляется когда
  команды реально начнут вступать в конфликты.

### Не в scope E09 вообще

Recurring procurement, QC gate, supplier scoring, barcode scan,
currency mid-flight change, approval workflow, PO numbers, tax line.

## Решённые вопросы (история)

- ✓ 2026-05-22: **Cancel/edit semantics зафиксированы.** Прямое удаление item/expense
  через `cancel_item_ids` / `cancel_expense_ids` разрешено только пока строка
  в `lifecycle_state=DRAFT` (нет связанных Payment / ReceiveBatch). После Payment
  строка переходит в `READY_FOR_RECEIVE` — изменения через **Amendment flow**
  (workspace menu → «Корректировка» → AmendmentSheet с обязательным reason).
  Это согласовано с append-only audit принципом: post-payment изменения
  обязательны фиксируются как `ProcurementAmendment(before, after, reason)`.
  Frontend (ProcurementCardItems / ProcurementCardExpenses) фильтрует
  `lifecycle_state==CANCELLED` строки из visible list — иначе на UI появлялись
  «zombie» строки после успешного cancel. Error messages из `_draft_item_for_update`
  / `_draft_expense_for_update` локализованы и явно указывают путь обхода
  (Amendment).

- ✓ 2026-05-21: **MIXED ownership убран; goods_ownership — derived, не user choice.**
  Реальные UI-проверки (sessions 2026-05-21) показали, что выбор «На реализации»
  при товарах OWNED падал с illegal-combination и без ясного выхода. Решение:
  `goods_ownership` derive из `payment_timing` (ON_SALE → CONSIGNED, иначе → OWNED).
  Per-item toggle (Wave A T-2) убран из UI; `_upsert_workspace_item` игнорирует
  `goods_ownership` в payload; `upsert_procurement_terms_draft` каскадирует
  derived ownership на все DRAFT items. `LEGAL_COMBINATIONS` сокращён до 8 точек
  (MIXED-строки удалены). Free-samples-в-одной-поставке сценарий моделируется
  отдельным ON_SALE procurement. Принцип: UI не предлагает выбор там, где
  система может вывести значение из других выборов.
  → Wave A T-2 (per-item goods_ownership) considered superseded.

- ✓ 2026-05-21: **INSTALLMENT total=0 после смены типа — fixed.**
  `_normalize_terms_values` пересчитывает `total_amount_due` из items для
  DRAFT terms (preserve only после activate). `update_workspace_lines`
  ресинхронизирует total через `_resync_draft_terms_total` после изменения
  items. Корень: terms был создан до items → total=0 → existing-preserve
  ветка сохраняла 0 при всех последующих переключениях. `terms.total_amount_due`
  теперь denormalized cache, source of truth — items × prices × fx.

- ✓ 2026-05-21: **CUSTOM periodicity для installment schedule.**
  `generate_installment_schedule` принимает `interval='CUSTOM'` +
  `interval_days: int` для произвольной кадреники (двухнедельная,
  трёхнедельная и т.п.). Frontend: третий chip «Свой интервал» + поле
  «дней между платежами». Datepicker замены отложены до общего редизайна.

- ✓ 2026-05-21: **Wave B frontend rebuild — закрыта (14/14 slices).** Все карточки workspace реализованы, компоненты держат бюджет ≤300 строк, view-orchestrator ≤262 строк. Два элемента polish деferred по итогам B-14: per-card loading skeletons (рефакторинг объёма, не polish) и swipe-down на AppBottomSheet (нет gesture-инфраструктуры). Оба не блокируют operational use; вернуться если появится реальная пользовательская боль. Оставшиеся ~5% = golden-path верификация 8 легальных комбинаций procurement matrix.

- ✓ 2026-05-19: **`HYBRID` источник денег — не нужен.** PARTNERSHIP уже
  покрывает оба сценария мудараба + мушарака через `AgreementPartner.role`
  (INVESTOR/OPERATOR). Деньги бизнеса в мушараке проходят через
  `AgreementContribution(role=OPERATOR)`, не напрямую из CashAccount.
  Иначе нарушится инвариант Σ capital_share == 1.0 в Lot.contract_snapshot.
- ✓ 2026-05-19: **Procurement matrix — 3 независимые оси.**
  Из 30 теоретических точек легальны 6 (см. матрицу выше). Все остальные
  блокируются `validate_procurement_combination`.
- ✓ 2026-05-19: **Returnability — cross-cutting, не новая ось.**
  ProductVariant default + Lot override + SupplierReturn документ. Не
  блокер для MVP (на ~95% товаров не применимо), но архитектура должна
  поддерживать без миграции данных.
- ✓ 2026-05-19: **PARTNERSHIP × non-PREPAID запрещено категорически.**
  Если бизнес хочет привлечь инвестора и взять у поставщика отсрочку —
  это разные procurement-ы или операционная проблема. Архитектура не
  моделирует.
  → пересмотрено 2026-05-20 (см. ниже): добавлен AT_RECEIPT для
  партнёрского, потому что AT_RECEIPT не делегирует финансирование
  поставщику.
- ✓ 2026-05-20: **AT_RECEIPT как 6-е значение payment_timing.**
  Семантика — оплата в момент получения (один combined action
  «принять и оплатить», без отдельной payment-карточки). Архитектурно
  ближе к PREPAID (никакой A/P), но UX-радикально другое. Реальный
  частый кейс: товар привозят, отдают деньги, оприходуют — одной
  операцией.
- ✓ 2026-05-20: **PARTNERSHIP допускает PREPAID и AT_RECEIPT.**
  Пересмотр предыдущего правила. Реальное архитектурное требование к
  партнёрскому: инвестор (или бизнес через агреемент) — источник
  капитала, поставщик не даёт credit. Этому удовлетворяют ОБЕ —
  PREPAID (capital flows до receive) и AT_RECEIPT (capital flows
  одновременно с receive). НЕ удовлетворяют DEFERRED / INSTALLMENT /
  PARTIAL / ON_SALE (там поставщик extends credit либо нет
  upfront-commitment).
- ✓ 2026-05-20: **Multi-payment per procurement разрешён.**
  `confirm` (а не первый payment) блокирует редактирование items.
  После confirm — sколько угодно Payments накопительно + сколько
  угодно ReceiveBatch-ей. Это нужно для «китайских поездок» где
  закупка идёт неделями: инвестор видит активность в real-time. Items
  изменяются только через amendment с before/after.
- ✓ 2026-05-19: **OPEN-1 — cost field для consignment obligation.** Используем `ProcurementItem.unit_purchase_price` (operation currency) + `item.fx_rate`, не `Lot.unit_purchase_price` (тот уже в UZS). Каждая продажа получает независимый snapshot.
- ✓ 2026-05-19: **OPEN-2 — CONSIGNED receive не трогает финансы.** Guards в `_ensure_supplier_payable_after_receive` и `_record_receive_journal`: CONSIGNED → return early. Только Lot-записи с `is_owned=False`, никакого journal и никакого payable при receive.
- ✓ 2026-05-19: **OPEN-3 — wire-up в create_sale.** Вызов `record_consignment_obligation_for_sale_line` после `SaleLine.objects.create` внутри FIFO-loop. `record_sale_cogs_journal` расширен `consignment_legs` — CR 2000 (A/P) вместо CR 1100 (Inventory) для CONSIGNED slice.
- ✓ 2026-05-19: **OPEN-4 — landed expenses запрещены для CONSIGNED.** Guard в `update_workspace_lines`: если `goods_ownership=CONSIGNED` и `expenses_payload` непустой → ValueError. Это гарантирует `landed_cost_per_unit == unit_purchase_price` для всех CONSIGNED Lot, journal сходится без 3-го counterparty.
- ✓ 2026-05-19: **«Сроки поставки» — не ось.** Это атрибут конкретного
  `ReceiveBatch.received_at` (timestamp), а не классификация procurement-а.
  Соответственно стадии «заказал → оплатил → получил» — state machine
  одного и того же Procurement, а не оси.
- ✓ 2026-05-20: **Wave A backend завершено.** 8 слайсов, 45 тестов (0 skipped). Commits: feat(E09-wave-A-1) → feat(E09-wave-A-8) + OPEN-S1.1 на ветке vacuum-rework-claude. Wave B (UI rebuild) под контролем founder'а.
- ✓ 2026-05-20: **OPEN-S6.1 — STRICT reject при sold lots.** `reverse_workspace_receive_batch` поднимает ValueError если любой Lot из batch уже продан. Post-sale corrections — отдельный action, не в E09 MVP.
- ✓ 2026-05-20: **OPEN-S1.1 — PARTNERSHIP × AT_RECEIPT: explicit-or-derived allocations.** `_pre_allocate_at_receipt_partnership_capital` atomically draws from agreement pool at receive time. `capital_allocations` in payload = explicit; absent = `_auto_capital_amounts` from planned shares. Same sharia invariants as PREPAID — `Lot.contract_snapshot` captures actual distribution.
- ✓ 2026-05-20: **OPEN-S7.1 — amendment не трогает payments.** `apply_items_amendment` / `apply_expenses_amendment` меняют только items/expenses. Delta поверхностируется через `payment_status` блок в workspace payload (obligation = item costs sum, paid = Payments sum). Пользователь сам инициирует refund/top-up.
