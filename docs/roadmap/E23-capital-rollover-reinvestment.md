# E23 — Capital Rollover & Real Reinvestment

**Статус:** `IN_PROGRESS`
**Прогресс:** 95%
**Зависит от:** E18, E21
**Блокирует:** production-grade Excel replay, корректный повторный оборот капитала,
payout-policy enforcement

---

## Цель

Сделать честный сценарий, когда восстановленный продажами капитал или прибыль не
выводятся партнёру, а остаются в деле и снова попадают в capital pool без
завышения внешне внесённого капитала и без висящих claims.

## Контекст и обоснование

Excel replay D-001/U-001 показал реальный сценарий нескольких оборотов капитала:
товар частично продан, деньги уже в операционной кассе, затем на эти деньги
покупается следующий товар. Текущий backend умеет `PROFIT_REINVEST` только как
погашение капитального долга из прибыли, а frontend показывает это в
`AdvanceSettleSheet`. Это не общий сценарий "оставить восстановленный капитал в
деле".

Если такой оборот записать простым `AgreementContribution`, система увеличивает
`paid_in/gross_contributed` и не списывает `capital_return_available`. В итоге
одни и те же 4k могут выглядеть одновременно как доступные к возврату и как
повторно внесённые в pool.

Этот же gap пересекается с payout policy. В E20 условия договора уже хранят
`review_interval_days`, `minimum_available_amount`,
`minimum_days_between_payouts`, `reserve_amount` и создают `PayoutObligation`.
Но прямые действия "вернуть капитал" / aggregated payout сейчас могут идти по
доступной сумме, не обязательно через due obligation. Для reinvest это опасно:
выбор "вернуть или оставить в деле" должен открываться в тех же условиях, в
которых договор разрешает распоряжаться восстановленным капиталом.

Текущая реализация policy evaluation ближе к hardcoded `OR`: положительный
порог может открыть действие раньше календарного review, иначе работает период.
Целевой E23 должен сделать это явным договорным параметром: `ANY` (`период OR
порог`) или `ALL` (`период AND порог`). Пауза после прошлого решения,
резерв, лимит доступности и partial policy применяются в обоих режимах.

## Сценарии (use cases)

- **US-1. Capital rollover.** Инвестор вложил 10k, продажи восстановили 4k
  капитала. Если эти 4k снова идут в закупку, внешний вклад остаётся 10k, активный
  капитал остаётся 10k, а `capital_return_available` уменьшается на 4k.
- **US-2. Profit capitalization.** Если партнёр осознанно превращает 1k прибыли в
  новый капитал, прибыль к выплате уменьшается на 1k, а капиталовая база растёт
  только по явному правилу договора.
- **US-3. Mixed source purchase.** Следующий receipt может финансироваться
  частично свободным pool cash, частично rollover recovered capital, частично
  новой внешней доплатой.
- **US-4. Multi-investor attribution.** Rollover относится к тем партнёрам, чей
  капитал/прибыль были восстановлены, а не к бизнесу только потому, что деньги
  физически лежат в кассе бизнеса.
- **US-5. Excel replay.** Replay D-001/U-001 восстанавливает несколько оборотов
  капитала без orphan `PROFIT_REINVEST` и без synthetic stock.
- **US-6. Policy-gated decision.** Когда payout policy говорит, что накопленная
  сумма/период/пауза позволяют действие, бизнес выбирает: выплатить капитал
  инвестору или оставить этот же капитал в деле.
- **US-7. Group payout allocation.** Порог/период считаются по общей сумме
  восстановленного капитала договора, а не по каждому инвестору отдельно.
  После выбора общей суммы система предлагает распределение по инвесторам, но
  бизнес может вручную округлить/поправить строки в пределах доступного капитала
  каждого инвестора.

## Текущее состояние

- ✅ **Что уже есть:** real cash capital pool, physical capital return from pool
  and proceeds, procurement-bound payout, `PROFIT_TO_CAPITAL` for settling a
  capital shortfall from profit.
- ⚠️ **Что начато, но не покрывает этот кейс:** `BUSINESS_FROM_TURNOVER` двигает
  operating cash в pool, но выглядит как contribution выбранного партнёра.
  `PROFIT_REINVEST` есть только для `settle_partner_capital(FROM_PROFIT)` и
  сейчас ограничен UZS agreement checks.
