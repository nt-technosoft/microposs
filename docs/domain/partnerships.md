# Partnerships — Мударабá и Мушарáка

## Исламская модель финансирования

MicroPOS поддерживает два вида партнёрства:

| Тип | Суть |
|---|---|
| **Мударабá (Mudaraba)** | Инвестор вкладывает капитал, оператор работает; прибыль считается через `mudaraba_ratio`; убытки идут по капиталу |
| **Мушарáка (Musharaka)** | Несколько сторон вкладывают капитал; убытки идут по капиталу, прибыль может быть договорной и проверяется формулой |

На практике контракт — **гибрид**: Мушарáка с настраиваемым `mudaraba_ratio`.

---

## Структура контракта

### InvestmentAgreement (родительское соглашение)

Покрывает несколько закупок под единым соглашением.

| Поле | Тип | Назначение |
|---|---|---|
| `mudaraba_ratio` | Decimal [0..1] | Доля прибыли, распределяемая пропорционально капиталу |
| `loss_rule` | BY_CAPITAL | Метод распределения убытков |
| `planned_budget` | Decimal | Планируемый объём |
| `currency` | str | Основная валюта соглашения |
| `status` | OPEN / ACTIVE / CLOSED / CANCELLED | |

### AgreementPartner
Участник соглашения.

| Поле | Тип | Назначение |
|---|---|---|
| `partner` | FK Partner | Партнёр |
| `role` | INVESTOR / OPERATOR | Роль |
| `planned_capital_share` | Decimal | Запланированная сумма капитала в валюте соглашения |
| `profit_share` | Decimal | Доля прибыли [0..1] |

**Инварианты:**
- Ровно 1 OPERATOR в каждом контракте
- `Σ profit_share` всех партнёров = 1.0
- `mudaraba_ratio` ∈ [0.0, 1.0]

---

## contract_snapshot — иммутабельный снимок

При приёмке товара (`receive_procurement_batch`) контракт записывается в `Lot.contract_snapshot`. После этого он никогда не меняется — даже если соглашение изменится.

```json
{
  "mudaraba_ratio": "0.7",
  "loss_rule": "BY_CAPITAL",
  "partners": [
    {
      "partner_id": 1,
      "role": "INVESTOR",
      "capital_share": "0.6",
      "profit_share": "0.42"
    },
    {
      "partner_id": 2,
      "role": "OPERATOR",
      "capital_share": "0.4",
      "profit_share": "0.58"
    }
  ]
}
```

---

## Формула распределения прибыли

**Входные данные:**
- `gross_line_profit = (unit_price − unit_landed_cost) × quantity`
- `contract_snapshot` из лота

**Расчёт на инвестора:**
```
profit_investor_i = gross_line_profit × capital_share_i × mudaraba_ratio
```

**Расчёт на оператора:**
```
profit_operator = gross_line_profit × (capital_share_op + (1 − mudaraba_ratio) × Σ capital_share_investors)
```

**Пример** (mudaraba_ratio = 0.7, инвестор 60%, оператор 40%):
- Валовая прибыль = 100 UZS
- Инвестор: `100 × 0.6 × 0.7 = 42 UZS`
- Оператор: `100 × (0.4 + 0.3 × 0.6) = 100 × 0.58 = 58 UZS`

Результат сохраняется в `SaleLine.profit_distribution_snapshot = {"1": "42.00", "2": "58.00"}`. Источник долей — `Lot.contract_snapshot`, который фиксируется на уровне конкретной партии приёмки; разные партии одного прихода могут иметь разные фактические доли.

---

## PartnerLedgerEntry — журнал партнёра

Append-only запись изменения позиции партнёра.

| Тип | Когда создаётся |
|---|---|
| `PROFIT_ACCRUED` | При каждой продаже (per partner, per lot-slice) |
| `PROFIT_REVERSED` | При возврате товара (RESTOCK или DISPOSE) |
| `LOSS_INCURRED` | При возврате с DISPOSE (товар уничтожен) |
| `CAPITAL_IN` | При внесении капитала в InvestmentAgreement |
| `CAPITAL_OUT` | При выводе капитала |
| `DIVIDEND_PAID` | При выплате дивидендов |

---

## Учёт капитала партнёра

Доступный баланс партнёра в соглашении вычисляется как:

```
available = CAPITAL_IN − CAPITAL_OUT − allocated_to_procurements + returned_from_procurements
```

`_agreement_partner_available(agreement)` возвращает `{partner_id: {currency: available_amount}}`.

При приёмке партнёрской закупки:
1. Проверяется что у партнёра достаточно баланса
2. Фиксируется `allocation_rows` в `ProcurementReceiveBatch`
3. Баланс партнёра уменьшается на вложенную сумму

---

## Жизненный цикл

```
InvestmentAgreement.status = OPEN
    └─ CAPITAL_IN: партнёры вносят капитал
           └─ PartnerLedgerEntry(CAPITAL_IN) per partner

Procurement (PARTNERSHIP type) создаётся
    └─ Привязывается к InvestmentAgreement

receive_procurement_batch()
    └─ contract_snapshot фиксируется в Lot
    └─ ProcurementReceiveBatchCapitalAllocation фиксирует капитал этой партии

Продажа → SaleLine (FIFO-слайс)
    └─ PartnerLedgerEntry(PROFIT_ACCRUED) per partner

Возврат RESTOCK:
    └─ PartnerLedgerEntry(PROFIT_REVERSED) per partner

Возврат DISPOSE:
    └─ PartnerLedgerEntry(PROFIT_REVERSED) + LOSS_INCURRED per partner

Закрытие Agreement:
    └─ Возможно только если нет активных Lot-ов
    └─ PartnerLedgerEntry(DIVIDEND_PAID) при выплате
```

---

## Ограничения при закрытии контракта

`InvestorContract` (и `InvestmentAgreement`) закрывается только если:
- Нет лотов со статусом `is_active=True`, связанных с данным контрактом
- Весь товар распродан или списан

---

## Profitability-отчёты для партнёрств

### `get_agreement_profitability_detail(tenant_id, agreement_id, report_currency?)`

Возвращает полный отчёт по соглашению:

```json
{
  "report_currency": "UZS",
  "agreement": { "id": 1, "status": "ACTIVE", "mudaraba_ratio": "0.7", ... },
  "partners": [
    {
      "partner_id": 1,
      "role": "INVESTOR",
      "capital_in": "10000000",
      "capital_out": "0",
      "profit_accrued": "420000",
      "profit_reversed": "0",
      "losses_incurred": "0",
      "dividends_paid": "0",
      "pending_payout": "420000"
    }
  ],
  "procurements": [...]
}
```

### `get_procurement_profitability_detail(tenant_id, procurement_id, report_currency?)`

Детальный отчёт по конкретной закупке: каждая позиция, проданные/оставшиеся количества, маржа, прогнозируемая прибыль.

---

## Связи с другими доменами

- **Inventory:** `Lot.contract_snapshot` читается при каждой продаже; Lot деактивируется → контракт можно закрыть
- **Sales:** `calculate_profit_distribution()` использует `contract_snapshot`; создаёт `PartnerLedgerEntry(PROFIT_ACCRUED)`
- **Finance:** журнальные проводки при вложении/выплате капитала; FX-ставки для мультивалютных вложений
- **Core:** `Partner`, `BusinessInvestorRelation.ACTIVE` контролирует доступ к закупкам
