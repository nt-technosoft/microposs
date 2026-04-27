# MicroPOS — Financial Audit Matrix

**Snapshot:** 2026-04-27  
**Companion docs:** [reporting-audit-roadmap.md](/Users/aziztohirov/Desktop/Projects/microposs/docs/reporting-audit-roadmap.md), [financial-audit-batch-1.md](/Users/aziztohirov/Desktop/Projects/microposs/docs/financial-audit-batch-1.md), [financial-audit-batch-2.md](/Users/aziztohirov/Desktop/Projects/microposs/docs/financial-audit-batch-2.md), [financial-audit-batch-3.md](/Users/aziztohirov/Desktop/Projects/microposs/docs/financial-audit-batch-3.md)

## Purpose

This document is the working audit sheet for verifying that each important operation produces the expected:

- inventory consequence
- financial consequence
- partnership/investor consequence
- outbox/reporting consequence
- UI consequence

Use it before expanding reporting.

## Status Legend

- `Covered` — already backed by automated tests
- `Partial` — some consequence is covered, but not the full business chain
- `Missing` — no meaningful verification yet
- `Failed` — audited manually and mismatch found
- `Verified` — audited manually and matched expectations

## Phase 1 Priority

Audit these first:

1. partnership procurement lifecycle
2. receive + landed cost
3. sale with FIFO
4. mixed-payment sale
5. credit sale
6. returns
7. customer debt payment
8. supplier payment
9. dividend payout
10. FX exchange
11. session open/close
12. inventory transfer

---

## Audit Matrix

