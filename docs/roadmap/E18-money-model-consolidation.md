# E18 — Money Model Consolidation: Dimensioned GL + Thin Provisional Layer + Single Read-Model

**Статус:** `NOT_STARTED` (предложение на ревью аудитором + go/no-go владельца)
**Прогресс:** 0%
**Зависит от:** E11, E12, E14, E15, E16, E17 (вся партнёрская денежная база)
**Блокирует:** E03 (Real Value Reporting — нужен чистый read-model), масштабирование, доверие к деньгам у первого клиента

> Источник: независимый вакуум-аудит денежной архитектуры — [`docs/money-architecture-audit.md`](../money-architecture-audit.md) (2026-06-15). Раздел C аудита (большой rewrite в один новый журнал) **отклонён** после red-team как заякоренный и мис-скейленный; принят откалиброванный синтез (см. «Решённые вопросы»). Этот эпик — наложение синтеза на код безопасными фазами.

---

## Цель

Свести партнёрскую денежную модель к **одной правде без подгонок**: реализованные деньги
опираются на уже корректный GL (дименсионированный по partner/agreement/procurement/карману),
провизорный партнёрский сплит остаётся тонким честным слоем, а позиции читаются из **одного**
материализованного read-model. Итог: расхождение трёх узлов позиций (корень S1/S4-багов)
исчезает, в истории денег нет фиктивных записей, корректность доказуема числами + сохранением +
идентичностью GL.

## Контекст и обоснование

E11–E17 нарастили партнёрскую экономику инкрементально и оставили «шрам-tissue» (полный разбор
— в аудите, разделы A–B). Корень один: денежные факты — это **денормализованные per-partner
строки в ~10 таблицах разной гранулярности**, поэтому:

- **три параллельных узла позиций** на трёх базисах (`partner_capital_positions`,
  `procurement_venture_positions`, `_agreement_available_by_partner`) могут разойтись — и
  именно это породило баги приёмки S1/S4;
- источники сшиваются **эвристикой по `CashEntry.account`** (пул/операционка) минимум в 3 местах;
- есть **подделка фактов**: FROM_PROFIT-сеттл пишет несуществующие «дивиденд выплачен» +
  «взнос сделан», чтобы derived-баланс сошёлся (`advances.py:175‑183`);
- сохранение денег **переучитывается live** на каждый запрос, а не вытекает из структуры;
- остался мёртвый код (`CapitalAdvanceSettlement`) и дубли хелперов (quantize ×5, equity-map ×2,
  operator-residue ×4).

В деньгах техдолг быстро становится продуктовым риском. Эпик лечит **причину** (множественность
источников + подгонки), а не симптомы, и делает это **без big-bang миграции живых денег**.

Почему именно этот подход (а не большой rewrite в новый журнал): red-team показал, что ценность
была не в «event-log», а в (1) едином read-источнике, (2) явных типах, (3) сносе подгонок. Всё
это достижимо **консолидацией на месте**: реализованные деньги уже корректно лежат в GL —
дублировать их параллельным журналом не нужно; провизорный сплит (recovered/profit/loss по долям
до settlement) в GL не лежит и **не должен** — он остаётся отдельным тонким слоем. Чище, чем
rewrite: нет дублирования GL, уважается различие реализованного и провизорного, near-zero
миграционный риск.

## Сценарии (use cases)

- **US-1 (честный профит→капитал).** Партнёр гасит капитальный долг из своей нераспределённой
  прибыли. В системе появляется **одна** честная запись «прибыль → капитал»; в истории взносов
  и выплат **нет** фиктивных «дивиденд» и «взнос». Цифры и GL — те же.
- **US-2 (честная сверка).** Venture-settlement пересчитывает recovered/profit/loss по
  net-стоимости. Пересчёт оформляется **честным true-up-событием** (append-only, поверх
  оригиналов), а не live-перетиранием и не подложными строками. История показывает реальный ход.
- **US-3 (явный тип возврата).** Возврат капитала партнёру явно помечен как «из пула» или «из
  выручки»; система не вычисляет смысл задним числом по тому, с какого счёта ушёл `CashEntry`.
- **US-4 (одна позиция).** Любой экран/отчёт показывает партнёрскую позицию из **одного**
  read-model; разные узлы не могут показать разные числа.
- **US-5 (доказуемое закрытие).** Close прихода/договора гейтится сохранением с **точным нулём**
  по UZS (ε только на FX-ноге); невозможно закрыть венчур с утечкой, спрятанной под толеранс.
- **US-6 (аудируемость).** Аудитор может проследить **каждое** число позиции либо до GL-строки
  (реализованное), либо до провизорного события (сплит/true-up); фантомных строк нет.

## Текущее состояние

- ✅ **Что уже есть и остаётся правильным:** finance GL (`CashAccount/CashEntry/Payment/JournalEntry`,
  `record_capital_pool_*`) — консолидирован и корректен; sharia-формулы неттинга (`formulas.py`);
  immutability `contract_snapshot`; lifecycle receive→sale→settlement→close; read-only локи;
  3-карманный conservation-инвариант как **концепция**.
- ⚠️ **Что начато, но кривое:** позиции считаются в 3 узлах (расходятся); conservation
  переучитывается live; `ProcurementVentureSettlement.partner_positions` (JSON-снимок) в чтениях
  не переиспользуется; GL не несёт партнёрское измерение (эквити по роли 3100/3110/3000, не по
  партнёру).
