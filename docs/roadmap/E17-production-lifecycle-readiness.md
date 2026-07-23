# E17 — Production Lifecycle Readiness: Venture Close, Single Truth & UI Flow

**Статус:** `DONE` (закрыт 2026-06-15)
**Прогресс:** 100% — Фазы 1–5 done; acceptance 11/11 (S1–S11, S4 закрыт commit b62a3e1, conservation зелёный во всех). Фаза 6 (Excel-replay) закрыта как **не-применимая** — см. «Решённые вопросы».
**Зависит от:** E16
**Блокирует:** first-client pilot, E03, E06

---

## Цель

Довести партнёрский цикл до состояния, где первый клиент может пройти полный путь без
рассинхрона: приход → продажи/возвраты/списания → сверка → выплаты/погашения → закрытие.

Главный принцип: **одна денежная правда, один lifecycle, никакие деньги не исчезают и не
возникают из ниоткуда.**

## Контекст и обоснование

E16 закрыл ядро экономики: venture-netting, recovered capital, cross-currency FX,
partner-liability. Но вокруг ядра остались швы:

- часть старых отчётов/кабинетов ещё читает `PartnerLedgerEntry`;
- старая модель `CapitalAdvance` дублирует смысл взаиморасчётов;
- есть `FINAL settlement`, но нет полноценного `close` прихода/договора;
- после финальной сверки нет жёсткого lock жизненного цикла;
- возвраты не имеют полноценного idempotency-контракта;
- не все backend-операции имеют понятную UI-точку.

Эти швы нельзя оставлять как “потом”: в деньгах и партнёрском учёте технический долг быстро
становится продуктовым риском.

## Целевая модель

### Один источник правды

Для партнёрской экономики целевой источник правды — `ProcurementSaleRealization`,
`ProcurementVentureSettlement` и `procurement_venture_positions`.

`PartnerLedgerEntry` остаётся только для физически нужных событий денег/истории:
capital in/out, dividend paid и audit, но не как источник расчёта прибыли венчура.

### CapitalAdvance

`CapitalAdvance` — старая модель “один партнёр временно покрыл долю другого”.
Целевой путь: новые взаиморасчёты считаются через net-position договора/венчура.

Новые receive-flow не должны автоматически создавать `CapitalAdvance`. Старые таблицы можно
оставить для истории/миграции, но UI и guards не должны опираться на них как на активную
денежную модель.

**Важно (не только запись, но и чтение):** недостаточно «перестать создавать». Ни один
guard, расчёт позиции, payout-проверка или отчёт не должны **читать** `CapitalAdvance`
для денежных решений — иначе остаётся вторая правда. Целевое состояние: единственный
источник взаиморасчётов — net-position; `CapitalAdvance` нигде не участвует в расчёте
доступности/долга/выплат.

### Final settlement и close

`FINAL settlement` — это бухгалтерская фиксация результата венчура, но не само закрытие.

`Close procurement` разрешён только если:

- есть `FINAL settlement`;
- нет активного товара по приходу;
- нет отрицательных позиций;
- нет необработанных claim'ов, которые требуют явного решения;
- все backend/UI действия, меняющие экономику венчура, заблокированы после close.

`Close agreement` разрешён только если:

- все приходы договора закрыты;
- все net-позиции сторон сведены;
- нет доступного к выводу капитала/прибыли без решения;
- договор становится read-only.

### Negative position простыми словами

Это долг партнёра перед венчуром. Возникает, когда партнёр:

- вывел больше, чем ему положено после последующих убытков/коррекций;
- по своей вине уничтожил/потерял товар и должен восстановить капитал других;
- получил возврат капитала/прибыли, но после возврата/сторно его доля уменьшилась.

Пока есть negative position:

- вывод прибыли блокируется;
- вывод капитала блокируется или ограничивается безопасной частью;
- UI показывает понятное действие “Погасить долг”;
- погашение делается явно: деньгами или зачётом из будущей прибыли.

### Conservation invariant (дизайн — safety-critical)

Это формальный «закон сохранения денег»: ничто не появляется из ниоткуда и не исчезает.
Он не калькулятор «как хочется», а контрольный замок: если не сходится — закрытие
запрещено, расхождение показывается, цифры не подгоняются.

**Три кармана.** Деньги венчура живут в трёх местах, и инвариант обязан свести их
**все сразу**, иначе утечка на стыке пройдёт незамеченной:

1. **Капитал-пул договора** (COA 1300) — внесённый партнёрами капитал до развёртывания.
2. **Операционная касса** — куда падает выручка продаж.
3. **Claim'ы партнёров** — что положено, но ещё не выплачено.

