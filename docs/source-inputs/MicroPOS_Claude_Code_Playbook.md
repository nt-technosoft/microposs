# MicroPOS — Claude Code Playbook

> Этот документ — инструкция для Claude Code. Читай его полностью перед началом любой задачи.
> BRD (бизнес-требования) — отдельный документ. Здесь только то, что влияет на код.

---

## 1. СТЕК И СТРУКТУРА ПРОЕКТА

```
Backend:   Python 3.12 / Django 5.x / Django REST Framework
Database:  PostgreSQL 16
Cache:     Redis
Queue:     Celery + Redis broker
Auth:      JWT (djangorestframework-simplejwt)
API docs:  drf-spectacular (OpenAPI)
Frontend:  Vue.js 3 (отдельный репозиторий, не трогаем здесь)
```

### Структура Django-приложений (по доменам)

```
apps/
  catalog/        # категории, товары, атрибуты, характеристики, вариации (SKU)
  inventory/      # склады, точки продаж, партии (Lot), приходы, перемещения, остатки
  sales/          # продажи, строки продаж, корзина, POS-сессии, причины скидок
  finance/        # journal entries, plan of accounts, агрегаты P&L / Cash Flow
  investors/      # инвесторы, договоры, расчёт долей, кабинет инвестора
  suppliers/      # поставщики, A/P, консигнация
  customers/      # клиенты, A/R, история покупок
  risk/           # Risk Event Log, списания, инвентаризация
  analytics/      # витрины данных, агрегированные отчёты (только чтение)
  core/           # базовые модели, миксины, утилиты, tenant-логика
```

### Правило границ доменов

Приложения **не импортируют модели друг друга напрямую** для бизнес-логики.
Взаимодействие только через:
- сервисный слой (`services.py` внутри каждого приложения)
- события через таблицу `core.OutboxEvent`

Исключение: ForeignKey-связи в моделях — допустимы между доменами.

---

## 2. ОБЯЗАТЕЛЬНЫЕ ГЛОБАЛЬНЫЕ ПРАВИЛА (нарушать нельзя)

### 2.1 Soft-delete везде
```python
# Все модели наследуют BaseModel из core
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])
```
**Физический `delete()` запрещён для финансовых объектов** (Sale, Receipt, JournalEntry, Lot).
Менеджер по умолчанию фильтрует `deleted_at__isnull=True`.

### 2.2 Immutable financial records
Модели `Sale`, `Receipt`, `JournalEntry` после перехода в статус `confirmed/completed`:
- **не редактируются** (переопределить `save()` с проверкой статуса)
- **не удаляются физически**
- корректировки только через обратные операции (reversal/return)

```python
IMMUTABLE_STATUSES = {'confirmed', 'completed', 'closed'}

def save(self, *args, **kwargs):
    if self.pk:
        original = self.__class__.objects.get(pk=self.pk)
        if original.status in IMMUTABLE_STATUSES:
            raise ImmutableRecordError(f"Cannot modify {self.__class__.__name__} in status {original.status}")
    super().save(*args, **kwargs)
```

### 2.3 Multi-tenant
Каждая модель с бизнес-данными имеет поле `tenant_id` (FK на `core.Business`).
Индекс обязателен. Все queryset фильтруются по `tenant_id` через middleware или миксин.

```python
class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant_id):
        return self.filter(tenant_id=tenant_id)
```

### 2.4 Outbox pattern
При любой значимой операции (продажа, приход, списание, перемещение) — писать событие в `OutboxEvent`:

```python
class OutboxEvent(BaseModel):
    event_type = models.CharField(max_length=100)  # 'sale.completed', 'receipt.confirmed' и т.д.
    payload = models.JSONField()
    processed_at = models.DateTimeField(null=True)
    tenant_id = models.IntegerField(db_index=True)
```

Celery-воркер забирает необработанные события и обновляет аналитические витрины.

