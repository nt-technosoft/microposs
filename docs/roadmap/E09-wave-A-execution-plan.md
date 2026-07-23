# E09 Wave A — Backend Preconditions for UI Rebuild (для Sonnet)

> Это execution plan для backend-работы, которая должна быть выполнена
> ДО полной UI пересборки procurement workspace. Каждый slice — атомарная
> правка backend + миграция + тесты + один коммит.
>
> **Опус согласовал все архитектурные решения.** Sonnet исполняет, не
> принимает архитектурные решения. Любой branch point вне этого плана →
> стоп, surface founder'у.
>
> Параллельно вести checkboxes в [`E09-procurement-completeness.md`](./E09-procurement-completeness.md).

---

## Pre-flight (один раз до Slice 1)

Прочитать перед началом:
- `docs/roadmap/E09-procurement-completeness.md` — эпик E09, MVP scope
- `docs/roadmap/E09-procurement-ui-design.md` — UI design anchor с conditional matrix
- `docs/vision.md` — продуктовый контекст

Sanity: убедиться что текущая ветка `vacuum-rework-claude` и последний коммит существует:
```bash
cd /Users/aziztohirov/Desktop/Projects/microposs
git log --oneline -5
```

---

## Slice 1 — AT_RECEIPT payment_timing

**Цель**: добавить новое значение `AT_RECEIPT` в payment_timing enum,
обновить validator до 8 легальных комбинаций, реализовать combined
"receive + pay" action.

### Контракт

**Backend модель:**
- `ProcurementTerms.Type` enum: добавить `AT_RECEIPT = 'AT_RECEIPT', 'Оплата по получению'`

**Validator** (`apps/partnerships/policies.py`):
- Расширить `LEGAL_COMBINATIONS` до 8 точек:
  ```python
  LEGAL_COMBINATIONS = frozenset({
      (OWN_FUNDS, PREPAID, OWNED),
      (OWN_FUNDS, 'AT_RECEIPT', OWNED),  # NEW
      (OWN_FUNDS, PARTIAL, OWNED),
      (OWN_FUNDS, DEFERRED, OWNED),
      (OWN_FUNDS, INSTALLMENT, OWNED),
      (OWN_FUNDS, ON_SALE, CONSIGNED),
      (PARTNERSHIP, PREPAID, OWNED),
      (PARTNERSHIP, 'AT_RECEIPT', OWNED),  # NEW
  })
  ```

**Combined action**:
- В `apps/partnerships/workspace.py` функция `receive_workspace_batch`:
  - Если `procurement.terms.type == AT_RECEIPT` и payload содержит
    `payment_payload` (cash_account_id, amount, currency, fx_rate) — после создания
    ReceiveBatch создать `finance.Payment` в той же транзакции через
    `record_generic_cash_payment`.
  - Если `procurement.terms.type == AT_RECEIPT` и нет payment_payload — ValueError.
  - Snapshot и журналы создаются как обычно (через существующие функции).

**Гарды на стандартные пути**:
- В `pay_workspace_costs` и `pay_workspace_supplier_payable` — если
  `procurement.terms.type == AT_RECEIPT` — ValueError «AT_RECEIPT procurement
  pays only at receive moment, use receive action».

### Тесты (`apps/core/tests/test_e09_at_receipt.py` — новый файл)

- `test_at_receipt_combined_action_creates_payment_and_batch` — receive_workspace_batch
  с AT_RECEIPT + payment_payload создаёт и Payment и ReceiveBatch
- `test_at_receipt_receive_without_payment_payload_rejected` — без payment_payload → ValueError
- `test_at_receipt_separate_pay_action_rejected` — pay_workspace_costs на
  AT_RECEIPT procurement → ValueError
- `test_at_receipt_partnership_uses_capital_pool` — для PARTNERSHIP AT_RECEIPT
  payment source = CAPITAL_POOL (через AgreementAllocation)
- `test_at_receipt_legal_combinations` — validate_procurement_combination принимает
  оба AT_RECEIPT варианта

### Open question Sonnet surfaces (НЕ решает сам)