| ID | Operation | Why it matters | Expected consequences | Current evidence | Status |
|---|---|---|---|---|---|
| A01 | Open session | base for cashier shift accounting | session opens only on shop; single active session per cashier/location; opening cash stored; preview starts at `cash_sales_total=0`, `sales_count=0` | `test_pos_session_api.py` | `Covered` |
| A02 | Close session | final shift cash reconciliation | expected cash = opening cash + cash sales; actual cash stored; cash difference computed; closed session cannot be closed again | `test_pos_session_api.py` | `Covered` |
| A03 | Open partnership procurement | base contract state | procurement opens with valid partner structure; planned capital shares/profit shares valid; unrelated investors not visible; contract builder locked after balance activity | `test_partnerships_api.py`, `test_invariant_guards.py` | `Partial` |
| A04 | Pay procurement items / expenses | cost formation | payable state and procurement balance move correctly; paid items/expenses become receive basis; outbox events published | `test_partnerships_api.py`, `test_outbox_pipeline.py` | `Partial` |
| A05 | Receive procurement | inventory capitalization | lot created; lot stock appears in destination; contract snapshot frozen; landed cost calculated from purchase cost + allocated expenses; procurement balance ends at zero or valid auto-return | `test_procurement_lifecycle.py` | `Covered` |
| A06 | FIFO sale of financed goods | core sale correctness | oldest available lots are allocated first; stock decreases from correct lot/location; `SaleLine` stores lot, purchase cost, landed cost; `sale.total_cogs` correct | `test_procurement_lifecycle.py`, inventory service logic, `test_sale_multi_payment.py`, `test_audit_batch_one.py` | `Covered` |
| A07 | Cash/card sale | normal daily money flow | sale completes; incoming cash/card entries created; sale journal created; session stats update; outbox written | `test_sale_multi_payment.py`, `test_outbox_pipeline.py` | `Partial` |
| A08 | Mixed-payment sale | hardest sale shape | one sale with several payments; cash entries created per payment; journal count matches expected; total paid == sale total; partner profit accrues | `test_sale_multi_payment.py` | `Covered` |
| A09 | Credit sale | receivable integrity | `customer_id` required; receivable accrues; sale journal created; no immediate cash entry unless mixed payment; reports reflect debt | `test_sale_credit_integrity.py` | `Covered` |
| A10 | Customer debt payment | receivable settlement | customer debt decreases; cash entry created; journal created; cash flow reflects incoming debt payment | `test_customer_payment_cash_flow.py` | `Covered` |
| A11 | Supplier payment | payable settlement | supplier payable decreases; cash leaves account; journal/cash flow reflect outflow; reports update | `test_audit_batch_two.py` | `Covered` |
| A12 | Restock return | reverse realized profit | stock restored to correct location/lot; sale profit reversed pro-rata; pending payout adjusts; no loss recognized | `test_returns_shariah.py` | `Covered` |
| A13 | Dispose return / damaged return | loss allocation | stock not restored to sellable inventory; disposal record created; loss recognized by capital share; investor/business loss distribution correct | `test_returns_shariah.py` | `Covered` |
| A14 | Refund payout | money leaves business | refund creates cash outflow and journal; return/refund references consistent; cash balances and reports update | `test_refund_integrity.py` | `Covered` |
| A15 | Inventory transfer | stock location only | quantity moves between locations; ownership/participants/profit shares unchanged; no financial mutation | `test_inventory_transfer_api.py`, inventory service invariant | `Partial` |
| A16 | Dividend payout | investor settlement | amount cannot exceed pending payout; cash outflow created; ledger `DIVIDEND_PAID` created; pending payout decreases | `test_partnerships_api.py` | `Partial` |
| A17 | Owner contribution | business funding | cash increases; journal/cash entry created; cash account balances update | `test_finance_bridge_api.py` | `Covered` |
| A18 | Currency exchange | FX handling | from-account decreases, to-account increases, effective rate stored, balances split by currency remain coherent | `test_finance_bridge_api.py`, `test_fx_rates.py` | `Covered` |
| A19 | FX-based expense/payment | multi-currency trace | operation amount, functional UZS amount, fx snapshot consistent; reports use functional view correctly | `test_fx_rates.py` | `Partial` |
| A20 | Investor dashboard aggregate | trust layer | invested, capital net, accrued profit, dividends paid, pending payout computed from partner ledger correctly | `test_partner_ledger.py`, `test_investor_bridge_api.py`, `test_audit_batch_two.py` | `Covered` |
| A21 | Investor procurement detail | drill-down trust layer | procurement-level ledger and aggregate reflect only investor’s own participation and selected procurement | `test_investor_bridge_api.py`, `test_tenant_context.py`, `test_audit_batch_two.py` | `Covered` |
| A22 | Owner reports dashboard | management visibility | daily summary, cash flow, stock summary, debt/payables, cash balances reconcile with transactional flows | `test_audit_batch_one.py`, existing finance endpoints | `Covered` |
| A23 | Sales history / sale detail | operational explainability | sale card, detail, payment method, line items, profitability preview stay consistent with backend data | `SalesHistory.vue`, `SaleExplanationView.vue`, `test_profitability_reports.py`; broader manual regression still pending | `Partial` |
| A24 | Reconciliation endpoint | audit bridge | latest reconciliation exposes computed vs expected deltas and gap summary after import/operations | `test_reconciliation_view.py`, `/reports/reconciliation`, `financial-audit-batch-3.md` | `Covered` |
| A25 | Profitability read-models | owner analytics foundation | sale profitability, product profitability, remaining stock projection, investor/business split remain consistent with transactional engine | `test_profitability_reports.py` | `Covered` |

---

## Detailed Checks Per Scenario

Use these when running a manual audit.

## A05 — Receive procurement

### Preconditions
- procurement opened
- contributions added
- items and expenses paid
- FX rate available when needed

### Verify
- lot created with correct `quantity_initial`
- stock appears in target warehouse/store
- `unit_purchase_price` matches normalized purchase basis
- `landed_cost_per_unit` matches purchase + allocated expenses
- `contract_snapshot` contains exact partner/capital/profit shares
- procurement balance returns to zero or valid surplus return path