### 2.5 Идемпотентность
Все POST-эндпоинты для финансовых операций принимают `client_request_id` (UUID генерируется на клиенте).
Повторный запрос с тем же `client_request_id` возвращает уже созданный объект, не дублирует.

---

## 3. КЛЮЧЕВЫЕ МОДЕЛИ — ТОЛЬКО НЕОЧЕВИДНЫЕ ПОЛЯ

> Структуру таблиц и связи строишь сам. Ниже — только поля с нетривиальной логикой.

### 3.1 Receipt (Приход)

```python
class ReceiptType(models.TextChoices):
    BUSINESS_OWNED     = 'BUSINESS_OWNED'      # свой товар
    MUDARABA           = 'MUDARABA'            # товар инвестора (100%)
    MUSHARAKA          = 'MUSHARAKA'           # совместный (бизнес + инвесторы)
    SUPPLIER_PURCHASE  = 'SUPPLIER_PURCHASE'   # закупка у поставщика
    CONSIGNMENT        = 'CONSIGNMENT'         # товар на реализацию

class ReceiptStatus(models.TextChoices):
    DRAFT     = 'draft'      # редактируется
    CONFIRMED = 'confirmed'  # IMMUTABLE, партии созданы

# Важные поля:
receipt_type  # ReceiptType — задаётся первым, определяет всё остальное
status        # ReceiptStatus — после confirmed нельзя менять ничего
```

**После перехода в `confirmed`:**
- Автоматически создаются `Lot` (партии) для каждой строки прихода
- Создаются `JournalEntry` по правилам CoA (см. раздел 5)
- Пишется `OutboxEvent('receipt.confirmed', ...)`

### 3.2 ReceiptParticipant (Участники прихода)

```python
# Только для MUDARABA и MUSHARAKA
class ParticipantType(models.TextChoices):
    BUSINESS  = 'business'
    INVESTOR  = 'investor'

# Важные поля:
participant_type   # ParticipantType
entity_id          # ID инвестора или бизнеса
capital_amount     # сколько вложил (Decimal)
capital_ratio      # считается автоматически: capital_amount / receipt.total_capital
profit_ratio       # договорная доля прибыли (Decimal, 0..1) — задаётся вручную
```

**Правило**: `sum(profit_ratio для всех участников) == 1.0` — валидация при сохранении.
`capital_ratio` — вычисляемое, не хранить жёстко (или хранить как snapshot на момент confirmed).

### 3.3 Lot (Партия)

```python
# Создаётся автоматически при Receipt.confirm()
# Одна строка прихода = одна партия

# Важные поля:
receipt          # FK на Receipt
receipt_line     # FK на ReceiptLine
product_variant  # FK на ProductVariant (SKU)
quantity_initial # сколько пришло
quantity_remaining  # текущий остаток (уменьшается при продажах)
cost_per_unit    # себестоимость единицы на момент прихода (snapshot, не меняется)
location         # FK на склад/точку продаж (меняется при перемещении)
is_active        # False когда quantity_remaining == 0
```

**Критично**: `cost_per_unit` — это snapshot себестоимости на момент прихода.
Он **не меняется** даже если потом поставщик изменил цену.

### 3.4 SaleLine (Строка продажи)

```python
# Важные поля:
lot              # FK на Lot — ОБЯЗАТЕЛЬНО, не просто product_variant
quantity         # количество
unit_price       # цена продажи (может отличаться от базовой)
base_price       # базовая цена товара на момент продажи (snapshot)
price_changed    # bool: unit_price != base_price
discount_reason  # FK на DiscountReason (nullable, только если price_changed=True)
```

### 3.5 PricingMode (Ценовой режим товара)

```python
class PricingMode(models.TextChoices):
    ASK_EACH_SALE    = 'ASK_EACH_SALE'    # всегда спрашивать
    DEFAULT_EDITABLE = 'DEFAULT_EDITABLE' # по умолчанию, можно менять
    FIXED_LOCKED     = 'FIXED_LOCKED'     # нельзя менять
```

