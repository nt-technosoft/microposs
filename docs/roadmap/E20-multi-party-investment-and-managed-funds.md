# E20 — Multi-Party Investment, Closed Funds & Contract Lifecycle

**Статус:** `IN_REVIEW`
**Прогресс:** 100% implementation; ожидает пилотной обкатки
**Зависит от:** E04 (явный contract type), E18 (acceptance единого money read-model)
**Блокирует:** управляемые фонды, multi-investor agreements, прозрачный lifecycle взаиморасчётов

---

## Цель

Дать бизнесу и нескольким инвесторам один честный инвестиционный контракт, а
также простой закрытый фонд с управляющим. Система должна фиксировать условия,
считать фактическую позицию каждого участника из неизменяемых событий и вести
стороны через выплаты, срок, закрытие и спор без автоматического движения денег.

## Контекст и обоснование

Текущая модель уже умеет фактические взносы, snapshots на приходе, FIFO-экономику
и возврат/распределение. Она рассчитана прежде всего на соглашение с отдельными
партнёрами. Следующий продуктовый шаг — не «ещё один коэффициент», а единый
контрактный слой над множеством экономических держателей: прямые инвесторы и
фонд как один держатель в отношениях с бизнесом.

Проектируем целевую модель в вакууме и накладываем её на E04/E18. Это не
создание серий фонда, реинвестирование или marketplace: MVP сознательно решает
наиболее частый закрытый сценарий без смешения капиталов разных циклов.

## Согласованная бизнес-модель

### 1. Прямой инвест-договор

- Стороны: владелец/оператор бизнеса и набор прямых инвесторов.
- В договоре вводится **общая** доля капитала инвесторского пула и **общая**
  доля прибыли пула; не ручные проценты прибыли на каждого инвестора.
- Доля каждого инвестора выводится из его фактического капитала в пуле.
  Убыток распределяется по фактическому capital share. Прибыль считается по
  действующей mudaraba/musharaka-модели, а не меняет старую формулу задним числом.
- Плановые доли — `AGREED`; факт взносов, аллокаций, продаж и выплат —
  `FACTUAL`. Для старых лотов всегда действует их неизменяемый snapshot.

### 2. Закрытый управляемый фонд (MVP)

- Фонд собирает взносы участников до первого размещения. После первого
  deployment он закрыт для новых взносов; новая идея — новый фонд, не следующая
  серия внутри этого фонда.
- Фонд выступает одним economic holder в договоре с бизнесом. Внутри фонда
  позиции его участников считаются отдельно и прозрачно.
- Управляющий фонда может быть одновременно инвестором. Его вознаграждение
  допускается нулевым; если оно есть, его правило фиксируется заранее в terms.
- Управляющий сам задаёт инвестиционные правила фонда. В MVP участники либо
  согласны с офлайн-договорённостью и вносят капитал, либо не входят; система
  не строит сложный механизм голосования, секторных лимитов или related-party
  approval.
- Сначала возвращается фактический капитал, затем распределяется net profit;
  комиссия управляющего — прозрачная часть согласованной waterfall, не скрытая
  надбавка к доходности участников.

### 3. Выплаты и срок

- Система не перечисляет деньги. Бизнес/управляющий создаёт и подтверждает
  факт платежа; получатель может подтвердить или оспорить его.
- В terms задаётся политика выплат: период проверки, порог доступной суммы,
  минимум между выплатами, резерв/льготный срок и допустимость частичной
  выплаты. Дефолт MVP: проверка раз в 30 дней без обязательного порога.
- Достижение периода или порога создаёт уведомление и обязательство к действию,
  но не автосписание. Подтверждённая выплата открывает следующий цикл политики.
- Дата окончания договора — review date, а не автоматическая ликвидация.
  При наступлении срока стороны выбирают: продолжить; согласовать распродажу;
  признать подтверждённый убыток; оформить добровольный выкуп остатка; либо
  зафиксировать спор. Продление — это одно действие, а не отдельный «темп продаж».

### 4. Спор и защита сторон

- В споре платформа фиксирует claim, контекст, доказательства и итог решения;
  она не делает вид, что может принудительно перевести офлайн-деньги.
- Само окончание срока или несогласие с условиями не блокирует бизнес.
- Если объективное обязательство по terms просрочено и подана подтверждаемая
  жалоба, платформа может временно ограничить **новое размещение в этом
  соглашении** до урегулирования. Торговля и остальной продукт бизнеса остаются
  доступны. Более широкая блокировка — только отдельное admin-решение.
- Любая поправка terms действует только вперёд и хранит версию и офлайн-факт
  согласия; она не переписывает factual snapshot или уже возникшую позицию.

## Сценарии (use cases)

- **US-1. Multi-investor agreement.** Бизнес создаёт договор, выбирает несколько
  инвесторов и общую долю инвесторского пула. После фактических взносов система
  показывает каждому его capital share, net position и производную прибыль.
