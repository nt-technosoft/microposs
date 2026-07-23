# E07 ProcurementWorkspace API Contract

> Target contract between the new E07 backend core and the new frontend
> `ProcurementWorkspace`.
>
> This is not the old `/partnerships/procurements/` API shape. Old endpoints can
> remain temporarily for reference/compatibility, but the new workspace should be
> implemented against this contract.
>
> UX order source of truth:
> [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md).
> The `sections` array in this document is transport/state metadata, not the
> required visual order for Phase D.

## Goals

The workspace API must give frontend one stable source of truth for:

- canonical flow step state;
- visible sections;
- readiness state;
- allowed actions;
- required fields;
- blocked reasons;
- documents and financial facts;
- next recommended action.

Frontend should not reconstruct domain rules from scattered `v-if` conditions.
Backend must validate the same policy before every mutation.

Frontend must not infer the user journey from the raw document grouping order.
The canonical Phase D order is:

```text
goods/expenses -> supplier/settlement -> funding -> payment/obligation -> receipt -> history
```

## Route Direction

Target routes:

```text
GET  /api/v1/procurement-workspaces/
POST /api/v1/procurement-workspaces/
GET  /api/v1/procurement-workspaces/{id}/
POST /api/v1/procurement-workspaces/{id}/actions/{action}/
```

Compatibility endpoints under `/api/v1/partnerships/procurements/` may exist
only during switch-over.

## Workspace Lifecycle

Recommended decision: create backend `OPEN` workspace early.

Reason:

- one UX for new and existing procurement;
- autosave and reload are simple;
- payments, allocations and receive actions always have a document id;
- browser refresh does not lose the draft.

If frontend needs a purely local draft for the first screen, it must be limited
to pre-document data. As soon as the user selects source/items or saves first
field, backend workspace should exist.

## Core Payload Shape

```ts
interface ProcurementWorkspacePayload {
  id: number
  status: WorkspaceStatus
  display: WorkspaceDisplay
  flow: WorkspaceFlow
  policy: WorkspacePolicy
  readiness: WorkspaceReadiness
  sections: WorkspaceSection[]
  documents: WorkspaceDocuments
  summaries: WorkspaceSummaries
  history: WorkspaceHistoryEntry[]
}
```

`flow` is the user-facing journey state. `sections` describes backend-visible
areas and may be used for layout/permissions, but must not override `flow`.

```ts
interface WorkspaceFlow {
  current_step: WorkspaceFlowStepKey
  steps: WorkspaceFlowStep[]
  next_action: WorkspaceActionKey | null
}

type WorkspaceFlowStepKey =
  | 'purchase_intent'
  | 'supplier_settlement'
  | 'funding'
  | 'payment_obligation'
  | 'goods_receipt'
  | 'history'

interface WorkspaceFlowStep {
  key: WorkspaceFlowStepKey
  title: string
  status: 'ready' | 'blocked' | 'complete' | 'locked'
  readiness_keys: Array<keyof WorkspaceReadiness>
  primary_actions: WorkspaceActionKey[]
  blocked_reason: string | null
}
```

## Status

```ts
type WorkspaceStatus =
  | 'OPEN'
  | 'PARTIALLY_RECEIVED'
  | 'RECEIVED'
  | 'CLOSED'
  | 'CANCELLED'
```

`DRAFT` may exist only if backend supports pre-open workspaces. Otherwise use
`OPEN` for editable workspaces.

## Display

```ts
interface WorkspaceDisplay {
  title: string
  subtitle: string | null
  created_at: string
  updated_at: string
  primary_currency: string
  next_action: {
    key: WorkspaceActionKey | null
    label: string
    reason: string | null
  }
}
```

## Policy

```ts
interface WorkspacePolicy {
  funding_source: 'OWN_FUNDS' | 'PARTNERSHIP' | null
  settlement_type: SettlementType | null
  allowed_settlements: SettlementType[]
  visible_sections: WorkspaceSectionKey[]
  locked_sections: Record<WorkspaceSectionKey, string | null>
  allowed_actions: WorkspaceActionKey[]
  blocked_reasons: WorkspaceBlockedReason[]
}
```

```ts
type SettlementType =
  | 'PREPAID'
  | 'PARTIAL'
  | 'DEFERRED'
  | 'INSTALLMENT'
  | 'CONSIGNMENT'

type WorkspaceSectionKey =
  | 'overview'
  | 'source'
  | 'items'
  | 'settlement'
  | 'capital'
  | 'receive'
  | 'history'
```

Policy source of truth: [`E07-policy-matrix.md`](./E07-policy-matrix.md).

## Readiness