Хранится на `ProductVariant`, не на `Product`. Шаблон берётся из `Category.default_pricing_mode` при создании варианта.

### 3.6 InvestorContract (Договор инвестора)

```python
class ContractType(models.TextChoices):
    MUDARABA  = 'MUDARABA'
    MUSHARAKA = 'MUSHARAKA'

class ContractStatus(models.TextChoices):
    ACTIVE    = 'active'
    CLOSED    = 'closed'   # IMMUTABLE после закрытия

# Важные поля:
contract_type     # ContractType
default_profit_ratio  # доля прибыли инвестора по этому договору (Decimal 0..1)
status            # ContractStatus
closed_at         # DateTime, заполняется при закрытии
final_settlement  # Decimal — итоговая сумма к выплате (заполняется при закрытии)
```

### 3.7 RiskEvent (Risk Event Log)

```python
class RiskEventType(models.TextChoices):
    WRITEOFF       = 'writeoff'       # списание
    DAMAGE         = 'damage'         # брак
    LOSS           = 'loss'           # пропажа
    RETURN         = 'return'         # возврат от покупателя
    STOCK_MISMATCH = 'stock_mismatch' # расхождение при инвентаризации
    ADJUSTMENT     = 'adjustment'     # ручная корректировка

# Важные поля:
event_type           # RiskEventType
lot                  # FK на Lot
quantity             # затронутое количество
affects_investor     # bool — автоматически True если lot.receipt.receipt_type in (MUDARABA, MUSHARAKA)
negligence           # bool, default=False — халатность управляющего (влияет на расчёты в будущем)
responsible_user     # FK на User
```

---

## 4. АЛГОРИТМЫ БИЗНЕС-ЛОГИКИ (псевдокод)

### 4.1 Продажа — выбор партии (FIFO)

```python
def get_lot_for_sale(product_variant_id, location_id, quantity):
    """
    По умолчанию — FIFO: самая ранняя активная партия.
    Если quantity > lot.quantity_remaining — берём из нескольких партий.
    """
    lots = Lot.objects.filter(
        product_variant_id=product_variant_id,
        location_id=location_id,
        is_active=True,
        quantity_remaining__gt=0
    ).order_by('receipt__date')  # FIFO

    result = []
    remaining = quantity
    for lot in lots:
        take = min(lot.quantity_remaining, remaining)
        result.append({'lot': lot, 'quantity': take})
        remaining -= take
        if remaining == 0:
            break

    if remaining > 0:
        raise InsufficientStockError(f"Not enough stock: {remaining} units short")

    return result  # список {lot, quantity}
```

### 4.2 Расчёт прибыли при продаже по партии

```python
def calculate_profit_distribution(lot, sale_line):
    """
    Считает кому сколько причитается с одной строки продажи.
    Возвращает список {entity_type, entity_id, amount}.
    """
    revenue = sale_line.unit_price * sale_line.quantity
    cogs = lot.cost_per_unit * sale_line.quantity
    gross_profit = revenue - cogs

    receipt = lot.receipt
    distributions = []

    if receipt.receipt_type == 'BUSINESS_OWNED':
        distributions.append({
            'entity_type': 'business',
            'entity_id': receipt.tenant_id,
            'amount': gross_profit
        })

    elif receipt.receipt_type == 'MUDARABA':
        investor_participant = receipt.participants.get(participant_type='investor')
        business_participant = receipt.participants.get(participant_type='business')

        investor_profit = gross_profit * investor_participant.profit_ratio
        business_profit = gross_profit * business_participant.profit_ratio

        distributions.append({'entity_type': 'investor', 'entity_id': investor_participant.entity_id, 'amount': investor_profit})
        distributions.append({'entity_type': 'business', 'entity_id': receipt.tenant_id, 'amount': business_profit})

    elif receipt.receipt_type == 'MUSHARAKA':
        for participant in receipt.participants.all():
            amount = gross_profit * participant.profit_ratio
            distributions.append({
                'entity_type': participant.participant_type,
                'entity_id': participant.entity_id,
                'amount': amount
            })

    elif receipt.receipt_type == 'CONSIGNMENT':
        # Бизнес берёт маржу/комиссию, остальное — обязательство поставщику
        rule = receipt.consignment_rule  # {type: 'margin'|'commission', value: Decimal}
        if rule['type'] == 'margin':
            business_amount = (sale_line.unit_price - lot.cost_per_unit) * sale_line.quantity
        else:  # commission %
            business_amount = revenue * rule['value']
        supplier_amount = revenue - business_amount

        distributions.append({'entity_type': 'business', 'entity_id': receipt.tenant_id, 'amount': business_amount})
        distributions.append({'entity_type': 'supplier', 'entity_id': receipt.supplier_id, 'amount': supplier_amount})

    elif receipt.receipt_type == 'SUPPLIER_PURCHASE':
        # Товар полностью бизнеса, прибыль — бизнесу
        distributions.append({'entity_type': 'business', 'entity_id': receipt.tenant_id, 'amount': gross_profit})

    return distributions
```

