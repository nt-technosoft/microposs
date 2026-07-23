# E09 Phase 1 — Refactor Execution Plan (для Sonnet)

> Этот документ — детальный план рефакторинга, рассчитанный на исполнение
> Сонетом в отдельном окне. Опус согласовал архитектурные решения, дальше —
> механика. **Sonnet не должен принимать архитектурные решения.** Если при
> исполнении вылезает branch point, не описанный здесь — стоп, surface
> founder'у, не угадывать.
>
> Параллельно вести epic checkboxes в [`E09-procurement-completeness.md`](./E09-procurement-completeness.md).
> Pre-flight: dev DB подтвердил 0 строк в `Procurement` и `ProcurementTerms`
> (2026-05-19), поэтому data migration тривиальная — `RemoveField` /
> `AddField` без backfill.

---

## Контракт изменений

### 1. Procurement gets `goods_ownership`

Файл: `backend/apps/partnerships/models.py`, класс `Procurement`.

```python
class GoodsOwnership(models.TextChoices):
    OWNED = 'OWNED', 'Свой товар'
    CONSIGNED = 'CONSIGNED', 'На реализации'

goods_ownership = models.CharField(
    max_length=12,
    choices=GoodsOwnership.choices,
    default=GoodsOwnership.OWNED,
)
```

### 2. ProcurementTerms.Type rename CONSIGNMENT → ON_SALE

Файл: `backend/apps/partnerships/models.py`, класс `ProcurementTerms.Type`.

- Заменить enum value `CONSIGNMENT = 'CONSIGNMENT'` на
  `ON_SALE = 'ON_SALE', 'Оплата после продажи'`.
- Grep по проекту: `CONSIGNMENT` (как строка / enum). Все вхождения за
  пределами `ProcurementTerms.Type` обновить на `ON_SALE`.
- `ConsignmentAgreement` (модель в suppliers) — **не трогать**, это
  separate концепция (соглашение с поставщиком, не enum-value).
- `ConsignmentReturn` (модель в partnerships) — **не трогать**, это
  отдельная сущность возврата.

### 3. Lot.is_owned

Файл: `backend/apps/inventory/models.py`, класс `Lot`.

```python
is_owned = models.BooleanField(default=True)
```

В `receive_workspace_batch` (`apps/partnerships/workspace.py`) при создании
каждого Lot устанавливать `is_owned=(procurement.goods_ownership ==
Procurement.GoodsOwnership.OWNED)`.

### 4. Validator `validate_procurement_combination`

Файл: `backend/apps/partnerships/policies.py`.

Добавить функцию:

```python
LEGAL_COMBINATIONS = frozenset({
    # (funding_source, payment_timing, goods_ownership)
    (OWN_FUNDS, PREPAID, OWNED),
    (OWN_FUNDS, PARTIAL, OWNED),
    (OWN_FUNDS, DEFERRED, OWNED),
    (OWN_FUNDS, INSTALLMENT, OWNED),
    (OWN_FUNDS, ON_SALE, CONSIGNED),
    (PARTNERSHIP, PREPAID, OWNED),
})

def validate_procurement_combination(funding_source, payment_timing, goods_ownership) -> None:
    combo = (funding_source, payment_timing, goods_ownership)
    if combo not in LEGAL_COMBINATIONS:
        raise ValueError(
            f'Illegal procurement combination: '
            f'funding={funding_source}, timing={payment_timing}, '
            f'ownership={goods_ownership}.'
        )
```

Вызвать validator в `_normalize_terms_values` (`workspace_support.py`) после
определения timing и при создании / обновлении terms.

### 5. Удалить MUSHARAKA legacy

Файл: `backend/apps/partnerships/policies.py`.

Удалить:
- Константу `MUSHARAKA = 'MUSHARAKA'`.
- Функцию `normalize_funding_source` (или сделать её noop — возвращает
  `funding_source` as-is).
- Ветку `if context.funding_source == MUSHARAKA` в `evaluate_procurement_policy`.

