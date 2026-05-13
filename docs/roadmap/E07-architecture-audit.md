# E07 Architecture Audit Against Canonical Flow

> Working audit after restoring the canonical E07 workspace flow.
>
> Canonical flow source:
> [`E07-canonical-workspace-flow.md`](./E07-canonical-workspace-flow.md).

## Audit Summary

The backend foundation is directionally aligned with the agreed architecture.
The frontend Phase D prototype is not aligned enough to continue as final UI.
The API contract is useful but must be treated as a transport contract, not as
the UX flow source of truth.

## Backend Alignment

### Aligned

- `Procurement` is being used as workspace/purchase root.
- `funding_source` separates own funds from partnership.
- `MUSHARAKA` is no longer a primary procurement UI concept.
- `ProcurementTerms` is conceptually used as supplier settlement.
- `SupplierPayable` exists as supplier debt document.
- Generic `Payment` exists in finance and is linked to cash/journal facts.
- Own-funds payment can come from `CashAccount`.
- Partnership capital is represented through agreement, contribution and
  allocation paths.
- `RECEIVE_BATCH` creates physical receive facts, lots, stock and snapshots.
- Partial receive with different factual batch shares remains part of the
  target design.
- Policy/readiness/actions exist and are backend-controlled.
- Workspace payload now exposes canonical `flow` metadata for Phase D.

### Risks / Gaps

- Policy still exposes technical sections/actions, but canonical `flow` now
  prevents frontend from treating section order as UX order.
- `items_ready` now reflects whether active items exist.
- Partnership readiness currently requires procurement balance too early,
  which may over-block the natural purchase-intent-first flow.
- `SupplierSettlement` is still named/implemented as `ProcurementTerms` in code;
  acceptable short-term, but documentation and serializers must be explicit.
- `PARTIAL` semantics need a stricter document flow: paid part as `Payment`,
  remainder as `SupplierPayable`.
- Consignment is not yet fully modeled with fixed supplier price vs commission.
- API/serializers may need reshape after frontend canonical flow is finalized.

## Frontend Alignment

### Aligned

- Old create/detail routes were moved toward one workspace route.
- The prototype uses the new workspace API instead of old procurement detail.
- Items and expenses are visually grouped together.
- Supplier settlement, capital, payment, receive and history are separate areas.
- Old `IntakeCreate` / `IntakeDetail` are no longer target architecture.
- Create flow now starts with goods instead of funding.
- Supplier/settlement and money source are visually separated.

### Not Aligned

- The prototype still needs a cleaner scenario-guided workflow and should not
  be considered final Phase D.
- Capital/payment/receive are rendered as technical forms, not scenario-guided
  steps.
- Partnership quick agreement creation is first-pass functional UI, not final
  workflow design.
- There is not yet a clear "next required business action" model.
- There is no complete deferred/installment/consignment UX.
- Browser/runtime smoke is not complete because local Vite launch hung in the
  current environment.

## Documentation Audit

### Source Of Truth

- `E07-canonical-workspace-flow.md` — user flow and Phase D source of truth.
- `E07-procurement-workspace.md` — epic entrypoint and progress tracking.
- `E07-controlled-radical-reset.md` — implementation strategy.
- `E07-policy-matrix.md` — funding/settlement rule matrix.
- `E07-target-backend-core.md` — backend model/service design.
- `E07-workspace-api-contract.md` — transport/API contract, subordinate to
  canonical flow for UX ordering.

### Reference Only

- `E07-procurement-workspace-unification.md` — useful context and edge cases,
  but not implementation roadmap.
- `E07-phase2-backend-plan.md` — useful backend insights from earlier path,
  but not active implementation order.
- `E07-phase3-data-strategy.md` — useful later for reset/test data, not current
  frontend flow.

### Risky If Misread

- `E07-workspace-api-contract.md`: section list can be mistaken for UX order.
- `E07-procurement-workspace-unification.md`: contains older ordering/context
  and must not drive new Phase D.
- Current `ProcurementWorkspace.vue`: technical prototype can be mistaken as
  accepted Phase D implementation.

## Corrected Implementation Order

1. Lock canonical flow as Phase D source.
2. Audit backend policy/payload against canonical flow.
3. Adjust API contract to expose flow/navigation metadata if needed.
4. Rebuild frontend workspace around canonical flow, not old wizard and not
   current technical prototype.
5. Add scenario tests after the flow closes end-to-end.

## Recommendation

Keep backend services unless a concrete invariant violation is found. They are
close to the document/event architecture.

Treat the current frontend workspace as disposable prototype. It can be read for
payload/action wiring, but final Phase D should be rebuilt from the canonical
flow.
