# Excel financial model analysis

Source workbook: `/Users/aziztohirov/Downloads/MUZORABA USTOZ VA BEKZOD AKA 2 (1).xlsx`

Purpose of this note: capture how the workbook behaves as a financial/operational model, not only the visible numbers. This is a working analysis for product decisions and implementation mapping.

## Executive summary

The workbook is a compact partnership-trading accounting model. It tracks:

- partner capital contributions;
- purchased goods;
- supplier/cost payments;
- sales and sales receipts;
- stock by warehouse/store;
- cash balances by account/currency;
- customer receivables and supplier payables/prepayments;
- final P&L, balance-style view, and profit/capital distribution.

The important discovery is that the file has two different capital-share concepts:

- raw contribution share: Ustoz `11279.30 / 15627.00 = 72.1783%`, Bekzod `27.8217%`;
- active inventory/cost share in `FOYDA TAQSIMOTI`: Ustoz `67.6787%`, Bekzod `32.3213%`.

The second share is calculated after excluding a `2175.50 USD` prepayment from Ustoz's side:

```text
Ustoz active capital share = (11279.30 - 2175.50) / (11279.30 + 4347.70 - 2175.50)
Bekzod active capital share = 4347.70 / (11279.30 + 4347.70 - 2175.50)
```

Profit split is separate and fixed:

```text
Ustoz profit share = 40%
Bekzod/operator profit share = 60%
```

So capital/cost ownership and profit distribution are intentionally different.

## Workbook structure

| Sheet | Role | Depends on | Meaning |
|---|---|---|---|
| `MALUMOTLAR` | Master data | none | Dictionaries: customers, products, creditors, payment methods, accounts, warehouses, product images |
| `TUSHUM` | Money in | `SOTUV` for daily margin % | Capital injections and sales receipts |
| `SOTIB OLISH` | Purchase lines | none | Purchased goods: product, quantity, unit purchase price, FX, total purchase cost |
| `XARAJAT` | Money out | none | Supplier/product payments, customs-like payment, capital withdrawals, dividend payments |
| `SOTUV` | Sales lines | `SOTIB OLISH`, `MALUMOTLAR` | Sales by product/customer/location with revenue and line margin |
| `STOCK TRANSFER` | Inventory movement | none | Product movements between `ASOSIY` and `DOKON` |
| `OMBOR` | Stock report | `SOTIB OLISH`, `SOTUV`, `STOCK TRANSFER`, `MALUMOTLAR` | Remaining stock by product/location and inventory value |
| `PUL AYRIBOSHLASH` | FX exchange | none | Cash exchange between UZS and USD cash accounts |
| `KASSA` | Cash balance | `TUSHUM`, `XARAJAT`, `PUL AYRIBOSHLASH`, `MALUMOTLAR` | Cash in/out and balances by account |
| `QARZDORLAR` | Customer receivables | `SOTUV`, `TUSHUM` | Customer debt = sold amount - paid amount |
| `YETKAZIB BERUVCHILARDAN QARZ` | Supplier/partner payables | `SOTIB OLISH`, `XARAJAT` | Supplier debt/prepayment and partner payout tracking |
| `FOYDA TAQSIMOTI` | Final financial model | `SOTUV`, `SOTIB OLISH`, `OMBOR`, `KASSA`, `QARZDORLAR` | P&L, SOFP-style balance, profit/capital distribution |
| `EXPENSES` | Expense template/data | none | Separate expense table; not materially linked in current final model |

## Main data flow

```text
MALUMOTLAR
  -> validates/categories used by entry sheets

TUSHUM
  -> capital contributions
  -> sales cash receipts
  -> KASSA cash inflow
  -> QARZDORLAR customer payment side

SOTIB OLISH
  -> purchase cost and quantity
  -> SOTUV margin lookup
  -> OMBOR stock value
  -> YETKAZIB BERUVCHILARDAN QARZ supplier purchase side
  -> FOYDA TAQSIMOTI COGS

XARAJAT
  -> supplier payments / capital return / dividends
  -> KASSA cash outflow
  -> YETKAZIB BERUVCHILARDAN QARZ payment side

SOTUV
  -> revenue and margin
  -> OMBOR stock decrement by location
  -> QARZDORLAR customer debt side
  -> FOYDA TAQSIMOTI revenue

OMBOR + KASSA + QARZDORLAR
  -> FOYDA TAQSIMOTI final balance and distribution
```

## Key calculations

### Capital contributions

From `TUSHUM`:

| Partner | Amount |
|---|---:|
| Ustoz | `11279.30 USD` |
| Bekzod aka / business | `4347.70 USD` |
| Total | `15627.00 USD` |