- ✅ **E23 реализует:** append-only `capital rollover` / `proceeds to pool`,
  списание rollover из `capital_return_available`, group decision UI
  "вернуть / оставить в деле", и Excel replay без provisional top-up.
- ✅ **Ужесточено:** direct recovered-capital return, direct dividend payout и
  legacy aggregate payout не обходят payout policy; recovered money проходит
  через group-level decision preview/execution.

## Target contract

- `external_contribution` = новые деньги партнёра извне.
- `turnover_contribution` = бизнес довносит свои деньги или закрывает свою
  капиталовую обязанность из операционной кассы.
- `capital_rollover` = восстановленный капитал партнёра остаётся в договоре и
  снова становится pool cash; это не новый внешний вклад и не увеличивает
  external paid-in.
- `profit_to_capital` = прибыль партнёра капитализируется; это уменьшает
  `provisional_profit_available` и увеличивает капиталовую базу только по
  явному правилу.
- Read-model обязан разделять: external paid-in, cumulative deployed, rolled
  capital, profit capitalized, capital returned, active capital at risk.
- `active capital at risk` = external paid-in + profit capitalized по явному
  terms-rule + rolled recovered capital, минус confirmed capital paid out, но
  без повторного счёта одного и того же recovered cash как нового взноса.
- `cumulative deployed` = сколько капитала проходило через procurement cycles.
  Оно может быть выше external paid-in: 10k внешнего капитала может дать 14k
  cumulative deployed после 4k rollover. Это не означает, что инвестор внёс 14k.
- Payout policy - единый gate для решения по recovered money: если политика ещё
  не открыла due action, нельзя ни выплатить этот капитал, ни silently
  реинвестировать его в новый receipt.
- Due action должен иметь варианты решения: `PAY_OUT`, `ROLL_OVER_CAPITAL`,
  `CAPITALIZE_PROFIT` и, если договор позволяет, partial amount.
- Payout policy получает явный `trigger_mode`: `ANY` = сумма достигла порога
  или наступил период; `ALL` = сумма достигла порога и наступил период.
- Threshold применяется к общей eligible-сумме по договору/группе, не к каждой
  строке инвестора. `minimum_days_between_payouts` считается от последнего
  confirmed payout/rollover decision и не сбрасывается отдельными строками
  инвесторов.
- Групповое распределение - единственный нормальный способ вывода/rollover для
  нескольких инвесторов. Per-investor ручные действия не показываются как
  основной путь и не должны обходить policy.
- В allocation editor сумма каждой строки должна быть `0 <= amount <= available`
  конкретного инвестора; сумма строк должна равняться выбранной общей сумме.
  Default allocation строится пропорционально available capital, но UI должен
  позволять ручное округление до практичных сумм.
- Новый товар, купленный на recovered/rolled capital, обычно создаёт новый
  `Procurement` внутри того же `InvestmentAgreement`. Старый procurement
  продолжается только когда это реально тот же purchase/partial receive, а не
  новый оборот капитала после продаж.

## Domain math decisions

### Capital buckets

Базовый сценарий: инвестор внёс 10k, procurement продал часть товара и
восстановил 4k капитала. До решения эти 4k являются `capital_return_available`.

Если бизнес выбирает `ROLL_OVER_CAPITAL` на 4k:

- external paid-in остаётся 10k;
- capital returned cash не создаётся;
- `capital_rolled_to_pool` становится 4k;
- `capital_return_available = recovered - returned - rolled_to_pool + repayments`;
- active capital at risk остаётся 10k, если все 4k снова заведены в pool и
  доступны для следующего procurement;
- cumulative deployed становится 14k после следующего receipt на эти 4k.

Если бизнес выбирает `PAY_OUT` на 4k:

- external paid-in остаётся 10k как исторический факт;
- capital returned увеличивается на 4k;
- active capital at risk уменьшается до 6k, пока нет нового внешнего взноса или
  явной капитализации прибыли;
- `capital_return_available` уменьшается на 4k.

Если бизнес ничего не выбирает:

- recovered capital остаётся pending/eligible по policy;
- новый receipt не может silently потребить эти 4k как pool cash;
- UI показывает причину блокировки или доступное due decision.

### Profit capitalization

`PROFIT_REINVEST` в текущем коде сохраняется только как shortfall settlement:
`settle_partner_capital(FROM_PROFIT)` пишет `PROFIT_TO_CAPITAL` в procurement
ledger и matching `AgreementContribution(source=PROFIT_REINVEST)`. Это закрывает
долг партнёра перед pool и не является общим механизмом rollover.