**Полнота: в инвариант обязаны входить ВСЕ источники и стоки** (иначе ложное «сошлось»):
- источники IN: развёрнутый капитал (Σ capital_share × cost прихода) + собранная денежная
  выручка (cash, кредит-продажи отдельно как receivable, не как cash);
- стоки/держатели: COGS (капитал → товар), capital recovered, profit entitlement, losses,
  partner-liability (receivable с виновного), выплаченные дивиденды, возвращённый капитал,
  остаток товара по себестоимости, **FX gain/loss на капитале**.

**Тождество (нетто = 0, в пределах ε округления):**
`Σ deployed_capital + Σ sale_proceeds = Σ capital_recovered + Σ profit_entitlement
 − Σ loss + Σ partner_liability_receivable + Σ paid_out + Σ remaining_inventory_at_cost
 + Σ fx_gain_loss`

**Валюта.** Считать в функциональном UZS консистентно; для нативных ног (капитал/выручка
в разных валютах) проверять **и по каждой валюте отдельно** — иначе кросс-валюта даст
ложное «не сходится». Конкретную алгебру выводит реализатор; аудитор подтверждает GAP=0
прогоном по матрице сценариев (прибыль/убыток/смешанный/кросс-валюта/возврат/liability).

**Источник — только append-only события** (realizations, settlements, cash entries,
withdrawals, dividends). Никаких ручных вводов и подгона. Если |residual| > ε — close
**заблокирован**, residual показан с разбивкой по компонентам.

**Где проверяется:** на FINAL settlement, как precondition close_procurement, и на
close_agreement (сумма венчуров + сверка пула).

### Claim ≠ ликвидность

Инвариант доказывает сохранение **прав** (entitlement), но НЕ что кэш физически есть в
нужной валюте. Пример: выручка пришла в UZS, а возврат капитала инвестору положен в USD.
Поэтому close отдельно различает:
- entitlement **обработан** (выплачен ИЛИ явно зафиксирован как финальный долг) — ок;
- entitlement **висит** (положен, но нечем выплатить) — close запрещён.

Невыплатимый claim нельзя молча уронить, чтобы «закрыть». Только: явная конвертация (sarf)
→ выплата, ИЛИ фиксация как явный финальный долг с согласия сторон. Никогда — тихо.

## Сценарии (use cases)

- **US-1. Полный прибыльный цикл.** Товар продан, сделан `FINAL settlement`, капитал и прибыль
  выплачены, приход закрыт, договор закрыт.
- **US-2. Убыток после предварительного вывода.** Партнёр вывел раньше, затем убыток создал
  долг; система блокирует новые выплаты и требует погашения.
- **US-3. Partner-liability.** Товар потерян по вине бизнеса/оператора; капитал невиновного
  партнёра становится возвратным, виновный получает долг.
- **US-4. Возврат товара.** Повторный submit не создаёт второй возврат; realization сторнируется
  идемпотентно.
- **US-5. Договор с несколькими приходами.** Каждый приход закрывается отдельно; договор
  закрывается только после всех закрытых приходов и сведённых расчётов.
- **US-6. UI-only пользовательский путь.** Все ключевые операции доступны из интерфейса:
  сверка, выплаты, погашение долга, закрытие прихода, закрытие договора.
- **US-7. Claim в другой валюте.** Партнёру положен возврат капитала в USD, а кэш есть в UZS:
  система не закрывает молча — требует явную конвертацию (sarf) либо фиксацию финального долга.
- **US-8. Возврат после FINAL (до close).** Сторно/возврат уже после финальной сверки, но до
  закрытия, корректно пересчитывает позиции/FX и инвариант остаётся = 0.

## Текущее состояние

- ✅ **Что уже есть:** E16 venture positions, realization, settlement snapshots, payout preview,
  recovered-capital return UI, settlement card на приходе.
- ⚠️ **Что начато, но не завершено:** часть reports/investor views всё ещё может читать старый
  ledger; `CapitalAdvance` жив рядом с новой net-position моделью; close-flow не связан с
  settlement.
- ❌ **Чего нет:** clean close actions, read-only lock после close, единый proof conservation
  invariant, полный UI-flow для закрытия и negative-position repayment, idempotent returns.

## План реализации

> **Рекомендуемый порядок (зависимости), уточнён аудитом 2026-06-07:**
> Фаза 1 ✅ → Фаза 2 → **Фаза 4 (conservation invariant + idempotency + N+1)** →
> **Фаза 3 (close)** → Фаза 5 (UI) → Фаза 6 (replay).
> Причина: conservation invariant — это **гейт закрытия** (close разрешён только при
> |residual| = 0). Значит инвариант строится РАНЬШЕ close, иначе close какое-то время
> закрывал бы венчур без доказательства сохранения денег — это и есть тот компромисс,
> которого мы избегаем. Idempotency и N+1 из Фазы 4 независимы и делаются заодно.