### Existing evidence
- `test_receive_procurement_creates_lot_stock_and_contract_snapshot`
- `test_receive_procurement_respects_expense_allocation_method`
- `test_receive_procurement_auto_returns_surplus_by_planned_capital`
- `test_receive_procurement_normalizes_mixed_currency_contributions_to_contract_currency`

## A06 / A07 / A08 — Sale correctness

### Preconditions
- received procurement exists
- stock present in selling location
- active open session exists

### Verify
- selected lot is the oldest eligible lot
- stock decreases from the exact source lot/location
- `sale.total_amount` matches payments / line sums
- `sale.total_cogs` matches landed cost of sold quantity
- each `SaleLine` stores:
  - `lot`
  - `unit_purchase_price`
  - `unit_landed_cost`
  - `profit_distribution_snapshot`
- partner ledger gets `PROFIT_ACCRUED`
- cash/card payments create cash entries and journals
- session summary reflects sales count and cash sales

### Existing evidence
- `test_create_sale_creates_multiple_payments_and_profit_ledger_entries`
- `test_calculate_profit_distribution_respects_contract_formula`
- `test_partner_aggregate_uses_new_ledger_model`

## A09 / A10 — Credit and receivable flow

### Verify
- credit sale without customer is rejected
- credit sale creates receivable
- later payment reduces debt
- payment creates cash entry and journal
- reports reflect lower debt and higher cash

### Existing evidence
- `test_credit_sale_accrues_receivable_and_writes_sale_journal`
- `test_owner_customer_payment_creates_cash_entry_and_journal`

## A12 / A13 / A14 — Return and refund flow

### Restock return
- stock restored
- lot reactivated if needed
- profit reversed proportionally

### Dispose return
- disposal record created
- loss amount equals returned landed cost
- losses split by capital share

### Refund
- cash outflow and journal created
- sale/return/refund references remain coherent

### Existing evidence
- `test_restock_return_reverses_profit_and_restores_stock`
- `test_dispose_return_records_loss_by_capital_share`
- `test_cash_refund_creates_cash_entry_and_journal`

## A16 / A20 / A21 — Investor obligation transparency

### Verify
- profit accrual increases investor pending payout
- dividend payout decreases pending payout
- investor dashboard reflects:
  - capital in
  - capital net
  - profit accrued
  - dividends paid
  - pending payout
- procurement detail reflects procurement-only slice

### Existing evidence
- `test_partner_aggregate_uses_new_ledger_model`
- `test_investor_dashboard_and_procurements_are_available`
- `test_owner_can_create_dividend_payment_via_api`

---

## Coverage Gaps To Audit Manually First

These are the first things still hidden enough to justify manual audit:

1. **Session statistics after every sale type**
   - cash, card, credit, mixed
2. **Procurement / investor drill-down trust audit**
   - verify that summary profitability and investor transparency remain explainable at procurement level in real UI flows
3. **Category/location reporting trust audit**
   - verify that next analytics slices stay aligned with the same transactional engine

---

## Manual Execution Sheet

Use one line per executed scenario.

| Run ID | Scenario ID | Preconditions OK | Expected | Actual | Result | Severity | Notes |
|---|---|---|---|---|---|---|---|
| 001 | A05 |  |  |  |  |  |  |
| 002 | A06 |  |  |  |  |  |  |
| 003 | A09 |  |  |  |  |  |  |

---

## Recommended First Audit Batch

Run in this exact order:

1. A05 — receive procurement
2. A06 — FIFO sale
3. A08 — mixed payment sale
4. A09 — credit sale
5. A10 — customer debt payment
6. A12 — restock return
7. A13 — dispose return
8. A16 — dividend payout
9. A18 — currency exchange
10. A22 — owner reports consistency
11. A20/A21 — investor dashboard consistency

This batch is enough to reveal whether the financial engine is trustworthy enough for report expansion.
