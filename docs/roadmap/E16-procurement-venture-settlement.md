# E16 — Procurement Venture Settlement & Partner Proceeds

**Статус:** `IN_PROGRESS`
**Прогресс:** 98%
**Зависит от:** E07, E11, E12, E14, E15
**Блокирует:** E03, E06, Excel replay, production-ready partner payouts

---

## Цель

Перестроить партнёрскую экономику так, чтобы каждый партнёрский приход считался отдельным
венчуром: продажи фиксируют реализацию капитала и предварительный результат, а финальная
прибыль/убыток считается по net-результату венчура через фактическую или конструктивную
ликвидацию.

## Контекст и обоснование

Решение принято 2026-06-05 после обсуждения распределения выручки/прибыли. Текущая система
начисляет `PROFIT_ACCRUED` по каждой FIFO sale line, но не учитывает возврат капитала из
проданной себестоимости. Из-за этого E14/E15 видят `deployed - paid_in`, но не видят, что
часть deployed уже продана и стала деньгами/требованием. Это ломает корректный capital return,
вывод партнёрских денег, net asset reporting и финальную сверку.

Внешний sharia/finance ориентир: прибыль mudaraba/musharaka становится окончательной после
сохранности капитала, расходов/резервов и actual/constructive liquidation. Промежуточные
выплаты допустимы как on-account/preliminary и подлежат финальной корректировке.

## Сценарии (use cases)

- **US-1. Продажа с прибылью.** Продали часть товара: система фиксирует recovered capital по
  `capital_share` и provisional profit по `profit_share`, но не считает это финальным закрытием
  венчура.
- **US-2. Продажа ниже себестоимости.** Система фиксирует loss по `capital_share`; profit не
  начисляется.
- **US-3. Частичный вывод капитала.** Партнёр может вывести recovered capital, если есть
  доступная сумма и cash/claim, но вывод не должен ломать будущую финальную сверку.
- **US-4. Выплата прибыли после checkpoint.** Running profit до сверки является
  информационным результатом. Вывод прибыли разрешён только после constructive/final
  settlement, когда сохранность капитала и net P&L венчура зафиксированы snapshot-ом.
- **US-5. После вывода появился убыток.** Если финальная сверка показывает, что партнёр вывел
  больше, чем должен был, возникает negative partner position / долг перед venture. Новые
  выплаты блокируются или автоматически гасят этот минус; закрытие договора запрещено.
- **US-6. Полная распродажа.** Когда active lots по procurement закончились, система может
  выполнить final settlement и зафиксировать итоговую прибыль/убыток.
- **US-7. Конструктивная ликвидация.** До полной распродажи оператор может сделать settlement
  checkpoint с оценкой остатка и резервами; результат является управляемым snapshot, а не
  скрытым пересчётом.
- **US-8. Возвраты/списания после продажи.** Return/writeoff сторнирует realization/profit/loss
  append-only событиями и пересчитывает available-to-pay.
- **US-9. Мультивалюта.** Sale proceeds остаются в фактической валюте продажи;
  capital recovery хранится в валюте себестоимости/прихода; cross-currency margin требует
  явный sale-time FX snapshot. UZS используется как functional/reporting projection, а не
  единственная денежная правда.

## Текущее состояние

- ✅ **Есть:** `Lot.contract_snapshot`, FIFO sale lines, `PartnerLedgerEntry`, real agreement
  capital pool, physical capital withdrawal/dividend services, E14 capital positions.
- ⚠️ **Начато, но не завершено:** E14/E15 дают physical payouts, но источник доступности
  неполный: recovered capital from sales не включён в позицию партнёра.
- ✅ **Реализовано в E16:** per-currency sale realization model, venture settlement snapshot
  model, partner venture position helper, sale/return/writeoff integration, recovered-capital
  return from operating cash with explicit FX snapshot, profit payout guard after
  constructive/final settlement, procurement and agreement venture summary APIs, payout preview
  API, reports/E03 buckets, UI возврата recovered capital на странице инвестдоговора,
  settlement summary/action на странице прихода.
- ⚠️ **Осталось:** Excel replay и полноценная продуктовая обкатка финального
  settlement/close-flow на реальных сценариях.

## Целевая модель

### Венчур

`Procurement` = economic venture. `ReceiveBatch` и `Lot` остаются immutable источниками
себестоимости и долей. В одном procurement может быть несколько batches с разными snapshots;
realization считается по конкретному lot, а агрегируется по procurement.

### Sale realization

Каждая FIFO `SaleLine` по партнёрскому lot создаёт append-only realization:

