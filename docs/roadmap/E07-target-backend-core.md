# E07 Target Backend Core

> Phase B design document.
>
> Source documents:
>
> - [`E07-workspace-api-contract.md`](./E07-workspace-api-contract.md)
> - [`E07-dependency-map.md`](./E07-dependency-map.md)
> - [`../domain/procurement.md`](../domain/procurement.md)
> - [`../domain/partnerships.md`](../domain/partnerships.md)
> - [`../domain/finance.md`](../domain/finance.md)

## Decision

Use **replace-in-place inside existing domain apps**, not a temporary new Django
app.

Reason:

- current apps already own the correct bounded contexts: procurement/investment
  in `partnerships`, money/journal in `finance`, supplier debt in `suppliers`,
  lots/stock in `inventory`, FIFO in `sales`;
- a temporary parallel app would create two competing sources of truth;
- local data and old migrations are disposable, so clean migration reset is
  acceptable after model design is implemented;
- radical reset still applies: old model shapes do not constrain the new target
  design.

## App Ownership

| Domain responsibility | Target app | Notes |
|---|---|---|
| Procurement workspace root, items, expenses, receive batches | `apps.partnerships` for now | keep until a future rename/module split is worth it |
| Investment agreements, commitments, contributions, allocations, partner ledger | `apps.partnerships` | investment layer remains distinct from procurement documents |
| Cash accounts, generic payments, payment allocations, journal entries | `apps.finance` | finance owns money movement and accounting facts |
| Supplier settlement/payable/schedule/payment views | `apps.suppliers` | supplier debt belongs to supplier domain |
| Lots, lot snapshots, stock movements | `apps.inventory` | inventory owns physical/economic lot facts |
| FIFO sale lines and profit accrual from lot snapshots | `apps.sales` | sales must not depend on current agreement state |

## Target Models

### Procurement Workspace Layer

#### `Procurement`

Purpose: purchase/workspace root.

Fields:

- `tenant`
- `status`: `OPEN`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CLOSED`, `CANCELLED`
- `supplier` nullable FK
- `funding_source`: `OWN_FUNDS`, `PARTNERSHIP`
- `investment_agreement` nullable FK
- `notes`
- `opened_at`, `closed_at`
- `client_request_id` nullable unique per tenant

Rules:

- no `MUSHARAKA` as procurement funding source;
- source/funding cannot change after financial facts or receive batches;
- supplier required by settlement policy, not always by procurement itself.

#### `ProcurementItem`

Purpose: planned purchase line.

Fields:

- `procurement`
- `product_variant`
- `quantity`
- `unit_purchase_price`
- `currency`
- `fx_rate`
- `lifecycle_state`: `DRAFT`, `READY_FOR_RECEIVE`, `RECEIVED`, `CANCELLED`

Rules:

- payment state is derived, not authoritative;
- paid/received lines are not silently edited;
- corrections use split/new/cancel/reversal documents.

#### `ProcurementExpense`

Purpose: landed cost component.

Fields:

- `procurement`
- `expense_type`
- `amount`
- `currency`
- `fx_rate`
- `allocation_method`: `BY_VALUE`, `BY_QUANTITY`
- `lifecycle_state`
- `notes`

#### `ProcurementExpenseTarget`

Purpose: explicit scope for partial receive landed cost.

Fields:

- `expense`
- `item`

Rules:

- empty target set means all eligible items;
- partial receive must reject ambiguous expenses touching received and delayed
  items unless targets/splits make scope explicit.

### Supplier Settlement Layer

#### `SupplierSettlement`

Replacement for conceptual `ProcurementTerms`.

Fields:

- `procurement` one-to-one
- `type`: `PREPAID`, `PARTIAL`, `DEFERRED`, `INSTALLMENT`, `CONSIGNMENT`
- `currency_of_obligation`
- `fx_rate_at_obligation`
- `total_amount_due`
- `paid_amount`
- `remaining_amount`
- `deadline_date`
- `consignment_mode`: `FIXED_SUPPLIER_PRICE`, `COMMISSION`, nullable
- `notes`

Rules:

- supplier required for all non-prepaid terms and consignment;
- `PARTNERSHIP` may use only `PREPAID` in MVP;
- after financial/receive facts, changes are amendments, not silent edits.

#### `SupplierSettlementAmendment`

Append-only changes to supplier terms.

#### `SupplierPayable`

Owned by `suppliers`.

Fields:

- `supplier`
- `procurement`
- `settlement`
- `original_amount`
- `paid_amount`
- `remaining_amount`
- `currency`
- `fx_rate`
- `status`
- `due_date`

Rules:

- created from settlement/receive/payment policy;
- paid only through payment allocation;
- remaining amount is derived/controlled by payment postings.

#### `PaymentScheduleRow`

Installment operational schedule.

Actual payment remains a `Payment`.

### Finance Payment Layer

#### `Payment`

Generic append-only money document in `finance`.

Fields:

- `tenant`
- `source_type`: `CASH_ACCOUNT`, `CAPITAL_POOL`, `EXTERNAL_PARTNER`
- `source_id`
- `target_type`: `PROCUREMENT_COST`, `SUPPLIER_PAYABLE`,
  `CAPITAL_CONTRIBUTION`, `DIVIDEND`
- `target_id`
- `amount`
- `currency`
- `fx_rate`
- `status`: `POSTED`, `REVERSED`
- `paid_at`
- `client_request_id`
- `journal_entry`

Rules:

- no physical delete;
- reversal creates linked reversal document;
- every procurement cost payment derives item/expense payment state.

#### `PaymentAllocation`

Optional split allocation when one payment covers multiple targets.

Fields:

- `payment`
- `target_type`
- `target_id`
- `amount`
- `currency`

MVP can start without split payments if each payment targets one document, but
the service boundary should allow allocations.

### Investment Layer

#### `InvestmentAgreement`

Approved agreement between business/operator/investors.

Fields:

- `tenant`
- `status`
- `legal_mode`: `MUDARABA`, `MUSHARAKA`, `HYBRID`, nullable
- `currency`
- `planned_budget`
- `profit_rule`
- `loss_rule`
- `notes`

Rules:

- agreement can fund one or many procurements;
- agreement edits never rewrite existing receive/lot snapshots.

#### `CapitalCommitment`

Planned partner promise.

Fields:

- `agreement`
- `partner`
- `role`
- `planned_amount`
- `planned_capital_share`
- `planned_profit_share`

#### `CapitalContribution`

Actual capital movement into agreement/capital pool.

Fields:

- `agreement`
- `partner`
- `amount`
- `currency`
- `fx_rate`
- `contributed_at`
- `payment` nullable
- `notes`

#### `InvestmentAllocation`

Capital reserved or consumed for procurement/receive batch.

Fields:

- `agreement`
- `procurement`
- `receive_batch` nullable
- `partner`
- `amount`
- `currency`
- `fx_rate`
- `status`: `RESERVED`, `POSTED`, `REVERSED`

Rules:

- procurement-level allocation may reserve capital;
- receive-batch allocation finalizes factual capital snapshot;
- allocation cannot exceed available contribution balance.

#### `PartnerLedgerEntry`

Append-only partner economic ledger.

Event types:

- `CAPITAL_COMMITTED`
- `CAPITAL_IN`
- `CAPITAL_ALLOCATED`
- `CAPITAL_RETURNED`
- `PROFIT_ACCRUED`
- `PROFIT_REVERSED`
- `LOSS_INCURRED`
- `DIVIDEND_PAID`

### Receive / Inventory Layer

#### `ReceiveBatch`

Physical receive fact.

Fields:

- `procurement`
- `warehouse`
- `received_at`
- `status`: `POSTED`, `REVERSED`
- `inventory_total_uzs`
- `journal_entry`

Rules:

- append-only;
- reversal/correction document instead of silent edit;
- creates inventory lots and stock movement.

#### `ReceiveBatchLine`

Snapshot of received item quantity and cost.

Fields:

- `batch`
- `procurement_item`
- `quantity`
- `unit_purchase_price_uzs`
- `allocated_expense_uzs`
- `landed_cost_per_unit_uzs`
- `lot`

#### `ReceiveBatchExpense`

Snapshot of expenses included in this batch.

#### `BatchCapitalSnapshot`

Immutable factual partner shares for the batch.

Fields:

- `batch`
- `currency`
- `required_amount`

#### `BatchCapitalSnapshotPartner`

Fields:

- `snapshot`
- `partner`
- `capital_amount`
- `capital_share`
- `profit_share`

#### `Lot`

Keep existing inventory ownership, but target lot must contain immutable
economic snapshot.

MVP decision:

- keep snapshot as immutable JSON on `Lot` initially;
- do not create a separate `LotSnapshot` table in first backend pass unless
  implementation shows clear need.

## Service Boundaries

### `ProcurementWorkspaceService`

Responsibilities:

- create/open workspace;
- build `ProcurementWorkspacePayload`;
- route action mutations;
- call policy before every mutation;
- return full updated payload after mutation.

### `ProcurementPolicyService`

Responsibilities:

- evaluate funding/settlement/status/facts;
- return visible sections, readiness, allowed actions and blocked reasons;
- backend validators and frontend payload use same policy output.

### `ProcurementDocumentService`

Responsibilities:

- update source;
- update items/expenses;
- split/cancel draft-safe lines;
- calculate landed cost previews;
- enforce locking.

### `SupplierSettlementService`

Responsibilities:

- create/update settlement before facts;
- create amendments after facts;
- create/update supplier payable and schedule according to policy.

### `ProcurementPaymentService`

Responsibilities:

- own-funds procurement cost payments from `CashAccount`;
- supplier payable payments;
- idempotency;
- payment allocations;
- cash entries and journal hooks.

### `InvestmentFundingService`

Responsibilities:

- create/link agreement;
- record capital contribution;
- reserve capital for procurement;
- finalize batch capital allocation;
- partner ledger entries.

### `ReceiveBatchService`

Responsibilities:

- validate receive readiness;
- resolve item/expense scope;
- calculate landed cost;
- finalize capital snapshot for partnership;
- create lots, lot stock and inventory movement;
- create inventory/accounting events.

### `WorkspaceHistoryService`

Responsibilities:

- collect domain events/facts for history section;
- expose payments, amendments, receive batches, journal references and capital
  events in one timeline.

## Action To Service Mapping

| Workspace action | Service |
|---|---|
| `UPDATE_SOURCE` | `ProcurementDocumentService` |
| `UPDATE_ITEMS` | `ProcurementDocumentService` |
| `UPDATE_EXPENSES` | `ProcurementDocumentService` |
| `UPDATE_SETTLEMENT` | `SupplierSettlementService` |
| `CREATE_INVESTMENT_AGREEMENT` | `InvestmentFundingService` |
| `LINK_INVESTMENT_AGREEMENT` | `InvestmentFundingService` |
| `RECORD_CAPITAL_CONTRIBUTION` | `InvestmentFundingService` |
| `ALLOCATE_CAPITAL` | `InvestmentFundingService` |
| `PAY_COSTS` | `ProcurementPaymentService` |
| `PAY_SUPPLIER_PAYABLE` | `ProcurementPaymentService` |
| `GENERATE_INSTALLMENT_SCHEDULE` | `SupplierSettlementService` |
| `RECEIVE_BATCH` | `ReceiveBatchService` |
| `AMEND_SETTLEMENT` | `SupplierSettlementService` |
| `RETURN_CONSIGNMENT` | future `ConsignmentService` |
| `CLOSE_WORKSPACE` | `ProcurementWorkspaceService` |
| `CANCEL_WORKSPACE` | `ProcurementWorkspaceService` |

## Accounting Points

Target services must explicitly choose journal timing:

| Event | Journal expectation |
|---|---|
| own-funds procurement cost payment | cash out; cost/prepaid/payable settlement depending settlement |
| supplier payable creation | liability recognition |
| supplier payable payment | debit payable, credit cash |
| capital contribution | partner capital in |
| capital allocation | partner capital deployed/reserved |
| receive batch | inventory recognition at landed cost |
| sale | revenue, COGS, partner profit accrual |
| sale return/writeoff | reversal/loss allocation |
| dividend payout | partner payout cash movement |

If a service does not create a journal entry, it must document why.

## Implementation Strategy

Recommended order:

1. Define/rename models in existing apps according to this target.
2. Update migrations through clean reset, not historical migration stitching.
3. Implement policy and workspace payload builder first.
4. Implement source/items/settlement mutations.
5. Implement payments and supplier payable.
6. Implement investment contribution/allocation.
7. Implement receive batch and lot snapshot.
8. Reconnect sales/FIFO, reports and investor views to target contracts.
9. Build frontend workspace only after backend payload is stable enough.

## Phase B Open Decisions Resolved

- Backend `OPEN Procurement` should be created early for the new workspace.
- No separate `PurchaseOrder` in MVP; `Procurement` is enough as purchase/workspace root.
- Replace-in-place existing domain apps; do not create temporary parallel app.
- `Payment` should be a finance model, not procurement-local.
- `FundingSource` should be explicit field/policy in MVP, not a separate table.
- `LotSnapshot` can remain immutable JSON on `Lot` in MVP.

## Acceptance Criteria

Phase B design is complete when:

- model ownership is clear;
- service boundaries are clear;
- target model choices resolve the open architecture questions;
- E07 roadmap can move from design into implementation/migration reset.