```ts
interface WorkspaceReadiness {
  source_ready: ReadinessState
  items_ready: ReadinessState
  expenses_ready: ReadinessState
  settlement_ready: ReadinessState
  capital_ready: ReadinessState
  payment_ready: ReadinessState
  receive_ready: ReadinessState
}

interface ReadinessState {
  ok: boolean
  severity: 'ok' | 'info' | 'warning' | 'blocked'
  message: string | null
  missing: string[]
}
```

Readiness is explanatory. Mutations still require backend validation.

## Documents

```ts
interface WorkspaceDocuments {
  procurement: ProcurementDocument
  source: SourceDocument
  items: ProcurementItemDocument[]
  expenses: ProcurementExpenseDocument[]
  settlement: SupplierSettlementDocument | null
  payables: SupplierPayableDocument[]
  payments: PaymentDocument[]
  investment: InvestmentWorkspaceDocument | null
  receive_batches: ReceiveBatchDocument[]
  lots_preview: LotSnapshotPreview[]
}
```

### ProcurementDocument

```ts
interface ProcurementDocument {
  id: number
  status: WorkspaceStatus
  supplier_id: number | null
  supplier_name: string | null
  notes: string
  opened_at: string
  closed_at: string | null
}
```

### SourceDocument

```ts
interface SourceDocument {
  funding_source: 'OWN_FUNDS' | 'PARTNERSHIP' | null
  supplier_required: boolean
  supplier_id: number | null
  investment_agreement_required: boolean
  investment_agreement_id: number | null
}
```

### ProcurementItemDocument

```ts
interface ProcurementItemDocument {
  id: number
  product_variant_id: number
  product_variant_name: string
  quantity: string
  unit_purchase_price: string
  currency: string
  fx_rate: string
  lifecycle_state: 'DRAFT' | 'READY_FOR_RECEIVE' | 'RECEIVED' | 'CANCELLED'
  payment_state: 'UNPAID' | 'PARTIALLY_PAID' | 'PAID' | 'PAYABLE'
  received_quantity: string
  remaining_quantity: string
  locked_reason: string | null
}
```

Payment state is derived from `Payment`, `SupplierPayable` or capital allocation
documents. It must not be the only source of financial truth.

### ProcurementExpenseDocument

```ts
interface ProcurementExpenseDocument {
  id: number
  expense_type: 'CUSTOMS' | 'LOGISTICS' | 'FEE' | 'OTHER'
  amount: string
  currency: string
  fx_rate: string
  allocation_method: 'BY_VALUE' | 'BY_QUANTITY'
  target_item_ids: number[]
  lifecycle_state: 'DRAFT' | 'READY_FOR_RECEIVE' | 'RECEIVED' | 'CANCELLED'
  payment_state: 'UNPAID' | 'PARTIALLY_PAID' | 'PAID' | 'PAYABLE'
  locked_reason: string | null
}
```

### SupplierSettlementDocument

```ts
interface SupplierSettlementDocument {
  id: number
  type: SettlementType
  currency_of_obligation: string
  fx_rate_at_obligation: string
  total_amount_due: string
  paid_amount: string
  remaining_amount: string
  deadline_date: string | null
  consignment_mode: 'FIXED_SUPPLIER_PRICE' | 'COMMISSION' | null
  notes: string
  schedule: PaymentScheduleRow[]
}
```

### PaymentDocument

```ts
interface PaymentDocument {
  id: number
  target_type: 'PROCUREMENT_COST' | 'SUPPLIER_PAYABLE' | 'CAPITAL_CONTRIBUTION' | 'DIVIDEND'
  target_id: number
  source_type: 'CASH_ACCOUNT' | 'CAPITAL_POOL' | 'EXTERNAL_PARTNER'
  source_id: number
  amount: string
  currency: string
  fx_rate: string
  status: 'POSTED' | 'REVERSED'
  paid_at: string
  journal_entry_id: number | null
}
```

### InvestmentWorkspaceDocument

```ts
interface InvestmentWorkspaceDocument {
  agreement_id: number
  agreement_label: string
  legal_mode: 'MUDARABA' | 'MUSHARAKA' | 'HYBRID' | null
  currency: string
  planned_budget: string
  partners: InvestmentPartnerDocument[]
  contributions: CapitalContributionDocument[]
  allocations: InvestmentAllocationDocument[]
  available_by_partner: Record<number, string>
}
```

### ReceiveBatchDocument

```ts
interface ReceiveBatchDocument {
  id: number
  received_at: string
  warehouse_id: number
  warehouse_name: string
  status: 'POSTED' | 'REVERSED'
  inventory_total_uzs: string
  lines: ReceiveBatchLineDocument[]
  expenses: ReceiveBatchExpenseDocument[]
  capital_snapshot: BatchCapitalSnapshotDocument | null
  journal_entry_id: number | null
}
```