- ❌ **Чего нет:** единого read-model; явных типов возврата (POOL/PROCEEDS); честного
  профит→капитал и честного settlement-true-up (вместо подгонок/перетирания); инварианта
  `replay==read-model`; дименсий на GL.

## Целевая модель

Два слоя денег + один read-model над ними. Без параллельного журнала-дубля.

### Слой 1 — Реализованные деньги = GL + partnerships-owned дименсии (tag-слой)

Каждое **партнёр-гранулярное** движение кэша/эквити получает аналитические измерения
`{partner_id, agreement_id, procurement_id, pocket}` — но они живут **не на `JournalLine`**, а в
**partnerships-owned tag-таблице `PartnerJournalLineTag`** (`journal_line FK → finance`,
направление зависимости **partnerships→finance**). finance остаётся **домен-агностичным**: он не
знает ни про партнёрства, ни про существование tag-таблицы; суммы денег живут в GL **один раз**,
тег лишь указывает НА строку (не копия факта, не вторая бухгалтерия). Тег пишется транзакционно
вместе с journal entry. Дименсионируются: взносы (paid_in), возвраты капитала, дивиденды,
погашения долга, профит→капитал.

- **Источник правды реализованного слоя** — GL-строка (сумма) + её tag (партнёр/карман), а не
  bespoke-таблица. «Сколько у партнёра» читается **единым `GROUP BY` по tag-таблице + join к
  `JournalLine` за суммами** — одна равномерная агрегация вместо UNION по 10 доменным таблицам.
- **Доменные таблицы намерения** (`AgreementContribution`/`Withdrawal`/`DividendPayment`/…)
  остаются как записи **намерения + идемпотентность + аудит**, но **деньги из них не читаются
  никогда** — только GL/tag-слой.
- **Сохранение реализованного слоя — бесплатно и точно:** это врождённый инвариант GL
  (debit=credit). Переизобретать его не нужно — нужно не сломать.
- `pocket` ∈ {CAPITAL, PROCEEDS, DISTRIBUTION} — выравнен на уже доказанную 3-карманную рамку
  `venture_conservation`. Новый «карман» не вводим.

### Слой 2 — Провизорный венчурный сплит = тонкий append-only слой (в GL нет и не должно быть)

`ProcurementSaleRealization` **сохраняется** как единственный носитель того, чего GL не несёт:
per-slice распределение `recovered / profit / loss / fx` по **неизменяемым долям** до settlement.
Это управленческая аллокация экономики продажи между партнёрами, у которой **нет кэш-ноги**, пока
она не станет реальной (дивиденд/возврат). Поэтому ей не место в GL.

- **deployed-per-partner — производное, не факт:** `batch total (из finance) × snapshot
  capital_share`. Отдельной таблицей не хранится.
- **settlement-true-up — честные события (US-2):** на settlement net-пересчёт
  (`_net_capital_loss_entitlements` / `_net_profit_entitlements`) **не перетирает** live-числа, а
  вычисляет нетто-энтайтлмент и **дописывает дельта-события** в провизорный слой (тип
  `SETTLEMENT_TRUEUP`): «recovered партнёра A +X, partner B −X», «profit netted …». Оригинальные
  realization-строки **не мутируются**. Read-model фолдит `оригиналы + true-up = settled
  position`. Те же числа — честная история. Сохранение держится, т.к. true-up — это
  **перераспределение** внутри венчура (Σ дельт по венчуру = 0), не создание денег.

### Read-model — один материализованный источник позиции

Таблица `PartnerPositionReadModel`, ключ `(agreement, procurement, partner, currency)`,
обновляется **транзакционно в том же atomic-блоке**, что и порождающая операция. Объединяет
оба слоя: реализованное (GROUP BY дименсионированного GL) + провизорное (свёртка
realization + true-up) + производный deployed.

- Заменяет все три live-узла; `_agreement_available_by_partner` удаляется как класс.
- **Полностью восстановим реплеем источников** → инвариант `replay(GL+провизор) == read-model`
  как anti-drift (ловит рассинхрон write/read-side).
- Чтения O(1) индексированным select (попутно убирает N×M-передеривание на рендере workspace) и
  даёт queryable read-side под E03.

### Явные типы вместо дискриминаторов

- Возврат капитала: явный тип/поле `return_kind ∈ {FROM_POOL, FROM_PROCEEDS}` (US-3). Дискриминатор
  по `CashEntry.account` удаляется во всех 3 местах.
- Профит→капитал: явный тип (US-1) вместо синтетических dividend+contribution.

### Принцип «честное событие, не подгонка» (сквозной)

Никакая производная не «подгоняется» подложными строками и не перетирается live. Любой пересчёт
(settlement-true-up, промежуточный/финальный net-recompute, профит→капитал) рождает **честное
append-only событие** с реальным экономическим смыслом. Read-model — функция от честных событий,
а не наоборот.

### Conservation — остаётся гейтом, но читается из чистых слоёв

3-карманный residual = JOIN (реализованное из GL) + (провизорное из слоя 2). **Точный 0 по
функциональному UZS** (Decimal), ε только на native-FX-ноге. Гейтит FINAL settlement и close
(как сейчас) — регресс невозможен незаметно.

