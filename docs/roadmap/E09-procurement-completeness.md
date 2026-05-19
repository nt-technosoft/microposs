# E09 — Procurement Completeness (non-PREPAID, ON_SALE, returnability)

**Статус:** `IN_PROGRESS`
**Прогресс:** ~30%
**Зависит от:** E07, E08 (DONE)
**Блокирует:** E03 (Net Value требует корректного учёта CONSIGNED inventory), частично E05

---

## Цель

Завершить procurement matrix: расщепить `payment_timing` и `goods_ownership`
на независимые оси, реализовать ON_SALE-обязательство для консигнации
(автоматический payable при продаже), добавить returnability как
cross-cutting attribute. Без этого Net Value считается некорректно
(консигнационный товар не наш, но сейчас он попадает в стоимость инвентаря),
а полноценная POS-для-ритейла поддержка «в долг / в отсрочку / на реализацию»
у поставщика не закрыта.

## Контекст и обоснование

После E07 (controlled radical reset) и E08 (source-of-truth consolidation)
партнёрский трек и базовая архитектура зацементированы. Vacuum-сессия от
2026-05-19 показала, что procurement matrix лучше моделировать через 3
независимые оси:

- **funding_source** — `OWN_FUNDS | PARTNERSHIP`
- **payment_timing** — `PREPAID | PARTIAL | DEFERRED | INSTALLMENT | ON_SALE`
- **goods_ownership** — `OWNED | CONSIGNED`

Из 30 теоретических комбинаций легально 6. Сейчас в коде:

- Ось `funding_source` есть как `Procurement.funding_source` ✓
- Ось `payment_timing` живёт внутри `ProcurementTerms.type`, но **CONSIGNMENT
  смешивает timing (ON_SALE) и ownership (CONSIGNED) в одном enum-значении** —
  категориальная ошибка, которую нужно расщепить.
- Ось `goods_ownership` отсутствует как явное поле.
- ON_SALE-обязательство (автомат-payable при продаже CONSIGNED Lot) не
  дописан до конца.
- Returnability работает только для CONSIGNED через `ConsignmentReturn`;
  generic возврат поставщику (просрочка, брак, сезонный возврат с
  OWNED-Lot) — отсутствует.

## Сценарии (use cases)

- **US-1.** Бизнесмен берёт товар на реализацию у дистрибьютора (CONSIGNED),
  продаёт через POS — система автоматически генерирует обязательство
  поставщику в размере себестоимости проданного. Кассир ничего лишнего не
  делает.
- **US-2.** Бизнес видит «к оплате поставщику X: 2 350 000 UZS» (накопленный
  debt из консигнационных продаж), делает один платёж — оплата корректно
  гасит payable.
- **US-3.** Возврат поставщику просроченного товара (OWNED, не консигнация) —
  отдельный документ, корректирует payable или генерирует обратный платёж.
- **US-4.** UI создания procurement показывает три флага (источник × timing ×
  ownership) как независимые элементы, не смешивая их в один selector.
  Невалидные комбинации блокируются на бэке.
- **US-5.** Отчёт Net Value корректно различает: OWNED-товар на полке входит
  в стоимость инвентаря, CONSIGNED — нет.

## Текущее состояние

- ✅ **Что есть:** `Procurement.funding_source`, `ProcurementTerms.Type`
  (со смешанным CONSIGNMENT), `ConsignmentReturn` + `ConsignmentReturnLine`,
  `ConsignmentAgreement` (suppliers), `AgreementPartner.Role` (INVESTOR/OPERATOR
  → мушарака уже поддержана), policies.py с `PARTNERSHIP_SETTLEMENTS = (PREPAID,)`.
- ⚠️ **Начато, но не завершено:** CONSIGNMENT существует как enum в
  `ProcurementTerms.Type`, но логика «продажа CONSIGNED Lot → автомат payable»
  не дописана.
- ❌ **Чего нет вообще:** `Procurement.goods_ownership`, `Lot.is_owned`,
  `ProductVariant.is_returnable_default`, `Lot.is_returnable`, `SupplierReturn`
  (generic, не консигнационный), `validate_procurement_combination()` валидатор
  легальных точек матрицы.

## План реализации

### Фаза 1 — Refactor matrix axes

Backend-only рефакторинг без новой функциональности: расщепить CONSIGNMENT
на две оси, добавить `goods_ownership` и `Lot.is_owned`, чистка legacy.
Не трогает UI. План пригоден для делегирования Сонету.

### Фаза 2 — ON_SALE механика

Реализация автомат-генерации payable при продаже CONSIGNED Lot. Это новая
функциональность, влияет на sale.completed flow. Backend + минимальный UI
(отображение накопленного консигнационного долга, action оплаты).

### Фаза 3 — Returnability

Возврат поставщику как cross-cutting функциональность для OWNED-Lot. Новые
поля + новая модель `SupplierReturn` + service + UI. Может быть отложена
если приоритет — Net Value (E03) сначала.

## Задачи (чек-лист)

### Фаза 1 — Refactor (backend-only)

- [x] T-1.1 Добавить `Procurement.goods_ownership` поле (`OWNED | CONSIGNED`,
      default `OWNED`) + миграция.
- [x] T-1.2 Переименовать `ProcurementTerms.Type.CONSIGNMENT` → `ON_SALE`;
      data migration (если есть CONSIGNMENT строки — выставить
      `Procurement.goods_ownership=CONSIGNED` для родительского procurement).
- [x] T-1.3 Добавить `Lot.is_owned` boolean; в `receive_workspace_batch`
      устанавливать из `procurement.goods_ownership` при создании.
