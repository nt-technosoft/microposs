# Procurement Workspace Rework — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans to implement task-by-task. Steps use `- [ ]`.
> Any frontend/UI work MUST go through the `impeccable` skill and obey
> `PRODUCT.md` / `DESIGN.md` (green primary, calm confidence, tabular numbers,
> no hero-metric/card-grid slop). Backend money rules: `CLAUDE.md` Key Business
> Rules + `docs/vision.md` принципы.

**Goal:** Перестроить страницу создания прихода (procurement workspace) по
canonical flow: тип прихода определяется точкой входа (не выбором на странице),
партнёрский начинается с выбора/создания инвест-договора, settlement имеет
умные дефолты, валюта дисциплинирована в UI, оплата без авто-конверсии, лишняя
sticky-кнопка убрана.

**Architecture:** Один экран `ProcurementWorkspaceView` + карточки-секции
(`ProcurementCard*`). Backend — workspace services (`workspace.py`,
`workspace_support.py`), модель уже на 3 осях. Переиспользуемые виджеты
инвест-договора — единый источник для страницы и модалки.

**Tech Stack:** Vue 3 `<script setup>` + Pinia + TypeScript; Django/DRF backend.

---

## Уже сделано (НЕ дублировать)

- **Backend currency discipline** (commit `2fbb71b`): `total_amount_due = Σ(qty×price)`
  в валюте товара; mixed-currency items отклоняются; `pay_workspace_costs` /
  `pay_workspace_supplier_payable` требуют совпадения валюты кассы и обязательства;
  `test_procurement_currency.py` 9/9. → Backend часть валютной дисциплины готова.
- **Expense type `OTHER` («Прочее»)** уже в `ProcurementExpense.ExpenseType`.
- **Entry query `mode: 'partnership'`** уже передаётся из `IntakeList.vue`
  (`goToPartnershipCreate`), но `createDraft({})` его НЕ читает — это чинится в Phase 1.
- **Компоненты инвест-договора существуют:** `InvestmentAgreementQuickForm.vue` (665
  строк, вся логика), `AgreementCreate.vue` (77 строк — тонкая обёртка-страница),
  `WorkspaceAgreementPickerSheet.vue`, `InvestmentAgreementDetailSheet.vue`,
  `ProcurementCardFinancing.vue`, `WorkspaceInvestmentStartBlock.vue`.
- **Cash management + CurrencyExchange** есть (deposit/withdraw/transfer +
  inline top-up). Конвертацию валют переиспользуем для payment.
- **Backend расходы НЕ объединяются** по типу (`_upsert_workspace_expense` создаёт
  отдельную запись на каждый). Если схлопывание видно в UI — это frontend, чинится в Phase 5.

---

## Phase 1 — Тип прихода определяется точкой входа

**Решение:** funding_source задаётся на создании из query, не выбором на странице.
Две точки входа партнёрского: кнопка «Партнёрский приход» (`?mode=partnership`)
и из инвест-договора (`?mode=partnership&agreement=<id>`). Funding toggle убрать.

**Files:**
- Modify: `frontend/src/api/partnerships.ts` — `ProcurementWorkspaceCreatePayload`
  должен включать `funding_source?: 'OWN_FUNDS'|'PARTNERSHIP'` и
  `investment_agreement_id?: number` (проверить, есть ли уже).
- Modify: `frontend/src/modules/intake/views/ProcurementWorkspaceView.vue`
  (`ensureWorkspace`) — читать `route.query.mode` и `route.query.agreement`;
  для нового прихода `createDraft({ funding_source: mode==='partnership'
  ? 'PARTNERSHIP' : 'OWN_FUNDS', investment_agreement_id: query.agreement })`.
- Modify: `frontend/src/modules/intake/components/workspace/ProcurementCardSupplier.vue`
  — удалить весь `funding-row` блок (toggle Собственные/Партнёрский) + `setFunding`
  + `request-partnership` emit + agreement-stub. Карточка остаётся: поставщик + тип оплаты.
- Modify: `frontend/src/modules/intake/views/IntakeList.vue` — вход из инвест-договора
  (если кнопка/ссылка с конкретным agreement) добавляет `&agreement=<id>`.
