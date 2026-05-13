# E07 Phase 2 — Backend Core Rebuild Plan

> **Reference / pre-reset context.**
>
> This document was written during the earlier sequential backend adaptation path.
> After the 2026-05-13 decision, E07 follows **controlled radical reset**.
> Do not execute this file as the active roadmap.
>
> Active entrypoint: [`E07-procurement-workspace.md`](./E07-procurement-workspace.md).
> Active reset plan: [`E07-controlled-radical-reset.md`](./E07-controlled-radical-reset.md).
>
> Use this file only to preserve useful backend insights, required scenarios and
> edge cases while designing the new target backend core.

## Current Status

This plan is not deleted because it contains useful requirements:

- own-funds payment through `CashAccount`;
- supplier settlement/payable expectations;
- partnership capital pool and allocation expectations;
- partial receive and immutable lot snapshot requirements;
- backend policy validation requirements.

But it is **not** the final target model and must not force new code to keep old
API/model shapes.

## Goal

Preserve backend requirements discovered before the controlled reset.

The current active goal is stronger: rebuild procurement/investment/payment core
around target documents without adapting to old `procurement_type`,
`ProcurementBalance` or create/detail compromises.

Phase 2 must produce a backend that can safely support the future unified
workspace:

- own funds purchases paid from `CashAccount`;
- supplier settlement terms and supplier payables;
- partnership purchases funded from investment capital;
- partial receive batches with immutable lot economic snapshots;
- backend policy validation equivalent to the frontend workspace policy.

## Non-Goals

- Do not build the final frontend workspace in Phase 2.
- Do not support partnership + supplier credit hybrid in MVP.
- Do not migrate or reset dev data here; that is Phase 3.
- Do not treat legacy compatibility endpoints as target contracts.
- Do not treat `MUSHARAKA` as a separate primary procurement UI/type.

## Current Backend Reality

The codebase already has useful pieces, but their boundaries are mixed:

- `Procurement.procurement_type` currently carries funding semantics.
- `ProcurementTerms` already models supplier settlement, but is not yet the
  central policy driver.
- `SupplierPayable` and `SupplierPayment` exist and should be reused.
- `ProcurementBalance` exists and should be restricted to partnership flows.
- `InvestmentAgreement`, agreement contributions and allocations exist, but
  still need clearer service boundaries.
- `InvestmentContract` / `ContractPartner` are legacy procurement-attached
  partnership structures and should be bridged or absorbed gradually.
- `ProcurementReceiveBatch*` already captures partial receive and batch capital
  snapshots; this must be preserved and strengthened.

## Target Backend Boundaries

### Procurement

Owns purchase intent, supplier link, status, items, landed cost expenses and
receive batches.

It must not directly mean:

- investment contract;
- supplier debt;
- payment;
- cash movement.

### Funding Policy

Owns the question: whose money funds the purchase.

MVP values:

- `OWN_FUNDS`;
- `PARTNERSHIP`.

Target design should use explicit funding semantics. Existing
`Procurement.procurement_type` may be used only as reference during mapping, not
as a constraint on the new architecture.

### Supplier Settlement

Owns the question: how the supplier is settled.

Use/strengthen `ProcurementTerms` as the current implementation of
`SupplierSettlement`.

Allowed MVP combinations are defined in
`docs/roadmap/E07-policy-matrix.md`.

### Payment

Payments must be explicit financial facts:

- own funds payments use `CashAccount` / `CashEntry`;
- supplier credit payments use `SupplierPayment`;
- partnership item/expense payments use partnership capital pool withdrawals;
- every payment path must be idempotent and journalled where required.

### Investment Layer

Investment agreements, commitments/contributions and allocations must remain
outside the procurement purchase document.

Procurement can link to an agreement and consume allocated capital, but it must
not be the agreement itself.

### Receive Batch

Physical receiving must be append-only.

Each receive batch must freeze:

- received quantities;
- landed cost allocation;
- warehouse;
- inventory lots;
- partnership capital/profit snapshot when funding is partnership.

## Implementation Sequence

### Step 2.1 — Backend Policy Module

Create a single backend policy service for procurement workspace rules.

Expected shape:

- input: procurement/funding/terms/status/facts;
- output: allowed settlements, required sections, allowed actions, blocked
  reasons, readiness keys;
- backend validators use this policy before mutating state.

Initial policy must enforce:

- `OWN_FUNDS` allows `PREPAID`, `PARTIAL`, `DEFERRED`, `INSTALLMENT`,
  `CONSIGNMENT`;
- `PARTNERSHIP` allows only `PREPAID` in MVP;
- `PARTNERSHIP` requires agreement/capital;
- `OWN_FUNDS` must not create/use `ProcurementBalance`;
- `MUSHARAKA` is legacy-compatible but not a new primary flow.

### Step 2.2 — Own Funds Payment Flow

Implement/repair direct payment for own funds:

- pay items/expenses from selected `CashAccount`;
- create append-only cash movement;
- create required journal entry;
- mark paid facts without creating `ProcurementBalance`;
- support idempotency via `client_request_id`;
- reject if procurement is partnership.

### Step 2.3 — Supplier Settlement Flow

Strengthen `ProcurementTerms` and supplier payable behavior:

- supplier is required for credit/consignment terms;
- `PREPAID` should not create payable;
- `PARTIAL` creates payment fact plus remaining payable;
- `DEFERRED` creates payable with deadline;
- `INSTALLMENT` creates payable plus editable/generated schedule;
- `CONSIGNMENT` creates consignment-specific obligation logic.

### Step 2.4 — Partnership Capital Flow

Keep partnership capital pool behavior, but align it with E07:

- agreement contributions are factual capital;
- agreement allocations move available capital into a procurement;
- procurement balance is only valid for partnership;
- batch capital allocation is based on factual available capital;
- per-batch capital/profit shares can differ from planned agreement shares.

### Step 2.5 — Receive Batch and Lot Snapshot

Strengthen receive as the boundary where inventory becomes real:

- receive batch is append-only;
- partial receive supports different batch capital snapshots;
- each lot receives immutable `contract_snapshot`;
- sales/FIFO continue using lot snapshot, not current agreement state;
- corrections must be future explicit documents, not silent edits.

### Step 2.6 — API Compatibility Layer

Keep current endpoints usable while moving internals to policy/service calls.

Only expose new API fields when they are backed by domain services, not by
frontend-only assumptions.

## Required Tests

Backend Phase 2 is not complete until these tests exist or are adapted:

- own funds + prepaid pays from `CashAccount`;
- own funds + partial creates payment + payable;
- own funds + deferred creates payable;
- own funds + installment creates schedule + payable;
- own funds + consignment fixed supplier price;
- own funds + consignment commission;
- partnership + prepaid uses capital pool;
- partnership + partial/deferred/installment/consignment is rejected;
- partial partnership receive can freeze 68/32 then 72/28 snapshots;
- lot snapshot remains immutable after agreement or capital changes;
- supplier payable payment creates correct journal/cash effects.

## Completion Criteria

Phase 2 can be marked complete when:

- policy module exists and is used by mutating procurement services;
- own funds payments no longer depend on procurement balance;
- partnership capital flow still supports batch snapshots;
- invalid MVP hybrid scenarios are backend-rejected;
- receive batch / lot snapshot invariants are covered by tests;
- E07 policy matrix and entity mapping are updated if implementation decisions
  change.