В тестах удалить любые проверки на MUSHARAKA → PARTNERSHIP normalization.

### 6. Rename context flag

Файл: `backend/apps/partnerships/policies.py`, `ProcurementPolicyContext`.

- `has_procurement_balance: bool` → `has_partnership_capital_activity: bool`.

Файл: `backend/apps/partnerships/workspace.py`, `build_workspace_payload`:

- Переименовать вычисление `has_procurement_balance=...` на
  `has_partnership_capital_activity=...`.
- Удалить устаревший комментарий о ProcurementBalance в логике.

Поменять имя в сообщении ошибки policy (line ~99 в policies.py):
`'OWN_FUNDS must not carry partnership capital activity.'` — уже подходящее,
не трогать.

В тестах:
- `apps/core/tests/test_e07_procurement_policy.py` — переименовать поле в
  кейсе `test_own_funds_rejects_procurement_balance`.

### 7. Тесты

#### Обновить
- `apps/core/tests/test_e07_procurement_policy.py` — кейсы по PARTNERSHIP и
  MUSHARAKA: удалить MUSHARAKA-кейсы, обновить имя поля в context.

#### Добавить
Новый файл `apps/core/tests/test_e09_procurement_combinations.py`:

- `test_legal_combinations_accepted` — каждую из 6 LEGAL_COMBINATIONS
  прогнать через `validate_procurement_combination`, ничего не должно
  падать.
- `test_partnership_with_non_prepaid_rejected` — PARTNERSHIP + DEFERRED →
  ValueError.
- `test_partnership_with_consigned_rejected` — PARTNERSHIP + ON_SALE +
  CONSIGNED → ValueError.
- `test_own_funds_consigned_with_prepaid_rejected` — OWN_FUNDS + PREPAID +
  CONSIGNED (нельзя предоплатить консигнацию) → ValueError.
- `test_own_funds_on_sale_with_owned_rejected` — OWN_FUNDS + ON_SALE +
  OWNED (нет триггера платежа) → ValueError.

#### Расширить
`apps/core/tests/test_e08_sharia_invariants.py` — добавить:

- `test_consigned_lot_has_is_owned_false` — Lot из CONSIGNED procurement
  имеет `is_owned=false`.
- `test_owned_lot_has_is_owned_true` — Lot из OWNED procurement имеет
  `is_owned=true`.

---

## Порядок выполнения (slices)

### Slice 1 — Модели + миграция (atomic)

1. Edit `partnerships/models.py`: добавить `GoodsOwnership` enum +
   `goods_ownership` field; переименовать `CONSIGNMENT` → `ON_SALE`.
2. Edit `inventory/models.py`: добавить `Lot.is_owned`.
3. `cd backend && DJANGO_SETTINGS_MODULE=config.settings.development
   .venv/bin/python manage.py makemigrations partnerships inventory`.
4. Проверить миграции — должны быть простые AddField + AlterField
   (RemoveField+AddField для enum rename — это нормально, в dev DB 0 строк).
5. Apply: `manage.py migrate partnerships && manage.py migrate inventory`.
6. Sanity: `manage.py shell -c "from apps.partnerships.models import
   Procurement, ProcurementTerms; print(Procurement.GoodsOwnership.choices,
   ProcurementTerms.Type.ON_SALE)"`.

**Commit**: `feat(E09-T-1.1,T-1.2,T-1.3): introduce goods_ownership axis + ON_SALE rename`

### Slice 2 — Policies refactor (atomic)

1. Edit `policies.py`: удалить MUSHARAKA, переименовать context flag,
   добавить `LEGAL_COMBINATIONS` + `validate_procurement_combination`.
2. Edit `workspace_support.py:_normalize_terms_values`: вызвать validator.
3. Edit `workspace.py:build_workspace_payload`: переименование context flag.
4. Run: `manage.py test apps/core/tests/test_e07_procurement_policy.py`
   и `apps/core/tests/test_e08_sharia_invariants.py` — должны зелёные.