- Verify backend: `create_workspace` / store `createDraft` принимает `funding_source`
  и `investment_agreement_id` (workspace.py). Если нет — добавить параметр.

**Acceptance:** Вход по «Обычный» → funding OWN_FUNDS, выбора нет. Вход по
«Партнёрский» → funding PARTNERSHIP, выбора нет. Funding toggle отсутствует на экране.

---

## Phase 2 — Партнёрский этап 1: выбор/создание инвест-договора (единый источник)

**Решение:** Для PARTNERSHIP первая секция workspace = выбор инвест-договора.
Список карточек существующих договоров (базовые данные: партнёры, план-бюджет,
валюта, статус). Тап → bottom-sheet детали (`InvestmentAgreementDetailSheet`).
«Создать новый» → bottom-sheet с формой. **Форма создания — единый виджет,
переиспользуемый страницей `AgreementCreate` и модалкой в workspace** (один
источник: правка логики/визуала отражается в обоих местах).

**Files:**
- Audit + consolidate: `InvestmentAgreementQuickForm.vue` (665 строк) — это уже
  ядро. Убедиться, что `AgreementCreate.vue` (страница) рендерит ТОТ ЖЕ
  `InvestmentAgreementQuickForm`, а не дублирует поля. Если дублирует — извлечь
  единый `<InvestmentAgreementForm>` (или composable `useAgreementForm`) и
  переиспользовать в обоих. **Никаких двух копий логики договора.**
- Modify: `ProcurementCardFinancing.vue` — для PARTNERSHIP показывать секцию
  «Инвест-договор»: карточки выбора + кнопка «Создать новый» (открывает sheet с
  единым form-виджетом). Использовать `WorkspaceAgreementPickerSheet` для выбора.
- Modify: `ProcurementWorkspaceView.vue` — для PARTNERSHIP секция договора идёт
  ПЕРВОЙ (до поставщика), как этап 1. Для OWN_FUNDS не показывается.
- Карточка выбора договора: компактные базовые данные + тап раскрывает
  `InvestmentAgreementDetailSheet` (полный bottom-sheet, уже есть).

**Acceptance:** В партнёрском приходе первый шаг — выбор договора из списка или
создание нового через ту же форму, что и на странице создания договора. Правка
поля в форме появляется в обоих местах (страница + модалка).

---

## Phase 3 — Умные дефолты типа оплаты

**Решение:** До выбора поставщика — `PREPAID` по умолчанию (визуально активен).
После выбора поставщика — авто-переключение на `AT_RECEIPT` («По получению»),
ЕСЛИ пользователь не выбирал timing руками. После ручного выбора — не перетирать.

**Files:**
- Modify: `ProcurementCardSupplier.vue` — добавить локальный флаг
  `userPickedTiming` (ставится в `setTiming`). При первом появлении supplier и
  `!userPickedTiming` → emit `update-settlement {type:'AT_RECEIPT'}`. Если timing
  ещё не задан и нет supplier → отображать PREPAID как активный дефолт (можно
  отправлять PREPAID на создании terms, либо показывать как preselected).
- Логику дефолта держать в компоненте (UI-уровень), backend не меняем.

**Acceptance:** Новый приход без поставщика — PREPAID активен. Выбрал поставщика
(не трогая тип) — переключилось на «По получению». Выбрал руками PREPAID, потом
поставщика — остаётся PREPAID.

---

## Phase 4 — Товары: layout qty/price + скрыть fx

**Решение:** Количество и цена закупки в одной строке, пропорция 1:2. Поле курса
валют (fx_rate) скрыть везде на этой итерации (переключатель валюты работает, fx
дефолтный). Отдельная фича позже.

**Files:**
- Modify: `ProcurementItemEditSheet.vue` — «Количество» и «Цена закупки» в одну
  flex-строку (`grid-template-columns: 1fr 2fr` или flex 1:2). Скрыть блок
  `Курс USD/UZS` (`v-if="currency !== 'UZS'"` → удалить/закомментить рендер,
  но оставить `fxRateLocal` дефолтным значением, отправляемым в payload).
- Применить DESIGN.md токены (spacing, radius, tabular numbers на цене/кол-ве).