- **OPEN-S1.1**: для PARTNERSHIP AT_RECEIPT — должен ли payment_payload содержать
  явные allocation amounts per partner, или derive из planned shares? Опус ответит.

### Migration

```bash
cd backend && DJANGO_SETTINGS_MODULE=config.settings.development \
  .venv/bin/python manage.py makemigrations partnerships
# Migration: AlterField для ProcurementTerms.type choices
```

### Commit

`feat(E09-wave-A-1): AT_RECEIPT timing — combined receive+pay action`

---

## Slice 2 — Per-item ownership refactor

**Цель**: перенести `goods_ownership` с уровня Procurement на уровень
ProcurementItem, чтобы поддержать смешанные приходы (80% OWNED + 20%
CONSIGNED от одного поставщика).

### Контракт

**Модель**:
- `ProcurementItem`: добавить `goods_ownership` (CharField с choices из
  `Procurement.GoodsOwnership.choices`, default `OWNED`)
- `Procurement.goods_ownership` — превратить в @property:
  ```python
  @property
  def goods_ownership(self) -> str:
      ownerships = set(self.items.values_list('goods_ownership', flat=True).distinct())
      if not ownerships:
          return self.GoodsOwnership.OWNED  # default for empty draft
      if ownerships == {'OWNED'}:
          return 'OWNED'
      if ownerships == {'CONSIGNED'}:
          return 'CONSIGNED'
      return 'MIXED'  # NEW value
  ```
- Добавить `Procurement.GoodsOwnership.MIXED = 'MIXED', 'Смешанный'`
  — но это не выбор пользователя, а derived состояние.

**Migration**:
- Add field `ProcurementItem.goods_ownership` (default 'OWNED')
- Data migration: backfill каждого ProcurementItem из родительского
  `Procurement.goods_ownership` (BEFORE removing the field)
- Remove `Procurement.goods_ownership` field (replaced by @property)

**Validator** (`apps/partnerships/policies.py`):
- При проверке комбинации использовать derived `procurement.goods_ownership`
- Добавить правило: если `MIXED` — обязательно `funding_source=OWN_FUNDS`
  (PARTNERSHIP не разрешает смешанный)
- Добавить правило: если `MIXED` — `payment_timing` не может быть `ON_SALE`
  (это бы означало no payment вообще, что бессмысленно для OWNED части)
- Легальные MIXED-комбинации:
  - OWN_FUNDS × {PREPAID, AT_RECEIPT, PARTIAL, DEFERRED, INSTALLMENT} × MIXED

**Receive логика**:
- В `receive_workspace_batch` функция создания Lot:
  ```python
  Lot.objects.create(
      ...,
      is_owned=(item.goods_ownership == 'OWNED'),
      ...
  )
  ```
  то есть per-item, не per-procurement

**ConsignmentReturn**:
- Уже per-line, изменений не требуется

### Тесты

- `test_per_item_ownership_lot_creation` — создан Procurement с 5 OWNED + 5
  CONSIGNED items, после receive_workspace_batch создаются 5 Lot с
  is_owned=True и 5 с is_owned=False
- `test_mixed_procurement_legal` — `(OWN_FUNDS, PREPAID, MIXED)` принимается
  validator-ом
- `test_mixed_partnership_rejected` — `(PARTNERSHIP, PREPAID, MIXED)` → ValueError
- `test_mixed_on_sale_rejected` — `(OWN_FUNDS, ON_SALE, MIXED)` → ValueError
- `test_procurement_ownership_property_owned_only` — все items OWNED →
  procurement.goods_ownership == 'OWNED'
- `test_procurement_ownership_property_mixed` — items mixed →
  procurement.goods_ownership == 'MIXED'

### Open question Sonnet surfaces

- **OPEN-S2.1**: как должна работать `CONSIGNMENT_SALE` payable для MIXED
  procurement? Только для CONSIGNED items, OWNED не трогаются. Подтвердить
  что текущий `record_consignment_obligation_for_sale_line` уже это делает
  (он чекает `lot.is_owned`).