- **US-2. Closed fund.** Лид-инвестор создаёт фонд, вносит капитал сам и с
  друзьями, фиксирует нулевую либо заданную комиссию, закрывает фонд после
  первого deployment и использует его как одного инвестора в бизнесе.
- **US-3. Periodic payout.** Порог/дата достигнуты; стороны получают уведомление,
  оператор фиксирует офлайн-платёж, участник видит изменившуюся позицию.
- **US-4. End-of-term review.** Срок наступил при активном товаре; стороны
  продолжают договор или оформляют продажу/выкуп/реальный убыток без потери
  истории и без автоматической ликвидации.
- **US-5. Overdue claim.** Инвестор оспаривает просроченное обязательство;
  система сохраняет доказательства и при обоснованном claim ограничивает новое
  funding в данном agreement, не останавливая деятельность бизнеса.

## Целевая архитектура

### Экономические держатели и уровни расчёта

`EconomicHolder` — абстракция того, кто владеет экономической позицией перед
бизнесом: прямой инвестор либо `InvestmentFund`. Контракт и procurement видят
одного holder; фонд разворачивает его позицию в свои `FundMember`.

Не вводить отдельную формулу `mudo robo ratio`. Существующая классификация E04 и
снимок договора определяют правовую/прибыльную формулу; много участников — это
измерение распределения фактического пула, а не новая математика доходности.

### План, факт и снимки

| Слой | Назначение | Изменяемость |
|---|---|---|
| `AgreementTermsVersion` / `FundTermsVersion` | стороны, правила, payout policy, review date, fee waterfall | новая версия только вперёд |
| Contribution / allocation / payment | фактическое экономическое событие | append-only |
| Batch/lot `contract_snapshot` | правило, применимое к проданному товару | immutable |
| `PartnerPositionReadModel` | производная текущая позиция | rebuildable read model |

Использовать E18 как денежную основу: деньги живут в GL + partnerships-owned
tags, а расчётная аллокация остаётся тонким доменным слоем. E20 не создаёт второй
ledger и не хранит «ручной баланс участника».

### Минимальные сущности

- `EconomicHolder` (direct investor или fund); `AgreementHolder` — holder в
  конкретном agreement и его agreed pool terms.
- `InvestmentFund`, `FundMember`, `FundContribution`, `FundDeployment`.
- `AgreementTermsVersion`, `FundTermsVersion`, `PayoutPolicy`,
  `PayoutObligation`, `PaymentConfirmation`, `ContractReview`, `DisputeCase`.

Названия — target contract, не обязательный literal schema. Перед миграцией
сверить их с моделями E18 и не дублировать уже существующие intent-records.

## UX flow

1. **Создать договор**: стороны → тип/общий инвесторский пул → прибыль/убыток →
   payout policy и review date → preview terms → офлайн-согласие → активировать.
2. **Создать фонд**: управляющий и его роль → участники/взносы → fee (включая 0)
   → terms preview → офлайн-согласие → собрать капитал → первое deployment →
   фонд закрыт для новых взносов.
3. **Договор/фонд dashboard**: planned vs factual capital, net position,
   ближайшая проверка выплаты, статусы обязательств, история событий и actions.
4. **Review/спор**: reminder → выбрать сценарий → зафиксировать офлайн-решение
   и приложить доказательство → показать последствия для доступного funding.

Не делать PDF/печать в MVP; модель terms должна быть готова к рендеру позже.

## Текущее состояние и дельта

- ✅ Уже есть: `InvestmentAgreement`, роли партнёров, planned/factual capital,
  immutable snapshots, FIFO profit/loss, append-only money intent и E18
  `PartnerPositionReadModel` как целевой источник позиции.
- ⚠️ Нужна сверка: E04 ещё не формализовал contract type; E18 находится в
  acceptance. Эти контракты нельзя обходить новой локальной моделью.
- ❌ Нет: first-class multi-party pool UX, fund holder/membership/deployment,
  terms versioning, payout policy/obligation, review/dispute lifecycle и
  целевой read-side для фонда.

## План реализации

### Фаза 0 — Acceptance и target contracts

Закрыть E18 acceptance, согласовать integration contract с E04, провести code
delta-аудит и записать migration boundary. Без этого не начинать persistence.

### Фаза 1 — Terms и multi-party agreement

Ввести versioned terms, pool-level profit rule и multi-holder selection; сохранить
совместимость старых snapshots только как исторических фактов, не как новый API.

### Фаза 2 — Fund domain и closed deployment

Добавить fund/member/contribution/deployment поверх `EconomicHolder`, waterfall
capital → net profit → disclosed manager fee, и close-on-first-deployment.

### Фаза 3 — Payout, review и dispute lifecycle

Сделать policy engine, obligations/notices, payment confirmation, review actions
и узкий agreement-level funding hold при обоснованной просрочке.

### Фаза 4 — UI и расчётные представления

Построить договорный constructor, fund constructor, dashboards и actions по
flow выше. Выполнить mobile-first UX и роль/permission audit.

### Фаза 5 — Migration, evidence и rollout

