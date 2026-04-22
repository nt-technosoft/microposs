# MicroPOS — Financial Audit Batch 2

**Snapshot:** 2026-04-23  
**Scope:** supplier settlement chain and investor capital-state transparency.

## Command

```bash
./.venv/bin/python manage.py test \
  apps.core.tests.test_audit_batch_two \
  --keepdb --verbosity 1
```

## Result

- **2 tests**
- **OK**
- batch confirms both the supplier settlement chain and the new investor capital-state read-model

## What Was Verified

| Scenario IDs | Area | Evidence | Result |
|---|---|---|---|
| A11 | supplier payment settlement | `test_supplier_payment_reduces_payable_and_updates_owner_cash_flow` | `Verified` |
| A20, A21 | investor capital-state transparency by cost basis | `test_investor_dashboard_exposes_capital_state_at_cost_basis` | `Verified` |

## What Changed In Code

1. investor endpoints now expose `capital_state` based on procurement lots and partner capital share:
   - sold cost in UZS
   - in-stock cost in UZS
   - tracked cost in UZS
   - sold revenue in UZS
2. this read-model is partner/procurement based and does not rely on the stale legacy `Receipt` contract path
3. supplier payment chain is now explicitly covered from:
   - payable reduction
   - to journal entry
   - to owner cash flow summary

## Important Finding

Before this batch, investor transparency had a real semantic gap:

- ledger totals were available,
- but there was no trustworthy split between:
  - capital already sold at cost basis
  - capital still tied in remaining stock.

That gap is now covered in the current procurement-based flow.

## Remaining Gaps

- projected margin on remaining financed stock
- profitability read-model for sale line / product / procurement analytics
- reconciliation-specific controlled scenario audit
- broader session/UI smoke for every payment shape
