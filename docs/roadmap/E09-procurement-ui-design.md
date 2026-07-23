# E09 — Procurement UI Design (vacuum brainstorm output)

**Дата:** 2026-05-20
**Контекст:** vacuum-сессия по UI после reset процкуремент-фронтенда.
**Статус:** working document для следующих шагов (Step 4 action flow,
Step 5 conditional matrix, далее execution plan).

> Этот документ — закрепление решений, принятых в ходе брейншторма
> Steps 1-3 (mental model, композиция, информационная архитектура).
> Это **не план реализации** — план составляется отдельно после Steps
> 4-5. Это **архитектурный anchor** для UI работы.

---

## Mental model — кто, когда, как

**Пользователь:** собственник SMB / управляющий / отдельный
«закупщик-снабженец-кладовщик» / бухгалтер. **Один экран на всех ролей**
(role-based UI не делаем сейчас). Плотный интерфейс, но с
разворачиваемыми подсказками для нового пользователя.

**Контекст входа:** Excel / телеграм-чат / бумажная накладная / товар у
дверей / план будущей закупки. Сценарии разнятся от «оформляю по факту»
до «многомесячный цикл с зарубежом».

**Поведенческая реалия:** Excel — текущий de-facto для партнёрского
прихода с зарубежа. Наш UI должен быть **быстрее Excel** иначе люди не
переключатся. На первых этапах большая часть пользователей будет
использовать систему как **систему учёта (after-fact entry)**, не как
operational tool. Наш стратегический dft — **operational by default**,
с поддержкой accounting-mode как обходной путь.

**Основная боль:** люди не вводят данные потому что **не видят
ценности** (рисуют «миллион штук», ругают свою же отчётность). UI value
emerges from workflow guidance (cash-flow indicator, payment deadlines,
margin signals) — это и есть наше отличие от Excel.

**Принцип:** фреймворк, не библиотека. Гибкие функциональные
возможности + направляющий workflow. Не «всё можно», но и не жёсткие
рельсы.

## Композиция (Step 2) — один компонент, conditional секции

**Settled**: единый `ProcurementWorkspace` компонент с conditional
секциями вместо двух раздельных flow.

Аргументы:
- Общие сущности (поставщик, товары, расходы, приём, история)
  доминируют над уникальными (агреемент, capital allocation —
  только PARTNERSHIP).
- Переключение OWN_FUNDS ↔ PARTNERSHIP в DRAFT — toggle, не пересоздание.
- Mobile-first выигрывает от единой ментальной модели.
- Backend payload уже отдаёт `policy.visible_sections`, `flow.steps`,
  `policy.allowed_actions` — frontend читает и рендерит условно.

Визуальное разделение partnership vs own-funds — на уровне иерархии и
шапки, не компонентов.

## Информационная архитектура (Step 3) — карточки

**Header (sticky)**: Procurement #ID + status badge + краткое summary
(supplier / сумма / timing). Action menu (⋯): amend / cancel /
attachments.

**Body — карточки в порядке «что делать дальше»**:

1. **Поставщик и тип оплаты** — supplier picker + general payment_timing
   chips + (при PARTNERSHIP) агреемент-привязка. Top-карточка
   определяет shape остального экрана.
2. **Товары** — line items с swipe edit/delete/split. FAB «+» для
   добавления (catalog picker / quick-create / barcode scan future).
3. **Расходы** — пусто по умолчанию (свёрнуто). Кнопка «добавить
   расход». Allocation per item / by value / by qty (как в старой
   версии).
4. **Финансирование** — *только при PARTNERSHIP*. Capital allocation,
   доли участников, ссылка на агреемент.
5. **Оплата и обязательства** — содержание зависит от timing:
   - PREPAID: «оплатить сейчас», после оплаты — фиксация
   - PARTIAL: upfront amount + payable preview
   - DEFERRED: payable + deadline picker
   - INSTALLMENT: schedule builder + payable с N due dates
   - ON_SALE: placeholder «формируется при продажах»
6. **Приём** — список receive batches. Каждый — per-line `planned vs
   received` + reason codes для расхождений. Кнопка «новая приёмка»
   пока не всё получено.
7. **История и документы** — события timeline + attachments. Свёрнуто
   по умолчанию.

**Bottom action bar (sticky)**: один primary action,
динамически меняется по состоянию («сохранить черновик» / «подтвердить»
/ «оплатить» / «принять» / «закрыть приход»).

## Калки (зафиксированные решения)

### Архитектурные

- **Per-item payment НЕ нужен.** Один primary Payment per procurement
  (по timing-у). «Частичные оплаты» — это PARTIAL terms, не дробление
  PREPAID на штучные платежи.
