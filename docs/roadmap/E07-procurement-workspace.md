# E07 — Procurement & Investment Workspace Re-architecture

**Статус:** `IN_PROGRESS`
**Прогресс:** 70%
**Приоритет:** P0 — главный архитектурный цикл проекта
**Зависит от:** E01, E04
**Блокирует:** E03, E05, investor marketplace, стабильный procurement UX

---

## Current Decision

E07 — это **controlled radical reset**, а не постепенная адаптация старого intake/procurement flow.

Мы проектируем procurement / investment / payment core как целевую архитектуру “с нуля”, но выполняем reset контролируемо:

- старый backend/frontend procurement код — только reference для бизнес-правил и edge cases;
- новую архитектуру не подгоняем под старые компромиссы;
- локальные данные и старые миграции не являются ограничением;
- перед заменой фиксируем зависимости, чтобы не потерять FIFO, partial receive snapshots, supplier payables, partner profit logic, journal effects и Excel-like сценарии.

Главный reset-план: [`E07-controlled-radical-reset.md`](./E07-controlled-radical-reset.md).

Canonical пользовательский flow для Phase D:
[`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md).

Важно: API sections/readiness/actions — это transport/backend contract, а не
порядок UX. Frontend Phase D должен следовать canonical flow:

```text
товары/расходы -> поставщик/условия -> источник денег -> оплата/обязательство -> приёмка -> история
```

## Цель

Собрать один понятный `Procurement Workspace`, внутри которого пользователь работает с приходом товара, а система создаёт правильные документы:

- `Procurement` — что покупаем;
- `FundingSource` — чьими деньгами покупаем;
- `SupplierSettlement` — как рассчитываемся с поставщиком;
- `SupplierPayable` — кредиторка перед поставщиком;
- `Payment` — факт движения денег;
- `InvestmentAgreement` — партнёрская договорённость;
- `CapitalContribution` / `InvestmentAllocation` — фактический капитал и его использование;
- `ReceiveBatch` — физическая приёмка;
- `LotSnapshot` — неизменяемый snapshot для FIFO/profit split;
- `JournalEntry` — бухгалтерская проводка.

## Что Не Делаем

- Не продолжаем “лечить” старый `IntakeCreate.vue` / `IntakeDetail.vue` как целевой UI.
- Не считаем текущие procurement/partnership backend модели финальной архитектурой.
- Не мигрируем старые экспериментальные procurement данные без отдельной причины.
- Не делаем `MUSHARAKA` отдельной UI-карточкой прихода.
- Не разрешаем `PARTNERSHIP + supplier credit` в MVP.
- Не обновляем Excel replay раньше стабилизации нового backend core.
- Не добавляем compatibility-shims только ради зелёных legacy-тестов.
- Не считаем временно красные legacy-тесты проблемой, если они проверяют старый flow.

## Главные Правила Модели

Procurement разделяет три независимых вопроса:

| Вопрос | Целевая сущность |
|---|---|
| Что покупаем? | `Procurement`, items, expenses, landed cost |
| Чьими деньгами покупаем? | `FundingSource`, investment/capital layer |
| Как рассчитываемся с поставщиком? | `SupplierSettlement`, `SupplierPayable`, `Payment` |

Правила:

- `OWN_FUNDS` может использовать `PREPAID`, `PARTIAL`, `DEFERRED`, `INSTALLMENT`, `CONSIGNMENT`.
- `PARTNERSHIP` в MVP может использовать только `PREPAID`.
- Regular procurement и partnership procurement имеют разные entry points.
- Regular procurement стартует с товаров/расходов.
- Partnership procurement стартует с выбора или быстрого создания `InvestmentAgreement`.
- Own funds payment идёт напрямую из `CashAccount`.
- Partnership payment всегда идёт через `InvestmentAgreement`: `CapitalContribution -> CapitalAllocation -> Payment`.
- Прямой оплаты "мимо договора" в partnership flow нет; если UX выглядит как
  "оплатить долю бизнеса из кассы", backend всё равно фиксирует business
  contribution в договор и allocation на приход.
- Один procurement может иметь несколько `ReceiveBatch`.
- Каждый receive batch может иметь свой factual capital snapshot.
- Lot snapshot immutable и является источником FIFO profit distribution.
- Payments, receive batches, journal entries и capital movements append-only.

## Partnership Money Discipline

Новая договорённость от 2026-05-18:

Партнёрский приход не использует старый "баланс прихода" как отдельный источник
правды. Старый смысл баланса прихода переносится на капитал инвестдоговора.

Canonical chain:

```text
CapitalCommitment -> CapitalContribution -> CapitalAllocation -> Payment -> ReceiveBatchSnapshot
```

Практический смысл:

- вклад инвестора и вклад бизнеса сначала становятся капиталом договора;
- только затем капитал выделяется на конкретный приход;
- только выделенный капитал может оплачивать товары/расходы партнёрского прихода;
- фактические доли партии считаются по allocation/contribution, а не по плану;
- сдача/остаток остаётся доступным балансом договора или выводится через
  withdrawal.

Для UX допустимо объединять действия, например `Внести и выделить на приход`,
но backend обязан сохранить отдельные документы contribution и allocation.

## Investment Agreement Creation Principle

`planned_budget` больше не должен быть главным пользовательским вводом.

Целевой UX:

- основной ввод: `инвестор планирует вложить X`;
- система рассчитывает рекомендуемый вклад бизнеса по плановым долям;
- система может вывести ориентировочный общий объём договора как derived value;
- пользователь может внести факт меньше/больше плана;
- рекомендации не блокируют, потому что snapshot партии считает факт.

`planned_budget` можно оставить в backend как ориентир/derived planned volume,
но не использовать как единственный источник истины. Истина для отчётов и
snapshot — реальные contributions и allocations.

## Future Investor Workflow Readiness

MVP остаётся business-managed: бизнес может создать договор, зафиксировать
взнос инвестора и управлять приходом.

Но модель должна быть готова к будущему investor-side workflow:

- договор — это agreement между сторонами, не просто форма бизнеса;
- будущий инвестор сможет принять/отклонить договор;
- инвестор сможет отправить факт взноса;
- бизнес подтверждает, что деньги получены;
- стороны могут спорить/отменять неподтверждённые действия.

Target additions for audit/backend readiness:

- `CapitalCommitment` для планового намерения вложить сумму;
- `confirmation_status` / `created_by` / `actor_partner` на contribution-like facts;
- `AgreementEvent` для append-only истории договора;
- статусы договора уровня `DRAFT`, `PROPOSED`, `ACCEPTED`, `REJECTED`, `ACTIVE`, `CLOSED`.

Эти возможности не обязательно выводить в MVP UI, но новые backend/API решения
не должны закрывать путь к ним.

## Документы

| Документ | Назначение |
|---|---|
| [`E07-controlled-radical-reset.md`](./E07-controlled-radical-reset.md) | главный план reset и порядок реализации |
| [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md) | canonical пользовательский flow для Phase D |
| [`E07-architecture-audit.md`](./E07-architecture-audit.md) | сверка backend/frontend/docs относительно canonical flow |
| [`E07-dependency-map.md`](./E07-dependency-map.md) | карта текущих backend/frontend связей перед заменой core |
| [`E07-workspace-api-contract.md`](./E07-workspace-api-contract.md) | target API contract для нового ProcurementWorkspace |
| [`E07-target-backend-core.md`](./E07-target-backend-core.md) | target backend model/service design для Phase B |
| [`E07-backend-implementation-plan.md`](./E07-backend-implementation-plan.md) | порядок backend implementation slices и migration/reset boundary |
| [`E07-policy-matrix.md`](./E07-policy-matrix.md) | правила funding × settlement × status |
| [`E07-entity-mapping.md`](./E07-entity-mapping.md) | old responsibility → new responsibility |
| [`E07-phase2-backend-plan.md`](./E07-phase2-backend-plan.md) | подготовительный backend-plan, теперь reference для target core |
| [`E07-phase3-data-strategy.md`](./E07-phase3-data-strategy.md) | reset/test data стратегия |
| [`E07-procurement-workspace-unification.md`](./E07-procurement-workspace-unification.md) | подготовительный UI-plan, теперь reference для нового workspace |
| [`../domain/procurement.md`](../domain/procurement.md) | target procurement domain |
| [`../domain/partnerships.md`](../domain/partnerships.md) | target investment layer |
| [`../domain/finance.md`](../domain/finance.md) | target finance/payment/journal layer |

## Текущее Состояние

| Область | Состояние |
|---|---|
| Backup | дампы сохранены в `backups/` |
| Roadmap | E07 выбран как P0 |
| Target docs | procurement / partnerships / finance описаны как целевая модель |
| Backend | target core в целом соответствует разделённой document/event architecture; workspace payload now exposes canonical `flow` |
| Frontend | `ProcurementWorkspace.vue` переведён на первый canonical-flow slice; дальше нужно добить сценарные UX-состояния и smoke |
| Excel workflow | оставить на потом, после стабилизации core |

## Следующий Правильный Шаг

Продолжать не с наращивания текущего frontend-прототипа, а с canonical flow
reset:

1. Использовать [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md) как Phase D source of truth.
2. Довести backend policy/API payload до поддержки этого flow.
3. Пересобрать frontend workspace вокруг canonical user order.
4. После end-to-end замыкания включить scenario/smoke tests.

Ближайшие задачи:

- [x] `B1` Write target backend model/service design from `E07-workspace-api-contract.md`.
- [x] `B2` Decide replace-in-place vs temporary new module/app.
- [x] `B3` Подготовить backend implementation plan и migration/reset boundary.
- [ ] `B4` Реализовать target backend core.
  - [x] Model core: `funding_source`, line lifecycle state, generic `Payment`, supplier settlement/payment links.
  - [x] Workspace API skeleton: `GET/POST /api/v1/procurement-workspaces/`, payload sections/readiness/policy.
  - [x] First actions: `UPDATE_SOURCE`, `UPDATE_SETTLEMENT`, `AMEND_SETTLEMENT`.
  - [x] Payments/payables actions: `PAY_COSTS`, `PAY_SUPPLIER_PAYABLE` with generic `Payment` + cash facts.
  - [x] Investment funding actions: create/link agreement, record contribution, allocate capital to procurement balance.
  - [x] Investment agreement readiness foundation: `CapitalCommitment`, confirmation/source/actor metadata and append-only `AgreementEvent`.
  - [x] Receive batch/lot snapshot rewrite: `RECEIVE_BATCH` creates immutable batch, lots, stocks, movements, capital snapshot and payable/journal facts.
  - [ ] Integration rewire baseline: заменить старые вызовы целевыми контрактами без compatibility shims.
    - [x] Active `partnerships/procurements` create/update/list/retrieve/pay/receive facade now routes through workspace payload/actions.
    - [x] Finance/sales report payloads use `funding_source` and line `lifecycle_state` instead of legacy procurement naming.
    - [x] Partnerships serializers and investment agreement allocation endpoints no longer depend on legacy procurement receive/cost services.
    - [x] E07 focused tests now exercise target workspace contracts for own-funds cash payment, partnership capital pool and immutable receive snapshots.
    - [ ] Replace remaining legacy investor/intake frontend surfaces during Phase D workspace switch-over.

Frontend workspace начат после B4/Phase C baseline; старые intake screens не являются целевым UI.
Первый `ProcurementWorkspace.vue` является wiring prototype, а не финальным
Phase D UX.

## Implementation Roadmap

### Phase A — Freeze And Map

- [x] Mark old intake/procurement UI and services as reference-only.
- [x] Complete backend dependency map.
- [x] Complete frontend dependency map.
- [x] Define target workspace API contract.

### Phase B — Target Backend Core

- [x] Write target backend model/service design from `E07-workspace-api-contract.md`.
- [x] Design target models/services without adapting to old API shapes.
- [x] Decide replace-in-place vs temporary new module/app.
- [x] Prepare backend implementation plan and migration/reset boundary.
- [x] Implement clean domain services MVP.
- [ ] Clean migration reset before frontend switch-over if needed.

### Phase C — Integration Contracts

- [x] Connect receive batches to inventory lots through target contracts.
- [x] Connect lot snapshots to sales/FIFO profit split through target contracts.
- [x] Connect payments/payables/capital to finance journals through target contracts.
- [x] Connect supplier payables to suppliers module through target contracts.
- [x] Connect partner ledger/reporting to investment layer through target contracts.

### Phase D — New Frontend Workspace

- [x] Restore and document canonical workspace flow.
- [x] Add canonical `flow` metadata to workspace payload.
- [x] Build first technical `ProcurementWorkspace` prototype.
- [ ] Rebuild final `ProcurementWorkspace` around canonical flow.
  - [x] Reoriented current prototype: create flow starts with goods, supplier moved to settlement, funding separated as money-source block.
  - [x] Added explicit canonical navigation: goods/expenses -> supplier/settlement -> funding -> payment/obligation -> receipt -> history.
  - [x] Added scenario-first workspace pass: compact metrics, next-action context, settlement/payable guidance, partnership capital summary and batch snapshot display.
  - [x] Split own-funds payment UX into prepaid, partial advance and payable-only branches instead of showing all settlement modes as ordinary prepayment.
  - [x] Added partial-receive guardrails for expense allocation: global/mixed expenses are blocked in UI until user targets or splits them.
- [ ] Add flow/navigation metadata to API contract if needed.
- [x] Build policy-driven sections without letting API order dictate UX order.
- [x] Keep old intake screens as reference until switch-over.
- [x] Switch procurement create/detail/edit routes to the final canonical workspace.
- [ ] Harden partnership agreement creation/linking UX inside workspace.
  - [x] First in-workspace agreement creation/linking form added for partner-funded procurement.
  - [x] Quick agreement action can switch an own-funds draft workspace into partnership without legacy endpoint fallback.
  - [x] Partnership workspace split into explicit secondary entry point; regular procurement remains default.
  - [x] Agreement picker uses compact agreement cards and in-workspace quick create.
  - [ ] Rework agreement creation around investor planned investment amount instead of user-primary total budget.
  - [ ] Add contribution/allocation UX that follows `Contribution -> Allocation -> Payment`.
  - [ ] Add agreement detail sheet/card showing balances, linked procurements and recalculation simulation.
- [ ] Add frontend smoke coverage for own funds, deferred payable and partnership capital scenarios.
  - [x] Added target `SPLIT_ITEM` workspace action and frontend split control for partial receive preparation.
- [x] Phase D.2 UX improvement pass:
  - [x] Replaced all product-variant and supplier `<select>` elements with bottom-sheet pickers (`WorkspaceVariantPickerSheet`, `WorkspaceSupplierPickerSheet`).
  - [x] Added quick-create flows for products and suppliers inside pickers (`WorkspaceQuickProductSheet`, `WorkspaceQuickSupplierSheet`).
  - [x] Added confirmation sheet for `RECEIVE_BATCH` with mandatory partnership snapshot checkbox (`WorkspaceReceiveConfirmSheet`).
  - [x] Added split-item sheet for partial-receive preparation (`WorkspaceSplitItemSheet`).
  - [x] Converted settlement type, funding source, allocation method, schedule interval and partner role selects to chip-group buttons.
  - [x] Replaced warehouse select with card-picker.
  - [x] Added human-readable label dictionaries for all technical enum values (lifecycle states, payment states, expense types, history kinds, payable statuses).
  - [x] Removed all raw enum values from user-facing UI strings and warning messages.
  - [x] Added Slice 3 CSS (obligation-context, account-cards, partner-cards, partner-chips, payable-cards, contribution/allocation forms).

### Phase E — Verification

- [ ] Backend scenario tests.
- [ ] Partial receive tests with different batch snapshots.
- [ ] FIFO sale/profit split tests.
- [ ] Supplier payable/payment tests.
- [ ] Frontend smoke tests.
- [ ] Excel replay after core stabilizes.

## Решённые Решения

- 2026-05-13: E07 является P0.
- 2026-05-13: Выбран controlled radical reset.
- 2026-05-13: Старый intake/procurement код — reference-only, не target architecture.
- 2026-05-13: `MUSHARAKA` не отдельная UI-карточка.
- 2026-05-13: `PARTNERSHIP + supplier credit` запрещён в MVP.
- 2026-05-13: Консигнация должна поддерживать fixed supplier price и commission.
- 2026-05-13: Частичные приёмки и per-batch snapshots сохраняются.
- 2026-05-13: Lot snapshot остаётся фундаментом FIFO profit distribution.
- 2026-05-13: Старые phase docs помечены как reference/pre-reset context.
- 2026-05-13: Создана initial dependency map для backend/frontend replacement.
- 2026-05-13: Определён target API contract для нового `ProcurementWorkspace`.
- 2026-05-13: Phase B backend design принят: replace-in-place в существующих apps, раннее создание `OPEN Procurement`, generic `Payment` в finance, `FundingSource` как поле/policy, `LotSnapshot` как immutable JSON на Lot в MVP.
- 2026-05-13: Подготовлен backend implementation plan: Slice 1 starts with model core, then policy/workspace payload, actions, payments, investment funding, receive batch, integration, tests/reset.
- 2026-05-13: B4 начат: реализованы model core, workspace payload/readiness/policy и первые source/settlement actions; Excel/smoke остаются после стабилизации backend-flow.
- 2026-05-13: Реализован Slice 4 MVP: `PAY_COSTS` оплачивает own-funds draft costs из `CashAccount`, `PAY_SUPPLIER_PAYABLE` гасит supplier payable через generic `Payment` и cash facts.
- 2026-05-13: Реализован Slice 5 MVP: `CREATE/LINK_INVESTMENT_AGREEMENT`, `RECORD_CAPITAL_CONTRIBUTION`, `ALLOCATE_CAPITAL`; workspace payload показывает partners/contributions/allocations/available_by_partner.
- 2026-05-13: Реализован Slice 6 MVP: `RECEIVE_BATCH` создаёт immutable receive batch, inventory lots/stocks/movements, per-batch capital snapshot, supplier payable и receipt journal.
- 2026-05-13: Compatibility shims для legacy `status`/`procurement_type` признаны неверным компромиссом и удалены. До переписывания target tests старые legacy-тесты могут быть красными; это допустимо и не должно лечиться подгонкой архитектуры.
- 2026-05-13: B4 integration rewire started without shims: active old procurement endpoint is now a workspace facade, `UPDATE_ITEMS/UPDATE_EXPENSES` added as target actions, and focused workspace contract test covers own-funds pay/receive.
- 2026-05-13: Finance/sales reporting contracts rewired to target naming: `funding_source` replaces `procurement_type`, pending line calculations read `lifecycle_state`, and frontend report views/types were synced.
- 2026-05-13: B4 backend rewire continued: partnerships serializers use workspace payload instead of legacy receive/cost preview services; investment agreement allocation endpoint uses `allocate_workspace_capital`; E07 tests were rewritten around target workspace behavior, not legacy service aliases.
- 2026-05-13: Phase C started: sales profit/return ledger writes now use target `workspace_support` ledger helpers; profitability and sale explanation tests run against target workspace seed data and `funding_source`.
- 2026-05-13: Phase C finance/supplier integration advanced: supplier payables now link settlement and update supplier A/P balance; payable payments create generic `Payment`, cash entry and journal facts; installment schedule generation is a workspace action; capital contributions record cash-in/journal/payment facts with `EXTERNAL_PARTNER` source.
- 2026-05-13: Phase D started: added typed frontend client for `/api/v1/procurement-workspaces/`, created `ProcurementWorkspace.vue`, switched procurement create/detail/edit routes to it, and rewired procurement list to workspace payload.
- 2026-05-13: Phase D partnership UX advanced: workspace can create and link a basic investment agreement from active partners, then continue contribution/allocation flow from the same screen.
- 2026-05-13: Restored canonical Phase D flow from the original "design from zero" agreement. Current frontend workspace is classified as technical prototype; final Phase D must follow `goods/expenses -> supplier/settlement -> funding -> payment/obligation -> receipt -> history`.
- 2026-05-13: Backend workspace payload now includes canonical `flow` steps/current_step/next_action so frontend no longer has to infer user order from technical sections.
- 2026-05-13: Frontend prototype reoriented toward canonical flow: create no longer starts with funding, goods/expenses render first, supplier/settlement and funding are separated.
- 2026-05-13: Phase D frontend canonical slice implemented: workspace uses `payload.flow` navigation, create starts from purchase intent, supplier settlement is separated from funding, and payment/obligation handles own funds, payables and partnership capital paths.
- 2026-05-13: `PARTIAL` settlement behavior corrected as target domain logic: receive requires an upfront procurement payment; that payment updates settlement `paid_amount`; supplier payable is created only for the remaining obligation after receive.
- 2026-05-13: Partnership funding boundary corrected: `InvestmentAgreement` completes the funding step; capital contribution/allocation belongs to payment/obligation step and then unlocks receive.
- 2026-05-13: Deferred/installment target contracts covered: deferred receive creates payable without upfront payment; installment receive requires generated schedule.
- 2026-05-13: Browser smoke covered own-funds prepaid receive/reopen, partnership agreement -> contribution -> allocation -> receive, and installment schedule gating to receive.
- 2026-05-13: Phase D scenario UX pass started: workspace gained next-action context, compact cost/status metrics, expense allocation scope, target `SPLIT_ITEM`, payable-oriented settlement hints, partnership capital summaries and receive-batch snapshot display.
- 2026-05-18: E07 partnership flow refined: regular and partnership procurements have separate entry points. Partnership starts from `InvestmentAgreement`; regular procurement stays focused on goods/expenses and supplier/payment scenarios.
- 2026-05-18: Partnership money discipline accepted: all participant money must pass through `InvestmentAgreement` as contribution and allocation before payment; direct payment "mimo agreement" is forbidden as source of truth.
- 2026-05-18: Old "procurement balance" meaning is replaced by agreement capital pool for partnership. UX may combine contribution/allocation for convenience, but backend must keep separate append-only facts.
- 2026-05-18: Investment agreement creation direction accepted: primary UX should be "investor plans to invest X", with recommended business contribution and derived overall volume, not a rigid user-primary total budget.
- 2026-05-18: Future investor workflow must be preserved architecturally: commitments, confirmation status, actor/source metadata and agreement events should be prepared even if MVP remains business-managed.
- 2026-05-18: Backend agreement readiness audit completed: added `CapitalCommitment`, agreement event log, confirmation/source/actor metadata for contribution/withdrawal/allocation facts, exposed them in serializers/workspace payload, and wired API/workspace services to record business-managed MVP facts through those target fields.
- 2026-05-18: Investment agreement creation contract moved to target UX shape: API can accept investor planned amount + capital/profit percentages, derives total planned volume and business recommended contribution, and frontend creation form no longer makes total budget the primary input.

## Открытые Вопросы

- Нет backend-блокеров для продолжения Phase D.
- UX/flow обычного и партнёрского прихода остаётся user-controlled зоной: не
  перестраивать эти интерфейсы дальше без явного направления пользователя.