### Фаза 1 — Proof & Source-of-Truth Cutover — ✅ ВЫПОЛНЕНО (коммит c02b980, аудит зелёный)

Доказать рассинхрон старых и новых источников, затем перевести читателей на venture-модель.
Не удалять старые таблицы механически, но убрать их из активного расчёта партнёрской прибыли.

### Фаза 2 — Retire Active CapitalAdvance Workflow

Остановить создание новых `CapitalAdvance` в receive-flow. Взаиморасчёты считать через
agreement/venture net positions. Старые endpoints либо убрать из UI, либо оставить только как
legacy read-only до миграции.

### Фаза 3 — Close Lifecycle & Locks

Добавить `close procurement` и `close agreement` как доменные действия. Связать их с
blocking reasons, final settlement, negative positions и read-only lock.

### Фаза 4 — Idempotency & Conservation Guards

Закрыть повторные submit-риски и добавить invariant checks, которые запрещают закрытие при
денежном расхождении.

### Фаза 5 — UI Flow Completion

Дать пользователю все нужные действия в интерфейсе: закрыть приход, закрыть договор, погасить
долг, увидеть blocking reasons, понять что именно мешает закрытию.

### Фаза 6 — End-to-End Replay

Прогнать реальные Excel-сценарии через UI/API-like путь и сверить отчёты, кассы, капитал,
прибыль, долги, закрытие.

## Задачи (чек-лист)

### Фаза 1 — Source of truth — ✅ ВЫПОЛНЕНО (c02b980, аудит зелёный)
- [x] T-1.1 Написать proof-test: старый `PartnerLedgerEntry` vs venture positions расходятся на
  смешанном прибыль/убыток венчуре. (test_e17_lifecycle: legacy 540k vs venture 380k, overstatement 160k)
- [x] T-1.2 Перевести investor dashboard/detail на venture buckets. (get_partner_aggregate venture-backed)
- [x] T-1.3 Перевести finance reports / profitability rows на venture buckets.
- [x] T-1.4 Перевести sale explanations на venture realization. (+ фронт SaleExplanationView → realization_entries)
- [x] T-1.5 Прекратить писать `PROFIT_ACCRUED`, `PROFIT_REVERSED`, `LOSS_INCURRED` как активный
  источник партнёрской экономики для новых E16-flow.
- [x] T-1.6 Оставить `PartnerLedgerEntry` только для physical/audit событий, где это реально
  нужно.
- [x] T-1.7 (F4) Очистить контракт `partner_capital_positions`: нативные суммы с явным `currency`,
  функциональные — суффикс `_uzs`, не складываются. (закрыто)

### Фаза 2 — CapitalAdvance cleanup — ✅ ВЫПОЛНЕНО (аудит зелёный)
- [x] T-2.1 Остановить автоматическое `CapitalAdvance.objects.create(...)` на receive.
- [x] T-2.2 Перенести UI взаиморасчётов на net-position model без legacy advance endpoints.
  (фронт уже был на `fetchCapitalPositions`/`settlePartnerCapital`; удалён мёртвый advance-api)
- [x] T-2.3 Убрать `advances/settle-advance` из активного UI/API workflow (endpoints+сериализаторы сняты).
- [x] T-2.4 E14/E15 тесты переписаны на net-position; retired-фича (FROM_PROFIT auto-settle) удалена.
- [x] T-2.5 Все READER'ы `CapitalAdvance` убраны из денежных путей. `partner_capital_positions`
  считает gap из batch-allocations+contributions+venture; CapitalAdvance остался только как
  модель/таблица (история), мёртвые сервис-функции удалены. Решение: `default_advance_repayment_mode`
  удалён (поле+enum+миграция 0025).

### Фаза 3 — Close lifecycle — ✅ ВЫПОЛНЕНО (аудит зелёный)
- [x] T-3.1 `close_procurement_venture` + `procurement_close_blocking_reasons` (идемпотентно, переход через `.update()`).
- [x] T-3.2 Гейты close procurement: FINAL settlement / нет active lots / нет negative position /
  conservation residual=0 (переиспользует `venture_conservation`) / нет висящих claim'ов (T-4.6).
- [x] T-3.3 Read-only lock `assert_procurement_open` в settlement/writeoff/dividend/withdrawal/return;
  sale заблокирован by-construction.