**Acceptance:** В sheet товара кол-во и цена рядом (1:2), на 375px помещаются.
Курс не отображается, при выборе USD товар сохраняется с дефолтным fx.

---

## Phase 5 — Расходы: OTHER в UI, без объединения, скрыть fx

**Решение:** `OTHER` («Прочее») доступен в селекторе типа. Несколько расходов
одного типа — отдельные строки, не схлопываются. fx скрыть.

**Files:**
- Modify: `ProcurementExpenseEditSheet.vue` — добавить `OTHER` в список типов,
  если отсутствует; скрыть fx input (как в Phase 4).
- Check: `ProcurementCardExpenses.vue` / `ProcurementExpenseRow.vue` — рендерит
  ли каждый расход отдельной строкой. Backend не объединяет; если frontend
  группирует по типу при отправке/отображении — убрать группировку, каждый
  расход = своя строка с своим id.
- Применить DESIGN.md токены.

**Acceptance:** Два расхода «Логистика» отображаются двумя отдельными строками.
`Прочее` выбирается. Курс не отображается.

---

## Phase 6 — Frontend: валютные итоги без авто-конверсии

**Решение:** Итоги товаров и расходов — в валюте(ах) операций, БЕЗ × fx в сумы.
Если одна валюта — одна сумма ($200). Если несколько — раздельно по валютам
($200 + 1 200 000 UZS). Backend уже в obligation currency; это чисто
презентационный слой (та же дисциплина, что в `DESIGN.md` Money display).

**Files:**
- Modify: `ProcurementCardItems.vue` — заменить `totalUzs` (× fx) на
  `totalsByCurrency: Record<string, number>` (группировка `qty×price` по
  `item.currency`, без fx). Рендер: одна строка если одна валюта, иначе список.
- Modify: `ProcurementCardExpenses.vue` — то же для `totalUzs` расходов.
- Money display: tabular numbers, валюта рядом с суммой (DESIGN.md).

**Acceptance:** 20 шт × $10 → итог «$200» (не сумы). Логистика $100 → итог
расходов «$100». Mixed валюты — раздельные суммы.

---

## Phase 7 — Оплата: валюта строго обязательства + конвертация + AT_RECEIPT UX

**Решение:** Оплата только в валюте обязательства. Касса другой валюты → блок +
кнопка «Конвертировать» (открывает существующий CurrencyExchange flow, после —
повтор payment). Backend-проверка уже есть (2fbb71b); добавить frontend-проверку
и inline-конвертацию. `AT_RECEIPT` «принять и оплатить» — разнести на понятные
шаги внутри `ReceiveBatchConfirmSheet` (приём → подтверждение количеств → оплата),
без смешения в одном плоском окне.

**Files:**
- Modify: `ProcurementCardPayment.vue` / `PaymentMakeSheet.vue` — при выборе
  кассы валюты ≠ obligation: показать предупреждение + кнопку «Конвертировать»
  (deep-link/sheet к CurrencyExchange с pre-fill: to_currency=obligation,
  amount=remaining). После успешной конвертации — retry payment dispatch.
  Валюту payment не давать менять руками (= obligation currency).
- Modify: `ReceiveBatchConfirmSheet.vue` — для AT_RECEIPT разнести на шаги
  (stepper или секции): 1) приёмка/расхождения, 2) оплата в валюте обязательства.
- Frontend currency check ДО dispatch (UX), backend остаётся источником правды.

**Acceptance:** Обязательство $200, касса в сумах → payment заблокирован,
предложена конвертация. После конвертации сум→$ → оплата проходит. AT_RECEIPT
проходит понятными шагами, не одним плоским окном.

---

## Phase 8 — Убрать sticky bottom action bar

**Решение:** Текущая глобальная `ProcurementBottomActionBar` (динамический CTA по
статусу) не несёт ценности и путает. Убрать. Primary action размещать контекстно
в карточке соответствующего этапа (оплата — в карточке оплаты, приёмка — в
карточке приёмки), где у действия есть ясный контекст.

**Files:**
- Modify: `ProcurementWorkspaceView.vue` — убрать рендер
  `<ProcurementBottomActionBar>` + связанный `handlePrimaryAction` если больше
  не нужен.
- Delete (или оставить unused): `ProcurementBottomActionBar.vue` — удалить если
  нигде больше не используется.
