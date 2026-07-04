# E21 — Business Context, Investor-Led Funds & Settlement UX Hardening

**Статус:** `IN_REVIEW`
**Прогресс:** follow-ups implemented
**Зависит от:** E18 (единый money read-model), E20 (multi-party/fund/lifecycle base)
**Блокирует:** pilot-ready investor fund workflow, корректный rollout E20 UX

> 2026-07-04: часть E21 про tenant-scoped fund ownership superseded by
> [E22 — Investor-Owned Funds + E21 UX Correction](./E22-investor-owned-funds-e21-correction.md).
> E21 остаётся историей по business context, settlement UX и FACTUAL guard.

---

## Цель

Довести E20 до продуктово правильной модели: фонд создаётся и управляется со
стороны инвестора, бизнес работает с фондом только как с готовым economic
holder, договоры и приходы показывают net/read-model факты без misleading
gross-цифр, а business context перестаёт молча выбирать первый бизнес.

## Контекст и обоснование

После реализации E20 пилотный просмотр выявил несколько архитектурно важных
швов:

- фонд был реализован ближе к business-side constructor, хотя целевая модель —
  investor-led fundraising workflow;
- `owner` технически может иметь несколько business tenants, но UI не даёт
  явного выбора и backend может silently fallback на первый бизнес;
- agreement detail смешивает gross contributions и net paid-in, поэтому после
  циклов “пополнение → возврат” показывает неверное ощущение капитала;
- UI не различает `FROM_POOL`, `FROM_PROCEEDS` и payout прибыли на уровне
  языка пользователя;
- страница прихода после receive должна становиться операционной аналитикой,
  а не оставаться в первую очередь формой старого заполнения.
- `FACTUAL` partial receive создаёт несколько immutable share-profile/tranches
  внутри одного procurement; технически это работает через `Lot.contract_snapshot`,
  но продуктово плохо объясняется и создаёт неоднозначность при продажах до
  финального прихода.

Принцип реализации: проектируем целевую модель в вакууме и накладываем дельту
на текущую E18/E20 реализацию. Не вводить второй ledger и не хранить ручные
балансы: источник истины остаётся append-only facts + E18 read-model.

## Сценарии (use cases)

- **US-1. Business context guard.** Owner входит в систему; если у него один
  active business — он попадает в него. Если active businesses несколько, без
  выбранного контекста система не выбирает первый молча.
- **US-2. Business/profile identity.** Пользователь видит, кто он как user,
  какой бизнес сейчас активен, кто он как operator/business owner и какие
  investor profiles с ним связаны.
- **US-3. Investor creates fund.** Лид-инвестор создаёт фонд в investor cabinet,
  задаёт target, min contribution, visibility, terms и получает invite link.
- **US-4. Investor applies to fund.** Участник открывает публичный фонд или
  invite link, видит условия и подаёт заявку с requested amount.
- **US-5. Manager approves capital.** Управляющий видит заявки, progress к target,
  делает approve/reject/partial approve и подтверждает фактический капитал.
- **US-6. Pre-deployment exit.** До первого deployment участник может выйти, а
  управляющий может убрать участника только вместе с корректным refund, если
  деньги уже подтверждены.
- **US-7. Agreement capital truth.** После пополнений и возвратов договор
  показывает net paid-in/withdrawable, а не сумму всех исторических взносов.
- **US-8. Procurement-bound payout.** Реализованный капитал и прибыль
  возвращаются из конкретного прихода; agreement-level wizard только показывает
  preview разбивки и создаёт per-procurement records.
- **US-9. Post-receive procurement view.** После оприходования страница прихода
  по умолчанию показывает продажи, остатки, recovered capital, profit/loss и
  доступные действия; старые детали формы свернуты.
- **US-10. Action queue.** Заявки фонда, payout obligations, review date,
  disputes и confirmations попадают в единый in-app список действий.