### Migration ordering

Важно: Migration должна быть в правильном порядке:
1. AddField `goods_ownership` to ProcurementItem (default OWNED)
2. Data migration backfill
3. Validator update
4. RemoveField `Procurement.goods_ownership` (последним, после backfill)

### Commit

`feat(E09-wave-A-2): per-item goods_ownership refactor`

---

## Slice 3 — Discrepancy fields on ReceiveBatchLine

**Цель**: поддержать частичный приём с reason codes.

### Контракт

**Модель** (`apps/partnerships/models.py`, `ProcurementReceiveBatchLine`):
- Переименовать существующий `quantity` (если есть) в `quantity_planned`
  ИЛИ добавить `quantity_planned` отдельно (зависит от текущего состояния
  — проверить и решить через grep)
- Добавить `quantity_received` (DecimalField, default 0)
- Добавить `discrepancy_reason` (CharField choices):
  ```python
  class DiscrepancyReason(models.TextChoices):
      NONE = 'NONE', 'Без расхождения'
      MISSING_EXPECTED_LATER = 'MISSING_EXPECTED_LATER', 'Не привезли, ждём'
      DAMAGED = 'DAMAGED', 'Повреждён'
      QUALITY_REJECT = 'QUALITY_REJECT', 'Отказ по качеству'
      ACCEPT_AS_SHORTFALL = 'ACCEPT_AS_SHORTFALL', 'Закрыть с недостачей'
  ```

**Receive action**:
- Payload accepts per-line `qty_received` (default = planned) и `discrepancy_reason`
  (default = NONE если qty_received == qty_planned, иначе MISSING_EXPECTED_LATER)
- Если qty_received < qty_planned и reason != NONE — допустимо
- Если qty_received < qty_planned и reason == NONE — ValueError (требуется указать reason)
- Если qty_received > qty_planned — ValueError всегда

**Эффект на состояние**:
- ACCEPT_AS_SHORTFALL: уменьшает planned qty до received qty (item considered fully received)
- MISSING_EXPECTED_LATER: оставляет остаток как expected, procurement остаётся PARTIALLY_RECEIVED
- DAMAGED / QUALITY_REJECT: то же что MISSING_EXPECTED_LATER + flag для отчётности

### Тесты

- `test_discrepancy_accept_shortfall_closes_item` — qty_planned=100, received=98,
  reason=ACCEPT_AS_SHORTFALL → item.qty_planned уменьшен до 98
- `test_discrepancy_missing_later_keeps_open` — qty_planned=100, received=98,
  reason=MISSING_EXPECTED_LATER → procurement.status=PARTIALLY_RECEIVED, ждёт ещё 2
- `test_discrepancy_without_reason_rejected` — qty_received < qty_planned без reason
  → ValueError
- `test_discrepancy_over_received_rejected` — qty_received > qty_planned → ValueError

### Commit

`feat(E09-wave-A-3): discrepancy reason codes on receive batch lines`

---

## Slice 4 — Generic Attachment model

**Цель**: универсальный механизм для прикрепления файлов к любым моделям.

### Контракт

**Новое app `apps/attachments/`** (или внутри `apps/core/`):
```python
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Attachment(TenantModel):
    class Kind(models.TextChoices):
        INVOICE = 'INVOICE', 'Накладная'
        RECEIPT_PHOTO = 'RECEIPT_PHOTO', 'Фото приёма'
        DOCUMENT = 'DOCUMENT', 'Документ'
        OTHER = 'OTHER', 'Другое'

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    attachable = GenericForeignKey('content_type', 'object_id')

    file = models.FileField(upload_to='attachments/%Y/%m/')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    caption = models.CharField(max_length=255, blank=True, default='')
    uploaded_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'content_type', 'object_id']),
            models.Index(fields=['tenant', 'kind']),
        ]
```

**Service** (`apps/attachments/services.py`):
- `attach_file(*, tenant_id, attachable, file, kind, caption='', uploaded_by_id=None) -> Attachment`
- `list_attachments(*, attachable) -> QuerySet[Attachment]`
- `detach(attachment_id, tenant_id, deleted_by_id) -> None` (soft delete)