## Доказательство эквивалентности (контракт с аудиторской сессией)

Золотые сценарии и эталонные цифры готовит **аудиторская сессия**; этот эпик с ними состыковывается.
Эквивалентность доказывается **четырьмя** калибрами на каждом golden-сценарии:

1. **Числа поле-в-поле:** `read-model(partner) == текущие procurement_venture_positions /
   partner_capital_positions(partner)` по всем полям.
2. **Сохранение:** `residual(pocket,currency)` = **точный 0** по UZS, ≤ε только на FX-ноге — тот
   же критерий, что гейтит FINAL/close сейчас.
3. **GL идентичен:** множество `JournalEntry`-строк по операции совпадает до и после (те же
   finance-вызовы; `JournalLine` вообще не меняется — дименсии живут в отдельном partnerships-owned
   tag-слое, money-суммы не двигаются) → Excel-replay и отчётность не меняются.
4. **Anti-drift:** `replay(источники) == read-model` на всех сценариях.

> Важно: дименсионирование — запись partnerships-owned тегов, ссылающихся на GL-строки, **не перенос
> денег** и **не изменение `JournalLine`**. Backfill тегов на исторические строки — read-only
> обогащение из `source_ref`, не money-миграция.

## План реализации

Каждая фаза **зелёная независимо**. **Никакого переноса живых денег в новую схему.**
Верификационная оснастка (shadow read-model, dual-read-сверки) — **временная**: удаляется в
финале, это доказательство эквивалентности, а не compatibility-слой.

### Фаза 1 — Честный профит→капитал (standalone, не зависит от архитектуры)
Убрать FROM_PROFIT-подделку: вместо `PartnerLedgerEntry.DIVIDEND_PAID` + фиктивного
`AgreementContribution` — **одна** честная запись «прибыль → капитал» (тот же GL-эффект:
профит-кэш операционка→пул, retained earnings 3200 → эквити партнёра). Те же цифры, честная
история. Ценно само по себе; шиппится первым.

### Фаза 2 — Декомпозиция `workspace.py` (behavior-preserving)
`workspace.py` (4406 строк) — **не денежное ядро**, поэтому денежные фазы E18 его НЕ уменьшат
(в отличие от venture/models/advances, которые усыхают как побочный эффект консолидации). Ему
нужна **отдельная** ранняя фаза: чистый перенос кода по границам, **без переписывания логики**,
ноль изменений в числах/GL/conservation. Размещена рано — сразу после Ф1, **до** денежных фаз,
чтобы они работали уже по чистым модулям. Продолжение паттерна, которым ранее был отколот
`workspace_support.py`. Полный аудит файла (trigger-map, кластеры, мёртвый код, швы) — ниже,
в разделе «Аудит `workspace.py`».

Метод (строго по шагам, не смешивать в одном коммите):
- **(a) Зафиксировать поведение.** Прогнать существующий suite; дописать характеризующие тесты
  на границе workspace-API для непокрытых путей; задокументировать trigger-map (что что вызывает).
- **(b) Первый вынос — read/payload-слой** (`build_workspace_payload` + всё семейство `_*_payload`,
  `_display`, `_flow_*`, money-neutral). Чистый перенос без переписывания логики; suite зелёный.
- **(c) Далее funding / payment / receive-кластеры** — чистый перенос. Сеть =
  `docs/money-equivalence-contract.md` (контракт аудита) + suite.
- **(d) Удаление доказанно-мёртвого кода** — **отдельным** шагом/коммитом ПОСЛЕ переноса, не в
  одном коммите с move (`_draft_cost_total_uzs`, `_payment_amount_for_terms` — доказательство ниже).
- **(e) После каждого шага** — воспроизвести те же сценарии + trigger-map, доказать идентичность поведения.

**Обязательные условия переноса (инварианты Фазы 2):**

1. **Ре-экспорт shell'а собран механически, не «на глаз».** Перед переносом — `grep` ВСЕХ внешних
   `from …workspace import` (views + serializers + 4 management-команды + ~10 тестов), развернуть
   многострочные `import (...)` в плоский список имён, и ре-экспортировать из `workspace.py`
   **ровно этот набор**. Заявленных 7–8 точек входа НЕдостаточно как источника истины — источник
   только grep. Цель: **ни один внешний импорт не падает** (поломка на импорте маскирует
   корректность переноса). Проверка: `python -c "import apps.partnerships.workspace"` + полный
   suite собирается.
2. **Межкластерные вызовы = DAG, без циклов.** Граф рёбер построен по коду (см. «Межкластерный DAG»
   в аудите): все рёбра ведут В funding (B); B ни в кого не звонит. Если при выносе появляется
   **взаимозависимая пара** — общий вызываемый **спускается в `workspace_common.py`**, ребро
   разрывается. **Ни один кластер не импортирует shell** (`workspace.py`); shell импортирует
   handler'ы из кластеров, не наоборот.
3. **Чистый перенос сохраняет дословно.** `@transaction.atomic`, `publish_event`/OutboxEvent-вызовы,
   любые декораторы и порядок сайд-эффектов переезжают **байт-в-байт**, без переписывания. Любой
   хелпер, используемый **≥2 кластерами**, имеет **единственный дом в `workspace_common.py`** и
   **НИКОГДА не копируется** (копия = два расходящихся источника правды).