- [x] T-1.4 Создать `validate_procurement_combination(funding_source,
      payment_timing, goods_ownership)` в `policies.py`. Таблица легальных
      6 точек явно зафиксирована в коде.
- [x] T-1.5 Удалить MUSHARAKA legacy-нормализацию из `policies.py` +
      связанный тест-страж.
- [x] T-1.6 Переименовать `ProcurementPolicyContext.has_procurement_balance`
      → `has_partnership_capital_activity` (имя устарело после Phase 2).
- [x] T-1.7 Обновить тесты: `test_e07_procurement_policy.py` под новые
      имена, добавить invariant-тест на матрицу комбинаций.

### Фаза 2 — ON_SALE механика

- [ ] T-2.1 Решить: где живёт trigger автомат-payable — в `sales/services.py`
      напрямую или через OutboxEvent receiver в suppliers (см. открытые
      вопросы).
- [ ] T-2.2 Реализовать trigger: при `sale.completed` для каждого
      `SaleLine` с `Lot.is_owned=false` создать (или дополнить) payable +
      генерировать `Payment` когда пользователь оплачивает.
- [ ] T-2.3 Service `pay_consignment_obligation(payable_id, allocations)` —
      multi-cash оплата накопленных консигнационных обязательств.
- [ ] T-2.4 Invariant-тесты: CONSIGNED Lot не может породить immediate payable
      до продажи; первая продажа создаёт payable; multi-sale из одного
      CONSIGNED Lot не дублирует payable.
- [ ] T-2.5 UI (под контролем founder'а): отображение накопленного debt по
      консигнации, action оплаты, история консигнационных обязательств.

### Фаза 3 — Returnability

- [ ] T-3.1 Добавить `ProductVariant.is_returnable_default` boolean,
      default false.
- [ ] T-3.2 Добавить `Lot.is_returnable` boolean (override per-batch);
      `ReceiveBatch.returnable_until` optional date.
- [ ] T-3.3 Создать модель `SupplierReturn` + `SupplierReturnLine` —
      generic возврат для OWNED-Lot (аналог `ConsignmentReturn` но для
      не-консигнации).
- [ ] T-3.4 Service `record_supplier_return(lot_id, qty, reason)` — снижает
      `Lot.stock`, корректирует payable или генерирует обратный Payment.
- [ ] T-3.5 UI (под контролем founder'а): возврат поставщику.

## Открытые вопросы

- **? ON_SALE trigger architecture.** Где живёт логика автомат-payable при
  продаже CONSIGNED Lot — напрямую в `sales/services.py` (синхронно) или
  через OutboxEvent receiver в suppliers (асинхронно, decoupled)? Outbox
  чище архитектурно (cross-domain), но добавляет latency и нужно строить
  receiver. **Решение принимать в начале Фазы 2.**
- **? Payable per sale or per lot?** Когда CONSIGNED Lot из 100 единиц
  продаётся постепенно — создавать один payable, который наращивается с
  каждой продажей, или новый payable per sale? Первый вариант проще для
  UX («один счёт от поставщика»), второй точнее для аудита. **Решение в
  Фазе 2.**
- ~~**? Миграция существующих CONSIGNMENT.**~~ → решено 2026-05-19: в dev DB 0 строк в `Procurement` и `ProcurementTerms`, поэтому migration тривиальная — `RemoveField`/`AddField` без backfill. Применено в T-1.2.
- **? SupplierReturn vs ConsignmentReturn — разделить или обобщить?**
  Архитектурно: оставить `ConsignmentReturn` для CONSIGNED-Lot returns
  (там consignment-specific логика), добавить отдельный `SupplierReturn`
  для OWNED-Lot returns. Два разных бизнес-кейса. **Решение в Фазе 3.**
- **? UI для Фазы 1 нужен?** Backend-only рефакторинг технически не
  требует UI-изменений, но если поле `goods_ownership` теперь явное —
  логично дать пользователю отдельный селектор «свой / на реализации»
  вместо смешанного с типом оплаты. **Решение после демо Фазы 1.**

## Решённые вопросы (история)

- ✓ 2026-05-19: **`HYBRID` источник денег — не нужен.** PARTNERSHIP уже
  покрывает оба сценария мудараба + мушарака через `AgreementPartner.role`
  (INVESTOR/OPERATOR). Деньги бизнеса в мушараке проходят через
  `AgreementContribution(role=OPERATOR)`, не напрямую из CashAccount.
  Иначе нарушится инвариант Σ capital_share == 1.0 в Lot.contract_snapshot.
- ✓ 2026-05-19: **Procurement matrix — 3 независимые оси.**
  Из 30 теоретических точек легальны 6 (см. матрицу выше). Все остальные
  блокируются `validate_procurement_combination`.
- ✓ 2026-05-19: **Returnability — cross-cutting, не новая ось.**
  ProductVariant default + Lot override + SupplierReturn документ. Не
  блокер для MVP (на ~95% товаров не применимо), но архитектура должна
  поддерживать без миграции данных.
- ✓ 2026-05-19: **PARTNERSHIP × non-PREPAID запрещено категорически.**
  Если бизнес хочет привлечь инвестора и взять у поставщика отсрочку —
  это разные procurement-ы или операционная проблема. Архитектура не
  моделирует.
- ✓ 2026-05-19: **«Сроки поставки» — не ось.** Это атрибут конкретного
  `ReceiveBatch.received_at` (timestamp), а не классификация procurement-а.
  Соответственно стадии «заказал → оплатил → получил» — state machine
  одного и того же Procurement, а не оси.
