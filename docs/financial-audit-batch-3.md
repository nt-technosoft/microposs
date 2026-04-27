# MicroPOS — Financial Audit Batch 3

**Snapshot:** 2026-04-27  
**Scope:** reconciliation scenario audit.

## Command

```bash
./backend/.venv/bin/python backend/manage.py test \
  apps.core.tests.test_reconciliation_view \
  --keepdb --verbosity 1
```

## Result

- **3 tests**
- **OK**
- reconciliation now has explicit coverage for:
  - healthy path
  - operational warning path
  - structural mismatch path

## What Was Verified

| Scenario | Area | Evidence | Result |
|---|---|---|---|
| healthy path | sales + receivable + cash + session + journal | `test_operational_reconciliation_exposes_healthy_operational_status` | `Verified` |
| warning path | non-zero shift cash difference | `test_operational_reconciliation_treats_nonzero_cash_difference_as_warning` | `Verified` |
| mismatch path | cash account snapshot diverges from cash entries | `test_operational_reconciliation_flags_cash_account_structural_mismatch` | `Verified` |

## Why This Matters

This closes the main trust gap in reconciliation:

- the endpoint no longer has coverage only for “all good”;
- it now proves that the surface distinguishes:
  - **warning**: operational cashier discrepancy
  - **mismatch**: structural accounting inconsistency

That distinction is important for owner audit UX, because cash shortage/excess in a shift is not the same class of problem as broken accounting state.