- **US-11. FACTUAL full receive guard.** Если договор использует `FACTUAL`,
  приход принимается целиком: один procurement получает один factual snapshot.
  Для partial receive и продаж до полного прихода используется `AGREED`, где
  batches/lots наследуют договорные доли, а недовзносы/переплаты уходят в net
  capital position.

## Текущее состояние

- ✅ **Что уже есть:** E20 модели фонда, fund member/contribution/deployment,
  payout policy/obligation, dispute/review lifecycle, `PartnerPositionReadModel`
  и explicit `AgreementWithdrawal.return_kind`.
- ⚠️ **Что начато, но не завершено:** fund screens существуют, но не как
  полноценный application/invite workflow; agreement screens используют часть
  read-model данных, но hero/participants всё ещё могут показывать gross totals.
- ✅ **Что реализовано в E21:** fund applications, public/private visibility,
  hard cap, explicit pre-deployment terms amendment, pre-deployment exit/refund
  flow, business context guard, profile/business page, aggregated payout
  preview, status-aware post-receive procurement view и action queue.
- ⚠️ **Superseded by E22:** fund ownership больше не считается tenant-scoped
  `Partner`/business-side конструкцией. Target owner — global
  `InvestmentProfile`; business видит только synthetic holder `Фонд: X`.

## Целевая модель

### Business context

- `User` и `Business` остаются разными сущностями: в будущем user reputation
  может переноситься между бизнесами.
- MVP invariant: `1 owner = 1 active business`.
- Пока нет полноценного switcher, несколько active businesses у owner без
  выбранного контекста — ошибка состояния, а не silent fallback.
- Product tenant context должен быть выбран на auth/session boundary. `X-Tenant-ID`
  не является пользовательским механизмом; его можно оставить только как
  dev/admin escape hatch.

### Investor-led fund

- Фонд создаётся в investor cabinet.
- Бизнес не создаёт фонд; он видит фонд только как одного investor/economic
  holder при включении в invest agreement.
- Visibility:
  - `PRIVATE_INVITE` — доступ по invite link;
  - `PUBLIC_LISTING` — виден в investor cabinet.
- В MVP любой вход в фонд идёт через заявку, не auto-join.
- Заявка и капитал разделены:
  - `requested_amount` — сколько участник хочет вложить;
  - `approved_amount` — сколько управляющий одобрил;
  - `paid_amount` — сколько отмечено как внесённое;
  - `confirmed_amount` — сколько подтверждено как капитал фонда.
- Hard cap: фонд не может молча собрать больше `target_amount`. Сверхлимит —
  только через явное изменение terms до первого deployment.
- До deployment участник может выйти/быть удалён только с refund, если
  confirmed capital уже есть.
- После deployment обычный выход/кик запрещён; будущие версии могут добавить
  buyout/secondary transfer/redemption.

### Agreement and procurement settlement

- `FROM_POOL` — возврат свободного капитала из пула договора.
- `FROM_PROCEEDS` — возврат реализованного капитала из конкретного прихода.
- Profit payout всегда привязан к конкретному приходу.
- Business/operator не является обычным получателем payout в UI. Его recovered
  capital/profit показываются как отчётность бизнеса; физический вывод денег
  owner-ом — finance owner drawing.
- Agreement-level aggregate payout — UX-удобство, не новый факт. Перед
  подтверждением система показывает preview разбивки по eligible procurements
  default order: oldest eligible first.

## План реализации

### Фаза 1 — Документы и target contracts

Оформить E21, зафиксировать state machines и границы миграции. Старую
финансовую историю не переписывать; исправлять display/read mapping и добавлять
новые intent records.

### Фаза 2 — Business context

Убрать silent first-business fallback, добавить explicit current business
contract, подготовить profile/business endpoint и UI.

### Фаза 3 — Fundraising domain/API

Добавить fund visibility, invite/public access, fund applications, partial
approval, hard cap, pre-deployment refund/exit и permission boundary.

### Фаза 4 — Agreement/procurement settlement fixes

Исправить labels, net paid-in, conditional action blocks, operator reporting
semantics, history titles и aggregated payout preview.

### Фаза 5 — Frontend UX