- **Двойная связь товар↔поставщик**: прямая (ProductSupplierLink, для
  picker filtering) + через procurement (ProcurementItem → Procurement
  → Supplier, для аналитики). Обе работают, оба слоя нужны.
- **Поставщик опционален для PREPAID**, обязателен для
  PARTIAL/DEFERRED/INSTALLMENT/CONSIGNMENT. Уже зашит в
  `SUPPLIER_REQUIRED_SETTLEMENTS`.
- **Авто-suggest поставщика** по истории товаров в корзине. Принимает/
  отклоняет пользователь.

### UX

- **Терms split**: general timing (PREPAID/PARTIAL/AT_RECEIPT/etc.) — в
  top-карточке «Поставщик+оплата». Детали (deadline, schedule) — в
  карточке «Оплата».
- **Multi-payment per procurement разрешён** (revision 2026-05-20).
  Блокирует редактирование items не первый payment, а `confirm`. После
  confirm — accumulating payments + multiple ReceiveBatches.
- **AT_RECEIPT — combined action** (новое 2026-05-20). Payment-карточка
  скрыта; в карточке «Приём» primary action = «Принять и оплатить»,
  одной транзакцией создаёт ReceiveBatch + Payment + Snapshot.
- **Amendment с before/after**, hard cancel только в DRAFT.
- **Discrepancy at receive**: per-line `qty_planned` vs `qty_received`
  + reason code (`damaged` / `missing_expected_later` / `quality_reject`
  / `accept_as_shortfall`). Дефолт `missing_expected_later`.
- **Attachments**: generic `Attachment` модель (один раз делаем — везде
  работает). В MVP — на Procurement и ReceiveBatch.
- **Receive shortage**: 4 сценария покрываются 4 reason codes; «supplier
  credit на следующую поставку» — после MVP.
- **Operational by default, accounting accepted**: дефолтный flow
  guided, но procurement list имеет entry-point «завести по факту»
  (pre-filled wizard).

### Quick-create товара

Минимум полей: name + category + unit. Selling price НЕ обязателен.
После receive — модалка «товар поступил по cost X, установи retail
price» (для quick-created без цены) или опциональная подсказка о
пересмотре цены (для существующих с изменившейся себестоимостью).

## Conditional UI matrix (full, 8 legal combinations)

### По оси `payment_timing`

| Timing | Items (после confirm) | Payment секция | Receive |
|---|---|---|---|
| **PREPAID** | amendments only | Multi-payment, primary = «оплатить остаток» | Доступен только когда `Σ payments ≥ Σ cost of items being received` |
| **AT_RECEIPT** | amendments only | **СКРЫТА** (объединена с Receive) | Combined action «Принять и оплатить» — одной транзакцией ReceiveBatch + Payment |
| **PARTIAL** | amendments only | Upfront amount + payable на остаток + multi-payment | Available в любой момент |
| **DEFERRED** | amendments only | Payable + deadline picker + multi-payment к payable | Available раньше платежей |
| **INSTALLMENT** | amendments only | Schedule builder + payable с N due dates + multi-payment | Available раньше платежей |
| **ON_SALE** | amendments only | **СКРЫТА** (накопительные obligations через продажи) | Создаёт CONSIGNED stock; payable per-sale |

### По оси `funding_source`

**OWN_FUNDS**:
- Карточка «Финансирование» скрыта целиком
- Header нейтральный
- Payment source = `CashAccount`

**PARTNERSHIP**:
- Карточка «Финансирование» появляется между «Расходы» и «Оплата»
  - Capital allocation: planned shares + edit для actual
  - Список AgreementContributions/Allocations для контекста
- Header подсвечивает «Партнёрский приход — Договор #N — Инвестор: X»
- Confirm требует привязки к `InvestmentAgreement`
- Payment source = `CapitalPool` (через `AgreementAllocation`)

### По оси `goods_ownership`

**OWNED**: дефолт. Стандартный inventory journal при receive.

**CONSIGNED**:
- Header помечает «Товар на реализации»
- Карточка «Расходы» **disabled** (landed expenses запрещены для CONSIGNED — guard на бэке)
- Receive создаёт Lots с `is_owned=False`
- Inventory journal при receive подавлен (нет 1100 debit)
- Карточка «Оплата» в этой комбинации не используется напрямую — payable
  накапливается через продажи (см. ON_SALE строку)

### 8 легальных комбинаций (cross-product)

