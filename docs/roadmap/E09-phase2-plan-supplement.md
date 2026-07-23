# E09 Phase 2 — Plan Supplement (resolutions for OPEN-1/2/3 + OPEN-4)

> Дополнение к [`E09-phase2-execution-plan.md`](./E09-phase2-execution-plan.md).
> На основе Slice 0 investigation report от Сонета (2026-05-19) + одно
> уточнение, всплывшее после анализа.
> Sonnet: применять эти резолюции в Slice 1–3, после — продолжать по
> исходному плану.

---

## OPEN-1 — Cost slice & currency для supplier-обязательства

**Решение:** использовать **per-line procurement_item поля**, не Lot.unit_purchase_price (тот в UZS, потерял операционную валюту). Это даёт обязательство в нативной валюте поставщика со снапшот-курсом.

В `apps/suppliers/consignment_obligations.py` заменить placeholder
`_resolve_sale_line_cost` на:

```python
def _resolve_sale_line_cost(sale_line, procurement) -> tuple[Decimal, str, Decimal]:
    """
    Cost slice для supplier-обязательства — в операционной валюте
    procurement_item-а (т.е. в валюте, в которой согласовалась цена с
    поставщиком). FX-rate тоже снапшот procurement_item-а.
    """
    item = sale_line.lot.procurement_item
    if item is None:
        raise ValueError(
            f'Sale line #{sale_line.pk}: lot has no procurement_item; '
            f'cannot resolve consignment cost.'
        )
    cost_slice = (
        Decimal(str(item.unit_purchase_price)) * Decimal(str(sale_line.quantity))
    ).quantize(Decimal('0.01'))
    currency = str(item.currency or 'UZS').upper()
    fx_rate = Decimal(str(item.fx_rate or 1))
    return cost_slice, currency, fx_rate
```

Обоснование: каждая консигнационная продажа получает собственный snapshot
(валюта + курс) из источника — `procurement_item`. Не агрегируем через
`terms.currency_of_obligation`, чтобы не делать ложное предположение «все
items procurement-а в одной валюте».

## OPEN-2 — Receive flow для CONSIGNED

**Решение:** при CONSIGNED procurement **не создавать SupplierPayable и не писать Inventory-журнал на этапе receive**. И то, и другое произойдёт только при продаже slice.

Два guard-а в `apps/partnerships/workspace.py`:

### Guard 1 — `_ensure_supplier_payable_after_receive` (line 2180)

```python
def _ensure_supplier_payable_after_receive(tenant_id, procurement, terms):
    if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
        return None  # CONSIGNED → payable создаётся per-sale, не at-receive
    if not terms or terms.type == ProcurementTerms.Type.PREPAID:
        return None
    # ... остальное без изменений ...
```

### Guard 2 — `_record_receive_journal` (line 2201)

```python
def _record_receive_journal(*, tenant_id, procurement, batch, amount, payable, received_at):
    if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
        return  # CONSIGNED inventory не на нашем балансе — никакого journal
    if amount <= 0:
        return
    # ... остальное без изменений ...
```

Эффект: receive CONSIGNED товара создаёт **только Lot-записи** (с `is_owned=False`, заложено Phase 1). Никакого payable, никакого journal. Stock на полке без owned-side-эффектов на финансы.

## OPEN-3 — Wrapper insertion + journal builder branch

### Часть A — вызов wrapper в `apps/sales/services.py:create_sale`

**Где:** внутри loop `for alloc in allocations`, **сразу после
`SaleLine.objects.create(...)` (~line 378)**, до stock decrement.

Перед циклом (≈line 336) инициализировать аккумулятор:
```python
consignment_legs: list[dict] = []
```

Внутри цикла, после создания SaleLine:
```python
sale_line = SaleLine.objects.create(...)  # существующее

# E09 Phase 2 — auto-obligation for CONSIGNED Lot sales
from apps.suppliers.consignment_obligations import (
    record_consignment_obligation_for_sale_line,
)
consignment_payable = record_consignment_obligation_for_sale_line(sale_line)
if consignment_payable is not None:
    # cogs_amount в UZS — landed_cost_per_unit это уже UZS
    leg_cogs_uzs = (
        Decimal(str(sale_line.lot.landed_cost_per_unit))
        * Decimal(str(sale_line.quantity))
    ).quantize(Decimal('0.01'))
    consignment_legs.append({
        'payable_id': consignment_payable.id,
        'amount_uzs': leg_cogs_uzs,
    })

# ... existing stock decrement + partner ledger ...
```

### Часть B — `record_sale_cogs_journal` accepts `consignment_legs`

Найти `record_sale_cogs_journal` (grep — скорее всего в
`apps/finance/services.py` или `apps/sales/services.py`).