Raw contribution shares:

| Partner | Raw share |
|---|---:|
| Ustoz | `72.1783%` |
| Bekzod aka / business | `27.8217%` |

### Purchase cost and supplier prepayment

From `SOTIB OLISH`:

```text
Purchased goods cost = 13451.50 USD
Purchased quantity = 3020 units
```

From `XARAJAT`, purchase-related outgoing payments:

```text
KOVRIK UCHUN = 7294.00 USD
NABOR UCHUN = 4351.00 USD
Rastamojka = 3982.00 USD
Total outgoing purchase-related payment = 15627.00 USD
```

`YETKAZIB BERUVCHILARDAN QARZ` compares purchase cost with payments:

```text
Supplier purchase = 13451.50 USD
Supplier/payment out = 15627.00 USD
QARZ = -2175.50 USD
```

The negative supplier debt is treated as `Prepayment` in `FOYDA TAQSIMOTI`.

Important: `Rastamojka` is currently treated by formulas as a payment/prepayment-side movement, not as landed cost in product COGS. Product COGS uses only `SOTIB OLISH` purchase prices.

### Sales and margin

From `SOTUV`:

```text
Sales revenue = 4742.11 USD
Line-level sales margin total = 1790.69266667 USD
```

Line formulas:

```text
JAMI SOM = qty * sale price, or USD amount converted to UZS
JAMI USD = JAMI SOM / FX rate
MARJA % = (JAMI USD - purchase_unit_price * qty) / JAMI USD
MARJA USD = JAMI USD - purchase_unit_price * qty
```

The purchase cost is found by product name via `XLOOKUP` into `SOTIB OLISH`.

Important implementation note: this is not FIFO and not lot-aware. If the same product appears in several purchase batches at different prices, the workbook formula does not model true lot allocation.

### Inventory

`OMBOR` calculates product-level stock:

```text
Bought quantity
- sold from ASOSIY
- sold from DOKON
+ transfer in
- transfer out
= remaining quantity by location
```

Current inventory value:

```text
OMBOR QIYMATI = 10555.4535 USD
```

Inventory value is purchase price based. It excludes the `Rastamojka` amount.

### P&L in `FOYDA TAQSIMOTI`

Core formulas:

```text
Revenue = SUM(SOTUV!N3:N109) = 4742.11
Cost of Sales = SUM('SOTIB OLISH'!K3:K109) - OMBOR!L2 = 2896.0465
Gross Profit = Revenue - Cost of Sales = 1846.0635
FX gain/loss = 6.65
Profit = Gross Profit + FX gain/loss = 1852.7135
```

Profit distribution:

```text
Ustoz profit = Profit * 40% = 741.0854
Bekzod profit = Profit * 60% = 1111.6281
```

Capital/cost distribution:

```text
Ustoz cost share = Cost of Sales * 67.6787% = 1960.006551
Bekzod cost share = Cost of Sales * 32.3213% = 936.0399486
```

Total entitlement before withdrawals/dividends:

```text
Ustoz total = cost share + profit share = 2701.091951
Bekzod total = 2047.668049
```

Already paid/withdrawn:

```text
Ustoz capital returned = 1393.40
Ustoz dividend paid = 477.30
Ustoz total paid = 1870.70

Bekzod capital returned = 665.40
Bekzod dividend paid = 715.90
Bekzod total paid = 1381.30
```

Remaining distribution/payable:

```text
Ustoz = 830.3919514
Bekzod = 666.3680486
```

### Balance-style view in `FOYDA TAQSIMOTI`

Assets:

```text
Cash = KASSA USD + KASSA UZS converted to USD = 1496.75
Inventory cost = 10555.4535
Prepayment = 2175.50
Receivables = 0
Total assets = 14227.7035
```

Inventory split:

```text
Ustoz inventory = 10555.4535 * 67.6787% = 7143.793449
Bekzod inventory = 10555.4535 * 32.3213% = 3411.660051
```

Equity/capital side:

```text
Ustoz capital remaining = 11279.30 - 1393.40 = 9885.90
Bekzod capital remaining = 4347.70 - 665.40 = 3682.30
Retained earnings = Profit - dividends paid = 659.5135
```

## Important inconsistencies / risks

### 1. Sales with blank warehouse are included in revenue but excluded from inventory

There are two `SOTUV` rows with blank `OMBOR`:

| Date | Product | Qty | Revenue | Margin |
|---|---|---:|---:|---:|
| 2026-04-26 | `2 talik 60x90` | `3` | `29.75` | `13.8125` |
| 2026-04-26 | `2 talik 50x80` | `10` | `74.38` | `34.94666667` |

