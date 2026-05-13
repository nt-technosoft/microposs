# E07 Controlled Radical Reset Plan

> Source of truth for the E07 implementation strategy after the 2026-05-13 decision.

## Decision

E07 is no longer an incremental adaptation of the old intake/procurement flow.

We use a **controlled radical reset**:

- target architecture is designed as if procurement/investment/payment were built from scratch;
- old backend services, models and frontend screens are reference material only;
- old code may stay temporarily to preserve business rules and edge cases;
- new architecture must not be bent to fit old compromises;
- legacy tests may be red until they are replaced by target scenario tests;
- do not add model/query compatibility shims solely to make old tests pass;
- switch-over happens only after dependency map, target contracts and tests are clear.

## Why Controlled, Not Chaotic

We are not protecting old local data or old migrations.

We are protecting business meaning:

- partial receive snapshots;
- FIFO lot-based profit distribution;
- partner capital/profit logic;
- supplier obligations and payment schedules;
- cash/accounting journal effects;
- inventory valuation;
- sales/reporting dependencies;
- Excel-like real scenario replay.

The reset is radical in design, controlled in execution.

## Dependency Map

### Procurement Currently Feeds

| Downstream area | What it consumes | Reset implication |
|---|---|---|
| Inventory | received lines, landed cost, warehouse, lot creation | new `ReceiveBatch` and immutable lot snapshot must be the new contract |
| Sales / FIFO | lot quantity, landed cost, partner snapshot | sale lines must continue to reference lots, not product variants |
| Partnerships | procurement contract, contributions, partner ledgers | replace procurement-as-contract with `InvestmentAgreement` + allocation/snapshot |
| Finance | cash entries, journal entries, inventory value, payables | payments/payables must become explicit documents |
| Suppliers | supplier link, settlement terms, payable state | `SupplierSettlement` and `SupplierPayable` must own supplier debt |
| Reports | inventory value, partner profit, cash/payables | reporting reads new documents, not old procurement status shortcuts |
| Excel workflow | real-world staged scenario | replay must be rebuilt after new core exists |
| Frontend intake | create/detail screens and balance actions | replace with new `ProcurementWorkspace`, old screens are reference only |

Detailed map: [`E07-dependency-map.md`](./E07-dependency-map.md).

### Old Responsibilities To Preserve

| Old responsibility | New owner |
|---|---|
| Procurement type decides funding/payment behavior | `FundingSource` + policy matrix |
| Procurement terms create supplier debt | `SupplierSettlement` + `SupplierPayable` |
| Item/expense payment status | `Payment` allocations + payable/capital state |
| Procurement balance for all flows | partnership-only capital pool/allocation |
| Partnership contract inside procurement | `InvestmentAgreement` + commitments |
| Partial receive with factual shares | `ReceiveBatch` + `BatchCapitalSnapshot` |
| Lot participant shares | immutable `LotSnapshot` copied from receive batch |
| UI create vs detail split | single `ProcurementWorkspace` |

## Target Backend Core

### Core Documents

- `Procurement`: purchase/workspace root, product lines, expenses, status.
- `FundingSource`: own funds or partnership capital.
- `SupplierSettlement`: supplier commercial terms.
- `SupplierPayable`: supplier liability and remaining balance.
- `Payment`: append-only money movement with allocations and idempotency.
- `InvestmentAgreement`: partner contract/plan outside procurement.
- `CapitalCommitment`: planned capital.
- `CapitalContribution`: actual capital movement.
- `InvestmentAllocation`: capital allocated to procurement/batch.
- `ReceiveBatch`: physical warehouse receipt.
- `BatchCapitalSnapshot`: factual shares for that batch.
- `LotSnapshot`: immutable inventory/profit source for FIFO.
- `JournalEntry`: accounting result of domain events.

### Policy Rules

- `OWN_FUNDS` may use `PREPAID`, `PARTIAL`, `DEFERRED`, `INSTALLMENT`, `CONSIGNMENT`.
- `PARTNERSHIP` MVP may use only `PREPAID`.
- `PARTNERSHIP + supplier credit` is blocked until a separate hybrid model exists.
- `MUSHARAKA` is not a procurement UI type; it may be a legal label on agreement.
- Payments and receipts are append-only facts; corrections are separate documents/events.

## Target Frontend Core

Build new feature-domain UI instead of extending old `IntakeCreate.vue` / `IntakeDetail.vue`.

Canonical Phase D flow is defined in
[`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md). It is
the source of truth for user-facing order.

Target route should use one workspace for:

- new procurement;
- existing `OPEN` procurement;
- `PARTIALLY_RECEIVED`;
- completed/read-only states.

Workspace sections:

- purchase intent: goods and landed costs;
- supplier and settlement terms;
- money source: own funds or partnership;
- payment / payable / capital movement;
- goods receipt;
- history/audit.

The UI must read one policy/state layer instead of scattering `v-if` logic.
Backend transport sections must not dictate the visible order when they conflict
with the canonical flow.

## Implementation Order

### Phase A — Freeze And Map

- [x] A1. Mark old intake/procurement UI and old procurement services as reference, not target.
- [x] A2. Complete backend dependency map at model/service/API level.
- [x] A3. Complete frontend dependency map at route/component/API-client level.
- [x] A4. Define target API contract for `ProcurementWorkspace`.

### Phase B — Target Backend Model

- [x] B1. Write new model/service design for procurement core.
- [x] B2. Decide whether to replace existing app models in place or create a new temporary app/module.
- [x] B3. Prepare backend implementation plan and migration/reset boundary.
- [ ] B4. Implement new core services behind clean service APIs.

### Phase C — Integration Contracts

- [ ] C1. Connect receive batches to inventory lots.
- [ ] C2. Connect lot snapshots to sales/FIFO profit split.
- [ ] C3. Connect payments/payables/capital to finance journals.
- [ ] C4. Connect supplier payables to supplier module.
- [ ] C5. Connect partner ledger/reporting to investment layer.

### Phase D — New Frontend Workspace

- [x] D0. Restore canonical workspace flow.
- [ ] D1. Rebuild new `ProcurementWorkspace` route/page around canonical flow.
- [ ] D2. Build policy-driven sections without making API order the UX order.
- [ ] D3. Keep old intake screens as reference until switch-over.
- [ ] D4. Switch procurement routes to the new workspace.

### Phase E — Verification

- [ ] E1. Backend scenario tests for all policy combinations.
- [ ] E2. Partial receive tests with different batch snapshots.
- [ ] E3. FIFO sale/profit split tests from lot snapshots.
- [ ] E4. Supplier payable/payment tests.
- [ ] E5. Frontend smoke tests for new workspace.
- [ ] E6. Rebuild Excel workflow only after core behavior is stable.

## Non-Goals During Reset

- Do not migrate old experimental procurement data unless explicitly needed.
- Do not perfect old intake screens.
- Do not force new target architecture to match old API shapes.
- Do not preserve old field aliases such as `procurement_type`/line `status` as hidden model behavior.
- Do not optimize for green legacy tests while the target architecture is mid-reset.
- Do not expand partnership + supplier credit before MVP policy is stable.
