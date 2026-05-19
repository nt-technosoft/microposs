# E09 Phase 2 — ON_SALE Mechanics Execution Plan (для Sonnet)

> Phase 2 — реализация автомат-обязательства поставщику при продаже из
> CONSIGNED Lot (товар на реализации). Архитектурные решения зафиксированы
> Опусом на брейншторме 2026-05-19. **Sonnet не должен принимать
> архитектурные решения.** Любой branch point, не описанный здесь → стоп,
> surface founder'у.
>
> Параллельно вести epic checkboxes в [`E09-procurement-completeness.md`](./E09-procurement-completeness.md).

---

## Архитектурные решения (locked)

1. **Trigger location: Variant A — синхронно в той же транзакции, что и `create_sale`.**
   Не через OutboxEvent receiver. Outbox остаётся для notification/audit,
   но не как primary mechanism для обязательной бизнес-логики.

2. **Модульность.** Логика живёт в новом модуле
   `apps/suppliers/consignment_obligations.py`, не размазана по
   `sales/services.py`. Sales вызывает одну функцию — это так же декаплено,
   как outbox-receiver, но без eventual consistency.

3. **Per-SaleLine payable, не накопительный.**
   Каждая продажа из CONSIGNED Lot → отдельный `SupplierPayable` с
   `reason=CONSIGNMENT_SALE`, `original_amount = unit_cost × quantity`.
   Это:
   - Согласуется с уже существующей моделью SupplierPayable + derived
     `paid_amount` (Phase 2 E08) без мутации `original_amount`.
   - Не требует новых моделей-аккумуляторов.
   - Аудит per-sale: каждая консигнационная продажа — отдельный fact.
   - Аггрегат «всего к оплате поставщику X» — это `Σ open consignment
     payables for X`, обычный query.

4. **Payment не создаётся автоматически.**
   `create_sale` создаёт только `SupplierPayable(reason=CONSIGNMENT_SALE)`.
   Реальная оплата поставщику — отдельная пользовательская операция
   (action `PAY_CONSIGNMENT_OBLIGATION` или существующий
   `pay_supplier_payable`).

5. **Journal для CONSIGNED-продажи.**
   Стандартная sale-журнализация (DR Cash/AR / CR Revenue) остаётся.
   Дополнительно для CONSIGNED slice: вместо `DR COGS / CR Inventory`
   пишем `DR COGS / CR A/P Supplier (linked to the new payable)`.
   Это — branch в существующем sale-journal builder. См. Slice 2.

6. **Idempotency не нужна на уровне wrapper.**
   `create_sale` уже атомарен + idempotent по `client_request_id`. Если
   повторный вызов — `create_sale` возвращает существующий sale, wrapper
   не вызывается дважды.

## Открытые вопросы — Sonnet обязан surface, не угадывать

Ни один из этих вопросов не должен решаться Сонетом самостоятельно:

- **OPEN-1.** В каком поле `Lot` хранится cost для CONSIGNED slice — `unit_cost` (functional UZS) или есть `operation_unit_cost` + `operation_currency`? Какая валюта supplier-обязательства — функциональная UZS или operation currency? Перед Slice 1 прочитать `apps/inventory/models.py:Lot` и сообщить.

- **OPEN-2.** Что сейчас делает `_record_receive_journal` (в `apps/partnerships/workspace.py`) для CONSIGNED procurement? Создаёт ли inventory journal вообще? Если да — нужно ли его теперь подавлять для CONSIGNED, потому что мы не владеем товаром? Перед Slice 1 прочитать функцию и сообщить.

- **OPEN-3.** Есть ли сейчас в `sales/services.py:create_sale` место, где можно безопасно вклинить wrapper-вызов? Где конкретно создаётся SaleLine и где формируется journal? Перед Slice 2 показать локацию.

Эти 3 вопроса должны быть пройдены в Slice 0 (investigation) до начала реализации.

---

## Контракт изменений

