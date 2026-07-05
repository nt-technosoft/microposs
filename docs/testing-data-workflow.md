# Test Data Workflow

Цель тестового заполнения базы — не перенести Excel-итоги в таблицы, а быстро
проиграть тот же жизненный цикл, который проходит владелец бизнеса в интерфейсе.
Только так совпадение цифр можно считать проверкой логики, а не проверкой
импортёра.

## Что считается правильной симуляцией

Тестовый сценарий должен идти через те же доменные входы, что и UI:

1. Создать пользователей, бизнес, склады, кассы, инвесторов и справочники.
2. Создать товары и категории через catalog/service или API.
3. Создать инвестдоговор или партнёрский приход через procurement/agreement flow.
4. Внести капитал, оплатить товары и расходы через штатные операции.
5. Оприходовать товар через `receive_procurement`, включая partial receive и batch
   allocation, если в реальном кейсе товар приходит партиями.
6. Переместить товар со склада в магазин через `transfer_lot_stock`.
7. Открыть POS-смену в магазине.
8. Создать продажи через `create_sale` с тем же payload-смыслом, который отправляет
   frontend.
9. Закрыть смены, выполнить возвраты, обмен валют, выплаты прибыли и погашения
   долгов только через доменные сервисы/API.
10. Сравнить отчёты, сверку, инвесторский кабинет и аудит продаж с ожидаемыми
    Excel-цифрами.

## Что нельзя считать доказательством корректности

- Вставить уже готовые Excel-итоги в отчётные таблицы.
- Создать `Lot`, `Sale`, `JournalEntry`, `CashEntry` прямым ORM-кодом в обход
  сервисов.
- Подставить данные, которые невозможно создать из UI/API.
- Автоматически менять склад продажи, если в Excel указан другой склад.
- Автоматически “доливать” деньги в кассу без явной операции, если этот шаг влияет
  на проверяемую финансовую картину.
- Пропускать продажи из-за нехватки остатков и считать сценарий полным.

## Sherik Excel Replay

**Sherik Excel Replay** - каноничное название процесса переноса реальной
Excel-истории в MicroPOS. Это не импорт таблиц и не загрузка готовых отчётов.
Процесс нормализует Excel как источник фактов, затем воспроизводит историю
через те же доменные входы, которыми пользуется UI: registration/invite,
catalog, investment agreement, capital contribution, procurement workspace,
receive, transfer, POS sale, payout и reporting.

Цель replay - получить живую базу, которая продолжает работу в MicroPOS и
одновременно проверяет FIFO, immutable lot snapshots, partnership accounting,
investor cabinet и бизнес-отчёты на реальных данных.

### Источники и приоритет

`INVESTOR MASTER SHEET.xlsx` используется как карта отношений:

- `INVESTORLAR` - реестр инвесторов и их каноничные имена.
- `INVESTOR_KIRITIM` - общий список внесений денег инвесторами.
- `BITIMLAR` - список сделок/приходов, их ID, даты, статус и краткое описание.
- `BITIM_FUNDING` - главный источник "какой инвестор сколько вложил в какой
  приход".
- `BITIM_METRICS_IMPORT`, `OMBOR_QOLDIQ_IMPORT`, `DASHBOARD`,
  `BITIM_DASHBOARD`, `INVESTOR_VIEW` - производные или cached-представления.
  Их можно использовать для сверки, но нельзя считать источником операций,
  если есть локальный файл прихода.
- `BITIMDAN_CHIQARILGAN_PUL`, `INVESTOR_PAYOUTS`, `FUNDING_QARZ` - кандидаты на
  payout, capital return, supplier/owner debt и repayment events. Перед replay
  каждую строку нужно сопоставить с доменным действием.

Локальные файлы приходов (`B-001.xlsx`, `D-001.xlsx`, `U-001.xlsx` и т.п.)
используются как операционная история:

- `FOYDA_TAQSIMOTI` - стороны сделки, капитал сторон, доля капитала, доля
  прибыли, P&L/SOFP summary. Это источник условий договора и контрольных сумм,
  но не место для прямого импорта отчётных итогов.