Расширить сигнатуру:
```python
def record_sale_cogs_journal(
    *,
    tenant_id: int,
    sale_id: int,
    total_cogs: Decimal,
    date,
    consignment_legs: list[dict] | None = None,
) -> JournalEntry:
    """
    DR 5000 (COGS) for total_cogs.

    Credits split:
      - CR 1100 (Inventory) for owned portion = total_cogs - sum(legs.amount_uzs)
      - CR 2000 (A/P Suppliers) per consignment leg, with source_ref to payable
    """
    legs = consignment_legs or []
    total_consigned = sum(
        (Decimal(str(leg['amount_uzs'])) for leg in legs),
        Decimal('0'),
    )
    total_owned = Decimal(str(total_cogs)) - total_consigned

    journal_lines = []
    # Debit COGS — единая дебетовая строка на полную сумму
    journal_lines.append({'account_code': '5000', 'debit': total_cogs, 'credit': 0})

    if total_owned > 0:
        journal_lines.append({
            'account_code': '1100', 'debit': 0, 'credit': total_owned,
        })
    for leg in legs:
        journal_lines.append({
            'account_code': '2000',
            'debit': 0,
            'credit': Decimal(str(leg['amount_uzs'])),
            'source_ref_type': 'supplier_payable',
            'source_ref_id': leg['payable_id'],
        })

    # ... создать JournalEntry с этими lines (используя существующий paths)
```

При вызове функции из `create_sale` (line ~567), передать
`consignment_legs=consignment_legs` (аккумулятор из части A).

**Важно:** реальный API существующей функции — посмотреть в коде, адаптировать сигнатуру. Имена полей в `journal_lines` могут отличаться (`account` vs `account_code` и т.п.).

---

## OPEN-4 — Landed expenses на CONSIGNED procurement

**Это вылезло после анализа OPEN-2/OPEN-3, Sonnet правильно бы не нашёл.**

Проблема:
- `Lot.landed_cost_per_unit` = `unit_purchase_price` + аллоцированные landed expenses.
- При CONSIGNED receive мы подавили inventory-journal (OPEN-2). Значит landed expenses **не были признаны** на нашем балансе как часть inventory.
- При CONSIGNED sale: COGS дебетует `landed_cost × qty`, A/P кредитует `unit_purchase_price × qty (в UZS)`. Разница = landed-portion. Без 3-го кредитного counterparty journal не сойдётся.

**Решение:** запретить landed expenses на CONSIGNED procurement. Это бизнес-корректно — поставщик-дистрибьютор обычно сам доставляет, а если есть наши логистические расходы — они уже expense, не cost basis.

Добавить guard в `apps/partnerships/workspace_support.py` (или
`workspace.py`, где валидируются expenses) — при попытке добавить
`ProcurementExpense` или confirmed procurement с `goods_ownership=CONSIGNED`
+ хотя бы один expense → `ValueError`:

```python
if procurement.goods_ownership == Procurement.GoodsOwnership.CONSIGNED:
    if procurement.expenses.exists():
        raise ValueError(
            'CONSIGNED procurement не поддерживает landed expenses. '
            'Расходы на логистику/доставку для консигнации фиксируйте '
            'как отдельные операционные расходы, не как cost basis товара.'
        )
```

Расположение guard-а:
- В `_normalize_terms_values` или `validate_procurement_combination` — НЕТ (там нет инфо об expenses).
- В action handler для `UPDATE_EXPENSES` — да, если procurement уже CONSIGNED → reject.
- В `UPDATE_SOURCE` / `confirm_procurement` (если есть такая стадия) — да, если переключаемся на CONSIGNED при существующих expenses → reject.
- Sonnet решает конкретное место по архитектуре action-handlers.

С этим guard-ом `landed_cost_per_unit == unit_purchase_price` для всех CONSIGNED Lot-ов, и журнал из OPEN-3 сходится без 3-го counterparty.

Sanity-инвариант для Slice 3:
- `test_consigned_procurement_rejects_expenses` — попытка добавить expense к CONSIGNED procurement даёт ValueError.

---

## Обновлённый порядок выполнения

После прочтения этого supplement, Sonnet продолжает по исходному плану,
но с уточнениями:

### Slice 1 — Модель + миграция + модуль
- Добавить `SupplierPayable.Reason.CONSIGNMENT_SALE` (как было).
- Создать модуль `consignment_obligations.py` с реализованным
  `_resolve_sale_line_cost` (OPEN-1) и proper guard на supplier_id.
- Добавить **OPEN-2 guards** в `_ensure_supplier_payable_after_receive`
  и `_record_receive_journal` (две короткие правки в workspace.py).
- Добавить **OPEN-4 guard** в expense-handler (точное место — Sonnet
  выбирает по action-architecture).

### Slice 2 — Wire-up в sales + journal branch
- Вставить wrapper-вызов как в OPEN-3 Часть A.
- Модифицировать `record_sale_cogs_journal` как в OPEN-3 Часть B.

### Slice 3 — Invariant tests
Все ранее перечисленные + новый:
- `test_consigned_receive_creates_no_payable_and_no_inventory_journal`
- `test_consigned_procurement_rejects_expenses` (OPEN-4)
- `test_consigned_sale_journal_credits_ap_not_inventory_with_correct_amount`
  — checks the CR A/P amount = unit_purchase_price × qty × fx_rate (UZS), и что нет CR 1100 для CONSIGNED slice.

### Slice 4 — Wrap (как было)

---

## Что НЕ менять в этом supplement

- Архитектурное решение Variant A (sync, не outbox) остаётся.
- Per-SaleLine payable (не накопительный) остаётся.
- Existing OWNED flow не трогаем — все изменения только добавляют CONSIGNED branch / guard-ы.

Sonnet: после применения supplement в Slices 1–3 — продолжать обычным
циклом «один slice, один коммит». На любом ещё непрописанном branch
point — стоп, surface.