### Новый модуль: `apps/suppliers/consignment_obligations.py`

```python
"""
E09 Phase 2 — авто-обязательство поставщику при продаже CONSIGNED Lot.

Вызывается синхронно из sales/services.py:create_sale в той же
транзакции. Если SaleLine соответствует CONSIGNED Lot, создаёт
SupplierPayable с reason=CONSIGNMENT_SALE.
"""

from decimal import Decimal
from django.db import transaction

from apps.suppliers.models import SupplierPayable


def record_consignment_obligation_for_sale_line(sale_line) -> SupplierPayable | None:
    """
    Если sale_line продаёт CONSIGNED товар — создать соответствующее
    обязательство поставщику. Иначе вернуть None.

    Должна вызываться внутри transaction.atomic() из create_sale.
    """
    lot = sale_line.lot
    if lot.is_owned:
        return None

    procurement = lot.received_batch.procurement
    supplier_id = procurement.supplier_id
    if supplier_id is None:
        # CONSIGNED Lot без supplier-а — невозможная ситуация по
        # validate_procurement_combination, но защищаемся.
        raise ValueError(
            f'Cannot create consignment obligation: Lot#{lot.pk} '
            f'has no supplier on its procurement.'
        )

    cost_slice, currency, fx_rate = _resolve_sale_line_cost(sale_line, procurement)

    payable = SupplierPayable.objects.create(
        tenant_id=sale_line.tenant_id,
        supplier_id=supplier_id,
        procurement=procurement,
        settlement=getattr(procurement, 'terms', None),
        original_amount=cost_slice,
        currency_of_obligation=currency,
        fx_rate_at_obligation=fx_rate,
        status=SupplierPayable.Status.OPEN,
        reason=SupplierPayable.Reason.CONSIGNMENT_SALE,
    )
    # Publish for audit only — НЕ как primary trigger.
    from apps.core.services import publish_event
    publish_event(
        event_type='consignment_obligation.created',
        payload={
            'sale_line_id': sale_line.id,
            'lot_id': lot.id,
            'supplier_id': supplier_id,
            'procurement_id': procurement.id,
            'payable_id': payable.id,
            'amount': str(cost_slice),
            'currency': currency,
        },
        tenant_id=sale_line.tenant_id,
    )
    return payable


def _resolve_sale_line_cost(sale_line, procurement) -> tuple[Decimal, str, Decimal]:
    """
    Resolve cost slice for sale_line in supplier-obligation currency.
    Returns (amount, currency, fx_rate_snapshot).

    Зависит от OPEN-1 — заполнить после ответа от founder'а.
    """
    # ПЛЕЙСХОЛДЕР — заменить после OPEN-1 resolution.
    raise NotImplementedError('OPEN-1 not resolved')
```

### Изменение `SupplierPayable.Reason`

Файл: `apps/suppliers/models.py`, class `SupplierPayable.Reason`:

Добавить новое значение:
```python
CONSIGNMENT_SALE = 'CONSIGNMENT_SALE', 'Продажа консигнации'
```

Migration: добавление enum value на CharField — не требует data migration.

### Изменение `apps/sales/services.py:create_sale`

Внутри существующей `transaction.atomic()` блока, **после** создания SaleLine и **до** journal builder вызова:

```python
from apps.suppliers.consignment_obligations import record_consignment_obligation_for_sale_line

# ... existing sale + sale_line creation ...

consignment_payables_by_line = {}
for sale_line in sale_lines:
    payable = record_consignment_obligation_for_sale_line(sale_line)
    if payable is not None:
        consignment_payables_by_line[sale_line.id] = payable

# ... pass consignment_payables_by_line into journal builder ...
```

Конкретная локация вставки определяется в OPEN-3.

### Изменение sale journal builder

Файл: где формируется JournalEntry для sale (это знает OPEN-3).

Для каждой SaleLine:
- Если `lot.is_owned == True` (стандартное поведение):
  `DR COGS account / CR Inventory account` (как сейчас)