**Commit**: `feat(E09-T-1.4,T-1.5,T-1.6): legal-combination validator + drop MUSHARAKA legacy`

### Slice 3 — Тесты

1. Update `test_e07_procurement_policy.py` (MUSHARAKA удалить, переименовать
   field).
2. Create `test_e09_procurement_combinations.py` (5 кейсов сверху).
3. Extend `test_e08_sharia_invariants.py` (2 кейса сверху).
4. Full sweep:
   ```
   cd backend && DJANGO_SETTINGS_MODULE=config.settings.development \
     .venv/bin/python -m pytest apps/core/tests/ -q
   ```
   Должны зелёные плюс минимум pre-existing failures (`test_partnerships_api`,
   `test_outbox_pipeline`, `test_fx_rates`, `test_role_matrix`,
   `test_investor_bridge_api`, `test_bootstrap_deploy_baseline`,
   `test_audit_batch_two::test_investor_dashboard_exposes_capital_state_at_cost_basis` —
   эти были красные ДО Phase 1 E09).

**Commit**: `test(E09-T-1.7): invariants for procurement combinations and ownership`

### Slice 4 — Wrap

1. Mark T-1.1..T-1.7 как `[x]` в `docs/roadmap/E09-procurement-completeness.md`.
2. Обновить статус E09 в `docs/ROADMAP.md` на `IN_PROGRESS`, прогресс ~30%.
3. Добавить решённый вопрос в epic: «миграция CONSIGNMENT — тривиальна,
   0 строк в dev DB».
4. Если возникли open questions для Phase 2 — записать в epic.

**Commit**: `docs(E09-phase1): mark refactor wave complete`

---

## Что НЕ делать в этом плане

- Не трогать UI. `ProcurementWorkspace.vue` и agreement-related screens —
  под прямым контролем founder'а.
- Не реализовывать ON_SALE-trigger механику (это Phase 2).
- Не трогать `ConsignmentAgreement` / `ConsignmentReturn` модели — они
  остаются.
- Не добавлять returnability поля (это Phase 3).
- Не делать «попутно» какую-то ещё чистку — каждый коммит атомарен по
  своему slice.

## Если что-то пошло не так

- **Миграция не делает RemoveField+AddField, а делает что-то странное** →
  Не применять. Сделать `--dry-run` и показать вывод. Возможно нужно
  написать SeparateDatabaseAndState вручную.
- **`validate_procurement_combination` блокирует существующий тест** →
  Скорее всего тест использует невалидную комбинацию (legacy). Surface
  founder'у — либо тест устарел, либо валидатор слишком строгий.
- **`Lot.is_owned` default=True падает на existing migration** → В dev DB
  0 Lot строк (по pre-flight), но если вдруг есть — добавить миграцию,
  которая backfill-ит is_owned=True для существующих.
- **MUSHARAKA удалить не получается потому что где-то используется** →
  Grep `MUSHARAKA` по всему apps/. Удалить вхождения. Если где-то в
  миграции — оставить там как историческое (миграции не редактируем).

## Sanity-чек после всего

```bash
cd /Users/aziztohirov/Desktop/Projects/microposs/backend
DJANGO_SETTINGS_MODULE=config.settings.development \
  .venv/bin/python manage.py validate_payable_consistency
# должно: OK
DJANGO_SETTINGS_MODULE=config.settings.development \
  .venv/bin/python -m pytest \
  apps/core/tests/test_e07_procurement_policy.py \
  apps/core/tests/test_e08_sharia_invariants.py \
  apps/core/tests/test_e09_procurement_combinations.py \
  apps/core/tests/test_e07_supplier_payables.py \
  apps/core/tests/test_e07_workspace_contract.py \
  apps/core/tests/test_partner_ledger.py \
  apps/core/tests/test_sale_multi_payment.py \
  -q
# должно: all green
```

Если оба зелёные — Slice 4 (документация), commit, готово.