Мигрировать существующие agreements консервативно, прогнать golden scenarios,
Excel replay и независимый review. Не включать fund series, recycling и PDF.

## Задачи (чек-лист)

### Фаза 0
- [x] T-0.1 Подтвердить E18 read-model и выделить его public contract для E20.
- [x] T-0.2 Зафиксировать E04-compatible contract type для multi-party agreement через existing `legal_mode` и immutable terms snapshot.
- [x] T-0.3 Сделать vacuum-to-current delta audit по моделям, API и UI.
- [x] T-0.4 Зафиксировать migration и backwards-history boundary.

### Фаза 1
- [x] T-1.1 Спроектировать и реализовать immutable `AgreementTermsVersion`.
- [x] T-1.2 Ввести fund-as-holder через системного `Partner` без второго ledger/дублирования позиций.
- [x] T-1.3 Вывести individual capital/profit entitlement из factual pool share.
- [x] T-1.4 Обновить agreement constructor и read API для нескольких инвесторов.

### Фаза 2
- [x] T-2.1 Реализовать `InvestmentFund`, membership, contributions и fund terms.
- [x] T-2.2 Реализовать deployment и irreversible close for new contributions.
- [x] T-2.3 Реализовать disclosed waterfall и manager-as-member/zero-fee/non-member cases.
- [x] T-2.4 Добавить fund read-model поверх E18 source facts.

### Фаза 3
- [x] T-3.1 Реализовать `PayoutPolicy`, daily obligation scheduler и outbox notices.
- [x] T-3.2 Реализовать offline payment record + recipient confirmation/dispute, включая partial payout.
- [x] T-3.3 Реализовать contract review actions и forward-only amendments.
- [x] T-3.4 Реализовать evidence-based agreement funding hold без торговой блокировки.

### Фаза 4
- [x] T-4.1 Построить mobile-first agreement constructor и terms preview.
- [x] T-4.2 Построить fund constructor, lifecycle dashboard и member view.
- [x] T-4.3 Построить payout/review/dispute action screens и role permissions.
- [x] T-4.4 Провести UX audit на понятность FACTUAL vs AGREED и offline consent.

### Фаза 5
- [x] T-5.1 Добавить golden numeric scenarios: direct multi-party, fund, payout,
  end-of-term, buyout/write-off, overdue claim.
- [x] T-5.2 Проверить conservation, read-model replay, immutability и idempotency.
- [x] T-5.3 Прогнать migration и canonical Excel workflow (`--dry-run`, без разрушения рабочей БД).
- [x] T-5.4 Провести fresh independent architecture and code review before rollout; P1/P2 findings устранены и покрыты tests.

## Реализация и evidence

- Миграции `0033`–`0036`: versioned terms с conservative backfill исторических
  соглашений, fund domain, partial payout settlements и active-obligation
  uniqueness.
- Периодическая задача `evaluate_due_contract_lifecycle` создаёт только actions
  и reminders; фактические деньги остаются в существующих GL/payment flows.
- `test_e20_multi_party_funds_lifecycle.py`: multi-party/fund lifecycle,
  partial payment, dispute hold, manager fee, scheduler, review actions,
  immutability, idempotency и uniqueness.
- Финальная локальная верификация: `400 passed`; frontend `type-check` и
  production build зелёные. Неразрушающий canonical Excel audit выполнен.

## Не входит в MVP

- Серии, переоткрытие, автоматическое реинвестирование и перенос прибыли в
  следующий фонд.
- Свободный вход/выход из фонда, secondary transfer, NAV/redemption engine.
- Автоматические переводы денег, escrow, KYC/AML, marketplace/discovery.
- PDF/печать юридического договора, e-signature и сложное голосование.
- Глобальная санкция бизнеса за обычный коммерческий спор.

## Открытые вопросы

- ? Точный юридический wording и Sharia/AAOIFI validation manager fee/waterfall
  должны быть подтверждены в E06 до внешнего позиционирования, но не блокируют
  техническую versioned terms model.
- ? Нужен ли default payout policy строго «30 дней / без порога», либо его
  следует оставить организационным default после пилота.
- ? Какие доказательства считаются достаточными для agreement-level hold и кто
  исполняет admin escalation — нужно принять перед Фазой 3.

## Решённые вопросы (история)

- ✓ 2026-06-23: Новый капитал после первого deployment фонда → запрещён; новый
  инвестиционный цикл оформляется отдельным фондом, не series/reopen MVP.
- ✓ 2026-06-23: Распределение прибыли прямым инвесторам → сначала общее правило
  investor pool, индивидуальная позиция выводится из factual capital share.
- ✓ 2026-06-23: Согласие на terms → офлайн допустимо; платформа хранит версию,
  стороны и факт согласования, но не требует e-signature в MVP.
- ✓ 2026-06-23: Окончание срока → review date, не автоматическое закрытие;
  продление является одним action «продолжить».
- ✓ 2026-06-23: Неисполненное подтверждённое payout obligation → узкий hold
  нового funding в данном agreement; торговая деятельность бизнеса не блокируется.