### 4.3 Расчёт убытка при списании / браке

```python
def calculate_loss_distribution(lot, quantity, negligence=False):
    """
    Убыток = себестоимость списанных единиц.
    Распределяется по capital_ratio (не profit_ratio).
    """
    loss = lot.cost_per_unit * quantity
    receipt = lot.receipt
    distributions = []

    if receipt.receipt_type == 'BUSINESS_OWNED':
        distributions.append({'entity_type': 'business', 'amount': loss})

    elif receipt.receipt_type == 'MUDARABA':
        if negligence:
            # Халатность управляющего — убыток на бизнесе
            # TODO: логика активируется после шариатской консультации
            distributions.append({'entity_type': 'business', 'amount': loss})
        else:
            # Стандарт: убыток несёт инвестор
            investor = receipt.participants.get(participant_type='investor')
            distributions.append({'entity_type': 'investor', 'entity_id': investor.entity_id, 'amount': loss})

    elif receipt.receipt_type == 'MUSHARAKA':
        # Убыток строго по capital_ratio
        for participant in receipt.participants.all():
            distributions.append({
                'entity_type': participant.participant_type,
                'entity_id': participant.entity_id,
                'amount': loss * participant.capital_ratio
            })

    return distributions
```

### 4.4 Возврат товара от покупателя

```python
def process_return(sale_line, return_quantity, condition):
    """
    condition: 'good' | 'damaged'
    Возврат всегда привязан к конкретной SaleLine → конкретному Lot.
    """
    # 1. Восстанавливаем остаток в партии
    lot = sale_line.lot
    lot.quantity_remaining += return_quantity
    lot.is_active = True
    lot.save()

    # 2. Сторнируем финансовые проводки пропорционально возврату
    create_reversal_journal_entries(sale_line, return_quantity)

    # 3. Если товар повреждён — создаём RiskEvent
    if condition == 'damaged':
        RiskEvent.objects.create(
            event_type='return',
            lot=lot,
            quantity=return_quantity,
            affects_investor=lot.receipt.receipt_type in ('MUDARABA', 'MUSHARAKA'),
        )
        # И сразу списываем — убыток по тем же правилам что и writeoff
        process_writeoff(lot, return_quantity, reason='damaged_return')
```

### 4.5 Закрытие договора инвестора

```python
def close_investor_contract(contract):
    """
    Нельзя закрыть если есть активные остатки по партиям договора.
    """
    # 1. Проверяем остатки
    active_lots = Lot.objects.filter(
        receipt__participants__entity_id=contract.investor_id,
        receipt__participants__participant_type='investor',
        is_active=True,
        quantity_remaining__gt=0
    )
    if active_lots.exists():
        raise ContractCloseError(
            "Cannot close contract: active lots remaining",
            lots=list(active_lots.values('id', 'product_variant__name', 'quantity_remaining'))
        )

    # 2. Считаем итоговый расчёт
    total_invested = contract.receipts_total_capital()
    total_profit = contract.investor_profit_total()
    total_settlement = total_invested + total_profit  # что должен бизнес

    # 3. Закрываем
    contract.status = 'closed'
    contract.closed_at = timezone.now()
    contract.final_settlement = total_settlement
    contract.save()

    # 4. Outbox
    OutboxEvent.objects.create(
        event_type='investor_contract.closed',
        payload={'contract_id': contract.id, 'settlement': str(total_settlement)},
        tenant_id=contract.tenant_id
    )
```