- Если `lot.is_owned == False` (CONSIGNED, новый case):
  `DR COGS account / CR Supplier A/P account`, **с reference на новый payable**
  из `consignment_payables_by_line[sale_line.id]`.

Revenue side (`DR Cash/AR / CR Revenue`) не меняется в любом случае.

### Action `PAY_CONSIGNMENT_OBLIGATION` (опционально для этой фазы)

**ВАРИАНТ A (минимум):** не делать отдельный action. Существующий
`pay_supplier_payable` уже умеет работать с любым payable по pk. UI просто
покажет список consignment-payables (фильтр по `reason=CONSIGNMENT_SALE`)
и для каждого вызовет существующий endpoint. **Рекомендую — минимум кода.**

**ВАРИАНТ B (агрегированная оплата):** новый service
`pay_consignment_obligations(supplier_id, total_amount, allocations)` —
платит **сразу за несколько** open consignment-payables этого поставщика,
автомат распределяя сумму по FIFO. Удобнее для UX, но логика сложнее.

**Решение в плане: ВАРИАНТ A.** Слайс с PAY_CONSIGNMENT_OBLIGATION action
отдельно — не входит в эту фазу.

---

## Порядок выполнения (slices)

### Slice 0 — Investigation (no code changes)

Прочитать и сообщить ответы founder'у:

1. **OPEN-1**: посмотреть `apps/inventory/models.py:Lot` — какие поля для
   cost. Сообщить набор и предложить какие использовать для
   supplier-обязательства.
2. **OPEN-2**: прочитать `apps/partnerships/workspace.py:_record_receive_journal`
   и понять что происходит для CONSIGNED procurement сейчас.
3. **OPEN-3**: найти место в `apps/sales/services.py:create_sale` где
   создаются SaleLine и формируется journal. Показать локацию (file:line).

**Не приступать к Slice 1 до получения ответов на эти 3 вопроса.**
Founder вернёт plan-supplement с конкретными решениями. После — продолжать.

### Slice 1 — Модель + миграция + модуль (atomic)

1. Edit `apps/suppliers/models.py`: добавить
   `SupplierPayable.Reason.CONSIGNMENT_SALE`.
2. `makemigrations suppliers` + apply.
3. Создать `apps/suppliers/consignment_obligations.py` с функцией
   `record_consignment_obligation_for_sale_line` (с резолвленным OPEN-1
   `_resolve_sale_line_cost`).
4. Edit `apps/suppliers/__init__.py` если нужно (вряд ли).
5. **Тестовый sanity check без интеграции в sales:**
   - В Django shell: создать procurement с `goods_ownership=CONSIGNED`,
     receive_batch, lot с `is_owned=False`. Создать mock SaleLine. Вызвать
     `record_consignment_obligation_for_sale_line(sale_line)`. Проверить
     что создался SupplierPayable с правильным reason / amount / currency.

**Commit**: `feat(E09-T-2.2 wrapper): supplier consignment obligation module + CONSIGNMENT_SALE reason`

### Slice 2 — Wire-up в sales/services.py (atomic)

1. Edit `sales/services.py:create_sale` (точная локация из OPEN-3):
   вызвать wrapper для каждого SaleLine после создания SaleLine.
2. Edit sale journal builder: branch на `lot.is_owned`. Для CONSIGNED →
   credit A/P вместо Inventory, с reference на новый payable.
3. Run: `pytest apps/core/tests/test_sale_multi_payment.py
   apps/core/tests/test_e07_supplier_payables.py
   apps/core/tests/test_e07_workspace_contract.py -q`. Все должны
   остаться зелёными — мы только добавили CONSIGNED branch, не изменили
   OWNED поведение.

**Commit**: `feat(E09-T-2.2): wire consignment obligation into create_sale + journal branch`

### Slice 3 — Invariant tests

Расширить `apps/core/tests/test_e08_sharia_invariants.py` новым классом
`ConsignmentObligationInvariants`:

- `test_owned_sale_does_not_create_consignment_payable` — продажа из OWNED
  Lot не создаёт payable с reason=CONSIGNMENT_SALE.
- `test_consigned_sale_creates_payable_with_correct_amount` — продажа из
  CONSIGNED Lot создаёт payable; `original_amount = unit_cost × quantity`;
  `currency = procurement.currency_of_obligation`; `reason=CONSIGNMENT_SALE`.
- `test_consigned_payable_has_open_status_initially` — created payable
  имеет `status=OPEN`, `paid_amount=0`, `remaining_amount=original`.
- `test_multiple_consigned_sales_create_separate_payables` — две продажи
  из одного Lot → два разных payable, не один накопительный.
- `test_consigned_payable_journal_credits_ap_not_inventory` — проверить
  что journal lines для CONSIGNED sale имеют CR A/P account, не CR Inventory.

Запуск: все эти + существующие sharia invariants → зелёные.

**Commit**: `test(E09-T-2.4): invariants for consignment obligation generation`

### Slice 4 — Wrap (docs)

1. Mark T-2.1, T-2.2, T-2.3 (как Variant A — без отдельного service),
   T-2.4 как `[x]` в `docs/roadmap/E09-procurement-completeness.md`.
2. T-2.5 (UI) — НЕ trogать. Это под контролем founder'а.
3. Закрыть `OPEN-1`, `OPEN-2`, `OPEN-3` в разделе «Открытые вопросы» с
   решениями.
4. Обновить прогресс E09 в `docs/ROADMAP.md` на ~65% (Phase 1 ~30% +
   Phase 2 ~35%).
5. Добавить решённый вопрос в epic: какой именно cost reso выбран
   (из OPEN-1), статус journal builder branch.

**Commit**: `docs(E09-phase2): mark ON_SALE mechanics complete; document OPEN-1/2/3 resolutions`

---

## Что НЕ делать в этом плане

- Не трогать UI. T-2.5 — под контролем founder'а.
- Не реализовывать `pay_consignment_obligations` агрегированный action
  (Вариант B из T-2.3). Существующий `pay_supplier_payable` достаточен.
- Не делать Phase 3 (returnability) — отдельный план.
- Не убирать `_record_receive_journal` или менять его поведение для
  OWNED procurement — только для CONSIGNED (если OPEN-2 покажет что
  оно вообще что-то делает для CONSIGNED).

## Если что-то пошло не так

- **Тесты на OWNED sale краснеют после Slice 2** → значит journal builder
  branch затронул OWNED-path. Откатить journal изменения, пересмотреть
  branching. Surface founder'у.
- **CONSIGNED Lot имеет supplier_id=None** → ошибка предыдущего слайса
  (validate_procurement_combination должна была это запретить). Surface.
- **`Lot.is_owned` отсутствует** → Phase 1 не до конца применена. Откатиться.
- **`SupplierPayable.Reason` уже имеет CONSIGNMENT_SALE** → кто-то уже
  начал. Surface.

## Sanity-чек после всего

```bash
cd /Users/aziztohirov/Desktop/Projects/microposs/backend
DJANGO_SETTINGS_MODULE=config.settings.development \
  .venv/bin/python manage.py validate_payable_consistency
# OK

DJANGO_SETTINGS_MODULE=config.settings.development \
  .venv/bin/python -m pytest \
  apps/core/tests/test_e07_procurement_policy.py \
  apps/core/tests/test_e08_sharia_invariants.py \
  apps/core/tests/test_e09_procurement_combinations.py \
  apps/core/tests/test_e07_supplier_payables.py \
  apps/core/tests/test_e07_workspace_contract.py \
  apps/core/tests/test_sale_multi_payment.py \
  apps/core/tests/test_partner_ledger.py \
  -q
# all green (или минимум pre-existing failures как в Phase 1)
```

Если зелёные — Slice 4, commit, готово.
