# E01 — Suppliers & Procurement (расширенная модель)

**Статус:** 🟡 `IN_PROGRESS`
**Прогресс:** ~30% (модель данных проектируется)
**Зависит от:** —
**Блокирует:** E02, E03, E05
**Параллельно:** E02, E04

---

## Цель

Расширить модель работы с поставщиками так, чтобы система покрывала **все реальные сценарии прихода товара и расчётов**: предоплата, частичная оплата, отсрочка, рассрочка, реализация (консигнация), мульти-кассовые и мульти-валютные расчёты. Из этого автоматически появляется корректная дебиторская/кредиторская позиция.

## Контекст и обоснование

Сегодня большая часть retail-бизнесов работает с поставщиками **не за наличные сразу**: дистрибьюторы дают товар в отсрочку, часть товара берут на реализацию, кто-то платит частично-наличными-частично-картой, кто-то держит долг в USD по фиксированному курсу. У нас в бэкенде заложен скелет (`Supplier`, `SupplierPayment`, частично консигнация), но **полный цикл взаимодействия и UX отсутствуют**. Без этого эпика мы не сможем дать честную отчётность о реальной ценности бизнеса (E03).

«Поставщик» в этом эпике — **любой контрагент, у которого мы получаем товар**: дистрибьютор, локальный поставщик (хлеб, молочка), производитель и т.д. Дистрибьютор — частный случай поставщика, не отдельная сущность.

## Сценарии (use cases)

### Виды условий получения товара
- **US-1.** Поставщик отдаёт товар, бизнес платит **сразу полностью** (наличные / карта / транзит)
- **US-2.** Поставщик отдаёт товар, бизнес платит **частично сейчас**, остальное в отсрочку / рассрочку
- **US-3.** Поставщик отдаёт товар **в отсрочку** (платёж в установленный срок, единым)
- **US-4.** Поставщик отдаёт товар **в рассрочку** (несколько платежей по графику)
- **US-5.** Поставщик отдаёт товар **на реализацию (консигнация)** — оплата только после продажи, можно вернуть нереализованный
- **US-6.** Смешанный сценарий: часть товара в одной приёмке оплачена сразу, часть — в отсрочку

### Виды оплат поставщику
- **US-7.** Оплата с **наличной кассы UZS**
- **US-8.** Оплата с **наличной кассы USD по курсу на дату оплаты**
- **US-9.** Оплата с **банковской карты / расчётного счёта**
- **US-10.** Оплата **частями из разных касс** (например: часть с карты, часть наличными)

### Учётные эффекты
- **US-11.** При оплате частично/отсрочка — автоматически возникает **кредиторская задолженность перед поставщиком** (`SupplierPayable`)
- **US-12.** При возврате товара по консигнации — корректное уменьшение задолженности
- **US-13.** При полной оплате — задолженность закрыта, журнал движения денег обновлён

## Текущее состояние

- ✅ **Что уже есть:**
  - Базовые модели `Supplier`, `SupplierPayment` в `apps/suppliers`
  - Модель `Procurement` (новый путь прихода товара) — `docs/domain/procurement.md`
  - Legacy `Receipt` поддерживает consignment_rule (margin / commission) — `docs/domain/procurement.md` §Консигнация
  - `ProcurementExpense` (landed costs)
  - `JournalEntry` создаётся при подтверждении приёмки (Inventory / Payables / Investor Capital)
  - Идемпотентность (`client_request_id`) для финансовых POST-эндпоинтов

- ⚠️ **Что начато, но не завершено:**
  - Полный цикл частичной оплаты + остатка в отсрочку — модель есть, UX нет
  - Мульти-кассовая оплата — `CashAccount` существует, но интерфейс «оплатить из нескольких касс» отсутствует
  - Консигнация на новой Procurement-канве (сейчас в legacy Receipt)

- ❌ **Чего нет вообще:**
  - Графика рассрочки (`PaymentSchedule`) с напоминаниями о срокам
  - Связи «один приёмочный акт → несколько платежей разной природы»
  - Авто-формирования `SupplierPayable` из приёмки в зависимости от условий
  - Учёта валютного долга (USD-долг по курсу даты сделки vs текущему)

## План реализации

### Фаза 1 — Модель условий оплаты и кредиторки

**Новые сущности:**