- `MALUMOTLAR` - справочники: клиенты, поставщики, товары, валюты, типы оплат.
- `SOTIB OLISH` - закупочные строки: товар, количество, себестоимость, дата,
  валюта и курс.
- `XARAJAT` - расходы и landed-cost evidence. Если распределение расхода по
  товарам не восстанавливается однозначно, replay использует уже
  зафиксированную себестоимость товара и помечает расход как источник сверки.
- `OMBOR` - остатки и складовая контрольная картина. Это сверка результата,
  а не единственный источник создания лотов.
- `STOCK TRANSFER` - перемещения между складом и магазином.
- `SOTUV` - продажи. Для бизнеса продажи из всех его приходов объединяются в
  один общий календарный порядок. Строки с нулевым количеством или нулевой
  ценой не считаются продажами.
- `TUSHUM` - поступления денег: капитал, оплата продаж, погашения.
- `PUL AYRIBOSHLASH` - FX-конвертации.
- `QARZDORLAR`, `YETKAZIB BERUVCHILARDAN QARZ` - долги клиентов,
  поставщиков и связанные repayment-события.

Если `Master` и локальный файл расходятся, правило такое:

1. Имена инвесторов, связи investor -> deal и поимённые суммы инвесторов берём
   из `BITIM_FUNDING`, если локальный файл содержит только общий пул `Ustoz`.
2. Условия договора, доли сторон, товары, продажи, остатки и операционную
   валюту берём из локального файла прихода.
3. `Capitaldagi ulush` и `Foydadan ulush` - разные договорные параметры.
   Доля капитала показывает, кто сколько внёс в общий capital base договора;
   доля прибыли показывает, как делится результат. Они не обязаны совпадать.
4. Если строка `Ustoz` агрегирует инвесторскую сторону, её `Capital` и
   `Foydadan ulush` раскрываются по реальным инвесторам пропорционально
   `BITIM_FUNDING`, если источник не даёт отдельные индивидуальные условия.
5. `mudaraba_ratio` в API является техническим способом провести текущую
   backend-валидацию. Он подбирается так, чтобы сохранить договорные
   `Foydadan ulush` из Excel, а не чтобы заново вывести прибыль из капитала.
6. Локальная сумма `Ustoz` должна сверяться с суммой инвесторского пула из
   `Master`. Расхождение больше округления становится blocker или требует
   явного FX/adjustment-события.
7. Курс в Excel - evidence, но не всегда историческая истина. Если фактическая
   сумма и договорная сумма восстанавливаются только другим курсом, replay
   фиксирует восстановленный FX snapshot как отдельный факт.
8. `TO'LOV TURI` определяет cash account для поступления/оплаты. Если валюта
   строки и касса не совпадают, replay использует сумму в валюте кассы
   (`JAMI (USD)` / `JAMI (SOM)`) и фиксирует это как cash movement, а не
   угадывает по `VALYUTA`.
9. `BITIMDAN_CHIQARILGAN_PUL` и `INVESTOR_PAYOUTS` сверяются до payout apply:
   выплата инвесторам не может превышать явно высвобожденную/выведенную из
   сделки сумму без отдельного founder-approved adjustment.
10. Если для payout в нужной валюте не хватает кассы, replay должен создать
   явную `PUL AYRIBOSHLASH`/FX-конвертацию до выплаты. Если проблема только в
   исторической дате, payouts можно перенести в финальный replay-stage после
   всех продаж; если итоговой высвобожденной суммы всё равно не хватает, это
   blocker.
11. Готовые dashboard-итоги не импортируются. Они только сверяют результат после
   replay.

### Нормализация сущностей

- Бизнесы создаются по реальным именам без уважительных приставок: `Bekzod`,
  `Doniyor`, `Uygun`, а не `Bekzod aka` / `Uygun aka`.
- Префикс ID прихода помогает определить бизнес (`B`, `D`, `U`), но ключом
  остаётся `Bitim ID`, а не отображаемое название сделки.
- `Ustoz` в локальных файлах - не отдельный бизнес. Это метка инвесторской
  стороны/пула. В MicroPOS этот пул раскрывается в конкретных инвесторов через
  `BITIM_FUNDING`.
