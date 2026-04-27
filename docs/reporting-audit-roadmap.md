# MicroPOS — Reporting and Financial Audit Roadmap

**Snapshot:** 2026-04-27  
**Goal:** make partnership trading transparent, auditable, and explainable for owner, business operator, and investor.

## 0. Progress Snapshot

- **Backend reporting/audit foundation:** `~90%`
- **Frontend reporting/transparency UI:** `~75%`
- **Docs/status sync:** `~50%`

Current state:
- core read-models and audit endpoints mostly exist;
- owner and investor UI already expose the main profitability and transparency surfaces;
- the biggest remaining gap is no longer raw calculation, but deeper drill-down, reconciliation-as-audit, and document sync.

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
  - procurement profitability
  - projected remaining stock margin
- **Audit / reconciliation**
  - reconciliation summary endpoint
  - sale explanation endpoint surface for owner audit flow

### Already exists in frontend

- `/reports` — owner dashboard
- `/reports/reconciliation`
- `/reports/audit/sales/:id`
- `/finance/exchange`
- `/investor`
- `/investor/procurements/:id`
- `/sales/history`

### Main gaps

- roadmap docs are behind the code and need active syncing
- no dedicated **per procurement** audit/explanation screen yet; procurement profitability currently lives inside owner `/reports`
- investor transparency still lacks deeper drill-down by product / lot / sale line / day
- category/location profitability is not yet surfaced as a first-class report
- reconciliation endpoint and UI exist and now have scenario coverage for `ok / warning / mismatch`; broader owner-facing trust review remains part of manual smoke

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

1. **Sale profitability detail** — `Implemented`
2. **Product profitability** — `Implemented`
3. **Inventory valuation by location** — `Partial`
4. **Investor capital state** — `Implemented`
5. **Investor pending payout / obligation** — `Implemented`
6. **Audit trail for one sale line** — `Implemented`
7. **Shift/day closing report** — `Partial`

## P1 — should exist next

8. **Procurement profitability** — `Implemented` in dashboard, `Partial` as deep drill-down
9. **Category profitability** — `Missing`
10. **Aging / stale stock report** — `Missing`
11. **Receivables aging** — `Partial`
12. **Payables aging** — `Partial`
13. **Cash account movement report** — `Partial`
14. **Owner contribution / withdrawal report** — `Partial`

## P2 — advanced

15. **Projected gross margin on remaining stock** — `Implemented` at investor/product/procurement summary level
16. **Margin waterfall** — `Missing`
17. **FX impact report** — `Partial`
18. **Partner settlement planner** — `Missing`
19. **Exportable audit packs** — `Missing`

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

## Stage 0 — Doc sync

Deliverables:
- sync roadmap/matrix/status docs with current code
- mark which old gaps are already closed
- leave only the real remaining tail in planning docs

## Stage 1 — Reconciliation trust audit

Deliverables:
- controlled scenario pack for reconciliation
- expected vs actual examples for import/operations deltas
- sign-off that reconciliation surfaces real business mismatches, not only raw endpoint health

Status today:
- healthy path covered
- warning path covered
- structural mismatch path covered

Remaining:
- keep reconciliation in owner smoke as reports expand

## Stage 2 — Deep reporting drill-down

Backend/API:
- keep current profitability contracts stable
- extend only where a drill-down truly needs more detail

Frontend:
- procurement profitability detail
- investor deeper transparency by product / lot / sale line
- better owner audit navigation from reports to explanation screens

## Stage 3 — Next analytical slices

- category profitability
- location profitability
- receivables/payables aging
- cash movement views

## Stage 4 — Advanced analytics and exports

- margin waterfall
- FX impact expansion
- partner settlement planner
- exportable audit packs

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

Status today:
- sales/product/procurement profitability — done
- investor capital state — done
- sale explanation surface — done
- reconciliation summary endpoint — done

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

Status today:
- owner `/reports` is already the main report surface
- reconciliation screen exists
- sale explanation screen exists
- investor dashboard/procurement transparency exists

Main remaining frontend work:
- deeper procurement audit view
- deeper investor drill-down
- category/location analytics surfaces

Restructure `/reports` into:

- Overview
- Sales
- Inventory
- Finance
- Partnership
- Audit

## Step D — Investor surfaces

Status today:
- summary — done
- procurements — done
- capital state / pending payout / projected metrics — done
- deeper audit drill-down — still pending

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