- **`ProcurementTerms`** (OneToOne к Procurement)
  - `type`: PREPAID | PARTIAL | DEFERRED | INSTALLMENT | CONSIGNMENT
  - `currency_of_obligation` (UZS / USD / …)
  - `fx_rate_at_obligation` (snapshot курса на момент возникновения долга)
  - `total_amount_due` (валидируется = Σ ProcurementItem.quantity × unit_price × fx_rate)
  - `paid_amount`, `remaining_amount` (агрегаты)
  - `status`: OPEN / PARTIALLY_PAID / FULLY_PAID / CANCELLED
  - `deadline_date` (только для DEFERRED)
  - `consignment_rule` JSON (для CONSIGNMENT)

- **`PaymentSchedule`** (для INSTALLMENT)
  - `procurement_terms_id`, `sequence_number`, `due_date`, `amount`, `currency`
  - `status`: PENDING / PAID / OVERDUE / CANCELLED
  - `paid_at`, `paid_amount`

- **`SupplierPayable`**
  - `tenant_id`, `supplier_id`, `procurement_id`
  - `original_amount`, `paid_amount`, `remaining_amount`
  - `currency_of_obligation`, `fx_rate_at_obligation`
  - `status`: OPEN / SETTLED / CANCELLED

**Расширения существующих:**

- `Supplier`: + `default_payment_terms`, + `default_currency`, + `notes`
- `Procurement`: `supplier_id` становится **nullable** (см. решённые вопросы)
- `SupplierPayment`: + `payable_id` (FK), + `allocations` (JSON списком `(cash_account_id, amount, currency)`), + `schedule_entry_id` (опц.)

**Инварианты:**
- `ProcurementTerms` обязателен для каждого подтверждённого Procurement
- `SupplierPayable` существует только если `type != PREPAID` И `remaining_amount > 0`
- Если `type != PREPAID` → `procurement.supplier_id` обязателен (валидируется на confirm)
- `remaining_amount = original_amount − paid_amount` (БД constraint)
- USD-обязательства фиксированы по `fx_rate_at_obligation`, не переоцениваются

### Фаза 2 — Мульти-касса и мульти-валюта в оплатах

`SupplierPayment.allocations` — JSON-список аллокаций: `[{cash_account_id, amount, currency}, ...]`. Сумма аллокаций в валюте обязательства = `payment.total_amount`. Курсовая разница (если карта в UZS, а долг в USD) фиксируется в момент платежа как FX-эффект, отдельным `JournalEntry`.

### Фаза 3 — UX: единая форма приёмки + экран оплат

**Форма приёмки (4 шага):**
1. Поставщик (опционально для PREPAID, обязательно иначе) — поиск + недавние + quick-add
2. Товары — поиск с сортировкой preferred → secondary → остальные (по `ProductSupplier` из E02), inline-создание товара
3. Условия оплаты — селектор типа + соответствующие поля
4. Подтверждение — atomic-транзакция: Procurement + Terms + Lots + Payable + Journal + ProductSupplier upsert

**Экран «Оплаты поставщику»** — список открытых `SupplierPayable`, фильтры (горящие, просроченные, по поставщику), форма оплаты с мульти-кассой.

### Фаза 4 — Консигнация и возвраты