Total:

```text
Qty = 13
Revenue = 104.13 USD
Line margin = 48.75916667 USD
Cost = 55.37083333 USD
```

Because `OMBOR` subtracts sales only when `OMBOR` is `ASOSIY` or `DOKON`, these blank-location sales are not reducing stock.

This explains why:

```text
FOYDA TAQSIMOTI Gross Profit = 1846.0635
SOTUV line margin total = 1790.69266667
Difference = 55.37083333
```

The difference is exactly the cost of those blank-location sales. Revenue includes them, but aggregate COGS from inventory does not.

### 2. `FOYDA TAQSIMOTI` mixes formulas and hardcoded values

Several important cells are hardcoded or manual sums:

- `B3 = 365.7 + 1174 + 2808`
- `K3 = 12100`
- `B11 = 0.15 + 0.1 + 1.6 + 4 + 0.8`
- `E8 = 1393.4`
- `E9 = 665.4`
- `E12 = 477.3`
- `E13 = 715.9`
- `H10 = 2175.5`
- `H18 = 3682.3`
- `C16`, `E16`, `C25` appear as hardcoded continuation values

For software implementation, these must become ledger-derived values, not manually typed summary numbers.

### 3. Google Sheets formulas were exported as unsupported Excel functions

Some formulas are stored as:

```text
__xludf.DUMMYFUNCTION(...)
```

Examples include Google Sheets-style `ARRAYFORMULA`, `IMAGE`, `REGEXEXTRACT`, `UNIQUE`, `QUERY`.

The workbook still contains cached values, but Excel itself cannot reliably recalculate those formulas unless the model is rebuilt in native Excel formulas or in app logic.

### 4. Product cost is product-name based, not lot/FIFO based

`SOTUV` margin uses product-name lookup:

```text
XLOOKUP(product, 'SOTIB OLISH' product column, purchase_unit_price)
```

This works only while each product has one relevant purchase cost. It does not support:

- multiple lots for same product;
- FIFO;
- landed-cost allocation by batch;
- partial returns by lot;
- exact per-sale procurement attribution.

### 5. `Rastamojka` is not in COGS

The file visually has `Rastamojka` as a purchase-related outgoing payment, but final COGS and inventory value use only `SOTIB OLISH` purchase cost. The `Rastamojka` amount contributes to overpayment/prepayment mechanics, not landed cost.

This may be intentional, but it is a business-rule decision we need to confirm before copying behavior into the app.

## Product implementation implications

The workbook suggests these domain concepts should be explicit in MicroPOS:

1. `CapitalContribution`: who contributed money and in which currency.
2. `ProcurementItem`: purchased product, quantity, unit cost, FX.
3. `SupplierPayment`: money paid for procurement/supplier/costs.
4. `ProcurementPrepayment`: overpayment or unused purchase cash that remains an asset.
5. `Lot`: actual stock created from purchase lines.
6. `SaleLine`: must reference lot/FIFO allocation, not only product name.
7. `InventoryMovement`: store/warehouse transfer.
8. `PartnerCapitalShare`: calculated from active capital attached to goods, not necessarily raw contribution total.
9. `PartnerProfitShare`: separate contractual split, here `40/60`.
10. `PartnerLedgerEntry`: capital consumed, profit accrued, dividend paid, capital returned, loss/reversal.
11. `CashAccountLedger`: cash in/out/exchange by currency/account.
12. `Receivable/Payable`: customer debts, supplier debts, partner payable/prepayment.

The main product decision is whether we want to reproduce the Excel behavior exactly or normalize it into a cleaner accounting model:

- exact Excel behavior: raw capital can exceed purchased goods, and excess becomes prepayment; active capital share is calculated only against goods-cost base;
- cleaner system behavior: explicitly separate procurement funding pot, supplier prepayment, landed-cost rules, and partner ownership of each asset bucket.

## Open questions for discussion

1. Should `Rastamojka` be part of landed cost/COGS or an operational/prepayment-side expense?
2. Is the `2175.50 USD` prepayment owned entirely by Ustoz, as implied by `C2=(B2-H10)/(B2+B3-H10)`?
3. Should profit always be `40/60` even when active capital share changes?
4. Should capital return be paid from sold COGS share only, or from any available cash?
5. Should the app expose both raw contribution share and active inventory/cost share?
6. Should sales without warehouse be forbidden? In the workbook they create a reporting mismatch.
7. Should supplier overpayment be shown as supplier prepayment, partner asset, or procurement balance?