**Endpoint** (`apps/attachments/views.py`):
- POST `/api/v1/attachments/` — multipart upload с attachable_type, attachable_id, kind, caption
- GET `/api/v1/attachments/?attachable_type=X&attachable_id=Y` — список
- DELETE `/api/v1/attachments/<id>/` — soft delete

В MVP attach-points: `Procurement`, `ProcurementReceiveBatch`. Дальше расширяется без новых таблиц.

### Тесты

- `test_attach_file_to_procurement` — attach + retrieve работает
- `test_attach_file_to_receive_batch` — то же
- `test_list_attachments_filtered_by_attachable` — query возвращает только релевантные
- `test_detach_soft_delete` — file остаётся на диске, но не виден в queryset

### Open question Sonnet surfaces

- **OPEN-S4.1**: file storage backend — local filesystem (Django default) или S3?
  В dev — local. Опус подтверждает что в MVP local OK.

### Commit

`feat(E09-wave-A-4): generic attachment model + service + endpoint`

---

## Slice 5 — Cancel procurement rule

**Цель**: явный action `CANCEL_PROCUREMENT` с правилами, когда отмена разрешена.

### Контракт

**Action** (`apps/partnerships/workspace.py`):
- Новая функция `cancel_workspace_procurement(tenant_id, procurement, payload)`:
  - Если `procurement.status == DRAFT` → hard delete с tombstone-логом (или soft delete с `status=CANCELLED`)
  - Если `procurement.status == OPEN` → допустимо только если **нет finance.Payment и нет ReceiveBatch**. Если есть — ValueError.
  - Если `procurement.status in (PARTIALLY_RECEIVED, RECEIVED, CLOSED)` → запрещено всегда
- При cancel: `Procurement.status = CANCELLED`, items list заморожен, terms.lifecycle_state замораживается

**ACTION_MAP entry**: `'CANCEL': 'CANCEL_PROCUREMENT'` в `ACTION_MAP`
для workspace dispatch.

### Тесты

- `test_cancel_draft_procurement_succeeds` — DRAFT cancel OK
- `test_cancel_open_without_payments_succeeds` — OPEN без Payment/Receive cancel OK
- `test_cancel_open_with_payment_rejected` — OPEN + Payment → ValueError
- `test_cancel_open_with_receive_rejected` — OPEN + ReceiveBatch → ValueError
- `test_cancel_received_procurement_rejected` — RECEIVED → ValueError

### Commit

`feat(E09-wave-A-5): cancel procurement action + rule`

---

## Slice 6 — Reverse receive batch action

**Цель**: явная отмена ошибочной приёмки через создание обратного документа.

### Контракт

**Action**:
- Новая функция `reverse_workspace_receive_batch(tenant_id, batch_id, reason)`:
  - Создаёт новый `ProcurementReceiveBatch` с `is_reversal=True` (новое поле)
    и `reversed_batch=<original_batch>` (новая FK)
  - Для каждого Lot из original batch: создаёт реверсивный stock movement
    (отрицательный) + помечает Lot как `reversed=True`
  - Inverts snapshot: новый snapshot в reversed_batch отрицательный
  - Обновляет procurement.status: если был RECEIVED → PARTIALLY_RECEIVED, если
    PARTIALLY_RECEIVED → проверить остались ли другие приёмки
  - Записывает в outbox `receive_batch.reversed`

**Модель**:
- `ProcurementReceiveBatch.is_reversal` (BooleanField, default False)
- `ProcurementReceiveBatch.reversed_batch` (FK self, null=True)
- `Lot.reversed` (BooleanField, default False) — для FIFO фильтрации
- `Lot.received_at` filter в FIFO: добавить `reversed=False`

### Тесты

- `test_reverse_receive_creates_inverse_batch` — original batch + reverse =
  net zero effect on stock