### 4.6 Продажа в долг — обязательная проверка клиента

```python
def validate_credit_sale(sale):
    """
    Вызывается перед подтверждением продажи.
    """
    if sale.payment_method == 'credit':
        if not sale.customer_id:
            raise ValidationError("Credit sale requires a customer")
        # Предупреждение (не блокировка в MVP) если есть долг
        customer = sale.customer
        if customer.outstanding_balance > 0:
            sale.customer_has_existing_debt = True  # флаг для UI
```

---

## 5. ЖУРНАЛ ПРОВОДОК — ПРАВИЛА

Каждая операция автоматически создаёт `JournalEntry`. Ниже — правила для каждого типа.

| Операция | Дебет | Кредит |
|----------|-------|--------|
| Продажа (наличные) | Cash | Revenue |
| Продажа (карта) | Bank | Revenue |
| Продажа (долг) | AccountsReceivable | Revenue |
| Списание COGS | COGS | Inventory |
| Погашение долга клиентом | Cash | AccountsReceivable |
| Приход BUSINESS_OWNED (оплачен) | Inventory | Cash |
| Приход SUPPLIER_PURCHASE (отсрочка) | Inventory | AccountsPayable |
| Оплата поставщику | AccountsPayable | Cash |
| Приход MUDARABA | Inventory | InvestorCapital |
| Прибыль инвестора MUDARABA | InvestorProfitExpense | InvestorPayable |
| Приход MUSHARAKA | Inventory | InvestorCapital + OwnerEquity (по долям) |
| Продажа CONSIGNMENT | Cash | Revenue (маржа) + SupplierPayable |
| Списание/брак | LossExpense | Inventory |
| Возврат товара (good) | Inventory | COGS (сторно) |

```python
def create_journal_entries(operation_type, operation_obj):
    """
    Вызывается из сервисного слоя после каждой финансовой операции.
    Использует таблицу выше для определения дебета/кредита.
    """
    # Реализацию строишь сам по таблице выше
    pass
```

---

## 6. API — КЛЮЧЕВЫЕ ЭНДПОИНТЫ

> Полный список строишь сам. Ниже — только эндпоинты с нетривиальной логикой.

### Продажа

```
POST /api/sales/
  body: {
    client_request_id: UUID,       # идемпотентность
    pos_session_id: ID,
    lines: [{
      product_variant_id: ID,
      quantity: int,
      unit_price: Decimal,
      lot_id: ID | null,           # null = FIFO автоматически
      discount_reason_id: ID | null
    }],
    payment_method: 'cash'|'card'|'credit',
    customer_id: ID | null         # обязателен если payment_method='credit'
  }
  logic:
    - validate_credit_sale()
    - для каждой строки: get_lot_for_sale() если lot_id=null
    - проверить остатки (предупреждение если уходит в минус, не блокировать в MVP)
    - создать Sale + SaleLines
    - уменьшить Lot.quantity_remaining
    - calculate_profit_distribution() для каждой строки
    - create_journal_entries()
    - OutboxEvent('sale.completed')
```

### Приход