- После E22 каждый реальный инвестор имеет глобальную `InvestmentProfile`,
  независимую от бизнеса. Tenant-scoped `Partner` создаётся только там, где
  инвестор реально связан с конкретным бизнесом через покрытый приход.
- Инвестора связываем с бизнесом только если у него есть фактическое участие в
  приходе этого бизнеса. Не создаём лишние visibility-связи "на всякий случай".
- `Ustoz` aggregate не моделируется как `InvestmentFund`, если в источниках нет
  отдельного факта фонда. Текущие pilot-файлы раскрывают его в прямых
  инвесторов, а не в fund-holder.
- Справочник товаров строится отдельно внутри каждого бизнеса. Одинаковые
  нормализованные названия в разных приходах одного бизнеса становятся одним
  `Product`/default `ProductVariant`, чтобы FIFO мог выбирать между лотами
  разных приходов.
- Базовая цена продажи продукта - самая часто встречающаяся цена из `SOTUV`,
  а не среднее значение.

### Хронология replay

Setup-сущности можно создавать до экономической истории: admin, users,
business registration requests, approved businesses, warehouses, cash accounts,
categories, products, investors, invites and accepted relations.

Экономические события нельзя группировать как "сначала все приходы, потом все
продажи". Для каждого бизнеса строится единый timeline из всех его Excel-файлов.
Replay идёт строго по этому timeline:

1. открыть/зафиксировать `InvestmentAgreement`;
2. внести capital contributions;
3. выполнить FX-конвертацию, если рабочая валюта прихода отличается от валюты
   договора;
4. создать `Procurement` и строки товаров/расходов;
5. зафиксировать settlement, allocation и оплату из capital pool;
6. выполнить `receive` и создать immutable lots;
7. выполнить stock transfers;
8. провести POS sales в календарном порядке;
9. провести returns, payouts, repayments, withdrawals и close/review events.

Это важно для повторяющихся товаров. Если заранее создать будущие receive
batches, ранняя продажа может увидеть будущий лот. Текущий FIFO выбирает лоты
по `lot.received_at`, но не фильтрует их по дате продажи, поэтому replay сам
обязан не создавать будущий складской факт раньше продаж, которые исторически
случились до него.

Если в Excel есть только дата без времени, используется стабильный порядок
внутри дня:

1. FX/contribution/agreement facts;
2. procurement items, expenses, settlement, allocation;
3. receive batch;
4. stock transfer;
5. sale rows по исходному файлу и номеру строки;
6. sale payments, payouts, repayments и прочие cash events.

Если такой порядок не сходится с остатками или деньгами, это не скрывается:
строка помечается как ambiguity и требует ручного решения или добавления
искусственного времени.

### Технический контракт replay-команды

Новый многофайловый replay должен быть staged-командой с dry-run по умолчанию.
Рекомендуемое имя команды: `sherik_excel_replay`.

Минимальные стадии:

1. `snapshot` - прочитать master и все локальные приходные файлы, построить
   нормализованный JSON snapshot.
2. `plan` - показать businesses, investors, relations, product merges,
   agreements, capital, timeline, blockers и warnings.
3. `baseline` - после явного `--apply --wipe` создать admin, users, businesses,
   справочники, склады, кассы и chart of accounts.
4. `relations` - пройти business registration approval и investor invite/accept
   flows.
5. `catalog` - создать товары и цены продажи.
6. `timeline` - воспроизвести agreements, contributions, procurements, receives,
   transfers, sales и payments в общей хронологии бизнеса.
7. `verify` - сверить капитал, остатки, продажи, FIFO lot allocation,
   procurement profitability, investor cabinet, business-level reports и
   conservation/read-model.

Команда не должна:

- писать напрямую в `Lot`, `Sale`, `JournalEntry`, `CashEntry` и read models;
- создавать будущие лоты до исторически более ранних продаж;
- создавать synthetic opening stock или ad-hoc investors, чтобы скрыть gap в
  источниках;
- пересчитывать договорные `profit_share` из капитала, если Excel явно задаёт
  `Foydadan ulush`;
- автоматически закрывать gaps без строки в плане;
- менять production/stage базу без отдельного confirm-флага;
- хранить постоянные пароли в репозитории или snapshot.