### Фаза 3 — Золотой контракт + read-model как shadow
Совместно с аудитом заморозить golden-сценарии (входы → эталонные позиции + GL-строки +
conservation). Построить `PartnerPositionReadModel` в режиме **shadow** (вычисляется из текущих
источников, reads НЕ переключены). Доказать `read-model == 3 узла` поле-в-поле на всём сьюте +
`replay==read-model`.

### Фаза 4 — Дименсии реализованного слоя (tag-слой)
Завести partnerships-owned `PartnerJournalLineTag` (`journal_line FK→finance`, FK направлен
partnerships→finance; `JournalLine` не трогаем). Писать теги `{partner, agreement, procurement,
pocket}` **вперёд** транзакционно с журналом; best-effort backfill там, где `source_ref`
однозначен (теги, не деньги). Реализованные позиции (paid_in, dividends, capital returns,
repayments) читаются единым `GROUP BY` по tag-слою + join к `JournalLine` за суммами. Verify:
реализованный слой == прежние числа; GL-суммы и `JournalLine` не изменились.

### Фаза 5 — Явные типы + честный settlement-true-up
`return_kind` (FROM_POOL/FROM_PROCEEDS) на возврате → снос дискриминатора по `CashEntry.account`.
Net-пересчёт на settlement → честные `SETTLEMENT_TRUEUP`-события вместо live-перетирания. Verify:
golden + conservation **точный 0** UZS; история показывает реальные события.

### Фаза 6 — Переключение чтений на read-model
Позиции, conservation, close-гейты, сериализаторы читают единый read-model. Удалить 3 live-узла
+ `_agreement_available_by_partner`. Verify: API-ответы байт-в-байт; close-гейты идентичны;
conservation из слоёв = 0.

### Фаза 7 — Снос мёртвого/дублей + удаление оснастки
Удалить `CapitalAdvanceSettlement` (модель+enum), дедупнуть quantize/equity-map/operator-residue.
Денежные god-модули (venture/models/advances) к этому моменту уже усохли как побочный эффект
консолидации — отдельной декомпозиции не требуют (`workspace.py` декомпозирован в Ф2). **Удалить
shadow-оснастку** — она доказала эквивалентность и больше не нужна. Verify: сьют зелёный, оснастки нет.

### Фаза 8 — Тест-режим (канон валидности + property-based)
Разовая чистка сьюта по канону «тест валиден ⇔ ловит реальный регресс» (см. ниже). Перевод
ядра на golden + property-based (сохранение как свойство). Может стартовать в Фазе 3 (даёт
golden-контракт) и финализироваться здесь.

## Задачи (чек-лист)

### Фаза 1 — Честный профит→капитал ✅ (commit ниже, money sign-off APPROVE 2026-06-15)
- [x] T-1.1 Спроектировать честный тип/проводку «прибыль → капитал» (GL-эффект = текущему).
- [x] T-1.2 Заменить `_settle_partner_from_profit`: убрать фиктивные DIVIDEND_PAID + contribution.
- [x] T-1.3 Golden: FROM_PROFIT-сценарий — числа/GL/conservation идентичны; в истории нет фантомов.
  (+ conservation вариант A: тавтологичный карман убран → честный agreement-level кросс-чек `agreement_profit_reinvestment_residual` в close-гейте.)

### Фаза 2 — Декомпозиция `workspace.py` (behavior-preserving)
**Слайс 1 ✅ (лид-аудит PASS 2026-06-16):** import integrity ok, `makemigrations --check` чисто,
338 passed = бейзлайн, ни один кластер не импортирует shell, payload→common без цикла.
- [x] T-2.1 (a) Зафиксировать поведение: прогон suite + характеризующие тесты на границе
  workspace-API для непокрытых путей; задокументировать trigger-map.
- [x] T-2.2 (инвариант 1) `grep` всех внешних `from …workspace import` (views/serializers/4 команды/
  ~10 тестов), развернуть многострочные импорты в плоский список → собрать **точный** набор ре-экспорта
  shell'а. Проверка: `import apps.partnerships.workspace` + сборка suite не падает.
- [x] T-2.3 (инвариант 2) Построить/зафиксировать межкластерный DAG; вынести хелперы с ≥2 кластерами
  в `workspace_common.py` (`_require_workspace_agreement`, `_amount_uzs_to_currency`,
  `_with_client_request_id`, `_normalize_currency`+fx-семейство, `_expense_value_uzs`,
  `_has_capital_activity`, `_has_payment_activity`, generic `_add_amount`/`_coerce_datetime`).
  Лид-уточнение: `_agreement_available_by_partner` — это A+B (≥2 кластера) → **остаётся в
  `workspace_common`** (не мигрирует в funding); удаляется в Фазе 6 при переходе на read-model.
- [x] T-2.4 (b) Первый вынос — read/payload-слой → `workspace_payload.py` (`build_workspace_payload` +
  `_*_payload` + `_display`/`_flow_*`, money-neutral); чистый перенос; suite зелёный.
- [x] T-2.5 (c) `workspace_funding.py` (10 B-функций) ✅ лид-аудит PASS 2026-06-16: 338 passed,
  makemigrations чисто, без shell-импортов/циклов. Call-graph поправил 3 размещения:
  `_spend_allocated_partnership_capital`→funding (B-only), `_receive_funding_breakdown`+
  `_ensure_source_editable`→common (≥2 кластера). `workspace.py` 4406→2693.
