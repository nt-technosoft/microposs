# Money Architecture — Vacuum Audit (partnerships)

> **Тип документа:** независимый архитектурный аудит денежной модели + вакуум-проектирование.
> **Режим:** анализ и дизайн. Кода не писалось.
> **Дата:** 2026-06-15.
> **Скоуп:** `backend/apps/partnerships/` (advances, venture, agreement_services,
> workspace, workspace_support, models, serializers), `apps/sales/services.py`,
> `apps/finance/` (journals/cash). Гипотезы проверены построчно по коду, не на слово.
> **Статус:** зафиксированный результат аудита для передачи на ревью/аудиторскую
> сессию. Решение о включении в работу (эпик) — **не принято**, выносится отдельно.

Документ самодостаточен и читается без сессии-чата. Привязки `file:line` даны для
трассируемости (актуальны на дату аудита; при последующих правках сверять).

---

## Оглавление

- [A. Карта текущей money-архитектуры](#a-карта-текущей-money-архитектуры)
- [B. Реестр шрамов, дублей и несогласованностей](#b-реестр-шрамов-дублей-и-несогласованностей)
- [C. Вакуум-идеал money-модели](#c-вакуум-идеал-money-модели)
- [D. Наложение идеала на текущее + доказательство эквивалентности](#d-наложение-идеала-на-текущее--доказательство-эквивалентности)
- [E. Фазовый план имплементации](#e-фазовый-план-имплементации)
- [F. За пределами денег: структура, поддерживаемость, оптимизации, тест-режим](#f-за-пределами-денег-структура-поддерживаемость-оптимизации-тест-режим)
- [Резюме](#резюме)

---

# A. Карта текущей money-архитектуры

## A.0 Один абзац сверху

Партнёрские деньги физически живут в **finance** (`CashAccount`/`CashEntry`/`Payment`/`JournalEntry`),
а их **доменный смысл** разбросан по **~10 партнёрским таблицам** в `partnerships`.
Ни одной материализованной партнёрской позиции нет: **каждая** цифра
«available / free / owed / profit / negative» **передеривается заново** из всех
событий на каждый запрос, в **трёх разных узлах** с **тремя разными базисами** и
**двумя единицами измерения** (валюта договора vs функциональный UZS). Сцепка между
узлами держится на **пост-фактум дискриминаторах** (по какому `CashEntry.account`
ушёл `AgreementWithdrawal`) — это и есть «шрам-tissue».

## A.1 Где физически хранятся денежные факты (fact stores)

### Капитальный слой (договор/пул)

| Таблица | Какой факт | Единица | Append-only | Кто пишет |
|---|---|---|---|---|
| `AgreementContribution` | взнос партнёра в пул | валюта договора | да (delete→reversal) | `add_agreement_contribution` (workspace_support.py:198) |
| `AgreementWithdrawal` | возврат партнёру **(перегружен: пуловый ИЛИ recovered-возврат из операционки)** | валюта договора | да | `add_agreement_withdrawal` (workspace_support.py:332) |
| `AgreementAllocation` (TO/FROM_PROCUREMENT) | перемещение капитала договор↔приход | валюта | да | `_pre_allocate_at_receipt_partnership_capital` (workspace.py:3799), `allocate_workspace_capital` (workspace.py:1434) |
| `ProcurementReceiveBatchCapitalAllocation` | доли капитала на батч приёмки (**базис «deployed»**) | доля + сумма | да (immutable batch) | receive-flow |

### Венчурный/прибыльный слой (приход)

| Таблица | Какой факт | Единица | Кто пишет |
|---|---|---|---|
| `ProcurementSaleRealization` | per-slice реализация: recovered / profit / loss / fx | native + UZS | `record_sale_line_realization` (venture.py:387) + return/loss варианты |
| `ProcurementVentureSettlement` | снимок-снапшот позиций+totals (JSON) | UZS | `create_venture_settlement` (venture.py:829) |
| `ProcurementPartnerVentureDebtRepayment` | погашение отрицательной позиции, разложение по waterfall | native + UZS | `repay_partner_venture_debt` (venture.py:1227) |
| `PartnerLedgerEntry` | **только** CAPITAL_IN/OUT + DIVIDEND_PAID (профит-триада ретайрнута в E17 T-1.6) | native + UZS | `append_ledger_entry` (agreement_services.py:116) |
| `DividendPayment` | фактическая выплата дивиденда | native | `pay_dividend` (agreement_services.py:222) |
| `ProcurementPartnerLedger` | контейнер леджера (procurement×partner) | — | `get_or_create_ledger` |

### Аудит + физика денег

| Таблица | Факт |
|---|---|
| `AgreementEvent` | append-only аудит workflow/денег |
| finance `CashEntry` | физическое движение по `CashAccount` (пул `kind=AGREEMENT_CAPITAL` / операционка) |
| finance `Payment` (`source_type=CAPITAL_POOL`, `target=PROCUREMENT_COST`) | оплата приёмки из пула |
| finance `JournalEntry` | GL-проводки (всегда UZS) |
| `AgreementCurrencyPool` / `CurrencyConversionLot` | мультивалютные суб-пулы + FIFO cost-basis конвертации |

**Мёртвый факт-стор:** `CapitalAdvanceSettlement` — `.objects.create` **не вызывается
нигде** (E17 ретайрнул сущность `CapitalAdvance`), но модель и её `Source`-enum живут,
и enum используется как параметр в `settle_partner_capital` (advances.py:72). Классический
недочищенный шрам.

## A.2 Где считаются позиции (LIVE-передеривание, ноль материализации)

Три **параллельных** узла, каждый со своим базисом:

**1. `partner_capital_positions(agreement)`** — `advances.py:186`. Пуловый уровень.
- `deployed` = Σ(доля капитала × required) по `ReceiveBatchCapitalAllocation`
- `paid_in` = Σ contributions − Σ **POOL**-withdrawals
- `net = deployed − paid_in` → `owed`(net>0) / `withdrawable`(net<0, ограничен `pool_free`)
- **Плюс** в ту же строку подмешивает все венчурные баки (вызывает узел №2 на каждый procurement).
- Единица native-ноги: **валюта договора**; венчурные баки: **UZS**. Явный комментарий «never sum the two» (advances.py:290‑296).

**2. `procurement_venture_positions(procurement)`** — `venture.py:659`. Венчурный уровень. Самый тяжёлый узел.
- `deployed_uzs` из батчей; recovered/profit/loss из `ProcurementSaleRealization` +
  **переопределяется** нетто-энтайтлментами (`_net_profit_entitlements` venture.py:161,
  при settlement — `_net_capital_loss_entitlements` venture.py:233,
  `_liability_capital_recovery_entitlements` venture.py:312); `capital_returned` =
  PLR.CAPITAL_OUT + `AgreementWithdrawal`; `dividends` = PLR.DIVIDEND_PAID; минус repayments.
- Выдаёт `capital_return_available_uzs`, `provisional_profit_available_uzs`, и компонентный
  `negative_position_uzs` (liability/capital/dividend).
- Профит «доступен» только после settlement (до него `provisional_profit_available_uzs=0`).

**3. `_agreement_available_by_partner(agreement)`** — `workspace.py:4370`. **Третий** базис «available».
- = Σ contributions − Σ withdrawals − Σ allocations (TO=−, FROM=+), per currency.
- Игнорирует deployment/realization вообще. Это «сколько у партнёра свободно в договоре по
  движению `AgreementAllocation`» — параллельная истина к №1, на другом наборе фактов.

Вспомогательные деривации поверх этих трёх: `undistributed_profit_uzs` (advances.py:53),
`_venture_partner_profit` (agreement_services.py:75), `get_partner_aggregate`
(agreement_services.py:144, **перетирает** профит-поля из узла №2),
`_remaining_inventory_capital_entitlements` (venture.py:349, по `LotStock`).

> Единственная «материализация» — `ProcurementVentureSettlement.partner_positions` (JSON).
> Но это **исторический снимок на момент settlement**, не CQRS read-side: текущие чтения его
> не используют, они зовут узел №2 заново.

## A.3 Conservation & reconciliation

- **`venture_conservation(procurement)`** — `venture.py:988`. Три кармана
  (CAPITAL / PROCEEDS / DISTRIBUTION) × валюта, каждый обязан независимо неттиться к ~0.
  Строится **только из append-only фактов**, заново, на каждый вызов. Используется как
  safety-gate в `create_venture_settlement(FINAL)` (venture.py:858‑870) и в close.
  `ConservationReport` умеет `merge` (агрегация по договору).
- **`agreement_pool_reconciliation_residual(agreement)`** — `agreement_services.py:386`.
  **Отдельный** инвариант: `pool.balance == Σcontrib − Σpool-payments − Σpool-returns`.
  Снова дискриминирует withdrawals по `CashEntry.account == pool`.

Две независимых системы доказательства целостности на разных слоях, не сшитые в один инвариант.

## A.4 Close / lifecycle

Два параллельных лестничных гейта:
- **Venture:** `procurement_close_blocking_reasons` (venture.py:1114) → `procurement_close_state`
  (venture.py:1156) → `close_procurement_venture` (venture.py:1185). Гейты: FINAL settlement;
  нет активных лотов; нет negative positions; нет «висящих» available капитала/прибыли;
  conservation=0.
- **Agreement:** `agreement_close_blocking_reasons` (agreement_services.py:433) →
  `agreement_close_state` (agreement_services.py:485) → `close_investment_agreement`
  (agreement_services.py:511). Гейты: все приходы CLOSED; все `net≈0`; pool reconciled;
  merged conservation=0.
- Read-only локи: `assert_procurement_open` (venture.py:1217) / `assert_agreement_open`
  (agreement_services.py:540).

## A.5 Слой проводок (finance) — единая физика

`create_cash_entry` (finance/services.py:1059), `create_journal_entry` (finance/services.py:43),
`record_journal_from_cash_entry` (finance/services.py:1099), `record_capital_pool_contribution`
(finance/services.py:596, внешний→`DR 1300 / CR equity 3100/3110/3000`),
`record_capital_pool_payment` (finance/services.py:783, `DR 1100 / CR 1300`).

Это **единственный** по-настоящему консолидированный слой — вся доменная разрозненность
сверху сходится сюда. Эквити распознаётся при contribution, на receive не пере-кредитуется
(Rule #13). GL всегда UZS.

## A.6 Поток фактов (как они рождаются)

```
contribution → record_capital_pool_contribution → пул(1300)↑
   receive → _fund_partnership_receive_from_pools → Payment(CAPITAL_POOL) → DR1100/CR1300
           → ReceiveBatchCapitalAllocation (базис deployed)
   sale POST → record_sale_line_realization → ProcurementSaleRealization (recovered/profit/loss)
   return/writeoff → REVERSAL/LOSS realization rows
   settlement → create_venture_settlement (conservation-gate на FINAL) → snapshot JSON
   dividend → pay_dividend → DividendPayment + PLR.DIVIDEND_PAID + DR3200/CR cash
   capital return → add_agreement_withdrawal (пул ИЛИ операционка — развилка по account)
   negative pos → repay_partner_venture_debt → waterfall(liability/capital/dividend)
   close → venture gate → agreement gate
```

Хук реализации продаж: `apps/sales/services.py:420` (`record_sale_line_realization` на POST продажи);
возвраты — `record_sale_line_return_realization` (sales/services.py:1162, 1192); списания —
`record_lot_loss_realization`.

## A.7 Единицы (критичный источник багов)

Три шкалы сосуществуют в одних и тех же словарях позиций:
1. **Валюта договора** — `deployed/paid_in/net/owed/withdrawable` (пул).
2. **Функциональный UZS** — все венчурные `_uzs`-баки.
3. **GL UZS** — проводки.

Защита от смешения — **соглашение об именах** (`_uzs`-суффикс) и комментарии, а не тип.
Это договорённость, а не инвариант.

## A.8 Вывод по A (тезисно)

- Не «два», а **~10 партнёрских fact-store** + 4 finance-таблицы; смысл денег размазан,
  физика — консолидирована.
- **Три** параллельных узла позиций на **трёх** базисах (`ReceiveBatchCapitalAllocation`
  vs realization-события vs `AgreementAllocation`).
- Сшивка слоёв — на **пост-фактум дискриминаторе** `CashEntry.account` (пул/операционка)
  минимум в 3 местах (`partner_capital_positions`, `agreement_pool_reconciliation_residual`,
  withdrawal-flow). Это прямой механизм S1/S4-багов.
- Всё **LIVE**, материализованного read-side нет; единственный снимок
  (`ProcurementVentureSettlement.partner_positions`) не переиспользуется в чтениях.
- Уже есть мёртвый шрам (`CapitalAdvanceSettlement`) и синтетические сверочные хаки
  (FROM_PROFIT пишет DIVIDEND_PAID + фейковый contribution row, чтобы derived-баланс
  сошёлся — `advances.py:175‑183`).

Гипотезы аудита 1–5 **подтверждаю** по коду (с уточнением: п.1 — профит-триада уже ушла из
`PartnerLedgerEntry`, так что дублирование сейчас не «профит в двух таблицах», а
«капитал/прибыль/долг размазаны по ~10 таблицам и 3 узлам»).

---

# B. Реестр шрамов, дублей и несогласованностей

## B.1 Подтверждение гипотез аудита 1–5

| # | Гипотеза | Вердикт | Доказательство по коду |
|---|---|---|---|
| 1 | Два money-факт-стора (PLR + PSR) | **Подтверждено, хуже заявленного** | Не 2, а ~10 партнёрских стора. Профит-триада из `PartnerLedgerEntry` уже ретайрнута (E17 T-1.6, `get_partner_aggregate` док), так что дублирование сместилось: PLR держит CAPITAL_IN/OUT+DIVIDEND, PSR — recovered/profit/loss, плюс Contribution/Withdrawal/Allocation/ReceiveBatchCapitalAllocation как **четвёртый** капитальный набор |
| 2 | Две модели позиции, дискриминатор по счёту | **Подтверждено** | `partner_capital_positions` (advances.py:186) vs `procurement_venture_positions` (venture.py:659); сшивка — `pool_withdrawal_ids` через `CashEntry.account_id==pool` (advances.py:241‑252) |
| 3 | `AgreementWithdrawal` перегружен | **Подтверждено** | Один тип несёт и пуловый возврат, и recovered-из-операционки; различие — пост-фактум по `CashEntry.account` в **трёх** местах (advances.py:241, agreement_services.py:416, withdrawal-flow workspace_support.py:393) |
| 4 | Live-передеривание, нет проекций | **Подтверждено** | Каждый запрос заново фолдит все события; единственный снимок `ProcurementVentureSettlement.partner_positions` (JSON) в чтениях не используется |
| 5 | S1/S4-баги из множественности источников | **Подтверждено документально** | Фикс-комментарий advances.py:229‑235 прямо описывает double-count recovered-возврата из-за неоднозначности источника withdrawal — это и есть механизм бага |

## B.2 Новые находки (которых в гипотезах не было)

**B.2.1 — Третий, независимый узел «available».** `_agreement_available_by_partner`
(workspace.py:4370) считает доступное как `Σcontrib − Σwithdrawals − Σallocations` на базисе
`AgreementAllocation`, игнорируя deployment/realization. Это **третий** ответ на «сколько у
партнёра свободно», на наборе фактов, отличном и от пула (№1), и от венчура (№2). Три узла
могут разойтись — и никто этого не заметит, потому что нет инварианта, сшивающего их.

**B.2.2 — `AgreementAllocation` как параллельная бухгалтерия deployment.** Капитал,
заведённый в приход, фиксируется **дважды**: как `AgreementAllocation(TO_PROCUREMENT)`
(workspace.py:3858) **и** как `ReceiveBatchCapitalAllocation` (базис `deployed` в обоих узлах
позиций). Две таблицы про один экономический факт «капитал ушёл в инвентарь», с риском рассинхрона.

**B.2.3 — Синтетический сверочный хак в FROM_PROFIT.** `_settle_partner_from_profit`
(advances.py:131‑183), чтобы derived-баланс «сошёлся», пишет:
- `PartnerLedgerEntry.DIVIDEND_PAID` (хотя дивиденд не платился),
- `AgreementContribution` (хотя взноса не было — `notes='Погашение… из прибыли'`).

То есть в историю взносов и выплат попадают **события, которых не происходило**, ради того
чтобы две производные сошлись. Это прямое нарушение «append-only = факты, а не подгонка».
В вакууме это **одно** событие `PROFIT_TO_CAPITAL`.

**B.2.4 — Frankenstein-чтение `get_partner_aggregate`.** Берёт capital/dividend из леджера,
но `profit_accrued/losses/pending` **перетирает** из венчура (agreement_services.py:191‑194).
Один read смешивает два источника истины — у вызывающего нет способа узнать, что половина
словаря из одной таблицы, половина из другой.

**B.2.5 — Дубли инфраструктуры (низкий риск, но индикатор):**
- `money/_money/_q/_ratio/functional_uzs` определены **в 5 файлах** (formulas.py:15,
  venture.py:32, serializers.py:35, workspace_support.py:42, agreement_services.py:21).
- `_equity_account_code` (advances.py:37) — по собственному докстрингу «mirror of
  `_capital_equity_account_code`» (workspace_support.py:85). Две копии role→COA маппинга денег.
- Operator-residue паттерн (распределить остаток округления оператору) скопирован в **4**
  энтайтлмент-хелперах (`_net_profit`, `_net_capital_loss`, `_liability_capital_recovery`,
  `_remaining_inventory`). Любая правка sharia-residue-правила должна синхронно лечь в 4 места.

**B.2.6 — Мёртвый шрам.** `CapitalAdvanceSettlement` — модель жива, `.objects.create` не
вызывается; используется только её `Source`-enum как параметр. Недочищенный остаток ретайра
`CapitalAdvance`.

**B.2.7 — ε-толеранс на инварианте сохранения.** `venture_conservation` допускает `_EPS=0.01`
(venture.py:920). Для функционального UZS остаток обязан быть **точным нулём** (Decimal), ε
нужен только для native-ноги из-за FX-деления. Толеранс, применённый ко всем карманам
единообразно, — это место, где реальная утечка может спрятаться под «допустимое округление».

**B.2.8 — Lazy-import как симптом цикла зависимостей.** Десятки `from .venture import …` /
`from .advances import …` **внутри функций** (advances.py, agreement_services.py, venture.py) —
обход циклических импортов. Это сигнал: слои `advances ↔ venture ↔ workspace ↔
agreement_services` переплетены, нет однонаправленной зависимости. Архитектурный, не
косметический долг.

**B.2.9 — God-модули.** `workspace.py` — 4406 строк, `models.py` — 1891, `venture.py` — 1360.
`workspace.py` смешивает funding, allocation, payment, receive, capital snapshot, preview,
policy.

## B.3 Корневая причина (одним предложением)

Все 9 находок — следствия **одного** дефекта: **денежные события не двусторонние (не
double-entry по карманам), а денормализованные per-partner строки в десятке таблиц разной
гранулярности**, поэтому сохранение приходится *проверять* постфактум, позиции —
*передеривать* из нескольких источников, а источники — *сшивать* эвристиками по GL-счёту.

---

# C. Вакуум-идеал money-модели

> Спроектировано с нуля, имея весь нынешний контекст. Без оглядки на текущие таблицы.

## C.1 Главный принцип: партнёрские деньги — это размерный суб-леджер GL, а не набор доменных таблиц

Сейчас домен построен как таблицы, *приклеенные* к GL. Правильно — наоборот: **один
append-only партнёрский журнал, где каждое экономическое событие двусторонне по «карманам»**,
ровно как `JournalLine` двусторонни по счетам. Тогда:
- **сохранение денег становится структурным**, а не проверяемым: если каждое событие постит
  сбалансированные ноги-карманы, деньги физически не могут утечь;
- **позиция — это GROUP BY**, а не бесшовная переплётенная деривация из 3 узлов;
- **«дискриминатор по счёту» исчезает**: тип события явный.

## C.2 Карманы (pockets) — топология денег венчура

Четыре кармана, между которыми движутся деньги. Каждое событие = перевод между двумя (double-entry):

```
  POOL (капитал-пул, валюта договора)
    └─ contribution → POOL↑ ;  deploy → POOL↓ INVENTORY↑ ;  pool-return → POOL↓
  INVENTORY (развёрнутый капитал в товаре)
    └─ deploy → INVENTORY↑ ;  recover → INVENTORY↓ PROCEEDS↑ ;  loss → INVENTORY↓
  PROCEEDS (выручка/операционный кэш венчура)
    └─ recover/profit → PROCEEDS↑ ;  dividend/proceeds-return → PROCEEDS↓ ;  debt-repay → PROCEEDS↑
  CLAIM (нетто-требование партнёра — остаточный карман)
```

Сохранение: `Σ ног по каждому карману × валюте = 0` — **по построению**, не по проверке.

## C.3 Единый журнал: `PartnerMoneyEvent` (один тип строки на ВСЁ)

Поля (концептуально):
- ключи измерений: `tenant, agreement, procurement?, partner, lot?/sale_line?`
- `event_type` (явный, см. C.4), `pocket_from`, `pocket_to`
- деньги: `currency, amount_native, fx_rate, amount_uzs` (три шкалы — **разные колонки**,
  не соглашение об именах)
- происхождение: `source_ref, occurred_at`, `reversal_of`, `client_request_id`
- неизменяемость: immutable, delete→reversal-событие

Одна таблица заменяет: `AgreementContribution`, `AgreementWithdrawal`, `AgreementAllocation`,
`ReceiveBatchCapitalAllocation` (как факт), `PartnerLedgerEntry`, `ProcurementSaleRealization`,
`ProcurementPartnerVentureDebtRepayment`, `DividendPayment`. (`AgreementEvent` остаётся как
чисто аудиторный workflow-лог; `ProcurementVentureSettlement` — как именованный
снимок-чекпойнт, см. C.6.)

## C.4 Явные типы событий (никакого пост-фактум разбора)

| Карман | Событие | from→to |
|---|---|---|
| Капитал | `CAPITAL_CONTRIBUTED` | внешн→POOL |
| | `CAPITAL_DEPLOYED` | POOL→INVENTORY |
| | `CAPITAL_RECOVERED` | INVENTORY→PROCEEDS |
| | `CAPITAL_RETURNED_FROM_POOL` | POOL→партнёр |
| | `CAPITAL_RETURNED_FROM_PROCEEDS` | PROCEEDS→партнёр |
| Прибыль | `PROFIT_REALIZED` (provisional) | INVENTORY→PROCEEDS (profit-нога) |
| | `PROFIT_SETTLED` (true-up на settlement) | корректировка |
| | `DIVIDEND_PAID` | PROCEEDS→партнёр |
| | `PROFIT_TO_CAPITAL` (заменяет FROM_PROFIT-хак) | PROCEEDS→POOL |
| Убыток | `LOSS_MARKET` (по доле капитала) | INVENTORY→0 |
| | `LOSS_PARTNER_LIABILITY` (дебиторка с виновного) | INVENTORY→CLAIM(виновного) |
| Долг | `DEBT_REPAID` (компонентный: liability/capital/dividend) | внешн→PROCEEDS |
| FX | `FX_GAIN_LOSS` | измерительная нога |

Два бывших перегруженных смысла `AgreementWithdrawal` → **два явных события**
(`…FROM_POOL` / `…FROM_PROCEEDS`). Дискриминатор по `CashEntry.account` удаляется как класс проблемы.

## C.5 Материализованная проекция (CQRS read-side) — чтения O(1)

Таблица `PartnerPositionProjection`, ключ `(agreement, procurement, partner, currency)`,
обновляется **транзакционно в том же atomic-блоке**, что и append события. Колонки = ровно те,
что сейчас собираются live: `deployed, paid_in, recovered, profit_provisional, profit_settled,
loss_market, loss_liability, returned_pool, returned_proceeds, dividends,
debt_out_{liability,capital,dividend}, available_capital, available_profit, net, owed, withdrawable`.

Свойства:
- чтение — один индексированный select (не N процедур × N процurements);
- **полностью восстановима реплеем журнала** → инвариант `replay(events) == projection`
  сам по себе тест эквивалентности и anti-drift защита;
- под будущий масштаб (тысячи приходов) — это и есть read-side.

## C.6 Что меняет статус, но остаётся

- **Settlement** (`ProcurementVentureSettlement`) — остаётся как **именованный чекпойнт +
  событие true-up** (`PROFIT_SETTLED`/`net_capital_loss` true-up как события), а не как
  «магия, которую читают live». Sharia-неттинг по неизменяемому share-profile (`formulas.py`)
  — **сохраняется целиком**, но исполняется **один раз при settlement** (рождает события), а
  не на каждом чтении.
- **Conservation** — остаётся как safety-net и доказательство эквивалентности, но из
  «бухгалтерского переучёта» (текущий `venture_conservation`) превращается в **тривиальный
  `GROUP BY pocket,currency → Σ=0`** над журналом. ε только на native-FX-ноге; функциональный
  UZS — точный 0.
- **finance GL-слой** — **сохраняется как есть** (он уже консолидирован и корректен).
  Партнёрский журнал — это его размерная проекция; каждое событие по-прежнему вызывает те же
  `create_cash_entry/create_journal_entry`.

## C.7 Единицы — структурно, не по соглашению

`currency` — ключевая колонка и события, и проекции. Сложить две шкалы становится невозможно
без явного join по currency. `_uzs`-суффикс как «защита комментарием» исчезает.

## C.8 Что вакуум-модель убивает по дизайну

Три узла позиций → один; дискриминатор по счёту → явный тип; live-conservation-переучёт →
структурный Σ; FROM_PROFIT-хак → одно событие; `get_partner_aggregate`-франкенштейн → один
источник; `AgreementAllocation` двойная бухгалтерия → `CAPITAL_DEPLOYED`; 5 дублей quantize /
2 дубля equity-map / 4 дубля operator-residue → по одному (residue — общий helper, применяемый
при генерации событий).

---

# D. Наложение идеала на текущее + доказательство эквивалентности

## D.1 Что сохраняется (не трогаем — оно правильное)

- Весь **finance GL** (`CashAccount/CashEntry/Payment/JournalEntry`, `record_capital_pool_*`).
- **Sharia-формулы** распределения/неттинга (`formulas.py`,
  `calculate_sale_realization_distribution`, `distribute_loss_*`, `profit_shares_from_capital`).
- **Концепция трёх карманов** конверсии (она верна — становится структурой журнала).
- **Immutability** `contract_snapshot`, lifecycle receive→sale→settlement→close, read-only локи.
- **API-контракт** сериализаторов: проекция отдаёт те же поля → фронт стабилен.

## D.2 Что меняется

| Сейчас | Становится |
|---|---|
| ~10 партнёрских fact-store | 1 журнал `PartnerMoneyEvent` + 1 проекция |
| 3 узла позиций (3 базиса) | 1 проекция (1 источник) |
| `venture_conservation` (переучёт) | `GROUP BY pocket,currency` (структурно) |
| дискриминатор по `CashEntry.account` (×3) | явные `…FROM_POOL`/`…FROM_PROCEEDS` |
| FROM_PROFIT: dividend+fake contribution | `PROFIT_TO_CAPITAL` (1 событие) |
| `AgreementAllocation` как капитал-истина | `CAPITAL_DEPLOYED`-событие |
| `CapitalAdvanceSettlement` | удалить |
| 5/2/4 дублей хелперов | по одному |

## D.3 Доказательство эквивалентности (сшить с контрактом аудита)

Три независимых калибра, все обязаны сойтись на **golden-сценариях аудита**:

1. **Числа.** Для каждого golden-сценария: `projection(partner) == текущий
   procurement_venture_positions/partner_capital_positions(partner)` поле-в-поле. Это
   shadow-equality прогон (D.4 / E Фаза 1).
2. **Сохранение.** `residual(pocket,currency)==0` точно (UZS) / ≤ε (native-FX) на каждом
   сценарии — тот же критерий, что сейчас гейтит FINAL/close, поэтому регресс невозможен незаметно.
3. **GL.** Набор `JournalEntry`-строк по операции **идентичен** до и после (те же
   finance-вызовы) → Excel-replay и отчётность не меняются.

Доп. инвариант, которого сейчас нет: **`replay(events) == projection`** — anti-drift, ловит
рассинхрон write/read-side.

## D.4 Развилки, которые выношу явно (нужно решение, но не блокируют дизайн)

- **Гранулярность журнала: один общий или POOL-журнал + VENTURE-журнал?** Рекомендую **один**
  журнал, карман различает слой; это и устраняет сшивку. Но если аудит хочет физически
  раздельные реестры для договора и прихода — допустимо, ценой явного `DEPLOY`-моста (всё
  равно лучше нынешнего дискриминатора).
- **`PROFIT_SETTLED` как дельта-true-up vs полное переписывание профита на settlement.**
  Рекомендую дельту (чистый append).

Обе развилки имеют рекомендованный дефолт, совместимый с контрактом аудита.

---

# E. Фазовый план имплементации

Принцип: **каждая фаза самостоятельно проверяема; сохранение = доказательство эквивалентности
переноса; API стабилен; смежные модули (inventory/FIFO, finance, reporting, фронт) работают
всё время.** Никаких постоянных shim'ов — shadow-харнесс существует только ради доказательства
и затем удаляется (это верификационная оснастка, а не compatibility-слой — что соответствует
architecture-first политике проекта).

**Фаза 0 — Заморозка контракта (совместно с аудитом).** Зафиксировать golden-сценарии:
входы → эталонные позиции + GL-строки + conservation residual. Построить replay/shadow-харнесс
(прогон старого и нового бок-о-бок). *Verify: харнесс воспроизводит текущие числа 1:1.*

**Фаза 1 — Журнал + проекция как теневой write-side.** Ввести `PartnerMoneyEvent` +
`PartnerPositionProjection`; на каждой денежной операции писать события рядом со старыми
таблицами; backfill-реплей существующих fact-store в события (one-shot). Reads НЕ переключены.
*Verify: `projection == текущие 3 узла` поле-в-поле на ВСЕХ существующих тестах + golden;
`replay==projection`.* Это не двойная бухгалтерия «навсегда» — старые таблицы становятся
производными/удаляемыми.

**Фаза 2 — Переключение чтений.** Позиции, conservation, close-гейты, сериализаторы читают
проекцию. Удалить три live-узла (`procurement_venture_positions`/`partner_capital_positions`/
`_agreement_available_by_partner` сводятся к чтению проекции). Conservation → структурный Σ.
*Verify: API-ответы байт-в-байт; close-гейты идентичны; conservation=0.*

**Фаза 3 — События как источник истины.** Старые fact-store перестают писаться напрямую;
становятся (или удаляются) проекциями событий. Удалить: дискриминаторы по счёту,
`AgreementAllocation`-как-капитал, `CapitalAdvanceSettlement`, FROM_PROFIT-хак
(→ `PROFIT_TO_CAPITAL`), дубли хелперов/equity-map/operator-residue. *Verify: golden +
conservation; миграция истории через backfill идемпотентна.*

**Фаза 4 — Мультивалюта/FX и финальная чистка.** `FX_GAIN_LOSS`, cost-basis конверсии
(`CurrencyConversionLot`) как события; `remaining_inventory` как производное чтение;
декомпозиция god-модулей по bounded-context (workspace → funding/receive/capital/payment
под-модули). *Verify: E12/E13-сценарии; native-ε только на FX-ноге.*

Каждая фаза зелёная независимо; откат — отбросить переключение reads (Фаза 2) без потери
данных, т.к. старые таблицы живут до Фазы 3.

---

# F. За пределами денег: структура, поддерживаемость, оптимизации, тест-режим

## F.1 Слоистость / зависимости

- **God-модули** (`workspace.py` 4406, `models.py` 1891) — декомпозировать по контексту:
  `capital/`, `receive/`, `payment/`, `funding/`, `close/`. Соблюдает дух проектного правила
  декомпозиции.
- **Цикл зависимостей** (десятки function-local импортов `advances↔venture↔workspace↔
  agreement_services`) — лечится самим журналом: всё зависит от `PartnerMoneyEvent`/проекции,
  а не друг от друга. Однонаправленность убирает lazy-import-обходы.
- **`models.py` 1891 строк** — разнести по доменным под-модулям (capital, venture, terms,
  consignment).

## F.2 Оптимизации (производительность)

- Сейчас `partner_capital_positions` вызывает `procurement_venture_positions` **в цикле по
  всем приходам** (advances.py:259), каждый из которых делает 4+ агрегатных запроса +
  повторный `_realization_groups`. Это N×M на каждый рендер workspace. Проекция → один
  индексированный select. Это не преждевременная оптимизация: при росте числа приходов
  договора текущий путь деградирует линейно×квадратично.
- `venture_conservation` повторно зовёт `_net_*_entitlements` и `procurement_venture_positions`
  внутри себя — частично смягчено threading групп (E17 T-4.7), но в вакуум-модели исчезает целиком.

## F.3 Тест-режим — регламент валидности

67 тест-файлов; значительная часть — «зелёные ради зелёных». Предлагаю канон **«тест валиден
⇔ он ловит реальный регресс»**:

**Тест допустим, только если выполняет хотя бы одно:**
1. проверяет **реальное движение денег** (GL-строки сбалансированы и совпадают с эталоном), или
2. проверяет **бизнес-инвариант** (`conservation residual=0`; `Σprofit_share=1`; `net`
   сходится; `replay==projection`), или
3. **падал бы на конкретном реальном регрессе** (например, тот самый double-count S1/S4).

**Запрещены как самоцель:** тесты вида «функция вернула dict с ключом X», «поле сериализатора
присутствует», «создалась строка» без проверки экономики. Они дают ложную уверенность и
стоимость поддержки без anti-regression-ценности (прямо против architecture-first политики проекта).

**Сдвиг формы:** от примерно-богатых unit-тестов к **golden-сценариям + property-based**
(сохранение как свойство на сгенерированных последовательностях событий). Один property-тест
«любая последовательность событий → каждый карман Σ=0» покрывает больше, чем десятки примеров.

**Метрика чистки:** для каждого существующего money-теста спросить «какой реальный баг он бы
поймал?»; нет ответа → удалить или переписать в инвариант. Это разовый аудит сьюта, выполнить
в Фазе 0 (он же даёт golden-контракт).

## F.4 Прочие флаги (с обоснованием)

- **ε на conservation** ужесточить: точный 0 для UZS-карманов, ε только native-FX.
  Обоснование: толеранс на инварианте сохранения — укрытие для утечек.
- **`get_partner_aggregate`** — расщепить или пометить deprecated: смешанный источник опасен
  для любого нового потребителя.
- **`CapitalAdvanceSettlement`** — удалить модель и enum в Фазе 3.

---

# Резюме

**Диагноз.** Денежная архитектура корректна по результату (conservation гейтит, GL
консолидирован), но структурно больна **одним** корневым дефектом: денежные события — это
*денормализованные per-partner строки в ~10 таблицах разной гранулярности*, а не *двусторонние
по карманам события одного журнала*. Из этого механически вытекают все шрамы: 3 узла позиций
на 3 базисах, сшивка эвристикой по GL-счёту (источник S1/S4), live-переучёт сохранения,
синтетические сверочные хаки (FROM_PROFIT), франкенштейн-чтения, дубли хелперов, цикл
зависимостей. Гипотезы аудита 1–5 подтверждены по коду; п.1 даже недооценён (стора ~10, а не 2).

**Вакуум-идеал.** Один append-only `PartnerMoneyEvent` (double-entry по карманам
POOL/INVENTORY/PROCEEDS/CLAIM, явные типы, три валютные шкалы как колонки) + одна
материализованная проекция (read-side O(1), реплей-восстановимая). Тогда **сохранение
становится структурным** (`GROUP BY pocket,currency Σ=0`), а не проверяемым; позиция —
`GROUP BY`, а не переплётенная деривация; дискриминатор по счёту исчезает как класс.
Sharia-неттинг и весь GL сохраняются; settlement рождает true-up события, а не читается «магией».

**Наложение и доказуемость.** Эквивалентность доказывается тремя калибрами на golden-сценариях
аудита: числа поле-в-поле, conservation residual=0, GL-строки идентичны; плюс новый anti-drift
инвариант `replay==projection`. Сохраняем finance, формулы, lifecycle, API-контракт.

**План.** 0) заморозка golden-контракта + shadow-харнесс; 1) журнал+проекция теневым
write-side с backfill (reads не тронуты, доказываем равенство на всём сьюте); 2) переключение
чтений, удаление 3 live-узлов; 3) события — источник истины, снос
дискриминаторов/`AgreementAllocation`-капитала/`CapitalAdvanceSettlement`/FROM_PROFIT-хака/
дублей; 4) FX-события + декомпозиция god-модулей. Каждая фаза зелёная независимо; conservation
— доказательство переноса; shadow-оснастка удаляется (не компромисс-слой).

**За пределами денег.** Декомпозировать `workspace.py`/`models.py`; цикл зависимостей лечится
журналом; проекция убирает N×M-переучёт на рендере; ε-сохранения ужесточить. Тест-режим:
канон «валиден ⇔ ловит реальный регресс» — допускать только тесты на движение денег / инвариант
/ конкретный регресс; сдвиг к golden+property-based; разовая чистка сьюта в Фазе 0.

## Независимая оценка ранее принятых решений

- Решение хранить позиции *live* без проекций — главная стратегическая ошибка; терпимо на
  текущем масштабе, но именно оно породило сшивки-эвристики и S1/S4.
- Дискриминатор withdrawal по `CashEntry.account` — следовало с самого начала развести на два
  типа события; это «умный» хак там, где нужен был явный тип.
- FROM_PROFIT, пишущий несуществующие dividend+contribution ради сходимости, — **самый
  тревожный** фрагмент: подделка фактов в append-only истории. Исправить в первую очередь даже
  до большого рефактора.
- E17-фиксы (pool-only paid_in, threading групп) — правильные локально, но они *лечат симптом
  множественности источников*, а не причину; вакуум-модель делает их ненужными.

Развилок, блокирующих дизайн, нет: две выявленные (единый vs раздельный журнал; дельта vs
переписывание профита) имеют рекомендованные дефолты, совместимые с контрактом аудита.

---

*Конец аудита. Документ фиксирует состояние и дизайн-предложение на 2026-06-15; решение о
включении в работу — отдельным шагом.*
