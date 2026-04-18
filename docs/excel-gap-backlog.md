# MicroPOS — Excel Alignment Gap Backlog

## P0 (Operational blockers)

| Gap | Excel expectation | Current state | Target action |
|---|---|---|---|
| Supplier payable lifecycle | Purchase on credit should increase supplier debt, payments should decrease | Increased in import flow for credit rows; broader native flow needs explicit AP policy | Add explicit AP service/pipeline for supplier purchase obligations outside import context |
| Expense domain model | Non-supplier expenses tracked as first-class operations | Currently imported as journal-only expense for non-supplier creditor | Introduce dedicated Expense model + service + reports binding |
| Multi-currency operational views | Operators see source/functional amounts per operation | Canonical amounts stored in staging trace, not exposed everywhere in UI | Surface operation currency trace in relevant history/report endpoints |
| Historical timestamp parity | Imported operations should preserve source chronology everywhere | Core services updated for sale/customer/supplier date injection; some side records still default now | Extend timestamp control for all dependent records where required |

## P1 (Reporting and UX acceleration)

| Gap | Excel expectation | Current state | Target action |
|---|---|---|---|
| KASSA parity dashboard | Cash picture by account/channel | Reconcile exists; dedicated UI parity pending | Add cash pivot widget by account/method/date |
| OMBOR parity | Inventory qty/value by location/product | Reconcile + stock summary exist; no full parity view yet | Add inventory valuation report equivalent to OMBOR logic |
| AR/AP parity screens | QARZDORLAR + YETKAZIB... behavior with aging | Aggregate totals exist; aging/filters limited | Add AR/AP analytics with aging buckets + creditor/customer filters |
| FX movement analytics | PUL AYRIBOSHLASH trace and FX impact | Journal transfer exists; no dedicated FX report | Add FX operations report and revaluation deltas |

## P2 (Advanced analytics / insight layer)

| Gap | Opportunity | Target action |
|---|---|---|
| Insight-first reporting | Move beyond spreadsheet mirrors | Build anomaly detection (margin drop, stock risk, debt growth) |
| Assisted operations | Reduce manual interpretation | Add rule-based recommendations (reorder, debt follow-up, margin tuning) |
| Role-adaptive intelligence | Different insights per role | Owner/cashier/warehouse/investor KPI packs with alerts |

## Tracking Rule
Каждый новый gap фиксируется с полями:
- `what_in_excel`
- `current_micropos_state`
- `target_state`
- `reason_for_deviation`
- `decision`
- `owner`
- `target_iteration`