- [x] T-2.6 (c) `workspace_payment.py` ✅ лид-аудит PASS 2026-06-16: 338 passed, makemigrations чисто,
  без shell-импортов/циклов. `_has_procurement_cost_payment` оставлен в payment как доменный предикат
  (импортируется D/E-guard'ом, ацикл — прецедент `_payment_status_block`); `_resolve_action_datetime`/
  `_draft_cost_total_in_obligation_currency` — C-only. `workspace.py` 108083→84862 байт.
- [x] T-2.7 (c) `workspace_receive.py` ✅ лид-аудит PASS 2026-06-16: 338 passed, makemigrations чисто,
  без shell-импортов/циклов; receive корректно импортирует funding-версии `_pre_allocate`/
  `_resolve_workspace_capital_snapshot`. Call-graph добавил receive-only `_check_prepaid_coverage`/
  `_receivable_line_states`; `_landed_expense_allocations` остаётся в common (A+D). `workspace.py` 85k→52k байт.
  ⚠️ Вскрыто: 2 shadow-def в shell со слайса 2 (дубли funding) — мёртвые, в T-2.9.
- [ ] T-2.8 (c) `workspace_amendments.py` (source/lines/settlement/amend/split/cancel); сеть = то же.
- [ ] T-2.9 (d) **Отдельным коммитом** удалить доказанно-мёртвый код (`_draft_cost_total_uzs`,
  `_payment_amount_for_terms`) **+ 2 shadow-def в `workspace.py`** (`_pre_allocate_at_receipt_partnership_capital`,
  `_resolve_workspace_capital_snapshot` — дубли funding со слайса 2, ноль вызовов; сохранить
  import-из-funding для re-export) — после переносов, не вместе с move. Сверить дубль-сканом = 0.
- [ ] T-2.10 (инвариант 3 + e) После каждого шага: дословность (`@transaction.atomic`/publish_event/
  декораторы) сохранена; те же сценарии + trigger-map → доказать идентичность; ни один кластер не импортирует shell.
- [ ] T-2.11 Acceptance: `makemigrations --check` чисто; полный suite зелёный; ноль изменений
  в числах/GL/conservation; `workspace.py` заметно меньше + новые модули по границам.

### Фаза 3 — Золотой контракт + shadow read-model
- [ ] T-3.1 Состыковать golden-контракт с аудиторской сессией (входы/эталоны/residual).
- [ ] T-3.2 `PartnerPositionReadModel` (схема, ключ, транзакционное обновление) в shadow-режиме.
- [ ] T-3.3 Dual-read сверка `read-model == 3 узла` поле-в-поле на всём сьюте.
- [ ] T-3.4 Инвариант `replay==read-model` как тест.

### Фаза 4 — Дименсии реализованного слоя (tag-слой)
- [ ] T-4.1 Завести partnerships-owned `PartnerJournalLineTag` (`journal_line FK→finance`,
  partner/agreement/procurement/pocket; FK направлен partnerships→finance; `JournalLine` не трогаем).
- [ ] T-4.2 Писать теги на всех партнёр-гранулярных проводках (вперёд, транзакционно с журналом).
- [ ] T-4.3 Best-effort backfill тегов по однозначному `source_ref` (теги, не деньги).
- [ ] T-4.4 Реализованные позиции через `GROUP BY` tag-слой + join к `JournalLine`; verify == прежние.

### Фаза 5 — Явные типы + честный true-up
- [ ] T-5.1 `return_kind` на возврате; снос дискриминатора по `CashEntry.account` (3 места).
- [ ] T-5.2 `SETTLEMENT_TRUEUP`-события; net-пересчёт перестаёт перетирать live.
- [ ] T-5.3 Verify: conservation точный 0 UZS; honest history.

### Фаза 6 — Переключение чтений
- [ ] T-6.1 Позиции/conservation/close-гейты/сериализаторы → read-model.
- [ ] T-6.2 Удалить `procurement_venture_positions`/`partner_capital_positions`-live +
  `_agreement_available_by_partner`.
- [ ] T-6.3 Verify: API байт-в-байт, close-гейты идентичны.

### Фаза 7 — Чистка + снос оснастки
- [ ] T-7.1 Удалить `CapitalAdvanceSettlement` (модель+enum).
- [ ] T-7.2 Дедуп quantize (×5) / equity-map (×2) / operator-residue (×4) → по одному.
- [ ] T-7.3 Удалить shadow/dual-read оснастку (venture/models/advances уже усохли через консолидацию).

### Фаза 8 — Тест-режим
- [ ] T-8.1 Аудит сьюта: для каждого money-теста «какой реальный баг ловит?»; нет ответа → удалить/переписать.
- [ ] T-8.2 Property-based: «любая последовательность событий → каждый карман Σ=0».
- [ ] T-8.3 Ужесточить ε: точный 0 по UZS-карманам, ε только native-FX. Вкл. close-гейт
  `agreement_profit_reinvestment_residual` (сейчас `_EPS=0.01`, Ф1 reviewer-note 2026-06-15) → точный 0 по UZS.

## Аудит `workspace.py` (приложение к Фазе 2)

Фактический аудит на 2026-06-15 (95 top-level defs, 4406 строк). Привязки `file:line` — для границ.

### Точки входа (вызываются извне workspace.py)

Импортируются из `views.py` / `serializers.py` + management-команд:
`create_workspace` (131), `build_workspace_payload` (165, читается и в serializers.py),
`workspace_queryset` (211), `dispatch_workspace_action` (409), `allocate_workspace_capital` (1434),
`build_workspace_capital_allocation_preview` (1608), `reverse_workspace_receive_batch` (614),
`apply_items_amendment` (729). Всё прочее — **внутренние хелперы** (вызываются только изнутри).

**`dispatch_workspace_action` (409)** — единственный action-диспетчер, маршрутизирует 18 действий
в handler'ы (все — внутренние функции этого же файла; `GENERATE_INSTALLMENT_SCHEDULE` уходит в
`workspace_support`):
UPDATE_SOURCE→`update_workspace_source`, UPDATE_SETTLEMENT→`update_workspace_settlement`,
UPDATE_LINES→`update_workspace_lines`, SPLIT_ITEM→`split_workspace_item`, PAY_COSTS→`pay_workspace_costs`,
RESOLVE_OVERPAYMENT→`resolve_workspace_overpayment`, PAY_SUPPLIER_PAYABLE→`pay_workspace_supplier_payable`,
CREATE_INVESTMENT_AGREEMENT→`create_and_link_workspace_agreement`, LINK_INVESTMENT_AGREEMENT→`link_workspace_agreement`,
RECORD_CAPITAL_CONTRIBUTION→`record_workspace_capital_contribution`, ALLOCATE_CAPITAL→`allocate_workspace_capital`,
CONVERT_CAPITAL_POOL→`convert_workspace_capital_pool`, RECEIVE_BATCH→`receive_workspace_batch`,
CANCEL_PROCUREMENT→`cancel_workspace_procurement`, REVERSE_BATCH→`reverse_workspace_receive_batch`,
AMEND_ITEMS→`apply_items_amendment`, AMEND_EXPENSES→`apply_expenses_amendment`.

