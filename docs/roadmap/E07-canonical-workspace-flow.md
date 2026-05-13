# E07 Canonical Procurement Workspace Flow

> Source of truth for the E07 user-facing workflow.
>
> This document captures the "design from zero" decision: one procurement
> workspace for the user, backed by separated financial and inventory documents.
> It overrides older frontend ordering from pre-reset documents.

## Decision

The procurement workspace is not a wizard built around historical backend
fields. It is a work surface that guides the operator through the real business
sequence while the system creates strict internal documents.

Canonical user order:

```text
Purchase intent -> Supplier terms -> Funding -> Payment/obligation -> Goods receipt -> History/audit
```

Readable UI blocks:

1. Goods and landed costs.
2. Supplier and settlement terms.
3. Money source.
4. Payment / payable / capital movement.
5. Warehouse receipt.
6. History and follow-up obligations.

This order is canonical for Phase D. Backend payload sections may be grouped
differently for transport, but frontend must not treat transport order as UX
order.

## Core Principle

The workspace answers three independent questions:

| Question | Target owner |
|---|---|
| What are we buying? | `Procurement`, items, expenses, landed cost |
| Whose money funds it? | `FundingSource`, investment/capital layer |
| How do we settle with the supplier? | `SupplierSettlement`, `SupplierPayable`, `Payment` |

These questions must not be collapsed into a single "procurement type".

## User Flow

### 0. Workspace Shell

One screen is used for:

- new procurement;
- existing `OPEN` procurement;
- `PARTIALLY_RECEIVED` procurement;
- completed/read-only procurement.

The difference is allowed actions and locked facts, not a different UI family.

The system may create an early backend `OPEN Procurement` for autosave, but the
first user-facing decision is not funding. The first user-facing decision is the
purchase intent.

### 1. Purchase Intent: Goods And Landed Costs

The operator starts with what the business wants to bring in:

- product variants;
- quantity;
- supplier price;
- currency and FX;
- landed cost expenses;
- expense allocation scope.

Rules:

- items and expenses live together because both form inventory cost;
- expenses are not supplier terms;
- lines are draft until payment/receive facts exist;
- after facts exist, corrections are explicit new/split/cancel/reversal
  documents, not silent rewrites.

### 2. Supplier And Settlement Terms

The operator defines who provides the goods and on what commercial terms:

- supplier;
- `PREPAID`;
- `PARTIAL`;
- `DEFERRED`;
- `INSTALLMENT`;
- `CONSIGNMENT`.

Rules:

- supplier is optional only for simple own-funds prepaid purchases;
- supplier is required for `PARTIAL`, `DEFERRED`, `INSTALLMENT`,
  `CONSIGNMENT`;
- supplier terms create supplier obligations, not investment logic;
- `PARTIAL`, `DEFERRED`, `INSTALLMENT` create or lead to `SupplierPayable`;
- `INSTALLMENT` must have a schedule before receive/payment readiness;
- consignment must explicitly choose fixed supplier price or commission mode
  when that feature is enabled.

### 3. Money Source

The operator defines whose money funds the purchase:

- `OWN_FUNDS`;
- `PARTNERSHIP`.

Rules:

- own funds use business `CashAccount`; they do not use procurement balance;
- partnership uses `InvestmentAgreement`, contributions and capital allocation;
- `MUSHARAKA` is not a procurement UI type; it can be a legal/agreement label;
- partnership and supplier credit are not combined in MVP.

For partnership, the workspace supports two real-world modes:

- choose an existing `InvestmentAgreement`;
- create a quick agreement inside the workspace when the business already has an
  offline/manual agreement and only needs to digitize it.

Marketplace-originated investment flows should create offers/agreements first;
they should not directly create procurement.

### 4. Payment / Obligation / Capital Movement

The workspace then records the financial facts required before goods can be
received.

Own-funds examples:

- prepaid: `Payment` from `CashAccount`;
- partial: `Payment` plus `SupplierPayable` for the remainder;
- deferred: `SupplierPayable`;
- installment: `SupplierPayable` plus schedule;
- consignment: obligation depends on consignment mode.

Partnership example:

- capital is contributed by partners;
- capital is allocated into the procurement or batch;
- supplier payment is funded from capital allocation/pool;
- factual batch allocation may differ from agreement plan.

Payment is always a document/fact. It is not just a line status.

### 5. Goods Receipt

Physical receipt creates inventory facts:

- one procurement may have multiple receive batches;
- each batch has its own received lines and landed cost;
- each partnership batch freezes its own capital/profit snapshot;
- created lots copy that snapshot into immutable `Lot.contract_snapshot`;
- FIFO sales distribute profit from the lot snapshot, not from the current
  agreement.

Required partnership behavior:

- planned agreement can be 70/30;
- first batch can freeze 68/32;
- second batch can freeze 72/28;
- existing lots are never rewritten when agreement/capital changes later.

### 6. History, Audit And Follow-Up

History is not a UI log. It is a domain event timeline:

- workspace opened;
- lines/expenses changed;
- settlement created/amended;
- payment posted;
- payable created/paid;
- capital contributed/allocated/returned;
- receive batch posted;
- lots created;
- journal entry created.

After receive, the workspace remains useful for:

- paying supplier payables;
- viewing batch snapshots;
- reviewing capital facts;
- auditing inventory and journal effects.

## Backend Implications

Backend must preserve domain invariants, not frontend section order.

Required backend capabilities:

- policy engine returns allowed actions, blockers and readiness;
- services create separated append-only documents;
- API contract supports the canonical flow without forcing old endpoint shapes;
- serializers expose enough data for frontend to render the canonical order.

If an API shape makes frontend start with funding as the primary decision, the
API shape is incomplete for Phase D even if backend models are correct.

## Frontend Implications

The Phase D target UI should be rebuilt around the canonical flow.

Do not continue adapting old screens:

- `IntakeCreate.vue`;
- `IntakeDetail.vue`;
- `IntakeCreateLegacy.vue`;
- current technical `ProcurementWorkspace.vue` prototype if its structure fights
  the canonical flow.

Reusable pieces are allowed only when they fit the new order:

- product/variant selectors;
- supplier selectors;
- cash account selectors;
- agreement/partner selectors;
- formatting utilities;
- layout primitives.

## Acceptance Criteria For Phase D

Phase D is complete only when:

- `/procurements/create`, `/procurements/:id`, `/procurements/:id/edit` use one
  canonical workspace;
- the first working block is goods and landed costs, not funding type;
- supplier settlement and funding are visibly separate;
- own funds never asks for procurement balance;
- partnership asks for agreement/capital only in the money-source/capital area;
- deferred/installment paths create payable-oriented UI;
- receive batch UI supports partial receive and batch snapshots;
- completed procurement opens in the same workspace with locked facts and
  follow-up payment/audit actions.