Полная profit capitalization (партнёр превращает свободную прибыль в новый
capital base сверх shortfall) не включается по умолчанию. Она разрешается только
если новая `AgreementTermsVersion` явно допускает изменение capital base/share
после старта. До такого terms-rule действие `CAPITALIZE_PROFIT` в preview
возвращает блокировку, а UI не показывает его как обычную кнопку.

Шариатская причина: прибыль нельзя тихо превратить в новую долю капитала, если
это меняет будущий риск/доходность других участников без согласованного правила.
Rollover восстановленного капитала не меняет economic ownership; profit
capitalization может менять, поэтому это другой договорный акт.

### Policy gate

Policy gate считается на уровне agreement decision group:

1. собрать eligible recovered/profit amounts по договору и типу действия;
2. вычесть `reserve_amount`;
3. проверить `minimum_days_between_payouts` от последнего confirmed group
   decision (`PAY_OUT`, `ROLL_OVER_CAPITAL`, `CAPITALIZE_PROFIT`);
4. проверить trigger:
   - `ANY`: due, если наступил `review_interval_days` OR group eligible total
     достиг `minimum_available_amount`;
   - `ALL`: due, если наступил `review_interval_days` AND group eligible total
     достиг `minimum_available_amount`;
5. если `allow_partial=false`, execution amount должен равняться eligible total
   после reserve; если `true`, amount может быть меньше, но allocation rows всё
   равно должны суммироваться ровно в выбранный total.

Threshold не применяется к отдельной строке инвестора. Например, policy threshold
1,000 и recovered rows 600 + 500 дают due group decision на 1,100; две отдельные
строки по 600/500 не должны блокироваться только потому, что каждая меньше 1,000.

### Group allocation

Default allocation строится proportionally by available recovered capital с
largest-remainder/last-row residue handling в минимальной денежной единице
валюты. UI может дать quick-round presets, но backend принимает свободные
decimal amounts и проверяет:

- каждая строка относится к участнику договора;
- business/operator не является обычным recipient payout/rollover decision;
- `0 <= row.amount <= row.available`;
- сумма строк равна selected total;
- для `PAY_OUT` есть physical cash source;
- для `ROLL_OVER_CAPITAL` есть operating cash source, из которого деньги
  переносятся в agreement pool;
- для `CAPITALIZE_PROFIT` есть explicit terms permission.

### Admin override

Обычный manual override для досрочного payout/rollover не входит в E23 UX. Если
нужна исключительная досрочная операция, она оформляется forward-only
`AgreementTermsVersion`/amendment или отдельным admin-only escape hatch с явной
причиной и audit trail. Такой escape hatch не должен быть доступен как основной
frontend flow и не должен обходить append-only facts.

## План реализации

### Фаза 1 — Domain math

Зафиксировать формулы active capital vs cumulative deployed:
`capital_return_available = recovered - returned - capital_rollover + repayments`.
Profit capitalization меняет capital/profit share только при явном terms-rule;
иначе текущий `PROFIT_REINVEST` остаётся только shortfall settlement.
Одновременно зафиксировать payout-policy gate: review interval, amount threshold,
minimum spacing, reserve и allow_partial должны применяться к payout и rollover
одинаково.
Сюда же входит целевое правило `ANY/ALL`: календарный период и минимальная сумма
могут работать как `OR` или как `AND`, но пауза после прошлого решения всегда
остаётся жёстким ограничением.

### Фаза 2 — Backend facts

Добавить append-only факт rollover: operating cash -> agreement pool, attribution
to partner/procurement, GL asset transfer, read-model bucket
`capital_rolled_to_pool_uzs`. `profit_to_capital_uzs` остаётся отдельным bucket
для profit capitalization/shortfall settlement.
Закрыть обход прямых payout endpoints: capital return/profit payout/rollover
должны либо ссылаться на due `PayoutObligation`, либо пройти один общий backend
policy preview, который явно объясняет разрешение/запрет.

### Фаза 3 — Frontend flow

На экране realized capital добавить действие "Оставить в деле" рядом с
"Вернуть капитал"; для прибыли - отдельное "Капитализировать прибыль", если это
разрешено условиями договора. Эти действия должны появляться рядом только после
payout-policy eligibility, а не на каждой мелкой продаже.