### Cohesion-кластеры (кандидатные границы модулей)

- **A. read/payload (money-neutral)** — `build_workspace_payload` (165) + `_display` (2589),
  `_policy_payload`/`_flow_payload`/`_flow_step`/`_funding_flow_complete`/`_payment_obligation_complete`
  (2607–2799), `_allowed_action_keys`/`_first_blocker`/`_readiness_payload`/`_sections_payload`/
  `_documents_payload` (2829–2940), `_item_payload`/`_expense_payload`/`_payment_status_block`/
  `_settlement_payload`/`_payable_payload`/`_payment_payload`/`_investment_payload`/`_receive_batch_payload`/
  `_summaries_payload`/`_history_payload` (2941–3360), `_section_key`/`_legacy_payment_state` (3361/3493),
  `_payments_for_procurement` (3785). **Кандидат на ПЕРВЫЙ вынос (шаг b).** Шов: `_investment_payload`
  читает `_agreement_available_by_partner` (позиционный шов — см. ниже).
- **B. funding / капитал** — `create_and_link_workspace_agreement`/`link_workspace_agreement` (1309/1343),
  `record_workspace_capital_contribution`/`convert_workspace_capital_pool`/`allocate_workspace_capital`/
  `build_workspace_capital_allocation_preview` (1360–1672), `_resolve_workspace_capital_snapshot` (3874),
  `_pre_allocate_at_receipt_partnership_capital` (3799), `_procurement_capital_available_by_partner` (4018),
  `_auto_capital_amounts` (4049), `_agreement_available_by_partner` (4370), `_require_workspace_agreement` (4347).
- **C. payment** — `pay_workspace_costs` (1672), `resolve_workspace_overpayment` (1778),
  `_record_own_funds_overpayment_refund` (1849), `_return_partnership_overpayment_to_pool` (1958),
  `_resolve_overpayment_partner_splits` (2141), `pay_workspace_supplier_payable` (2194),
  `_has_procurement_cost_payment` (3484).
- **D. receive** — `receive_workspace_batch` (2247), `reverse_workspace_receive_batch` (614),
  `_sync_procurement_status_after_reversal`/`_after_receive` (714/4080), `_receive_funding_breakdown` (4100),
  `_partnership_receive_lines_already_paid` (4138), `_prepaid_partnership_receive_base_cost` (4146),
  `_spend_allocated_partnership_capital` (4168), `_fund_partnership_receive_from_pools` (4218),
  `_ensure_supplier_payable_after_receive` (4283), `_record_receive_journal` (4308),
  `_expenses_for_receive` (3658), `_landed_expense_allocations` (3685).
- **E. amendments / source / lines** — `update_workspace_source`/`update_workspace_settlement`/
  `update_workspace_lines` (233–316), `_resync_draft_terms_total` (371), `apply_items_amendment`/
  `apply_expenses_amendment` (729/805), `split_workspace_item` (1187), `cancel_workspace_procurement` (565),
  семейство `_upsert_*`/`_amendment_*`/`_draft_*_for_update`/`_replace_expense_targets` (897–1308),
  `_ensure_source_editable`/`_validate_source_transition` (4384/4398), `_items_snapshot`/`_expenses_snapshot`.
- **F. action-диспетчер** — `dispatch_workspace_action` (409) — тонкий роутер; остаётся точкой входа
  (в shell `workspace.py`), импортирует handler'ы из кластеров B–E. **Ни один кластер не импортирует shell.**