- `sale_proceeds` — сумма продажи в валюте операции и functional UZS projection;
- `cost_basis` — landed cost проданной части в валюте прихода/себестоимости и functional UZS projection;
- `cost_basis_at_sale` — та же native cost, переоценённая по sale-time FX snapshot;
- `capital_recovered` — `min(sale_proceeds, cost_basis_at_sale)` по `capital_share`;
- `provisional_profit` — `max(sale_proceeds - cost_basis_at_sale, 0)` по `profit_share`;
- `loss` — `max(cost_basis_at_sale - sale_proceeds, 0)` по `capital_share`;
- `fx_gain_loss_uzs` — явная разница между historical cost basis и sale-time FX measurement
  при buy/sell в разных валютах;
- `status` — active/reversed/settled-reference.

Для buy/sell в разных валютах нативная себестоимость берётся из buy-факта/исторического
buy-FX, а не обратным делением historical UZS на текущий курс. FX-дрейф капитала относится
к capital leg по `capital_share`; торговая прибыль считается как `sale_proceeds -
cost_basis_at_sale` и только она делится по `profit_share`.

До settlement `capital_recovered` остаётся консервативным per-sale: нельзя вернуть больше,
чем уже пришло по конкретной продаже. На constructive/final settlement выполняется true-up:
`recovered_capital = min(Σproceeds, Σcost) × capital_share`,
`loss = max(Σcost - Σproceeds, 0) × capital_share`.

Net P&L и recovered/loss нельзя считать поперёк валют без явного FX snapshot. Поэтому порядок
всегда такой: **per-currency realization → sale-time FX measurement для cross-currency margin
→ netting by venture/share-profile → settlement true-up → payout availability after settlement**.

### Settlement

Финальный/конструктивный результат венчура считается только через `VentureSettlementSnapshot`:

- фактическая ликвидация: active lots по procurement = 0;
- конструктивная ликвидация: остаток оценён вручную/по политике, с резервами;
- settlement фиксирует net P&L by immutable share-profile, capital/loss true-up, final capital
  return, final profit/loss by partner, preliminary payouts, overpaid/owed positions.

### Available-to-pay

Разделить доступность:

- `capital_return_available` = recovered capital + undeployed pool - already returned - reserve;
- `provisional_profit_available` = 0 до constructive/final settlement; после settlement =
  net profit entitlement - dividends paid - reserve - negative position;
- `final_available` = finalized entitlement - paid out.

Кредитные продажи не дают cash-available до фактического платежа. Если cash есть в другой валюте,
нужна явная конвертация.

### Over-withdrawal / negative partner position

Если партнёр получил больше, чем показывает текущий settlement/net position:

- создаётся negative partner position / receivable to venture;
- будущие dividends/capital returns блокируются или auto-net against negative;
- договор/procurement нельзя закрыть до урегулирования;
- отдельное ручное погашение допускается через cash contribution/return-to-venture.

Обычный venture loss уменьшает net result и remaining inventory capital. Убыток по вине
оператора/бизнеса (`partner liability`) дополнительно создаёт immediate negative position у
ответственного партнёра.

## Инварианты

- `Lot.contract_snapshot` immutable; realization и settlement не переписывают lot shares.
- Profit share применяется только к net profit after cost/loss within the same venture
  share-profile; loss share — по capital share.
- Sale realization append-only; возвраты/сторно — новые события.
- Деньги физически двигаются только через `CashEntry` + `JournalEntry`.
- Продажа может создать claim/available proceeds, но не должна молча переводить деньги из
  операционной кассы в capital pool.
- Вывод партнёру не может быть ledger-only.
- Закрытие procurement/agreement запрещено при active lots, unresolved negative positions,
  outstanding advances или unsettled required payout corrections.

## План реализации

### Фаза 1 — Domain schema and formulas
Добавить модели realization/settlement/partner position helpers и единые формулы split.

### Фаза 2 — Sale integration
На продаже создавать realization events рядом с существующим FIFO/ledger path. Старый
`PROFIT_ACCRUED` оставить как compatibility только до миграции отчётов, затем перевести в
provisional semantics.

### Фаза 3 — Partner positions and payouts
Переписать E14/E15 availability: capital return и dividend guards должны читать venture
positions, учитывая recovered capital, preliminary payouts, losses и reserves.

### Фаза 4 — Returns/writeoffs/reversals
Сторнировать realization append-only событиями и корректно двигать provisional/final positions.

### Фаза 5 — APIs and reports
Добавить endpoints/serializers для procurement venture state, agreement summary, payout preview,
negative positions, settlement snapshots. Обновить reports/E03 inputs.

### Фаза 6 — Frontend
Обновить карточку договора, finance/payment sheets, procurement detail: показать recovered capital,
preliminary profit, final/constructive settlement, ограничения вывода и negative position.

### Фаза 7 — Tests and Excel replay
Покрыть backend сценарии US-1..US-9, прогнать frontend build, затем replay на Excel данных через
API/UI-like workflow.

## Задачи (чек-лист)