- [x] T-3.4 `close_investment_agreement` + `agreement_close_blocking_reasons` (read-only после close).
- [x] T-3.5 Гейты close agreement: все приходы CLOSED / net-позиции=0 / пул сведён (валюто-aware) /
  нет висящих claim'ов / `ConservationReport.merge` по венчурам = 0.
- [x] T-3.6 18 тестов: каждый гейт блокирует инъекцию (нет FINAL / активный лот / neg position /
  residual≠0 / висящий claim / net≠0 / пул не сведён), read-only после close, happy full close, идемпотентность.

### Фаза 4 — Idempotency & conservation — ✅ ВЫПОЛНЕНО (аудит зелёный; T-4.6 → Фаза 3)
- [x] T-4.1 Добавить `client_request_id` в return API/service (поле `Return.client_request_id` + миграция 0004).
- [x] T-4.2 `process_return` идемпотентен по `client_request_id`; realization-реверс — по source_ref/reversal_of.
- [x] T-4.3 `venture_conservation`: три кармана (capital/proceeds/distribution), все источники/стоки
  (вкл. FX-ногу и partner-liability), только append-only события, без ручного подгона.
- [x] T-4.4 Валюто-aware: функц. UZS (точный 0) И нативная cost-валюта (deployed=recovered+loss+remaining+PLR,
  через buy-FX); per-pocket × per-currency, без master-sum.
- [x] T-4.5 FINAL settlement блокируется при `|residual|>ε` с разбивкой по компонентам (без подгона).
- [x] T-4.6 Claim ≠ ликвидность — реализован в Фазе 3 close: висящий claim (available capital|profit>0,
  не выплачен/не зафиксирован) блокирует close с понятной причиной (выплатить / sarf / явный долг).
- [x] T-4.7 (F6) Перф/N+1: `_realization_groups` считается один раз и прокидывается во все нетто-хелперы
  (`groups=`); агрегаты батчем; import'ы вне циклов.
- [x] T-4.8 Тесты-матрица (14): profit / loss / mixed-netting / cross-currency (рост+падение) /
  partner-liability / **partner-liability × cross-currency** / return RESTOCK+DISPOSE / FINAL settlement /
  idempotent repeated return / over-withdrawal→loss / FINAL-gate блокирует инъекцию — GAP=0 везде.

### Фаза 5 — UI
- [x] 5a (backend close API): REST `close` + `close-preview` на procurement/agreement
  (идемпотентно, blocking → HTTP 400 с причинами); `venture_blocking_reasons` заменён на
  `*_close_blocking_reasons` и удалён. `close-preview` отдаёт derived read-model
  `{show_close, closeable, blocking_reasons}` (wind-down по «нет активных лотов»/FINAL, не
  constructive; считается одной функцией с гейтами, без хранимой стадии). Гейты только на
  бэке — фронт отображает. (аудит зелёный)
- [x] T-5.1 Кнопка «Закрыть приход» в `ProcurementWorkspaceView` (`VentureCloseCard`, контекстная:
  скрыта в setup/operational; wind-down → блок+чек-лист; closeable → активна; CLOSED → итог).
- [x] T-5.2 Blocking reasons человеческим языком — `blocking_reasons` с бэка как есть, чек-листом.
- [x] T-5.3 Negative-position repayment (backend money-слайс, аудит зелёный): append-only
  `ProcurementPartnerVentureDebtRepayment` + `repay_partner_venture_debt` — кэш IN в операционную
  кассу, waterfall liability→over-capital→over-dividend, компонентный GL (5100/equity/3200),
  валюто-aware, идемпотентно, лок после close; терм `repaid` вычитает из negative_position
  (originals не трогаем), кэш фондирует claim контрагента; conservation остаётся 0 (value-neutral).
  Матрица 8 тестов. UI-кнопка «Погасить долг» (endpoint+фронт) — follow-up.
- [x] T-5.4 Кнопка «Закрыть договор» в `AgreementDetail` (тот же `VentureCloseCard`).
- [x] T-5.5 После CLOSED действия **скрыты** (settlement `:readonly`; взнос/возврат/аллокация/новый
  приход/распределение скрыты), данные и итог остаются.
- [x] T-5.6 Аудит UI-точек: все E16/E17-операции имеют UI-вход (sale/return/writeoff, settlement,
  recovered-возврат, dividend, settle-partner, contribution/allocate, close прихода/договора);
  только negative-position repayment осознанно скрыт до своего слайса.
- Чистки: убран неиспользуемый `venture-summary.blocking_reasons`; FINAL-гейт фронта выровнен на
  authoritative `has_active_lots` (UI и бэк не расходятся).

