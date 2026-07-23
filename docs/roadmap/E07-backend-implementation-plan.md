# E07 Backend Implementation Plan

> Phase B implementation plan and migration/reset boundary.
>
> This document turns [`E07-target-backend-core.md`](./E07-target-backend-core.md)
> into a concrete coding sequence.

## Strategy

Implement the target backend core **replace-in-place** inside existing apps.

Do not try to preserve old migration history. After model changes are complete
enough for the first backend pass, regenerate clean initial migrations and reset
local dev DB again.

## Migration / Reset Boundary

Allowed:

- delete/regenerate local app migrations after model rewrite;
- drop/recreate local dev DB after explicit user confirmation if needed;
- rebuild test data later through domain services / Excel workflow.

Not allowed:

- production/stage destructive reset;
- historical migration stitching for old experimental procurement drafts;
- frontend switch-over before backend payload/actions are stable.

Before destructive reset:

- ensure latest dump exists in `backups/`;
- run `manage.py makemigrations --check --dry-run` before and after model work;
- run backend tests after migration reset.

## Implementation Slices

### Slice 1 — Model Core

Files:

- `backend/apps/partnerships/models.py`
- `backend/apps/finance/models.py`
- `backend/apps/suppliers/models.py`
- `backend/apps/inventory/models.py`

Work:

- replace `Procurement.procurement_type` with target `funding_source`;
- remove `MUSHARAKA` / `DISTRIBUTOR` as procurement funding choices;
- rename conceptual line status to lifecycle state;
- introduce generic `finance.Payment` and optional `PaymentAllocation`;
- align supplier payable/schedule with `SupplierSettlement`;
- keep lot snapshot as immutable JSON on `Lot`;
- keep receive batch append-only models, rename/align fields where needed.

Acceptance:

- models express target documents;
- no own-funds dependency on `ProcurementBalance`;
- old procurement-attached `InvestmentContract` is removed or clearly bridge-only.

### Slice 2 — Policy And Workspace Payload

Files:

- `backend/apps/partnerships/policies.py`
- `backend/apps/partnerships/workspace.py` or `services/workspace.py`
- `backend/apps/partnerships/serializers.py`
- `backend/apps/partnerships/views.py`
- `backend/apps/partnerships/urls.py`

Work:

- implement backend policy from `E07-policy-matrix.md`;
- implement `ProcurementWorkspacePayload` builder;
- expose target route:
  `GET/POST /api/v1/procurement-workspaces/`;
- return sections, readiness, allowed actions and blocked reasons from backend.

Acceptance:

- frontend can fetch a workspace payload without old `IntakeDetail` assumptions;
- backend rejects invalid funding/settlement combinations.

### Slice 3 — Source / Items / Settlement Actions

Actions:

- `UPDATE_SOURCE`
- `UPDATE_ITEMS`
- `UPDATE_EXPENSES`
- `UPDATE_SETTLEMENT`
- `AMEND_SETTLEMENT`
- `GENERATE_INSTALLMENT_SCHEDULE`

Work:

- create early `OPEN Procurement`;
- support draft-safe item/expense edits;
- enforce supplier requirements;
- create supplier settlement;
- create amendments after financial/receive facts.

Acceptance:

- own funds and partnership source rules are enforced;
- supplier settlement no longer behaves like procurement type;
- item/expense payment state is derived, not authoritative.

### Slice 4 — Payments / Payables

Actions:

- `PAY_COSTS`
- `PAY_SUPPLIER_PAYABLE`

Files:

- `backend/apps/finance/services.py`
- `backend/apps/suppliers/services.py`
- `backend/apps/partnerships/services.py`

Work:

- own-funds procurement cost payments from `CashAccount`;
- partnership cost payments through investment allocation/capital pool;
- supplier payable creation/payment through generic `Payment`;
- idempotency via `client_request_id`;
- journal hooks for each money operation.

Acceptance:

- own funds prepaid works without procurement balance;
- partial/deferred/installment creates payable path;
- partnership + supplier credit rejected.

### Slice 5 — Investment Funding

Actions:

- `CREATE_INVESTMENT_AGREEMENT`
- `LINK_INVESTMENT_AGREEMENT`
- `RECORD_CAPITAL_CONTRIBUTION`
- `ALLOCATE_CAPITAL`

Work:

- align agreement/commitment/contribution/allocation models;
- support capital availability by partner;
- reserve capital at procurement level;
- finalize allocation at receive-batch level;
- write partner ledger entries.

Acceptance:

- 68/32 and 72/28 batch scenarios remain possible;
- agreement edits never rewrite existing batch/lot snapshots.

### Slice 6 — Receive Batch / Lot Snapshot

Action:

- `RECEIVE_BATCH`

Work:

- validate receive readiness;
- resolve partial receive item/expense scope;
- calculate landed cost;
- create receive batch, lines, included expenses;
- create batch capital snapshot for partnership;
- create lots and lot stocks;
- create inventory/accounting events.

Acceptance:

- products enter inventory only through receive batch;
- lots have immutable landed cost and contract snapshot;
- sales/FIFO can consume lots without current agreement state.

### Slice 7 — Integration Rewire

Areas:

- sales profit accrual;
- risk/writeoff;
- finance reports;
- investor views;
- supplier payable views;
- catalog product-supplier history.

Work:

- replace old procurement assumptions with target documents;
- reports read payments/payables/allocations/receive batches/lot snapshots;
- investor views read agreement/allocation/ledger, not procurement-as-contract.

### Slice 8 — Tests And Reset

Required test groups:

- policy matrix tests;
- workspace payload tests;
- own funds prepaid from `CashAccount`;
- own funds partial/deferred/installment payable;
- consignment fixed price and commission smoke;
- partnership prepaid with capital contribution/allocation;
- partnership + supplier credit rejected;
- partial receive with 68/32 and 72/28 snapshots;
- FIFO sale profit from lot snapshot;
- payable payment journal/cash effect.

Commands:

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python -m pytest apps/core/tests/ -q
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python manage.py check
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python manage.py makemigrations --check --dry-run
```

## First Coding Step

Start with Slice 1 model core.

Recommended first file order:

1. `backend/apps/finance/models.py` — add generic `Payment` / `PaymentAllocation`.
2. `backend/apps/partnerships/models.py` — align procurement, settlement,
   investment allocation and receive batch names/states.
3. `backend/apps/suppliers/models.py` — point payable/schedule at target
   settlement/payment concepts.
4. `backend/apps/inventory/models.py` — keep lot snapshot immutable and remove
   target reliance on legacy receipt where possible.

Do not start frontend implementation until Slice 2 workspace payload exists.

## Acceptance Criteria For B3

- coding slices are ordered;
- migration/reset boundary is explicit;
- first backend coding step is clear;
- roadmap can proceed to `B4 Implement target backend core`.