### Фаза 1
- [x] T-1.1 Добавить `ProcurementSaleRealization` и `ProcurementVentureSettlement` models.
- [x] T-1.2 Добавить formula helper: sale proceeds → per-currency capital/profit/loss split.
- [x] T-1.3 Добавить aggregate helper: procurement venture position by partner.
- [x] T-1.4 Миграции без backfill; для dev reset допускается очистка БД после схемы.

### Фаза 2
- [x] T-2.1 Интегрировать realization creation в sale service.
- [x] T-2.2 Добавить idempotency/source refs для sale_line/return/writeoff.
- [x] T-2.3 Сохранить совместимость текущих profit ledger tests или заменить целевыми тестами.

### Фаза 3
- [x] T-3.1 Переписать `partner_capital_positions` с учётом recovered capital.
- [x] T-3.2 Переписать capital return guard: undeployed pool + recovered capital - returned - reserve. *(UZS/USD payout with explicit FX snapshot; if funds are in another currency, use explicit finance conversion first)*
- [x] T-3.3 Переписать dividend guard: profit unavailable before settlement; after settlement
  net profit entitlement - paid - reserve - negative.
- [x] T-3.4 Добавить negative position service и payout/settlement blocking reasons. *(close action itself is still product-flow dependent)*

### Фаза 4
- [x] T-4.1 Sale return reverses realization/provisional profit append-only.
- [x] T-4.2 Disposal/writeoff records loss by capital share and reduces available-to-pay.
- [x] T-4.3 Procurement/batch reversal respects realized vs unsold quantities. *(strict guard: sold lots block batch reversal)*

### Фаза 5
- [x] T-5.1 API: procurement venture summary.
- [x] T-5.2 API: agreement partner proceeds summary.
- [x] T-5.3 API: payout preview with blocking reasons.
- [x] T-5.4 Reports: expose capital/recovered/provisional/final/paid buckets.

### Фаза 6
- [x] T-6.1 Frontend agreement card: venture proceeds and positions.
- [x] T-6.2 Frontend recovered-capital payout from sales with operating cash source. *(UZS/USD with explicit FX snapshot)*
- [x] T-6.3 Frontend recovered-capital payout sheet: capital return states and currency-aware account filtering.
- [x] T-6.4 Procurement detail: settlement checkpoint action and summary.

### Фаза 7
- [x] T-7.1 Unit tests for formula matrix.
- [x] T-7.2 Service tests: sale profit, sale loss, return, writeoff, over-withdrawal.
- [x] T-7.3 API tests for procurement venture summary and recovered-capital fields.
- [x] T-7.6 API tests for payout preview/blocking reasons.
- [x] T-7.4 Frontend `npm run build`.
- [ ] T-7.5 Excel replay validation through API/UI-like workflow.

## Открытые вопросы

- ? Какой UX-термин выбрать: “предварительная прибыль”, “доступно к выводу”, “финальная сверка”.

## Решённые вопросы (история)

- ✓ 2026-06-05: единица результата → `Procurement` как отдельный venture; agreement может
  содержать несколько venture.
- ✓ 2026-06-05: продажа не финализирует profit; она создаёт realization и preliminary result.
- ✓ 2026-06-05: capital recovery должен учитываться отдельно от profit.
- ✓ 2026-06-05: промежуточные выплаты разрешены, но требуют final adjustment и negative position
  при переплате.
- ✓ 2026-06-05: продажные деньги физически остаются в операционной кассе; claim/перевод в pool
  должен быть явным, не молчаливым.
- ✓ 2026-06-06: recovered capital из операционной кассы в pool автоматически не переводим;
  payout/transfer остаётся явным действием.
- ✓ 2026-06-06: reserve policy по умолчанию — 0%; резервы задаются явно на settlement/checkpoint.
- ✓ 2026-06-06: recovered capital можно выводить в UZS/USD только с явным FX snapshot; скрытой
  межвалютной конвертации при payout нет.
- ✓ 2026-06-06: порядок E16-rework зафиксирован как per-currency realization first, затем
  netting by venture/share-profile; running profit до settlement не является withdrawable.
- ✓ 2026-06-06: cross-currency margin требует явный sale-time FX snapshot; UZS-поля являются
  functional/reporting projection. FX-дрейф капитала идёт по capital share, не по profit share.
- ✓ 2026-06-06: на settlement неттится не только profit, но и recovered capital/loss. Для
  полностью ликвидированного прибыльного венчура весь proceeds должен принадлежать партнёрам:
  `Σ(capital_return_available + profit_available) == Σproceeds`.
- ✓ 2026-06-06: `remaining_inventory_capital_uzs` означает только капитал в физически
  нераспроданном товаре. Partner-liability loss не считается рыночным убытком венчура:
  капитал невиновного партнёра становится возвратным, а у виновного партнёра появляется
  negative position.