- `test_reverse_receive_inverts_snapshot` — capital snapshot обратный
- `test_reverse_receive_changes_procurement_status` — RECEIVED → PARTIALLY_RECEIVED
- `test_lot_reversed_excluded_from_fifo` — reversed Lot не выбирается в sale
- `test_reverse_already_sold_lot_rejected` — если Lot уже частично продан → ValueError

### Open question Sonnet surfaces

- **OPEN-S6.1**: что делать если на reverse-able Lot уже есть продажи?
  Strict: reject (как написано выше). Lenient: разрешить, продажи остаются
  валидными, но Lot.stock уходит в минус. **Опус решает.**

### Commit

`feat(E09-wave-A-6): reverse receive batch action + inverse documents`

---

## Slice 7 — Amendment model for items/expenses

**Цель**: правки items/expenses после confirm — через явный amendment с записью before/after.

### Контракт

**Новая модель** (`apps/partnerships/models.py`):
```python
class ProcurementAmendment(TenantModel):
    class TargetType(models.TextChoices):
        ITEMS = 'ITEMS', 'Товары'
        EXPENSES = 'EXPENSES', 'Расходы'
        SUPPLIER = 'SUPPLIER', 'Поставщик'

    procurement = models.ForeignKey(Procurement, on_delete=models.PROTECT,
                                     related_name='amendments_items_expenses')
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    amended_at = models.DateTimeField()
    changed_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True)
    before = models.JSONField()  # snapshot до правки
    after = models.JSONField()   # snapshot после правки
    reason = models.TextField(blank=True, default='')

    class Meta:
        indexes = [
            models.Index(fields=['procurement', 'amended_at']),
        ]

    def delete(self, *args, **kwargs):
        raise ValueError('ProcurementAmendment is append-only.')
```

**Service**:
- `apply_items_amendment(tenant_id, procurement, new_items_payload, reason, user_id)`:
  - Только если `procurement.status` in (OPEN, PARTIALLY_RECEIVED)
  - Snapshot существующих items → before
  - Применить изменения (add/remove/update qty/price)
  - Snapshot новых items → after
  - Создать ProcurementAmendment запись
  - Запретить: удалить item, который уже в ReceiveBatch (его qty_received > 0)

- `apply_expenses_amendment` аналогично

**Action wire-up**:
- `AMEND_ITEMS` action в workspace dispatch
- `AMEND_EXPENSES` action в workspace dispatch

### Тесты

- `test_amend_items_records_before_after` — изменение qty → ProcurementAmendment
  создан с правильными before/after JSON
- `test_amend_items_in_draft_rejected` — пытаемся amend в DRAFT → ValueError
  (в DRAFT просто редактируется)
- `test_amend_received_item_rejected` — попытка удалить item с qty_received > 0
  → ValueError
- `test_amend_after_close_rejected` — CLOSED procurement → ValueError
- `test_amendment_delete_forbidden` — попытка удалить ProcurementAmendment → ValueError

### Open question Sonnet surfaces

- **OPEN-S7.1**: как amendment взаимодействует с уже сделанными Payment-ами для
  PREPAID procurement? Если уменьшили qty → переплата. Если увеличили → недоплата.
  Простой вариант: amendment не трогает payments, только меняет items. Recompute
  obligation на лету. Юзер видит "переплата 500 UZS" или "не хватает 1000 UZS"
  как индикатор. **Опус подтверждает.**

### Commit

`feat(E09-wave-A-7): amendment model for items/expenses after confirm`

---

## Slice 8 — Multi-payment + receive constraint

**Цель**: разрешить накопительные payments и контролировать receive по покрытию.

### Контракт

**Существующее**:
- finance.Payment уже поддерживает multiple payments per procurement (через
  target_type=PROCUREMENT_COST, target_id=procurement.id)
- ProcurementTerms.paid_amount уже derived (sum payments).
- Items list уже блокируется при confirm (`terms.lifecycle_state=ACTIVE`).

**Что добавить**:

**В `receive_workspace_batch`**:
- Для `procurement.terms.type == PREPAID`:
  - Считать `cost_of_received_items = Σ (item.unit_purchase_price * item.qty_received_so_far)`
    включая текущий batch
  - Считать `total_paid_uzs = Σ (Payment.amount * Payment.fx_rate) for target=PROCUREMENT_COST`
  - Convert `cost_of_received_items` to UZS via terms.fx_rate_at_obligation
  - Если `cost_of_received_items_uzs > total_paid_uzs` → ValueError
    «Cannot receive items exceeding payment coverage in PREPAID procurement»
- Для других timing (`PARTIAL`, `DEFERRED`, `INSTALLMENT`, `AT_RECEIPT`, `ON_SALE`) —
  без этой проверки (AT_RECEIPT создаёт payment атомарно, остальные allow
  receive-before-pay).

### Тесты

- `test_prepaid_partial_receive_with_partial_payment_ok` — заплатил 50% + receive 50% items → OK
- `test_prepaid_full_receive_with_partial_payment_rejected` — заплатил 50% + receive 100% → ValueError
- `test_prepaid_full_receive_after_full_payment_ok` — заплатил 100% + receive 100% → OK
- `test_deferred_receive_without_payment_ok` — DEFERRED + receive без payment → OK (там потом платится)

### Commit

`feat(E09-wave-A-8): multi-payment + receive coverage constraint for PREPAID`

---

## После всех slice — финальный wrap

### Документация

1. В `docs/roadmap/E09-procurement-completeness.md`:
   - Mark task list соответствующие slice как `[x]`
   - Прогресс E09 → ~85%
   - Раздел «Решённые вопросы» — добавить запись «Wave A backend завершено YYYY-MM-DD»

2. В `docs/ROADMAP.md`:
   - E09 прогресс → ~85%

### Final sanity

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
  apps/core/tests/test_e09_at_receipt.py \
  apps/core/tests/test_e07_supplier_payables.py \
  apps/core/tests/test_e07_workspace_contract.py \
  apps/core/tests/test_sale_multi_payment.py \
  apps/core/tests/test_partner_ledger.py \
  -q
# all green (минус pre-existing failures из Phase 1)
```

### Commit (final docs)

`docs(E09-wave-A): mark backend preconditions complete; mark task checkboxes`

---

## Что НЕ делать в этом плане

- Не трогать frontend (Vue файлы). UI rebuild — Wave B, под контролем founder'а.
- Не реализовывать E09 Phase 3 (returnability) — это после MVP.
- Не реализовывать Cash-flow inline, templates, multi-editor — это после MVP.
- Не делать «попутно» какую-то ещё чистку — slices атомарны.

## Что делать когда зависит

- Slice 1 (AT_RECEIPT) — независимый, можно делать первым.
- Slice 2 (per-item ownership) — независимый, можно делать первым.
- Slice 3, 4, 5 — независимые, после Slice 1 и 2.
- Slice 6 (reverse receive) — независимый, после Slice 2 (нужен per-item is_owned).
- Slice 7 (amendment) — после Slice 2 (amendment работает с items).
- Slice 8 (multi-payment receive constraint) — последним, потому что зависит
  от Slice 1 (AT_RECEIPT atomicity guarantee).

Можно идти строго по порядку 1 → 8 или параллелить 3/4/5 после 2. Для
безопасности рекомендую строгий порядок.

## Если что-то пошло не так

- **Любая Open question (S1.1, S2.1, S4.1, S6.1, S7.1)** → STOP, surface
  founder'у. Не угадывать.
- **Pre-existing тест начинает падать** → проверить не связано ли с твоим
  изменением. Если pre-existing — указать в commit message. Если ты сломал
  — fix или rollback.
- **Migration ломается** — surface, не применять. Может быть требуется
  ручное вмешательство.
- **`validate_procurement_combination` блокирует существующий тест** —
  скорее всего тест использует невалидную (legacy) комбинацию. Surface,
  Опус решит — обновить тест или ослабить validator.

## Sanity-чек после каждого slice

После каждого slice:
1. Migration применилась
2. Новые тесты зелёные
3. `validate_payable_consistency` OK
4. `pytest apps/core/tests/` — нет НОВЫХ regression-ов (старые pre-existing failures допустимы)