Построить investor fund application workflow, manager fund operations,
business agreement view и status-aware procurement detail. Mobile-first,
desktop-readable, без dashboard-card clutter.

### Фаза 6 — Verification and review

Покрыть golden scenarios, прогнать backend/frontend checks и провести fresh
review по tenant isolation, fund boundary, payout provenance и read-model/UI
mapping.

### Фаза 7 — Factual receive hardening

Закрыть продуктовую неоднозначность `FACTUAL` + partial receive без рефактора
snapshot model. `Lot.contract_snapshot` остаётся immutable source of truth для
FIFO, sales realization, settlement, reports и audit. Изменение — минимальный
guard на receive: `FACTUAL` требует full receive; `AGREED` остаётся основным
режимом по умолчанию и поддерживает partial receive/immediate sales.

### Фаза 8 — Investor-pool and payout UX follow-ups

Закрыть ошибки, найденные при pilot review после E21: все summary-блоки должны
говорить об инвесторской стороне как об агрегированном пуле, а не о первом
инвесторе; возврат восстановленного капитала должен работать в рабочей валюте
договора, не округлять max-сумму вверх и давать бизнесу групповой action вместо
обязательного клика по каждому инвестору.

## Задачи (чек-лист)

### Фаза 1
- [x] T-1.1 Зафиксировать E21 в roadmap и связать с E18/E20.
- [x] T-1.2 Описать state machines: business context, fund application,
  fund membership, payout action.
- [x] T-1.3 Зафиксировать migration boundary: no financial history rewrite.

### Фаза 2
- [x] T-2.1 Реализовать guard для owner с несколькими active businesses без
  выбранного контекста.
- [x] T-2.2 Подготовить JWT/session tenant-binding contract.
- [x] T-2.3 Добавить `/auth/me`/profile data для user + active business +
  operator/investor profiles.
- [x] T-2.4 Добавить profile/business UI.
- [x] T-2.5 Исправить demo/seed так, чтобы MVP не создавал неявный multi-business
  owner без switcher.

### Фаза 3
- [x] T-3.1 Добавить fund visibility и invite token/public listing.
- [x] T-3.2 Реализовать fund application model/API.
- [x] T-3.3 Реализовать requested/approved/paid/confirmed amounts.
- [x] T-3.4 Реализовать approve/reject/partial approve и bulk approve preview.
- [x] T-3.5 Реализовать hard cap и explicit terms change для сверхлимита.
- [x] T-3.6 Реализовать pre-deployment exit/remove with refund.
- [x] T-3.7 Проверить permissions: investor/manager owns fund workflow; business
  cannot create fund as business action.

### Фаза 4
- [x] T-4.1 Исправить agreement participant labels.
- [x] T-4.2 Перевести hero/participants на net paid-in/read-model values.
- [x] T-4.3 Показывать contribution/withdrawal blocks только по реальным условиям.
- [x] T-4.4 Разделить history titles по `FROM_POOL`, `FROM_PROCEEDS`, profit payout.
- [x] T-4.5 Убрать misleading operator payout action; оставить reporting row.
- [x] T-4.6 Добавить aggregated payout preview с per-procurement breakdown.

### Фаза 5
- [x] T-5.1 Перестроить investor fund list/detail/application screens.
- [x] T-5.2 Перестроить manager fund applications/capital progress screens.
- [x] T-5.3 Обновить business agreement detail под corrected settlement UX.
- [x] T-5.4 Сделать procurement detail status-aware: after receive analytics first,
  source details collapsed.
- [x] T-5.5 Добавить in-app action queue для fund/payout/review/dispute actions.

### Фаза 6
- [x] T-6.1 Backend tests: tenant guard, fund application lifecycle, hard cap,
  pre-deployment refund, post-deployment exit block.
- [x] T-6.2 Backend tests: contribution/withdrawal loop net paid-in, return kind
  labels/data, proceeds payout requires procurement.
- [x] T-6.3 Backend tests: aggregated payout preview creates per-procurement facts.
- [x] T-6.4 Frontend tests/type-check for labels, conditional blocks, fund
  application states and profile/business context.