См. отдельный раздел [Сценарии возврата консигнации](#сценарии-возврата-консигнации) ниже.

**Новые сущности:**
- `ConsignmentReturn` (документ возврата)
- `ConsignmentReturnLine` (с `disposition` enum)

Каждая линия может иметь разный disposition — это даёт гибкость для смешанных кейсов (часть вернули, часть списали).

### Фаза 5 — Графики рассрочки и напоминания

Celery-задача-сторож на `PaymentSchedule.due_date`. Дашборд «Что горит сегодня / эта неделя / просрочено». Без email/SMS на первом этапе — только in-app.

---

## Сценарии возврата консигнации

`ConsignmentReturnLine.disposition` определяет, что происходит с этой линией:

| Disposition | Stock-эффект | Payable-эффект | Journal | Кто несёт убыток |
|---|---|---|---|---|
| **RETURN_TO_SUPPLIER** | `-quantity` (StockMovement: CONSIGNMENT_RETURN_OUT) | `-= agreed_price × qty` | Debit Payables, Credit Inventory | Поставщик (забрал товар) |
| **DISPOSE_SUPPLIER_LOSS** | `-quantity` (StockMovement: DISPOSAL) | `-= cost × qty` | Debit Payables, Credit Inventory | Поставщик |
| **DISPOSE_BUSINESS_LOSS** | `-quantity` (StockMovement: DISPOSAL) | без изменений | Debit Loss, Credit Inventory | Бизнес |
| **CONVERT_TO_OWN** | лот «переоформляется» в собственный (`contract_snapshot` иммутабельный → делаем split: списываем consignment-часть лота, создаём новый owned-lot на ту же qty с новым landed_cost) | `+= agreed_price × qty` (новое payable) | Debit Inventory (если ↑cost), Credit Payables | Бизнес платит |

**Покрываемые real-world кейсы:**
- Сезон закончился, всё нереализованное вернули → все линии `RETURN_TO_SUPPLIER`
- Часть вернули, часть протух (брак на нашей совести) → `RETURN_TO_SUPPLIER` + `DISPOSE_BUSINESS_LOSS`
- Часть вернули, поставщик не принял испорченное (зачёт только за годное) → `RETURN_TO_SUPPLIER` с qty годного + `DISPOSE_BUSINESS_LOSS` на остаток
- Поставщик пошёл навстречу, списывает брак на себя → `DISPOSE_SUPPLIER_LOSS`
- Остатки выкупили в собственность по сниженной цене → `CONVERT_TO_OWN`

**Один документ `ConsignmentReturn` может содержать смесь dispositions** — это и есть гибкость.

**Иммутабельность `Lot`:** при `CONVERT_TO_OWN` лот не редактируется. Делаем «split»: уменьшаем quantity консигнационного лота (через StockMovement), создаём **новый Lot** с типом OWNED, тот же товар, новая landed_cost = agreed_price + аллокированные расходы. Аудит-trail сохранён.

## Задачи (чек-лист)

### Фаза 1 — модель и сервисы
- [ ] T-1.1 Спроектировать поля `ProcurementTerms` (final review с командой)
- [ ] T-1.2 Спроектировать поля `SupplierPayable` (final review)
- [ ] T-1.3 Спроектировать поля `PaymentSchedule` (final review)
- [ ] T-1.4 Расширения существующих моделей: `Supplier`, `Procurement.supplier_id` nullable, `SupplierPayment.allocations`
- [ ] T-1.5 Миграции БД (с обратной совместимостью для существующих Procurement)
- [ ] T-1.6 Сервис `procurement.confirm(procurement_id, terms_payload, payment_payload?)` — atomic-операция (Procurement + Terms + Lots + Payable + Journal)
- [ ] T-1.7 Валидаторы инвариантов (см. список инвариантов в Плане)
- [ ] T-1.8 Тесты: 5 типов условий × сценарии (PREPAID без поставщика, DEFERRED с дедлайном, INSTALLMENT с графиком, CONSIGNMENT, PARTIAL)
- [ ] T-1.9 API-эндпоинты: `POST /api/v1/procurement/{id}/confirm/`, `GET /api/v1/suppliers/payables/`

### Фаза 2 — мульти-касса / мульти-валюта
- [ ] T-2.1 Расширить `SupplierPayment.allocations` (JSON-field + validators)
- [ ] T-2.2 Сервис `supplier.pay(payable_id, allocations=[...])` с FX-конвертацией в валюте обязательства
- [ ] T-2.3 Журнальные проводки для FX-эффекта при платеже не в валюте обязательства
- [ ] T-2.4 API: `POST /api/v1/suppliers/payables/{id}/pay/`
- [ ] T-2.5 Тесты: однокассовая, мультикассовая, мультивалютная (UZS долг оплачен USD; USD долг оплачен карточкой UZS)

### Фаза 3 — UX
- [ ] T-3.1 Шаг 1 (поставщик): поиск + недавние + quick-add inline
- [ ] T-3.2 Шаг 2 (товары): сортировка preferred → остальные (использует E02 endpoint)
- [ ] T-3.3 Шаг 2: inline-создание товара с авто-привязкой к поставщику (использует E02 hook)
- [ ] T-3.4 Шаг 3 (условия): селектор типа + reactive-поля по выбранному типу
- [ ] T-3.5 Шаг 4 (подтверждение): сводка + atomic-confirm
- [ ] T-3.6 Экран «Оплаты поставщику»: список открытых payables, фильтры
- [ ] T-3.7 Форма оплаты: мульти-касса allocator, привязка к графику
- [ ] T-3.8 Mobile-first responsive все экраны
- [ ] T-3.9 AbortController + debounce на поисках

### Фаза 4 — консигнация
- [ ] T-4.1 Модель `ConsignmentReturn` + `ConsignmentReturnLine`
- [ ] T-4.2 Перенос consignment_rule из legacy Receipt в `ProcurementTerms.consignment_rule`
- [ ] T-4.3 Сервис `consignment.process_return(return_id)` — atomic с обработкой всех 4 dispositions
- [ ] T-4.4 Логика split-лота для `CONVERT_TO_OWN` (списание consignment-части + новый owned-lot)
- [ ] T-4.5 UX: экран «Возврат поставщику» с возможностью указать disposition построчно
- [ ] T-4.6 Тесты на все 4 disposition + смешанные сценарии

### Фаза 5 — графики и напоминания
- [ ] T-5.1 Celery beat-задача для проверки `PaymentSchedule.due_date`
- [ ] T-5.2 Логика отметки `OVERDUE` после due_date + 1 день
- [ ] T-5.3 UI-дашборд «Что горит» (горящие / просроченные / в работе)
- [ ] T-5.4 Карточка поставщика с историей задолженности

## Открытые вопросы

- ? **Изменение условий после приёмки через amendment** — модель `ProcurementTermsAmendment` (план: дата, что изменилось, кто, причина). Не блокер для Фазы 1, поднимаем когда дойдём до Фазы 2.
- ? **Inline-создание поставщика в форме приёмки** — какие минимальные поля (name + currency + ничего больше)? Или нужны контакты, реквизиты?
- ? **OVERDUE-нотификации** — только in-app, или нужны email/SMS сразу? (план: только in-app в MVP, email/SMS — после первых клиентов)
- ? **Quick-add нового товара** — нужна ли категория обязательная, или допускаем «без категории» (категория = NULL)?

## Решённые вопросы (история)

- ✓ 2026-05-12: «Дистрибьютор vs поставщик» → не разделяем как сущности; дистрибьютор это частный случай поставщика, отличается типом условий (чаще отсрочки, рассрочки)
- ✓ 2026-05-12: «Можно ли отказаться от halal-screening?» → да, технический фильтр обходим; вместо него — manual review бизнеса при онбординге
- ✓ 2026-05-12: «USD-долг переоценка по курсу или фикс?» → **фикс на момент возникновения** (`fx_rate_at_obligation`); курсовая разница появляется только в момент платежа в другой валюте и отражается отдельно как FX-эффект
- ✓ 2026-05-12: «Можно ли менять условия после приёмки?» → да, но **только через явное `ProcurementTermsAmendment`** с записью в историю. Молчаливое редактирование запрещено.
- ✓ 2026-05-12: «Primary supplier — флаг или сортировка?» → не делаем явный флаг. Сортируем по `last_received_at` + объёму (см. E02).
- ✓ 2026-05-12: «Inline-создание товара — полная форма или минимум?» → минимум (name + опц. category + опц. baseline price). Полная карточка — отдельный экран в каталоге.
- ✓ 2026-05-12: «Смешанные валюты в одной приёмке?» → товары могут быть в разных валютах (fx_rate per item), но `currency_of_obligation` всегда одна. Если в реальной накладной микс — делаем 2 приёмки.
- ✓ 2026-05-12: «Что считать просрочкой?» → DEFERRED: deadline + 1 день. INSTALLMENT: due_date + 1 день. Льготных периодов нет (если нужно — оформляется как amendment к условиям).
- ✓ 2026-05-12: «Штрафы/пени в модели?» → нет. Если возникают — отдельная ручная операция, создающая `SupplierPayable(type=PENALTY)`. Не плодим модель.
- ✓ 2026-05-12: «Procurement без поставщика разрешён?» → **да, только для PREPAID** («бизнес купил за свои деньги»). Для всех остальных типов (DEFERRED, INSTALLMENT, CONSIGNMENT, PARTIAL) — поставщик обязателен. Валидируется на confirm.
- ✓ 2026-05-12: «Модель ConsignmentReturn» → отдельный документ с построчными `disposition`: `RETURN_TO_SUPPLIER` / `DISPOSE_SUPPLIER_LOSS` / `DISPOSE_BUSINESS_LOSS` / `CONVERT_TO_OWN`. Один документ может содержать смесь.