### План подготовки и запуска

Текущий проектный путь делится на две части: сначала доказать план без записи в
базу, затем отдельно получить разрешение на destructive apply.

1. Source snapshot:
   - прочитать `файлы/INVESTOR MASTER SHEET.xlsx` и все `*-NNN.xlsx` приходные
     файлы из той же директории;
   - сохранить нормализованный snapshot без паролей и секретов;
   - для каждой строки сохранить provenance: workbook, sheet, row id, исходные
     значения, нормализованные дату, валюту, сумму и deal id.

2. Resolver/plan:
   - построить каноничные investors, businesses, deals, funding, product keys,
     customers, suppliers, cash accounts и warehouses;
   - показать только реальные investor/business relations, основанные на
     покрытых локальными файлами приходах;
   - посчитать capital reconciliation: `Master` investor pool vs локальный
     `Ustoz`/investor pool;
   - посчитать payout reconciliation:
     `BITIMDAN_CHIQARILGAN_PUL` >= `INVESTOR_PAYOUTS` по каждому приходу;
   - посчитать FX/cash coverage для payout currency и показать, где нужна
     явная конвертация перед выплатой;
   - построить product merge report по бизнесу, отдельно подсветив товары,
     повторяющиеся между приходами;
   - построить единый timeline по каждому бизнесу и список blockers/warnings.

3. Technical fit check:
   - `create_business_registration_request`,
     `approve_business_registration_request`, `create_investor_invite` и
     `accept_investor_invite` используются для пользовательского onboarding
     flow, а не прямое создание visibility-связей;
   - `create_workspace`, `CREATE_INVESTMENT_AGREEMENT`,
     `RECORD_CAPITAL_CONTRIBUTION`, `CONVERT_CAPITAL_POOL`,
     `ALLOCATE_CAPITAL`, `RECEIVE_BATCH`, `transfer_lot_stock`,
     `open_pos_session`/`create_sale` используются для экономической истории;
   - если сервис не принимает историческую дату, это фиксируется как technical
     gap. Предпочтительное решение - добавить явный optional timestamp в сервис,
     а не патчить confirmed economic records напрямую.

4. Baseline apply, только после явного разрешения:
   - сделать локальный dump перед `--wipe`;
   - очистить локальную базу через protected management command;
   - создать real admin account с username `sherik.admin`; пароль генерируется
     при запуске, выводится один раз и не пишется в git;
   - создать investor users и global `InvestmentProfile` по master;
   - провести business registration request -> admin approval для каждого
     бизнеса;
   - создать tenant setup: chart of accounts, warehouses, cash accounts,
     category, discount reason, default supplier/customer records.

5. Relations apply:
   - бизнес отправляет invite только тем инвесторам, которые фактически
     участвовали хотя бы в одном покрытом локальным файлом приходе этого
     бизнеса;
   - investor accepts invite, после чего появляется `Partner` и
     `BusinessInvestorRelation`;
   - инвестор из отсутствующего прихода может иметь user/profile, но не получает
     business relation до появления локального файла.
   - если в будущих источниках появится настоящий фонд, он создаётся profile-first
     как `InvestmentFund`; business-side synthetic `Partner` `Фонд: X`
     создаётся только при deployment в конкретный `InvestmentAgreement`.

6. Catalog apply:
   - товары создаются один раз на бизнес по canonical product key;
   - base sale price = mode из `SOTUV`, в UZS после FX-нормализации, если нужно;
   - старое поведение `excel_demo_seed_folder`, где товар префиксился deal id,
     не используется для `Sherik Excel Replay`.

7. Timeline apply:
   - события выполняются по business timeline, а не блоками по файлам;
   - receive будущего прихода нельзя выполнять до продаж, которые исторически
     раньше этого receive;
   - для каждой продажи заранее должен быть доступен товар в shop warehouse:
     через Excel `STOCK TRANSFER` или через явно показанный replay adjustment;
   - POS-смены лучше группировать по бизнесу, магазину и дате продаж. Если
     требуется историчный `opened_at`/`closed_at`, перед apply нужно расширить
     сервисы смены, потому что сейчас они ставят текущее время.