- [x] T-6.5 Run targeted backend suite, full core/partnership suite, frontend
  type-check/build and fresh review.

### Фаза 7
- [x] T-7.1 Backend guard: `RECEIVE_BATCH` blocks partial receive when linked
  `InvestmentAgreement.reconciliation_mode == FACTUAL`.
- [x] T-7.2 Error copy: `FACTUAL reconciliation requires full receive because
  shares are derived from final factual funding. Use AGREED for partial receive
  and immediate sales.`
- [x] T-7.3 Agreement form copy: selecting `FACTUAL` clearly warns that partial
  receive is unavailable.
- [x] T-7.4 Tests: `FACTUAL + partial receive` is blocked, `FACTUAL + full
  receive` is allowed, `AGREED + partial receive` remains allowed.

### Фаза 8
- [x] T-8.1 Backend list/detail/workspace payload exposes aggregate
  `investor_shares` for the investor pool.
- [x] T-8.2 Procurement financing card, agreement list/detail and profit
  simulator use investor-pool aggregates instead of the first investor.
- [x] T-8.3 Agreement detail fact profit display respects `AGREED` pinned
  shares and uses per-partner factual profit only in `FACTUAL`.
- [x] T-8.4 Recovered-capital return defaults to agreement currency and floors
  converted max amounts to avoid frontend/backend FX rounding rejection.
- [x] T-8.5 Recovered-capital card provides a grouped return action with
  automatic per-investor preview while preserving immutable per-row withdrawals.

## Не входит в MVP

- Full marketplace/discovery beyond simple public listing.
- KYC/AML, escrow, e-signature, automatic bank transfer.
- Secondary transfer, NAV/redemption engine, fund series/reinvestment.
- Полный multi-business switcher UX, если guard + auth contract достаточно для MVP.
- PDF/печать юридического договора.

## Открытые вопросы

- ✓ Полный business switcher не входит в E21: MVP guard + JWT/session tenant
  contract достаточно, полноценный switcher остаётся отдельным эпиком.
- ✓ Manager fee validation по Sharia/AAOIFI остаётся для E06/legal-policy слоя;
  E21 только фиксирует disclosed manager profit share в terms snapshot.
- ✓ Для пилота достаточно in-app action queue; external notifications не входят
  в E21.
- ✓ 2026-06-29: `FACTUAL` ограничивается full receive. Не делаем true-up по
  проданным лотам и не переписываем `Lot.contract_snapshot`; partial receive
  остаётся через `AGREED`.
- ✓ 2026-06-29: Обобщённые UI/read API по инвесторам должны использовать
  investor pool aggregate. Поименные строки остаются только там, где пользователь
  смотрит конкретного участника.

## Решённые вопросы (история)

- ✓ 2026-06-25: E21 оформляется отдельным эпиком, а не дописывается в E20,
  потому что затрагивает business context, fund UX и settlement UX одновременно.
- ✓ 2026-06-25: Public fund в MVP означает видимость + application, не auto-join.
- ✓ 2026-06-25: Фонд создаётся инвестором/управляющим в investor cabinet; бизнес
  видит фонд только как одного economic holder в invest agreement.
- ✓ 2026-06-25: Agreement-level payout aggregate — только wizard/preview; источник
  истины остаётся per-procurement append-only facts.
- ✓ 2026-06-25: Operator/business proceeds в UI — отчётность, не обычная кнопка
  payout самому себе.
- ✓ 2026-06-25: Cashier/warehouse tenant fallback допустим только если в системе
  ровно один active business; при нескольких бизнесах silent selection запрещён.
- ✓ 2026-06-25: Сверхлимит фонда не проходит через молчаливый approve; сначала
  создаётся явная amendment-версия условий до первого deployment.
- ✓ 2026-07-04: tenant-scoped fund ownership superseded by E22; фонд принадлежит
  global `InvestmentProfile`, а business-side `Partner` нужен только для
  deployment в конкретный invest agreement.