| # | Funding | Timing | Ownership | UX-следствие |
|---|---|---|---|---|
| 1 | OWN_FUNDS | PREPAID | OWNED | Стандартный «оплатил → получил» |
| 2 | OWN_FUNDS | **AT_RECEIPT** | OWNED | **Combined «принять и оплатить»** |
| 3 | OWN_FUNDS | PARTIAL | OWNED | Upfront + payable |
| 4 | OWN_FUNDS | DEFERRED | OWNED | Получил → плати к deadline |
| 5 | OWN_FUNDS | INSTALLMENT | OWNED | Получил → плати по графику |
| 6 | OWN_FUNDS | ON_SALE | CONSIGNED | Консигнация |
| 7 | PARTNERSHIP | PREPAID | OWNED | Инвестор оплатил, потом получили |
| 8 | PARTNERSHIP | **AT_RECEIPT** | OWNED | **Инвестор: combined принять+оплатить** |

Все остальные точки (28 из 36) — blocked `validate_procurement_combination`.

## Два UX-пути для одного procurement (Multi-payment scenario)

Один и тот же экран поддерживает оба пути, пользователь выбирает естественно:

**Путь A — «DRAFT весь период»** (для коротких циклов и неуверенности):
- Procurement сидит в DRAFT в течение всей закупочной активности
- Items / expenses свободно правятся, ничего не блокируется
- Когда готов — confirm + payment + receive в одной сессии
- Простой mental model, рекомендуется для одно-визитных закупок

**Путь B — «Confirm в начале, накопительная активность»** (для долгих циклов, партнёрских):
- Procurement создаётся, подтверждается early (фиксирует поставщика, агреемент, timing)
- Дальше накопительно:
  - Payments по мере фактических трат (multiple Payment-events)
  - Amendments к items при необходимости (с записью before/after)
  - Multiple ReceiveBatches по мере прибытия товара
- Инвестор видит активность real-time
- Рекомендуется для китайских поездок, многонедельных закупок

UX не форсит выбор. Карточки «Оплата» и «Приём» естественно показывают
multi-payment / multi-batch view когда нужно (если есть >1 событие).

## Правила blocking (обновлено 2026-05-20)

Что блокирует редактирование структуры procurement:

1. **DRAFT → OPEN (confirm)**: блокирует items/expenses от silent edit.
   После — только amendments с before/after.
2. **Первый ReceiveBatch**: окончательно фиксирует Lot-snapshot для уже
   принятых строк. Амендменты возможны только для НЕпринятых строк.
3. **CLOSED**: всё заморожено, никаких изменений.

Что НЕ блокирует (revision 2026-05-20):
- Первый Payment **больше не блокирует items**. Multi-payment-flow
  легитимен.
- Может быть несколько ReceiveBatches с разными snapshots.

### Особые правила по timing для receive

- **PREPAID** + receive: разрешён только когда `Σ Payments ≥ Σ cost of items
  being received in this batch`. То есть можно частично принять, если частично
  оплачено.
- **AT_RECEIPT** + receive: ReceiveBatch и Payment создаются атомарно одной
  транзакцией. Decouple запрещён.
- **DEFERRED / INSTALLMENT / PARTIAL** + receive: разрешён в любой момент
  после confirm, payments могут быть до и после.
- **ON_SALE** + receive: создаёт CONSIGNED stock без payable; обязательства
  накапливаются через продажи (E09 Phase 2).

## MVP scope reminder (из E09 эпика)

В MVP попадает (зафиксировано 2026-05-19):
- Per-item ownership (architectural shift)
- Amendment items/expenses mid-receive
- Reverse receive batch
- Cancel procurement rule (only в DRAFT or before any Payment/Receive)
- Discrepancy reason codes
- Document attachments (минимум на ReceiveBatch)

После MVP:
- Returnability (E09 Phase 3)
- Cash-flow inline (идёт с E03)
- Templates / clone
- Multi-editor conflict protection
- Excel import
- Desktop variant (отдельный design-build cycle)

## Что НЕ делаем сейчас и почему

- **Recurring procurement** (auto-create monthly) — после MVP.
- **QC gate** (pending → live) — после MVP.
- **Approval workflow** (manager approves before payment > X) —
  role-based, отложено до появления ролей.
- **Tax line** (НДС/VAT) — рассмотреть в следующем major workstream.
- **PO numbers / external supplier reference IDs** — после MVP.

## Следующие шаги

- **Step 4 — Action flow**: linear stages с lock-ами или free-form
  карточки + readiness индикаторы? Гипотеза — free-form карточки +
  bottom action bar с primary действием, обсуждение в следующем
  раунде.
- **Step 5 — Conditional UI matrix полная**: для всех 6 легальных
  комбинаций (funding × timing × ownership) — какие секции
  видимы/обязательны/заблокированы.
- **Затем** — execution plan для Codex/Sonnet с slice-разбивкой и
  per-slice контрактами.