```
POST /api/receipts/
  body: {
    client_request_id: UUID,
    receipt_type: ReceiptType,
    destination_id: ID,            # склад или точка продаж
    supplier_id: ID | null,        # для SUPPLIER_PURCHASE и CONSIGNMENT
    participants: [{               # только для MUDARABA и MUSHARAKA
      participant_type: 'business'|'investor',
      entity_id: ID,
      capital_amount: Decimal,
      profit_ratio: Decimal        # договорная доля прибыли
    }],
    payable_terms: {               # только для SUPPLIER_PURCHASE
      type: 'paid'|'credit',
      due_date: Date | null
    } | null,
    consignment_rule: {            # только для CONSIGNMENT
      type: 'margin'|'commission',
      value: Decimal
    } | null,
    lines: [{
      product_variant_id: ID,
      quantity: int,
      cost_per_unit: Decimal
    }]
  }

POST /api/receipts/{id}/confirm/
  logic:
    - проверить статус != confirmed
    - валидировать sum(profit_ratio) == 1.0 для MUDARABA/MUSHARAKA
    - создать Lot для каждой строки
    - create_journal_entries()
    - OutboxEvent('receipt.confirmed')
    - установить status = 'confirmed' (после этого immutable)
```

### Закрытие договора инвестора

```
POST /api/investors/contracts/{id}/close/
  logic:
    - close_investor_contract(contract)  # см. алгоритм 4.5
    - вернуть final_settlement
```

### Возврат товара

```
POST /api/sales/{id}/return/
  body: {
    lines: [{
      sale_line_id: ID,
      quantity: int,
      condition: 'good'|'damaged'
    }]
  }
  logic:
    - проверить что sale.status = 'completed'
    - для каждой строки: process_return(sale_line, quantity, condition)
```

---

## 7. КЛЮЧЕВЫЕ ИНДЕКСЫ (подсказка, не директива)

Следующие индексы критичны для производительности — убедись что они есть:

```python
# Lot
Index(['product_variant_id', 'location_id', 'is_active', 'quantity_remaining'])
Index(['receipt_id'])

# SaleLine
Index(['lot_id'])
Index(['sale_id'])

# Receipt
Index(['tenant_id', 'receipt_type', 'status'])

# OutboxEvent
Index(['processed_at', 'tenant_id'])  # для Celery воркера

# JournalEntry
Index(['tenant_id', 'created_at'])
```

---

## 8. CELERY ЗАДАЧИ

```python
# Запускаются по OutboxEvent или по расписанию

@shared_task
def aggregate_daily_pnl(tenant_id, date):
    """Агрегирует P&L за день в summary-таблицу. Не считать на лету."""

@shared_task
def aggregate_investor_summary(investor_id):
    """Пересчитывает витрину инвестора после каждой продажи из его партий."""

@shared_task
def process_outbox_events():
    """Забирает необработанные OutboxEvent и запускает нужные агрегации."""
```

---

## 9. ЖЁСТКИЕ ПРАВИЛА — ШПАРГАЛКА

```
✅ Товар появляется только через Receipt (кроме инвентаризации)
✅ Receipt.status = confirmed → immutable навсегда
✅ SaleLine всегда ссылается на Lot (не на ProductVariant напрямую)
✅ FIFO по умолчанию, ручной выбор Lot — опциональный параметр
✅ sum(profit_ratio всех участников) == 1.0 — валидация при confirm
✅ capital_ratio считается автоматически из capital_amount
✅ Продажа payment_method='credit' → customer_id обязателен
✅ Закрыть InvestorContract можно только если нет активных Lot
✅ Перемещение Lot меняет только location, не трогает участников и доли
✅ JournalEntry создаётся автоматически при каждой финансовой операции
✅ Все значимые операции пишут OutboxEvent
✅ Физический delete() запрещён для Sale, Receipt, JournalEntry, Lot

❌ Нельзя менять receipt_type после создания
❌ Нельзя редактировать confirmed Receipt
❌ Нельзя редактировать completed Sale (только return)
❌ Нельзя смешивать источники финансирования в одном Receipt
❌ Нельзя продавать в минус без явного флага (предупреждение в MVP)
❌ Нельзя закрыть InvestorContract с активными остатками
```

---

## 10. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (минимум)

```env
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=...
CELERY_BROKER_URL=redis://...
```

---

*Конец Playbook. Всё остальное — на усмотрение Claude Code.*