- Убедиться, что каждое ключевое действие доступно в своей карточке (оплата,
  приёмка, создание/выбор договора, амендмент через menu).

**Acceptance:** Sticky-кнопки внизу нет. Все действия доступны контекстно в
карточках. Ничего «потерянного».

---

## Phase 9 — Per-item row total + формат долей

**Решение:** Строка товара (`ProcurementItemRow`) и доли партнёров считаются/
отображаются неправильно. Привести к валютной дисциплине и формату.

**Files:**
- Modify: `ProcurementItemRow.vue` — per-item total = `qty × unit_purchase_price`
  в **валюте товара** (`item.currency`), БЕЗ × fx, с верной меткой. Сейчас:
  `qty×price×fx` с меткой UZS (рассинхрон: старые товары с fx=12100 дают
  «2 541 000 UZS», новые с fx=1 дают «222 UZS» — оба неверны). Tabular numbers.
- Fix формат долей в `ProcurementCardFinancing.vue` / agreement-карточках:
  `profit_share` / доля хранится как ratio (0.7) — отображать как `70%`
  (× 100, округление), а не сырое `1000000%`. Проверить источник значения
  (`profit_share` decimal vs planned_capital_share) и нормализовать рендер.

**Acceptance:** «21 шт × 10 USD = 210 USD» (валюта товара, без fx). Доля
«Устоз 70%», не «1000000%».

---

## Phase 10 — Валютная дисциплина (жёсткое правило) во всех денежных потоках

**Решение (окончательное, фиксируется в `docs/architecture.md`):** Реальное
движение денег — только в одной валюте на обе стороны (USD↔USD, UZS↔UZS).
Cross-currency перенос ЗАПРЕЩЁН напрямую; возможен только через explicit
`CurrencyExchange` (конвертация — отдельная осознанная операция). Авто-конвертация
по курсу допустима ТОЛЬКО в отчётах/аналитике (эквивалент для общей картины),
НИКОГДА при оплате/переводе/расходе. Итоги к оплате — раздельно по валютам.

**Files:**
- Audit backend money paths: `apps/partnerships/workspace.py`
  (`pay_workspace_costs`, `pay_workspace_supplier_payable`, partnership capital
  allocation), `apps/finance/services.py` (`record_generic_cash_payment`,
  `record_owner_drawing`, `record_cash_transfer`, `record_supplier_payment`).
  Везде, где деньги двигаются: проверка `source.currency == target.currency`,
  иначе ValueError с предложением конвертации. Никаких неявных `× fx` при
  списании/зачислении.