8. Verification:
   - investor funding by deal совпадает с `BITIM_FUNDING`;
   - локальный investor pool совпадает с master pool, кроме явно разрешённых
     rounding/FX cases;
   - итоговые остатки по товарам сверяются с `OMBOR`;
   - продажи сверяются по количеству, сумме, валюте и клиенту;
   - FIFO не использует лот, чей `received_at` позже даты продажи;
   - investor cabinet, procurement profitability, business reports,
     partner position read models и conservation checks сходятся после replay.

До `--apply` обязательный deliverable - dry-run пакет: summary в консоли,
`plan.json`, `timeline.json` или `timeline.csv`, `product_merge_report` и список
blockers/warnings. Если blockers не пустой, apply запрещён.

Текущий read-only preflight запускается так:

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python manage.py sherik_excel_replay --dry-run --folder ../файлы --stage preflight
```

На 2026-07-04 он проверяет agreements, master/local funding split,
`BITIMDAN_CHIQARILGAN_PUL` vs `INVESTOR_PAYOUTS`, FX coverage для USD payouts и
product catalog merge. Это ещё не apply-команда и она не пишет в базу.

### Account lifecycle gate

Перед переносом данных, которые будут передаваться реальным пользователям,
нельзя оставлять demo-подход к логинам и паролям.

Для `Sherik Excel Replay` правило такое:

- usernames генерируются стабильными и человекочитаемыми: например
  `bekzod.owner`, `doniyor.owner`, `alijon.ravshanov`, а при конфликте -
  deterministic suffix;
- initial passwords генерируются криптографически случайно, выводятся один раз в
  operator-only handoff и должны быть сменены пользователем;
- пароли, reset tokens и invite tokens не попадают в git, snapshots, logs и
  Excel-derived artifacts;
- для существующих реальных людей предпочтителен invite/setup link, а не
  постоянный пароль, придуманный replay-командой;
- replay не должен создавать investor/business relation только ради аккаунта.
  Аккаунт может существовать без связи до появления реального covered deal.

Текущий код уже имеет базовый путь:

- business: public registration request -> platform admin approval -> owner
  account/business;
- investor: business invite -> existing-user accept или invite register;
- auth: JWT login/refresh and `/auth/me`.

Но перед production handoff нужен отдельный минимальный account lifecycle slice:

1. Password reset request/confirm через одноразовый token с expiry, invalidation
   после использования и без раскрытия, существует ли пользователь.
2. Первый вход после replay: forced password change или setup link для всех
   generated accounts.
3. Единая password policy для business registration, investor invite register,
   admin/bootstrap/replay-generated accounts.
4. Account recovery для пользователей без email: admin-assisted reset с audit
   event и ручной re-identification по заранее сохранённым данным профиля.
5. UI: "Забыли пароль?", reset form, first-login password change, понятное
   состояние pending/rejected business registration.

Это отдельная задача от Excel replay, но её лучше выполнить до финального
`--apply --wipe` для базы, которую потом будем переносить на сервер. Без неё
импорт можно dry-run'ить и тестировать, но реальные credentials лучше не
раздавать.

### Текущий pilot-набор

На 2026-07-04 рабочая директория источников:

```text
файлы/
  INVESTOR MASTER SHEET.xlsx
  B-001.xlsx
  B-002.xlsx
  B-003.xlsx
  B-004.xlsx
  D-001.xlsx
  U-001.xlsx
