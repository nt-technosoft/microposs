# MicroPOS — Financial Audit Batch 1

**Snapshot:** 2026-04-23  
**Scope:** first technical audit batch for financial consequences before expanding reporting.

## Command

```bash
./.venv/bin/python manage.py test \
  apps.core.tests.test_procurement_lifecycle \
  apps.core.tests.test_audit_batch_one \
  apps.core.tests.test_sale_multi_payment \
  apps.core.tests.test_sale_credit_integrity \
  apps.core.tests.test_customer_payment_cash_flow \
  apps.core.tests.test_returns_shariah \
  apps.core.tests.test_partnerships_api \
  apps.core.tests.test_finance_bridge_api \
  apps.core.tests.test_fx_rates \
  apps.core.tests.test_pos_session_api \
  apps.core.tests.test_inventory_transfer_api \
  apps.core.tests.test_investor_bridge_api \
  --keepdb --verbosity 1
```

## Result

- **34 tests**
- **OK**
- no financial mismatch found in this batch

Note:
- `api_bad_request_response ... 400` lines in test output are expected negative validation scenarios, not failed financial flows.

## Verified Scenarios

| Scenario IDs | Area | Evidence | Result |
|---|---|---|---|
| A01, A02 | session open/close invariants | `test_pos_session_api.py` | `Verified` |
| A05 | receive procurement, landed cost, stock capitalization | `test_procurement_lifecycle.py` | `Verified` |
| A06 | FIFO sale consumes oldest financed lot first | `test_audit_batch_one.py::test_fifo_sale_consumes_oldest_lot_first` | `Verified` |
| A08 | mixed-payment sale, journal/cash/partner profit accrual | `test_sale_multi_payment.py` | `Verified` |
| A09 | credit sale creates receivable correctly | `test_sale_credit_integrity.py` | `Verified` |
| A10 | customer debt payment settles receivable and affects cash flow | `test_customer_payment_cash_flow.py` | `Verified` |
| A12, A13 | restock/dispose returns and profit-loss reversal logic | `test_returns_shariah.py` | `Verified` |
| A15 | inventory transfer changes location only | `test_inventory_transfer_api.py` | `Verified` |
| A16 | dividend payout guardrails and investor settlement path | `test_partnerships_api.py` | `Verified` |
| A18, A19 | currency exchange and FX trace basics | `test_finance_bridge_api.py`, `test_fx_rates.py` | `Verified` |
| A20, A21 | investor dashboard and procurement drill-down consistency | `test_investor_bridge_api.py`, `test_audit_batch_one.py` | `Verified` |
| A22 | owner reports remain consistent after controlled sale | `test_audit_batch_one.py::test_owner_reports_and_investor_dashboard_stay_consistent_after_sale` | `Verified` |

## What This Batch Proved

1. sale COGS and FIFO allocation are behaving deterministically in the audited scenario;
2. owner summary reports are consistent with the same sale that feeds investor profit accrual;
3. investor pending payout and owner gross profit stay aligned in the audited financed-sale path;
4. returns, receivables, FX, session, and transfer basics are already backed by automated coverage.

## Remaining Gaps

Still worth auditing before broad report expansion:

- supplier payment settlement chain (`A11`)
- session totals across every payment shape, especially mixed/non-cash UI refresh expectations (`A07`)
- investor capital state split:
  - sold at cost
  - still in stock at cost
  - projected margin on remaining financed inventory
- sales detail analytical read model / profitability UI (`A23`)
- reconciliation-specific scenario audit (`A24`)

## Recommended Next Batch

1. supplier payable settlement
2. investor capital-in-stock vs sold-at-cost read model
3. sale-line profitability read model
4. reconciliation report scenario audit