- **G. shared-хелперы → `workspace_common.py`** (новый модуль, НЕ `workspace_support.py`: support — это
  доменный модуль agreement/terms/ledger, а не утилиты; существующие `money`/`ratio`/`functional_uzs`
  в support **остаются на месте**). Сюда: `create_workspace` (131), `workspace_queryset` (211),
  currency/value-математика (`_primary_currency`/`_normalize_currency`/`_resolve_*_fx_rate`/`_item_value_uzs`/
  `_expense_*_value_uzs`/`_remaining_obligation_cost_*`/`_derive_items_currency`), `_with_client_request_id`/
  `_add_amount`/`_coerce_datetime`. Конкретный список «общих для ≥2 кластеров» — в DAG ниже.

### Межкластерный DAG (рёбра построены по коду)

Рёбра между кластерами по фактическим call-site (caller-line → cluster):

- **D (receive) → B (funding):** `_resolve_workspace_capital_snapshot` (B:3874, зовётся из receive:2385),
  `_pre_allocate_at_receipt_partnership_capital` (B:3799, из receive:2377,2571).
- **A (payload) → B (funding):** `_agreement_available_by_partner` (B:4370, из `_investment_payload`:3129).
- **F (shell) → B/C/D/E:** диспетчер зовёт handler'ы.

**Все рёбра ведут В funding (B); B ни в один кластер не звонит → граф ацикличен.** Цикла receive↔funding
нет: общие точки — это funding-функции, вызываемые из receive (D→B), и вынесенные в common хелперы.

**Хелперы, общие для ≥2 кластеров → единственный дом в `workspace_common.py` (доказано по callers):**
`_require_workspace_agreement` (B,C,D), `_amount_uzs_to_currency` (B,D), `_with_client_request_id` (B,C),
`_normalize_currency` (shell,E,C + fx-семейство), `_expense_value_uzs` (E,D), `_has_capital_activity` (A,E),
`_has_payment_activity` (A,E). Generic-утили (`_add_amount`, `_coerce_datetime`, `_primary_currency`,
`_item_value_uzs`) — туда же по природе, даже если сейчас 1 кластер. **Никогда не копировать — только переносить.**

### Кандидаты в мёртвый код (с доказательством)

- **`_draft_cost_total_uzs` (3749)** — **0 вызовов** в prod и тестах (только строка определения).
  Вероятно вытеснен `_draft_cost_total_in_obligation_currency` (3754, жив). → удалить (шаг d).
- **`_payment_amount_for_terms` (2809)** — **0 вызовов** в prod и тестах. → удалить (шаг d).

> Проверено: `grep -rInw <name> apps --include=*.py` даёт только def-строку. Удаление — отдельным
> коммитом после переносов (шаг d), не вместе с move.

### Швы (что поедет при денежных фазах E18)

- **Finance-шов:** кластеры **C (payment)**, **D (receive)**, **B (funding)** вызывают
  `create_cash_entry` / `create_journal_entry` / `record_journal_from_cash_entry` /
  `record_capital_pool_payment` (workspace.py:1922,1931,2050,4203,4262,4324) и
  `create_payable_from_procurement` (suppliers). **Именно здесь Фаза 4 (tag-слой)** будет дописывать
  `PartnerJournalLineTag` к проводкам — т.е. дименсии встают по этим швам. Декомпозиция в Ф2 их
  изолирует → Ф4 правит чистые модули, а не god-файл.
- **Позиционный шов:** `_agreement_available_by_partner` (4370) — это **3-й live-узел позиций**,
  подлежащий удалению в **Фазе 6**. Его читают кластеры B (allocate preview 1645, snapshot 3829),
  A (`_investment_payload` 3129) и D (pre-allocate 1497). При выносе оставить его в кластере B как
  единственный носитель; Ф6 заменит тело на чтение read-model — точечно, в одном модуле, а не по файлу.

## Тест-режим (канон валидности)

67 тест-файлов, значимая часть — «зелёные ради зелёных». **Тест валиден ⇔ ловит реальный регресс.**
Допустим, только если делает хотя бы одно:
1. проверяет **реальное движение денег** (GL-строки сбалансированы и совпадают с эталоном), или
2. проверяет **бизнес-инвариант** (`conservation residual=0`; `Σprofit_share=1`; `net` сходится;
   `replay==read-model`), или
3. **падал бы на конкретном реальном регрессе** (тот самый double-count S1/S4).

**Запрещены как самоцель:** «функция вернула dict с ключом X», «поле сериализатора присутствует»,
«создалась строка» без проверки экономики — ложная уверенность + стоимость поддержки без
anti-regression-ценности. **Сдвиг формы:** golden-сценарии + property-based вместо примерно-богатых
unit-тестов. **Метрика чистки:** нет ответа на «какой баг ловит» → удалить/переписать в инвариант.

## Открытые вопросы

Все архитектурные/денежные развилки закрыты владельцем 2026-06-15 — см. «Решённые вопросы».
Остаётся go/no-go по фазам.

