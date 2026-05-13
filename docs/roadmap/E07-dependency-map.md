# E07 Dependency Map

> Controlled radical reset artifact.
>
> Purpose: show what old procurement/intake code currently touches so the new
> target core can replace it without losing business rules.

## Status

Initial map created on 2026-05-13.

This is not a compatibility contract. It is a replacement checklist for the new
procurement/investment/payment architecture.

## Reference-Only Boundary

Old code below may be read for behavior and edge cases, but must not define the
target architecture:

| Area | Reference files |
|---|---|
| Old procurement backend core | `backend/apps/partnerships/models.py`, `services.py`, `views.py`, `serializers.py` |
| Old procurement frontend screens | `frontend/src/modules/intake/views/IntakeCreate.vue`, `IntakeDetail.vue`, `IntakeCreateLegacy.vue` |
| Old create components | `frontend/src/modules/intake/components/create/*` |
| Old frontend procurement API shape | `frontend/src/api/partnerships.ts` |
| Old workspace policy draft | `frontend/src/modules/intake/composables/useProcurementWorkspaceState.ts` |

Reusable foundation is allowed:

- shared/base components;
- auth/session/routing shell;
- currency utilities;
- product/supplier quick actions if they fit the new UX;
- API client infrastructure;
- design tokens and mobile layout primitives.

## Backend Dependency Map

### Partnerships App

Current responsibilities:

- `Procurement`, items, expenses, expense targets;
- `ProcurementTerms` and amendments;
- `ProcurementReceiveBatch`, lines, expenses, capital allocation rows;
- `ProcurementBalance`, contributions, withdrawals, exchanges;
- `InvestmentAgreement`, partners, contributions, withdrawals, allocations;
- procurement-attached `InvestmentContract` / `ContractPartner`;
- `ProcurementPartnerLedger`, ledger entries and dividend payout.

Target replacement:

- split into explicit purchase, funding, settlement, payment, investment and
  receive documents;
- procurement-attached contract becomes agreement/allocation/snapshot logic;
- procurement balance becomes partnership-only capital/allocation layer;
- item/expense payment state becomes `Payment`/allocation-derived state.

### Inventory App

Current touchpoints:

- `Lot.procurement_item`;
- `Lot.contract_snapshot`;
- `Lot.landed_cost_per_unit`;
- `LotStock`;
- stock movement on receive.

Target contract:

- new `ReceiveBatch` creates lots;
- lot snapshots remain immutable;
- sales continue to consume lots through FIFO;
- product must enter stock only through receive batch or initial stock.

### Sales App

Current touchpoints:

- sale lines reference `Lot`;
- profit distribution reads `lot.contract_snapshot`;
- partner ledger entries are created with `procurement_id`;
- sale returns/writeoffs reverse partner profit/loss from snapshot.

Target contract:

- keep `SaleLine.lot`;
- keep FIFO lot-slice behavior;
- replace dependency on old procurement models with stable lot snapshot and
  investment ledger contracts.

### Finance App

Current touchpoints:

- profitability reads procurement items, lots, receive batches and agreement
  procurements;
- journal/cash logic is partially connected to payments;
- reports expose procurement profitability and agreement profitability.

Target contract:

- reports should read explicit documents: `Payment`, `SupplierPayable`,
  `InvestmentAllocation`, `ReceiveBatch`, `LotSnapshot`, `PartnerLedgerEntry`;
- no report should infer financial truth only from old procurement line status.

### Suppliers App

Current touchpoints:

- `SupplierPayable` links to procurement;
- `SupplierPayment` pays supplier obligations;
- payable views select procurement terms and schedules;
- consignment return flow depends on procurement terms/items.

Target contract:

- `SupplierSettlement` owns supplier commercial terms;
- `SupplierPayable` owns debt;
- supplier payment allocates to payable/payment schedule;
- consignment return/conversion must be explicit documents.

### Investors App

Current touchpoints:

- investor procurement views read `ProcurementPartnerLedger`;
- agreement views count/list procurements through `InvestmentAgreement.procurements`;
- investor reports still expose procurement-centric rows.

Target contract:

- investor views should read `InvestmentAgreement`, allocations, lot snapshots,
  partner ledger and payouts;
- procurement remains visible as funded purchase context, not as the investment
  contract itself.

### Risk / Writeoff

Current touchpoints:

- writeoff/loss distribution reads `Lot.contract_snapshot`;
- writes partner ledger entries by procurement id when possible.

Target contract:

- keep loss distribution from immutable lot snapshot;
- journal/ledger effects should reference stable lot/investment allocation
  source, not old procurement-attached contract.

### Catalog / Product Supplier Links

Current touchpoints:

- product-supplier link stats are updated from procurement receipts;
- last received date and total procurements count depend on procurement flow.

Target contract:

- receive batch should update supplier/product purchase history.

## Backend API Map

Current public procurement API lives mostly under:

```text
/api/v1/partnerships/procurements/
```

Important current actions:

- list/detail/create/update procurement;
- receive procurement;
- receive plan;
- split item;
- pay items;
- pay expenses;
- contributions/withdrawals/balance exchanges;
- expense targets;
- terms amendments;
- consignment return;
- procurement ledger.

Target API direction:

- introduce a workspace-oriented API contract;
- expose target documents and allowed actions from policy;
- do not preserve old action names if they encode wrong architecture;
- keep compatibility endpoints only temporarily if needed.

## Frontend Dependency Map

### Routes

Current routes:

- `/procurements` → list;
- `/procurements/create` → old `IntakeCreate.vue`;
- `/procurements/:id/edit` → old `IntakeCreate.vue`;
- `/procurements/:id` → old `IntakeDetail.vue`;
- `/procurements/:id/consignment-return`;
- agreement routes under `/procurements/agreements`;
- investor procurement routes under `/investor/procurements`;
- report procurement routes under `/reports/procurements/:id`.

Target route direction:

- `/procurements/new` or `/procurements/create` should open new workspace;
- `/procurements/:id` and edit route should use the same workspace;
- old create/detail routes remain reference until switch-over.

### Old Screens

| Screen | Current role | Target decision |
|---|---|---|
| `IntakeCreate.vue` | wizard for create/edit | reference only |
| `IntakeDetail.vue` | old operational detail/workbench | reference only |
| `IntakeCreateLegacy.vue` | older create flow | reference only |
| `AgreementCreate/List/Detail.vue` | investment agreement UI | can inform new investment section |
| `ConsignmentReturnCreate.vue` | consignment operation | reference until explicit consignment documents are designed |

### Old Components/Composables

Potentially reusable only if they fit target UX:

- quick product/supplier sheets;
- variant picker;
- currency helpers;
- item/expense row components;
- terms history display.

Reference-only unless redesigned:

- old wizard progress;
- old type selector;
- old partnership section;
- old payment terms section;
- old `useIntakeSubmission`;
- old `useIntakeDraftSetup`;
- old scattered detail action sheets.

### Frontend API Client

Current `frontend/src/api/partnerships.ts` mixes:

- procurement workspace data;
- investment agreement data;
- capital/balance actions;
- payment actions;
- receive actions;
- terms actions.

Target direction:

- create workspace API client around target documents/actions;
- keep old client only while old screens exist;
- policy/state should come from target workspace payload, not inferred only in UI.

## Replacement Risks

- Losing partial receive with different capital snapshots.
- Accidentally making own-funds flow depend on procurement balance.
- Keeping payment truth inside item/expense status.
- Breaking `SaleLine.lot` FIFO behavior.
- Breaking investor profit from immutable lot snapshot.
- Creating supplier payable too early/late without explicit accounting point.
- Updating Excel replay before target core behavior is stable.

## Next Artifact

After this map, define the target `ProcurementWorkspace` API contract:

- workspace detail payload;
- allowed actions;
- readiness/state keys;
- document sections;
- mutation endpoints/events;
- compatibility cutoff plan.