- Backend obligation total для партнёрского пути: посчитать раздельно по
  валютам (товары+расходы), без свёртки в UZS. Найти источник «2 541 332 USD»
  (#24) и убрать смешение `× fx` товаров с разным fx.
- Frontend: итоги к оплате — `Record<currency, amount>`, раздельный показ.
- Reports layer: авто-конвертация остаётся только тут (помеченная как
  «эквивалент по курсу X»), не трогаем — это легитимный единственный потребитель fx.

**Acceptance:** Нельзя оплатить USD-обязательство из UZS-кассы без конвертации.
Расходы $100 + 1 000 000 UZS показываются как два итога, не свёрнуты. Обязательство
#24 = корректные суммы по валютам, не «2 541 332 USD».

---

## Phase 11 — Оплата на карточке оплаты + частичная оплата (selection)

**Решение:** Оплата выполняется в карточке «Оплата» (не «см. Финансирование»).
Кнопка «Оплатить» / «Оплатить частично» → выбор: всё ИЛИ выбранные товары +
выбранные расходы. Суммы к оплате — раздельно по валютам. Источник средств в
валюте обязательства; если не хватает — кнопка конвертации (Phase 7).

**Files:**
- Modify: `ProcurementCardPayment.vue` — selection-режим: чекбоксы/выбор
  товаров и расходов для частичной оплаты; «Оплатить всё» / «Оплатить
  выбранное». Передавать `item_ids` / `expense_ids` в PAY_COSTS (backend уже
  принимает `item_ids`/`expense_ids` — см. `pay_workspace_costs`).
- Backend: убедиться, что `pay_workspace_costs` корректно платит за подвыборку
  и считает остаток по валютам.
- Убрать со страницы прихода текст «оплата через инвест-договор — см.
  финансирование»; платёж инициируется здесь.

**Acceptance:** Можно оплатить только выбранные товары; остаток пересчитывается.
Оплата не отправляет в раздел «Финансирование».

---

## Phase 12 — Партнёрское финансирование: упрощение + оплата из capital pool

**Решение:** Убрать ручное «Распределение капитала» (модалку с инпутами на
партнёра) с экрана прихода. Карточка «Финансирование» показывает только:
стоимость прихода (в валюте обязательства) и покрыта ли она капиталом договора.
Разнесение суммы по партнёрам — автоматическое по плановым долям договора.
Оплата партнёрского прихода идёт из capital pool договора (money discipline:
contribution → allocation → payment), инициируется на карточке оплаты (Phase 11).
Если в pool не хватает — одна кнопка «Запросить вклад инвестора».

**Files:**
- Modify: `ProcurementCardFinancing.vue` — убрать ручной distribution-modal
  (`WorkspaceInvestmentStartBlock` / allocation inputs). Оставить: выбор
  договора (Phase 2) + статус покрытия (стоимость vs доступный капитал) +
  «Запросить вклад инвестора» (когда не хватает).
- Backend: авто-allocation по плановым долям при оплате партнёрского прихода
  (переиспользовать `_pre_allocate_at_receipt_partnership_capital` логику /
  agreement allocation). Доли из `AgreementPartner.profit_share` /
  `planned_capital_share`. Σ shares = 1.0 (инвариант).
- Capital pool валюта: оплата из pool в валюте обязательства; если pool в другой
  валюте — конвертация (Phase 10 правило).
- Удалить/спрятать `onSaveAllocations` ручной путь, если он только для модалки.

**Acceptance:** На экране партнёрского прихода нет ручных инпутов капитала по
партнёрам. Видна стоимость + покрытие. Оплата списывает из pool по долям
автоматически. Доли не редактируются здесь (только в договоре).

---

## Phase 13 — Split на списке товаров + receive-after-pay для PREPAID

**Решение:** Кнопка «Разделить» рядом с удалением товара (split партии на
позиции). Backend `SPLIT_ITEM` уже есть. Для PREPAID: приёмке (receive)
подлежат только оплаченные позиции — нельзя оприходовать неоплаченное.

**Files:**
- Modify: `ProcurementItemRow.vue` / `ProcurementCardItems.vue` — добавить
  действие «Разделить» (рядом с корзиной), открывает sheet ввода количества
  для отделения; dispatch `SPLIT_ITEM` ({item_id, quantity}). Доступно в OPEN
  для DRAFT/READY items.
- Modify: `ProcurementCardReceive.vue` / `ReceiveBatchConfirmSheet.vue` — для
  PREPAID показывать к приёмке только оплаченные позиции (lifecycle
  READY_FOR_RECEIVE после оплаты); неоплаченные недоступны с пояснением.
- Backend: проверить, что receive для PREPAID отклоняет неоплаченные позиции
  (`_check_prepaid_coverage` уже частично это делает — расширить на per-item
  при частичной оплате).

**Acceptance:** Товар 100 шт делится на 50+50 (две строки). При PREPAID нельзя
принять неоплаченную позицию; оплаченные принимаются.

---

## Сквозное: применить дизайн-систему

Все изменённые UI-компоненты привести к `DESIGN.md`: зелёный primary через
токены, tabular numbers на всех суммах/количествах, calm motion (ease-out
150–300ms), без hero-metric/identical-card-grid/gradient-text. Использовать
`impeccable` (`craft`/`polish`) при работе над каждой карточкой. Дизайн-токены —
CSS custom properties, чтобы смена primary была одной правкой.

## Verification (перед claim «готово»)

- Backend: `DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m
  pytest apps/core/tests/ -q` — зелёное (185+ tests). Особенно
  `test_procurement_currency.py`, `test_e09_*`, `test_e08_sharia_invariants.py`.
- Frontend: `npx vue-tsc --noEmit` без новых ошибок.
- Ручной smoke по каждому acceptance выше.
- superpowers:verification-before-completion перед коммитом.