Фаза 3 начинается только с отдельного Plan Mode прохода. Перед кодом нужно
текстом спроектировать новую страницу договора: блоки, данные, состояния,
кнопки, валидации, mobile/desktop поведение и то, какие старые блоки удаляются.
Текущую страницу нельзя править косметически; её нужно пересобрать по workflow,
сохранив бизнес-контракт и перенеся только нужную логику.

Целевой UX страницы договора:

1. **Agreement command header.** Название/статус договора, бизнес, инвесторский
   пул, валюта, active capital at risk, next policy gate: "доступно сейчас" /
   "ждём N дней" / "не хватает X до порога".
2. **Terms & policy summary.** Коротко: доли капитала/прибыли, `trigger_mode`
   (`ANY`/`ALL`), период, порог общей суммы, пауза после прошлого решения,
   резерв, partial allowed. Это читается как условия договора, не как форма.
3. **Capital lifecycle strip.** External paid-in, deployed, recovered pending,
   eligible for decision, rolled over, paid out, remaining inventory capital.
   Цель - быстро понять, где деньги сейчас.
4. **Decision workspace.** Главный рабочий блок, который появляется только при
   eligible recovered money. Сначала выбирается действие: `Вернуть инвесторам`,
   `Оставить в деле`, позже `Капитализировать прибыль`. Затем вводится общая
   сумма и касса/источник, если нужен physical cash movement.
5. **Group allocation editor.** Таблица инвесторов внутри decision workspace:
   investor, available, suggested amount, editable amount, remaining after
   action. Система предлагает распределение, бизнес может вручную округлить.
   Строка не может превысить available инвестора, сумма строк должна совпадать
   с общей суммой действия. Отдельный per-investor "Вернуть" блок убрать.
6. **Pending recovered money.** Если policy ещё не открыла действие, показывать
   locked/pending суммы и причину: `threshold`, `interval`, `spacing`, `reserve`.
   Без кнопок payout/reinvest.
7. **Partner positions.** Пересобрать странные текущие блоки "план/факт" в
   понятную таблицу: planned capital, external paid-in, active at risk, recovered
   pending, paid out, rolled over, profit pending. Детали раскрываются строкой.
8. **Procurements under agreement.** Список приходов как обороты договора:
   status, received, sold, recovered, profit, remaining inventory, linked
   decisions. Новый оборот на reinvest создаётся как новый procurement.
9. **History & audit.** Хронология только фактов: contribution, receive, sale
   settlement, payout, rollover, profit capitalization, amendment.

### Фаза 4 — Excel replay

Заменить provisional `PROFIT_REINVEST` top-up в D-001/U-001 на реальные rollover
facts. Replay должен проверять, хватает ли восстановленного капитала/прибыли на
каждый следующий receipt, и явно показывать недостающие новые доплаты.

## Задачи (чек-лист)

### Фаза 1
- [x] T-1.1 Зафиксировать формулы на сценариях 10k -> 4k recovered -> rollover.
- [x] T-1.2 Решить договорное правило profit capitalization: меняет ли future
  capital share или только закрывает shortfall.
- [x] T-1.3 Обновить E18/E21 терминологию paid-in vs active capital at risk.
- [x] T-1.4 Зафиксировать payout-policy gate для return/reinvest decision:
  threshold, review interval, minimum spacing, reserve, partial policy.
- [x] T-1.5 Добавить `trigger_mode` contract: `ANY` (`interval OR threshold`) и
  `ALL` (`interval AND threshold`); spacing/reserve остаются hard gates.
- [x] T-1.6 Зафиксировать, что threshold считается по общей eligible-сумме
  договора/decision group, не по каждому инвестору отдельно.

### Фаза 2
- [x] T-2.1 Добавить backend event/model для `capital_rollover`.
- [x] T-2.2 Научить venture/read-model вычитать rollover из
  `capital_return_available`.
- [x] T-2.3 Запретить orphan `PROFIT_REINVEST` для non-UZS или без
  `PROFIT_TO_CAPITAL` counterpart.
- [x] T-2.4 Покрыть conservation/pool reconciliation/property tests.
- [x] T-2.5 Сделать единый policy-gated endpoint для payout/rollover preview и
  execution; прямые endpoints не должны обходить due policy.
- [x] T-2.6 Backend preview должен возвращать group-level eligibility,
  blocking reasons, default allocation и editable allocation constraints.