```

Из `Master` видны 7 приходов: `B-001`, `B-002`, `B-003`, `B-004`, `B-005`,
`D-001`, `U-001`. Локально покрыты 6 приходов; `B-005` пока не replay-ready,
потому что локального файла нет.

Бизнесы pilot replay:

- `Bekzod`: `B-001`, `B-002`, `B-003`, `B-004`; `B-005` отложен.
- `Doniyor`: `D-001`.
- `Uygun`: `U-001`.

Инвесторы из master:

- Alijon Ravshanov
- Azizbek Norqarayev
- Kamoliddin Murtazaqulov
- Faxriyor Murtozayev
- Nilufar Tilavova (Ravshanova)
- Abdulloh Sayfuddinov
- Nurbol Abduraimov
- Shayxulmuhammad Setirzayev
- Omon Sultonov

Pilot-связи создаются только по покрытым локальным файлам. `Omon Sultonov`
имеет funding только в отсутствующем `B-005`, поэтому его user/profile можно
создать заранее, но связь с `Bekzod` и участие в replay откладываются до
появления файла `B-005`.

Сверка capital pool:

| Приход | Master investor pool | Локальный investor pool | Решение |
|---|---:|---:|---|
| `B-001` | 10,000 USD | 10,000 USD | совпадает |
| `B-002` | 11,279.40 USD | 11,279.30 USD | округление 0.10 USD |
| `B-003` | 10,486 USD | 10,486 USD | совпадает |
| `B-004` | 10,600 USD | 10,600 USD | совпадает |
| `D-001` | 12,500 USD | 12,500 USD | совпадает |
| `U-001` | 7,000 USD | 84,850,000 UZS | фиксировать FX 12,121.428571 |
| `B-005` | 11,000 USD | нет файла | отложить |

Для `B-001` локальный полный капитал договора = 14,900 USD: `Ustoz` 10,000 USD
и `Bekzod` 4,900 USD. Таблица выше сверяет только investor pool, поэтому
10,000 USD в `Master` и 10,000 USD по строке `Ustoz` не конфликтуют. Договорные
условия из `FOYDA_TAQSIMOTI`: `Ustoz` имеет 67.11409396% капитала и 40% прибыли,
`Bekzod` имеет 32.88590604% капитала и 60% прибыли; `Ustoz`-доля раскрывается на
Alijon/Azizbek по 75%/25% внутри investor pool.

Для `U-001` master фиксирует договорный капитал инвесторов в USD, а локальный
файл ведёт операционную историю в UZS. Replay должен создать USD capital facts,
затем FX-конвертацию `$7,000 -> 84,850,000 UZS`; курс из ячейки `KURS` не
используется как обязательная истина, если он не восстанавливает фактическую
сумму.

Утверждённые source-corrections pilot-набора находятся в `U-001.xlsx`:

- `J82350`: исходно куплено 20, продано 21; рядом `82350` куплено 5, продано 3.
  Founder-approved correction: `SOTUV` row 488 переносится с `J82350` на `82350`.
  После этого `J82350` = 20/20, `82350` = 5/4.
- `KURTKA 8803`: итоговый `OMBOR` положительный, но продажи идут
  2025-11-07/2025-11-08 раньше записи покупки 2025-11-15. Founder-approved
  correction: effective receive date для `SOTIB OLISH` row 29 = 2025-11-07.
- `99620`: итоговый `OMBOR` положительный, но продажа 2026-05-22 раньше записи
  покупки 2026-05-23. Founder-approved correction: effective receive date для
  `SOTIB OLISH` row 135 = 2026-05-22.

Replay не должен закрывать такие кейсы synthetic stock. Любое расхождение такого
типа фиксируется как явная source-correction с row id, причиной и проверкой
ожидаемого товара.

Если сумма закупок в локальном файле превышает стартовый капитал договора, это
реальный оборот капитала из продаж. После E23 replay больше не создаёт
provisional `PROFIT_REINVEST` top-up для `D-001`/`U-001`: недостающий капитал
для следующего оборота должен пройти через policy-gated `capital_rollover`
decision из recovered sale proceeds. `--dry-run --stage preflight` остаётся
безопасной проверкой источников; `--apply --wipe` является destructive replay и
требует явного разрешения перед запуском на локальной БД.

Отдельно preflight сейчас реконструирует 205 missing stock-transfer events:
товар есть в бизнесе, но Excel не всегда фиксирует перемещение в `DOKON` перед
продажей. Это не меняет экономику, но apply должен проводить такие перемещения
через `transfer_lot_stock` и показывать их как восстановленные пользовательские
действия.

По текущим локальным файлам `Bekzod` имеет 42 уникальных товара. Повторяются
между приходами:

- `32 PCS`
- `2 TALIK 60X90`
- `80X160`
- `120X180`
- `ATIRGUL 60X60`
- `WELCOME 60X90`

Поэтому `Bekzod` replay обязан сначала создать единый product catalog по
бизнесу, затем проигрывать `B-*` приходные и продажи в общей хронологии. Это
основная проверка реального FIFO: продажи повторяющихся товаров должны
списываться из ранних доступных лотов, а прибыль должна попадать в snapshot
того договора, откуда фактически вышел товар.

Подготовительный checklist перед `--apply`:

1. `snapshot` dry-run показывает все 6 локальных файлов и master.
2. `plan` не имеет blockers по missing products, invalid dates, negative stock,
   неизвестным инвесторам или невозможным FX.
3. Для каждого бизнеса построен общий ordered timeline.
4. Для каждой продажи известен склад или есть явное правило переноса в магазин.
5. Для каждого товара с повтором есть один canonical product key.
6. Для каждой суммы `Ustoz` есть сверка с master pool или явный adjustment.
7. Для платежей продаж есть явное правило: либо replay использует `SOTUV` как
   факт продажи и затем сверяет `TUSHUM`, либо отдельный reconciliation шаг
   сопоставляет строки `SOTUV` ↔ `TUSHUM` и восстанавливает cash account/метод
   оплаты. Без этого FIFO/прибыль можно проверить, но кассовые каналы нельзя
   считать полностью доказанными.
8. Перед `--wipe` создан локальный database dump.
9. Admin password генерируется при запуске и выводится один раз; не сохраняется
   в git.

## Актуальный Excel workflow

Для E07 этот workflow остаётся каноничным партнёрским replay, но не должен
считаться единственным доказательством новой procurement-архитектуры. После E07
нужно дополнительно покрывать own-funds, deferred/installment/consignment и
blocked hybrid сценарии отдельными smoke/test seed flows.

Старые команды прямого Excel-import удалены. Каноничный путь сейчас один:

1. `excel_snapshot_from_xlsx` — преобразует исходный `.xlsx` в JSON snapshot.
2. `excel_workflow_staged` — поэтапно проигрывает жизненный цикл владельца:
   baseline → procurements → transfers → sales → final.
3. `excel_workflow_audit` — тот же сценарий одной командой для быстрой
   регрессии после того, как staged-проход уже проверен руками.

Этот workflow не импортирует готовые отчётные итоги. Он создаёт пользователей,
товары, партнёрские приходы, partial receive, перемещения, POS-смены и продажи
через доменные сервисы, максимально близкие к UI/API.

## Текущая команда

Каноничный источник Excel-кейса лежит в корне проекта:

```text
MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx
```

Из него собран текущий snapshot:

```text
backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json
```

Если Excel-файл изменился, snapshot пересобирается так:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_snapshot_from_xlsx \
  --source-xlsx "MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx" \
  --output-json backend/import_snapshots/muzoraba_ustoz_bekzod_latest.json
```

