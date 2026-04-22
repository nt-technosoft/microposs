# MicroPOS — Reporting and Financial Audit Roadmap

**Snapshot:** 2026-04-23  
**Goal:** make partnership trading transparent, auditable, and explainable for owner, business operator, and investor.

## 1. Main Decision

Work order should be:

1. **Audit financial consequences and invariants**
2. **Then build reporting surfaces on top of trusted numbers**

Reason:
- reporting is only useful if sale, FIFO, margin, journal, cash, receivable/payable, and partner ledger consequences are correct;
- current codebase already has most core calculations, but visibility is incomplete and some consequences still need explicit verification.

## 2. Current Reality

### Already exists in backend/read-models

- **Sales core**
  - sale stores `total_amount`, `total_cogs`
  - each `SaleLine` stores:
    - `unit_purchase_price`
    - `unit_landed_cost`
    - `profit_distribution_snapshot`
- **FIFO**
  - sale allocation uses `allocate_lot()` by receive chronology
- **Partner/investor ledger**
  - profit accrual, reversal, losses, dividends are already represented in `PartnerLedgerEntry`
  - aggregate is available via `get_partner_aggregate()`
- **Owner finance summaries**
  - daily summaries
  - cash flow
  - trial balance
  - cash accounts
  - debt summary
  - payables summary
  - stock summary
- **Investor cabinet**
  - invested capital
  - capital net
  - accrued profit
  - dividends paid
  - pending payout
  - procurement-level ledger
  - sold capital at cost basis
  - remaining capital in stock at cost basis
  - projected partner profit on remaining stock
- **Profitability read-models**
  - sales profitability
  - product profitability
  - projected remaining stock margin

### Already exists in frontend

- `/reports` — owner dashboard
- `/reports/reconciliation`
- `/finance/exchange`
- `/investor`
- `/investor/procurements/:id`
- `/sales/history`

### Main gaps

- no UI surface yet for the new profitability read-models
- no full **per procurement** profitability screen
- no explicit **sales detail profitability** surface in operational history
- no complete **audit screen** that explains every number end-to-end
- reconciliation still needs its own focused scenario audit

## 3. Reporting Philosophy

We should split reports into 4 layers.

### A. Operational reports
Used daily.

- sales history
- session summary
- stock movements
- debts / payables
- open procurements

### B. Management reports
Used by owner/business.

- P&L
- cash flow
- balance / trial balance
- stock valuation
- profitability by product/category/location

### C. Partnership / investor reports
Used for trust, payouts, and audit.

- investor capital status
- investor profit accrual
- pending payout
- sold vs unsold capital
- profit split by procurement / product / sale line

### D. Audit / explanation reports
Used when someone doubts calculations.

- exact sale-line cost build-up
- exact FIFO source lot
- exact landed cost composition
- exact profit split per participant
- exact journal and ledger consequences

## 4. Recommended Report Matrix

## 4.1 Cashier

Should see:

- **Sales History**
  - what was sold
  - quantity
  - payment method
  - return handling
- **Session Summary**
  - opening cash
  - cash sales
  - expected cash
  - sales count
- **Daily Session Report**
  - all sales in current/closed shift
  - cash vs card vs credit split

Cashier should **not** see investor split and deep financial internals by default.

## 4.2 Warehouse

Should see:

- **Stock by location**
- **Lot aging / FIFO candidates**
- **Transfers**
- **Procurement receive cost preview**
- **Inventory valuation by landed cost**

Warehouse does not need full financial statements, but does need:
- cost visibility,
- quantity visibility,
- warehouse/store split.

## 4.3 Owner / Business

Should see:

### Core finance
- **P&L**
  - revenue
  - COGS
  - gross profit
  - expenses
  - operating profit
- **Cash Flow**
  - inflows
  - outflows
  - net cash flow
- **Balance / Trial Balance**
  - cash
  - receivables
  - payables
  - owner/investor obligations
  - inventory

### Operational profitability
- **Sales profitability report**
  - per sale
  - per sale line
  - sale amount
  - purchase cost
  - landed cost
  - gross margin sum
  - gross margin %
- **Product profitability**
  - by product
  - by variant
  - by category
  - by date range
  - by location
- **Inventory valuation**
  - store vs warehouse
  - quantity
  - purchase-cost value
  - landed-cost value
  - expected sale value
  - expected margin value

### Partnership control
- **Partner obligation report**
  - how much business owes each investor
  - accrued profit
  - paid dividends
  - capital still tied in stock
- **Procurement profitability**
  - each procurement
  - how much has sold
  - how much remains in stock
  - realized profit
  - unrealized expected margin

## 4.4 Investor

Investor should see:

### Summary
- total invested
- capital returned
- capital still active
- accrued profit
- profit paid out
- pending payout

### Capital state
- **Sold capital**
  - how much of his financed goods already sold at cost basis
- **Unsold capital**
  - how much still sits in inventory at cost basis
- **Realized profit**
  - from sold goods only
- **Projected margin**
  - based on current stock marked with planned sale price or current retail price

### Drill-down
- by procurement
- by product
- by lot
- by sale line
- by day / by shift

Investor view must answer:
- “How much did I put in?”
- “How much of my capital is still in goods?”
- “How much of my goods already sold?”
- “How much profit has been earned?”
- “How much is still owed to me?”

## 5. Mandatory Report Types

Below is the recommended minimum set.

## P0 — must exist

1. **Sale profitability detail**
2. **Product profitability**
3. **Inventory valuation by location**
4. **Investor capital state**
5. **Investor pending payout / obligation**
6. **Audit trail for one sale line**
7. **Shift/day closing report**

## P1 — should exist next