### BatchCapitalSnapshotDocument

```ts
interface BatchCapitalSnapshotDocument {
  currency: string
  required_amount: string
  partners: Array<{
    partner_id: number
    partner_name: string
    capital_amount: string
    capital_share: string
    profit_share: string
  }>
}
```

## Sections

```ts
interface WorkspaceSection {
  key: WorkspaceSectionKey
  title: string
  visible: boolean
  locked: boolean
  locked_reason: string | null
  readiness_key: keyof WorkspaceReadiness | null
}
```

Frontend renders sections from this list. It may choose layout, but should not
invent section visibility independently.

## Actions

```ts
type WorkspaceActionKey =
  | 'UPDATE_SOURCE'
  | 'UPDATE_ITEMS'
  | 'UPDATE_EXPENSES'
  | 'UPDATE_SETTLEMENT'
  | 'CREATE_INVESTMENT_AGREEMENT'
  | 'LINK_INVESTMENT_AGREEMENT'
  | 'RECORD_CAPITAL_CONTRIBUTION'
  | 'ALLOCATE_CAPITAL'
  | 'PAY_COSTS'
  | 'PAY_SUPPLIER_PAYABLE'
  | 'GENERATE_INSTALLMENT_SCHEDULE'
  | 'RECEIVE_BATCH'
  | 'AMEND_SETTLEMENT'
  | 'RETURN_CONSIGNMENT'
  | 'CLOSE_WORKSPACE'
  | 'CANCEL_WORKSPACE'
```

Mutation endpoint:

```text
POST /api/v1/procurement-workspaces/{id}/actions/{action}/
```

Each mutation payload must include:

```ts
interface WorkspaceMutationEnvelope<TPayload> {
  client_request_id: string
  payload: TPayload
}
```

Every successful mutation returns the full updated `ProcurementWorkspacePayload`.

## Required Mutations

### Update Source

Sets supplier, funding source and optional agreement link.

Backend must reject:

- changing funding after financial facts;
- partnership without agreement when action requires capital/payment/receive;
- old `MUSHARAKA` as primary funding source in new UI.

### Update Items / Expenses

Adds or changes draft lines.

Backend must reject silent edits after payment/receive. Corrections after facts
must be split/new line/reversal documents.

### Update Settlement

Sets supplier settlement.

Backend must enforce:

- supplier required for `PARTIAL`, `DEFERRED`, `INSTALLMENT`, `CONSIGNMENT`;
- partnership allows only `PREPAID` in MVP;
- installment requires schedule before receive/payment readiness.

### Pay Costs

Pays procurement items/expenses.

For `OWN_FUNDS`, source is `CashAccount`.

For `PARTNERSHIP`, source is capital pool/allocation.

Backend must create explicit payment/cash/capital/journal facts and return
derived payment state.

### Receive Batch

Creates physical receive batch and lots.

Payload must include:

- warehouse;
- item quantities or selected item ids;
- expense scope;
- batch capital allocation when funding is partnership.

Backend must freeze:

- received quantities;
- landed cost;
- capital/profit snapshot;
- lot snapshot;
- journal/inventory facts.

### Pay Supplier Payable

Pays existing payable from `CashAccount`.

Backend must reduce payable through payment allocation and journal/cash facts.

### Amend Settlement

Creates explicit amendment after receive/financial facts.

No silent rewrite of original supplier settlement.

## Events / History

Workspace history should include domain events, not just UI logs:

- workspace opened;
- source changed;
- settlement created/amended;
- item/expense added/split/cancelled;
- payment posted/reversed;
- capital contributed/allocated/returned;
- receive batch posted;
- lot snapshots created;
- supplier payable created/paid;
- journal entry created;
- workspace closed/cancelled.

## Open Decisions For Phase B

- Use replace-in-place models or a temporary new backend module/app.
- Final endpoint namespace: `/api/v1/procurement-workspaces/` vs `/api/v1/procurements/workspaces/`.
- Whether `Payment` is a generic finance model immediately or procurement-local first.
- Whether `FundingSource` is a model/table or explicit fields/policy document in MVP.
- Whether `LotSnapshot` is a separate table or immutable JSON snapshot attached to `Lot`.

## Acceptance Criteria

`A4/R-1.4` is complete when:

- frontend can build new workspace screens from one payload;
- backend Phase B can design models/services against this contract;
- old endpoint shapes are no longer considered target architecture;
- policy/readiness/actions are part of backend response, not frontend guesses.