- [x] T-2.7 Execution должен принимать batch allocation rows, а не одиночный
  per-investor withdrawal как основной business path.

### Фаза 3
- [x] T-3.1 Добавить UI "Оставить капитал в деле".
- [x] T-3.2 Добавить UI/guard для profit capitalization.
- [x] T-3.3 В отчётах разделить gross external contribution и rolled capital.
- [x] T-3.4 Перестроить бизнес-UI: eligible recovered money показывает выбор
  "Вернуть" / "Оставить в деле"; non-eligible суммы показываются как pending.
- [x] T-3.5 Удалить нижний per-investor manual return блок из recovered capital
  UI; оставить только group decision/allocation path.
- [x] T-3.6 До реализации UI подготовить Plan Mode документ по новой странице:
  IA, блоки, states, validation, mobile/desktop, copy, removed legacy sections.
- [x] T-3.7 Реализовать страницу через "preserve contract, rebuild presentation":
  сохранить данные/API-инварианты, но пересобрать template/layout, а не чинить
  старые карточки точечно.

### Фаза 4
- [x] T-4.1 Переписать `sherik_excel_replay` с provisional top-up на rollover.
- [ ] T-4.2 Переприменить D-001/U-001 и проверить отсутствие hanging/double-count
  claims. Требует явного разрешения на destructive `--apply --wipe`.
  - **Data gate 2026-07-20:** apply в отдельной fresh-базе остановился на U-001
    row 9. Общий `apply_credit_term_receive_deferrals()` перенёс COD-покупку
    `814` с 2025-11-02 на 2026-02-08 и создал потребность в 105.20 USD при
    59.44 USD eligible recovered capital. Этот перенос не входит в утверждённые
    source corrections.
  - Полный replay также требует явного terms/amendment для капитализации
    21,491,409.44 UZS investor profit. Рабочая модель и событийный график:
    [`docs/replay/u001-date-shift-model.md`](../replay/u001-date-shift-model.md).
    До founder decision нельзя закрывать gap synthetic contribution, скрытым
    переносом дат или обходом payout policy.
- [x] T-4.3 Обновить `docs/testing-data-workflow.md` после non-destructive
  preflight и E23 replay path.

## Открытые вопросы

- ? Точная frontend quick-round конфигурация остаётся UX-деталью Фазы 3:
  backend принимает свободные decimal amounts и возвращает constraints.

## Решённые вопросы (история)

- ✓ 2026-07-04: текущий `PROFIT_REINVEST` не считать полноценным rollover; он
  покрывает только погашение капитального shortfall из прибыли.
- ✓ 2026-07-04: Excel replay D-001/U-001 выявил gap, но provisional top-up не
  является production-grade financial truth.
- ✓ 2026-07-04: payout policy должна быть gate для обоих решений по
  восстановленным деньгам: payout и reinvest/rollover.
- ✓ 2026-07-04: period/threshold должны поддерживать явный `ANY`/`ALL` режим;
  текущий hardcoded early-threshold behavior недостаточно выразителен.
- ✓ 2026-07-04: для нескольких инвесторов payout/rollover - group decision,
  threshold считается по общей сумме, а распределение по инвесторам редактируется
  внутри batch allocation.
- ✓ 2026-07-04: нижний per-investor recovered-capital return UX убрать; он
  конфликтует с group-level payout policy.
- ✓ 2026-07-04: каждый implementation phase E23 начинается с Plan Mode, а
  frontend-фаза сначала проектируется текстом и только потом реализуется.
- ✓ 2026-07-04: `external paid-in`, `capital rolled to pool`, `profit to
  capital`, `capital returned`, `active capital at risk` и `cumulative deployed`
  являются разными display/read-model buckets; один recovered cash факт нельзя
  одновременно считать доступным к возврату и новым external contribution.
- ✓ 2026-07-04: full profit capitalization не разрешается по умолчанию. Она
  требует явного terms/amendment rule, потому что может менять будущую долю
  риска/доходности участников.
- ✓ 2026-07-04: capital rollover разрешается на sale-level recovered capital
  facts после policy gate; final procurement close не требуется, если конкретная
  recovered amount уже подтверждена и не имеет negative-position blockers.
- ✓ 2026-07-04: обычный досрочный payout/rollover не делается manual override.
  Исключения оформляются forward-only terms amendment или admin-only audited
  escape hatch вне основного UX.