8. **Procurement profitability**
9. **Category profitability**
10. **Aging / stale stock report**
11. **Receivables aging**
12. **Payables aging**
13. **Cash account movement report**
14. **Owner contribution / withdrawal report**

## P2 — advanced

15. **Projected gross margin on remaining stock**
16. **Margin waterfall**
17. **FX impact report**
18. **Partner settlement planner**
19. **Exportable audit packs**

## 6. Required Slices / Filters

Almost every serious report should support some subset of:

- date range
- shift / session
- location
- warehouse vs store
- product
- variant
- category
- procurement
- investor
- partner
- payment method
- sold / in stock / returned / damaged
- business-owned vs partnership-owned

## 7. Core Definitions We Must Freeze

Before building more reports, definitions must be explicit and stable.

### Cost terms

- **Purchase cost** = raw buy price per unit
- **Landed cost** = purchase cost + allocated procurement expenses per unit
- **COGS** = landed cost of sold quantity

### Profit terms

- **Gross profit** = sale amount - COGS
- **Gross margin %** = gross profit / sale amount
- **Markup %** = gross profit / COGS

### Partnership terms

- **Capital sold** = cost-basis amount of investor-financed goods already sold
- **Capital in stock** = cost-basis amount of investor-financed goods still remaining
- **Profit accrued** = realized profit already allocated by sale logic
- **Pending payout** = accrued profit - dividends already paid
- **Projected margin** = possible future gross profit if current stock sells at current planned price

These names should be used consistently in backend, frontend, docs, and UI.

## 8. Where Each Thing Should Live

### Sales History
Keep operational.

Should show:
- sale meta
- line items
- payment method
- amount
- maybe quick profitability preview

Should not become the main reporting center.

### Reports section
This should become the main analytical area.

Recommended subsections:

1. **Overview**
2. **Sales**
3. **Inventory**
4. **Finance**
5. **Partnership**
6. **Audit**

### Investor cabinet
Should be a role-specific read surface, not a copy of owner reports.

Investor should see only:
- his money,
- his goods,
- his profit,
- his obligations,
- his transaction history.

## 9. Audit Program: What Must Be Verified First

Before adding more report screens, run a structured audit of expected consequences.

## 9.1 Operations to test

1. open session
2. close session
3. cash sale
4. card sale
5. credit sale
6. mixed payment sale
7. sale of partnership goods
8. sale of business-owned goods
9. return (good condition)
10. return (damaged / loss case)
11. procurement creation
12. item payment
13. expense payment
14. receive procurement
15. stock transfer
16. customer debt payment
17. supplier payment
18. FX exchange
19. dividend payout
20. owner contribution

## 9.2 For each operation verify

### Inventory consequence
- stock changed?
- right location?
- right lot?
- FIFO respected?

### Financial consequence
- cash entry created?
- journal entry created?
- AR/AP changed?
- balances moved correctly?

### Partnership consequence
- profit allocated?
- ledger entry created?
- reversal/loss logic correct?
- pending payout updated?

### Outbox / analytics consequence
- outbox event exists?
- summary/report read models reflect the action?

### UI consequence
- history/screens update?
- session statistics update?
- report cards update?

## 10. Recommended Delivery Order

## Stage 1 — Audit and trust foundation

Deliverables:
- operation audit matrix
- expected outcome checklist per operation
- bug list from real execution
- invariant sign-off gaps

This should come first.

## Stage 2 — P0 reporting read models

Backend:
- sale profitability read model
- inventory valuation read model
- investor capital state read model
- procurement profitability read model

Frontend:
- reports information architecture
- owner report pages
- investor transparency pages

## Stage 3 — Audit explainability

Add deep drill-down:
- sale line -> lot -> procurement -> ledger -> journal

This is the most important transparency feature for disputes.

## Stage 4 — Advanced analytics

- projected margin
- aging
- scenario/export
- richer filters

## 11. Concrete Implementation Plan

## Step A — Audit pack

Create:
- `docs/financial-audit-matrix.md`
- operation-by-operation checklist
- manual + automated scenario table

Then execute flows and log:
- expected
- actual
- mismatch
- severity

## Step B — Backend report contracts

Add endpoints/read models for:

1. `sales profitability`
   - per sale
   - per line
   - landed cost
   - gross profit
   - margin %
   - markup %
   - partner split

2. `inventory valuation`
   - by location
   - by product/variant
   - by ownership type
   - by investor/partner

3. `investor capital state`
   - invested
   - sold at cost
   - still in stock at cost
   - accrued profit
   - paid profit
   - pending payout
   - projected margin

4. `procurement profitability`
   - capital in
   - sold cost basis
   - remaining stock cost basis
   - realized profit
   - projected profit

## Step C — Frontend report IA

Restructure `/reports` into:

- Overview
- Sales
- Inventory
- Finance
- Partnership
- Audit

## Step D — Investor surfaces

Expand investor cabinet with:

- summary
- procurements
- goods sold vs in stock
- pending payout
- ledger
- audit drill-down

## 12. Priority Recommendation

If we compare the two big tasks:

### Task 1: build report system
### Task 2: audit whether all financial consequences are actually correct

**Do Task 2 first.**

Reason:
- your reports will otherwise only visualize possibly wrong consequences;
- the current system already has enough hidden complexity in sale/payment/profit/journal/ledger consequences;
- one week of audit gives more value than one week of new dashboards on uncertain numbers.

## 13. Immediate Next Step

Recommended next action:

1. freeze this roadmap
2. use the **financial audit matrix**: [financial-audit-matrix.md](/Users/aziztohirov/Desktop/Projects/microposs/docs/financial-audit-matrix.md)
3. run scenario-based verification on the most sensitive flows:
   - partnership procurement
   - receive
   - sale
   - return
   - credit sale
   - debt payment
   - dividend payout
   - FX exchange

Only after that move into report implementation.