Полный workflow seed доступен как management command:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --dry-run
```

`--dry-run` только строит план и показывает предупреждения. Базу он не меняет.

В `DEBUG=False` Excel/demo команды защищены production guard-ом. Для stage/prod
их нельзя запускать случайно: нужен отдельный confirm-флаг, и перед этим должно
быть явное решение очистить или изменить базу.

Применение намеренно сделано разрушительным и требует явного флага:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_audit --apply --wipe
```

После `--apply --wipe` команда создаёт чистую базу для проверки: пользователей,
две пары `owner/investor`, товары, два партнёрских прихода, partial receive,
перемещения в магазин и продажи из Excel через доменные сервисы.

Для ручного аудита основной путь — staged-команда:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage baseline --dry-run
```

Этапы запускаются последовательно:

```bash
# 1. Очистить базу и создать пользователей, бизнесы, справочники, товары
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage baseline --apply --wipe

# 2. Создать два партнёрских прихода и частично оприходовать первую партию
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage procurements --apply

# 3. Переместить товар со склада в магазин
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage transfers --apply

# 4. Проиграть продажи из Excel через POS-сервисы
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage sales --apply

# 5. Обновить агрегаты и вывести финальную сводку
DJANGO_SETTINGS_MODULE=config.settings.development \
  backend/.venv/bin/python backend/manage.py excel_workflow_staged --stage final --apply
```