### Фаза 6 — Replay — ❌ ЗАКРЫТА КАК НЕ-ПРИМЕНИМАЯ (2026-06-15)

Excel-replay задумывался как сверка факта с Excel-данными. Но Excel — не оракул
(в нём самом возможны ошибки), поэтому сверка с ним **не доказывает формулы**.
Экономическая модель уже доказана сильнее: unit-сьют ассертит точные ожидаемые
сплиты (capital/loss/FX по capital_share, profit по profit_share), conservation
даёт точный-0 leak-proof, плюс независимые аудиторские прогоны и acceptance 11/11.
Единственная остаточная ценность replay — **покрытие на объёме** (FIFO-нарезка,
накопление округления, 3+ партнёра); правильный инструмент для этого —
**property/fuzz-тест** (случайная длинная последовательность → conservation +
реконсиляция), он вынесен в E18 Фаза 7, не в E17.

- [~] T-6.1–T-6.5 — сняты: заменены property/volume-тестом в E18.

## Открытые вопросы

- Нет. Ключевые решения зафиксированы ниже.

## Решённые вопросы (история)

- ✓ 2026-06-15 (закрытие эпика): acceptance 11/11 (S1–S11) зелёный. Последний FAIL —
  S4: возврат кредитора в пул отклонялся, т.к. гейт читал legacy
  `_agreement_partner_available` (0) вместо канонического
  `partner_capital_positions().withdrawable`. Фикс — направить гейт на канонический
  pool-read (commit b62a3e1), + регресс-тест (дыра: сьют читал позицию, но не звал
  withdrawal). Ре-верифицировано независимым прогоном: возврат проходит, net→0,
  conservation 0.
- ✓ 2026-06-15 (Фаза 6): Excel-replay закрыт как не-применимый — Excel не оракул,
  не доказывает формулы; экономика доказана unit-сплитами + conservation + аудитом;
  покрытие на объёме → property-тест в E18 Фаза 7. См. раздел «Фаза 6».
- ✓ 2026-06-09 (Фаза 3): двойной счёт в `partner_capital_positions` — recovered-capital возвраты
  (E16, из операционной кассы) вычитались из пулового `paid_in` И учитывались в venture-позиции,
  раздувая `net` в ложное «должен пулу». Решение (вариант аудита (a), корень): пуловый `paid_in`
  вычитает только возвраты, физически ушедшие ИЗ ПУЛА — дискриминатор = аккаунт `CashEntry`
  (пул vs операционная касса), не поле `paid_from_account` (у пуловых возвратов ненадёжно).
  Снимает T-1.7-мину; `net`/`owed`/`withdrawable` и UI перестали врать; гейт close `net==0` корректен.
- ✓ 2026-06-06: целевой источник партнёрской экономики — venture model, не старый
  per-transaction `PartnerLedgerEntry`.
- ✓ 2026-06-06: новые взаиморасчёты не строим вокруг `CapitalAdvance`; используем net-position.
  Legacy tables можно оставить только как read-only/historical layer до миграции, но новые
  операции и UI не должны на них опираться.
- ✓ 2026-06-06: `FINAL settlement` фиксирует результат, но отдельный `close` завершает lifecycle.
- ✓ 2026-06-06: negative position — явный долг перед венчуром; выплаты блокируются до погашения
  или явного зачёта.
- ✓ 2026-06-06: close требует сведённого состояния: нет активного товара, нет negative position,
  нет доступного к выводу капитала/прибыли без обработки. Висящий claim не считается закрытым
  циклом для первого production-ready workflow.
- ✓ 2026-06-06 (аудит Claude): conservation invariant спроектирован как safety-critical замок —
  три кармана (пул/касса/claim'ы), все источники/стоки вкл. FX и partner-liability,
  валюто-aware (функц. UZS + по каждой валюте), только append-only, блок+показ при расхождении.
  Дизайн пишет аудитор, реализует Codex, аудитор подтверждает GAP=0 прогоном. Рационал: это
  гарант «деньги не появляются/не исчезают»; неполная/одно-карманная/безвалютная версия даёт
  ложное «сошлось».
- ✓ 2026-06-06 (аудит Claude): добавлены в план F4 (mixed-units контракт `partner_capital_
  positions` — мультивалютная мина, не косметика), F6/N+1 (чинить заодно с close/инвариантом),
  CapitalAdvance reader-cleanup (не только перестать писать, но и не читать нигде в деньгах),
  claim≠ликвидность. Рационал founder'а: ноль компромиссов и тех-долга — идём сразу чисто,
  сюда не возвращаемся.