- ⚠️ **Шов functional-currency (учесть в read-model/conservation, НЕ реализовывать в E18).**
  Функциональная валюта сейчас захардкожена `UZS` (`_uzs`-поля, литерал `'UZS'` в
  `venture_conservation`, GL). В read-model/tag/conservation **не хардкодить функциональный
  литерал** — параметризовать как «functional currency тенанта» (дефолт UZS), чтобы будущий
  переход на базовую валюту бизнеса (USD-бизнес) был флипом конфига + сменой fx-резолва, а не
  перепроектированием read-model. Сам переход — отдельный будущий эпic (см. backlog), строить при
  появлении non-UZS-бизнеса. Связано: FROM_PROFIT non-UZS и [[E13]] mixed-currency приход.

## Решённые вопросы (история)

- ✓ 2026-06-15: Большой rewrite в один новый event-журнал (раздел C аудита) → **отклонён** после
  собственного red-team как заякоренный (вектор «event-log+projection+CQRS» был задан владельцем,
  не выведен независимо) и мис-скейленный (CQRS «под масштаб» не оправдан на этом масштабе;
  унификация сливала реализованное и провизорное; наивысший миграционный риск на живых деньгах).
- ✓ 2026-06-15: Принят синтез — **дименсионированный GL (реализованное) + тонкий провизорный слой
  (сплит до settlement) + один материализованный read-model + явные типы**. Чище C: нет
  дублирования GL, уважает реализованное vs провизорное, near-zero миграционный риск.
- ✓ 2026-06-15: Принцип **«честное событие, не подгонка»** — обязателен для FROM_PROFIT (Фаза 1),
  settlement-true-up и net-пересчётов; никаких подложных строк и live-перетирания.
- ✓ 2026-06-15: Сохранение — **точный 0 по функциональному UZS**, ε допустим только на native-FX-ноге.
- ✓ 2026-06-15: **Носитель дименсий (развилка №1)** → **partnerships-owned `PartnerJournalLineTag`**
  (`journal_line FK→finance`, partner/agreement/procurement/pocket; FK направлен partnerships→finance;
  `JournalLine` не трогаем). Колонки прямо на `JournalLine` **отклонены**: связывали бы finance с
  partnerships (ломая однонаправленность слоёв), давали бы NULL-колонки у большинства не-партнёрских
  проводок, а перф-выигрыш на нашем масштабе несостоятелен (один join — микросекунды). Generic-механизм
  дименсий в finance — **только при появлении второго потребителя** (sales/расходы/экосистема), не раньше
  (иначе спекулятивная общность). finance остаётся домен-агностичным.
- ✓ 2026-06-15: **Read-model (развилка №2)** → **материализованная таблица** (queryable под E03,
  anti-drift через replay; ценой транзакционного обновления).
- ✓ 2026-06-15: **Таблицы намерения (развилка №3)** → **сохранить** как intent/идемпотентность/аудит;
  **деньги из них не читать никогда** — только GL + tag-слой. Коллапс не делаем (избегаем миграции).
- ✓ 2026-06-15: **Backfill (развилка №4)** → **вперёд + best-effort** по однозначному `source_ref`;
  неоднозначную историю читать через legacy-путь до естественного истечения.
- ✓ 2026-06-15: **Декомпозиция god-модулей (развилка №5, уточнено)** → разделено по природе модуля:
  **(1) денежные god-модули** (`venture.py`/`models.py`/`advances.py`) **усыхают как побочный эффект**
  консолидации (3 узла→read-model, явные типы, снос дублей) — **отдельной работы не требуют**;
  **(2) `workspace.py`** — **НЕ денежное ядро**, денежные фазы E18 его не уменьшат, поэтому ему нужна
  **отдельная явная фаза** (Фаза 2, behavior-preserving, ранняя) — продолжение паттерна откола
  `workspace_support.py`. Полную нарезку прочих god-модулей сверх этого — отдельным cleanup-эпиком,
  если разрастётся.
- ✓ 2026-06-15: **Раскладка декомпозиции `workspace.py` — одобрена** (7 кластеров A–G). Модули:
  `workspace_payload` / `workspace_funding` / `workspace_payment` / `workspace_receive` /
  `workspace_amendments` / `workspace.py` (shell: dispatcher+create+queryset+ре-экспорты) /
  `workspace_common.py`. **Старт при go: Фаза 1 → Фаза 2, read/payload выносится первым.**
- ✓ 2026-06-15: **Decomp-OQ1** (единственный `_agreement_available_by_partner`) → **принято**: держать
  единственный экземпляр в `workspace_funding` до его замены на чтение read-model в Фазе 6.
- ✓ 2026-06-15: **Decomp-OQ2 переигран** → generic-хелперы кластера G идут в **новый `workspace_common.py`**,
  НЕ в `workspace_support.py` (support — доменный модуль agreement/terms/ledger, а не утили). Существующие
  `money`/`ratio`/`functional_uzs` в `workspace_support.py` остаются на месте.
- ✓ 2026-06-15: **Инварианты Фазы 2** зафиксированы: (1) ре-экспорт shell'а собран механически из grep
  всех внешних импортов (не «на глаз»), ни один импорт не падает; (2) межкластерные вызовы = DAG без
  циклов (все рёбра в funding; common разрывает любую взаимозависимость; кластеры не импортируют shell);
  (3) чистый перенос дословно сохраняет `@transaction.atomic`/publish_event/декораторы, хелпер ≥2
  кластеров — единственный дом в `workspace_common.py`, никогда не копируется.
