# Procurement — Target Domain Model

> E07 target document. Previous implementation details remain available in Git history. Current work must follow `docs/roadmap/E07-procurement-workspace.md`.

## Purpose

Procurement is the user-facing workspace for bringing goods into the business. It coordinates product lines, landed costs, supplier settlement, funding source, payments, physical receive batches, lot creation and audit history.

Procurement is not itself an investment agreement, a supplier debt, a cash payment or a warehouse receive document. Those are separate documents coordinated inside one workspace.

## Core Principle

Every procurement answers three independent questions:

| Question | Domain Document | Examples |
|---|---|---|
| What are we buying? | `Procurement` + items + expenses | carpets, qty, unit price, logistics |
| Whose money is used? | `FundingSource` / investment layer | own funds, partnership capital |
| How do we settle with supplier? | `SupplierSettlement` | prepaid, deferred, installment, consignment |

The UI may show one flow, but backend must preserve these boundaries.

## Workspace Sections

| Section | Responsibility |
|---|---|
| Overview | status, readiness, next action, key totals |
| Source | supplier, funding source, investment agreement if needed |
| Items & Landed Cost | products, quantities, prices, expenses, expense targets, landed cost preview |
| Settlement | supplier terms, payable preview, schedule, consignment mode, supplier payments |
| Capital | partnership commitments, contributions, available capital, allocations |
| Receive | warehouse, receive plan, partial receive, batch capital allocation |
| History | payments, amendments, capital movements, receive batches, journal refs |

## Target Documents

### Procurement

The purchase workspace root.

Holds:

- tenant;
- status;
- supplier link if relevant;
- business notes/reference;
- item lines;
- landed expenses;
- funding source;
- settlement reference;
- receive batches.

It must not silently mutate financial facts after payment or receive.

### ProcurementItem

Planned item line.

Key fields:

- product variant;
- quantity;
- unit purchase price;
- operation currency;
- FX snapshot;
- lifecycle state: draft / ready for receive / received / cancelled.

Payment state must be derived from `Payment` allocations or funding documents, not hidden inside a line status. After a line is financially or physically affected, correction must be explicit: split, new line, cancellation/reversal where allowed.

### ProcurementExpense

Landed cost component.

Examples:

- logistics;
- customs;
- fee;
- other.

Expenses live with items, not with supplier terms. They affect `landed_cost_per_unit` and must support target assignment for partial receipt.

### SupplierSettlement

Supplier-side commercial terms.

Allowed terms:

- `PREPAID`;
- `PARTIAL`;
- `DEFERRED`;
- `INSTALLMENT`;
- `CONSIGNMENT`.

If settlement creates future obligation, supplier is required and `SupplierPayable` is created at the proper accounting point.

### FundingSource

Determines where payment money comes from.

MVP options:

- `OWN_FUNDS`;
- `PARTNERSHIP`.

`MUSHARAKA` is not a primary procurement type in UI. If needed, it is a legal/contract label inside investment agreement.

### Payment

Append-only money movement.

For own funds, procurement payment uses business `CashAccount`.

For partnership, procurement item/expense payment uses partnership capital pool and explicit `InvestmentAllocation`.

Payment must store:

- source account/pool;
- recipient or target document;
- amount;
- operation currency;
- FX snapshot;
- date;
- idempotency key;
- journal reference.

### ReceiveBatch

Physical warehouse receive document.

One procurement may have multiple receive batches. Each batch can receive a subset of paid/ready items.

Batch records:

- warehouse;
- received item lines;
- included expenses;
- landed cost result;
- inventory total;
- capital allocation snapshot for partnership funding.

### LotSnapshot / Lot

Immutable inventory/profit snapshot created from a receive batch and attached to the lot.

For partnership-funded goods, each lot stores the batch's capital/profit snapshot. FIFO sales later use that snapshot, not current agreement values.

## Funding × Settlement Rules

| Funding | Settlement | MVP Rule |
|---|---|---|
| Own funds | Prepaid | allowed; supplier optional |
| Own funds | Partial | allowed; supplier required |
| Own funds | Deferred | allowed; supplier required |
| Own funds | Installment | allowed; supplier required and schedule required |
| Own funds | Consignment | allowed; supplier required |
| Partnership | Prepaid | allowed; investment agreement required |
| Partnership | Partial | blocked in MVP |
| Partnership | Deferred | blocked in MVP |
| Partnership | Installment | blocked in MVP |
| Partnership | Consignment | blocked in MVP |

Hybrid partnership + supplier credit requires a separate future model. It must not emerge from accidental selector combinations.

## Own Funds Flow

### Prepaid

1. Create procurement.
2. Add items and landed expenses.
3. Select business cash/bank account.
4. Pay items/expenses directly from `CashAccount`.
5. Receive goods.
6. Create lots and inventory journal.

No procurement capital balance is required.

### Deferred / Installment / Partial

1. Supplier is required.
2. Settlement terms are recorded.
3. Receive batch creates inventory and payable as needed.
4. Payments reduce `SupplierPayable`.
5. Installment rows track schedule state.

## Partnership Flow

1. Select or create `InvestmentAgreement`.
2. Record planned commitments.
3. Record actual contributions.
4. Pay items/expenses from partnership capital pool.
5. Receive batch.
6. Resolve actual batch capital allocation.
7. Create lots with immutable snapshot.

Partial receipts are first-class: one procurement may create batches with different factual capital shares.

## Partial Receive

Partial receive is required for real workflows.

Rules:

- only eligible lines may be received;
- expenses touching received and delayed items must be targeted or split;
- each receive batch gets its own cost and capital snapshot;
- received lines become immutable except through explicit correction documents.

## Amendments After Facts

Procurement amendments are append-only corrections. They change the current
procurement document, but they do not rewrite posted money movements, receive
batches or lots.

Production rules:

- paid but unreceived items/expenses may be amended;
- hard removal/cancellation is allowed only for `DRAFT` lines without payment or
  receive facts;
- received quantities, receive batches and lot snapshots are immutable;
- if an amendment increases obligation after payment/capital allocation,
  `payment_status` must show an underpaid delta and the user must create an
  explicit top-up/allocation;
- if an amendment decreases obligation after payment/capital allocation,
  `payment_status` must show `overpaid`; the excess is closed only by explicit
  `RESOLVE_OVERPAYMENT`: own-funds procurement records a supplier refund into a
  selected cash account, partnership procurement returns the excess from the
  procurement back to the agreement capital pool;
- partially allocated expenses may be increased for future receive batches, but
  cannot be reduced below the amount already allocated into received batches.

## Consignment

Consignment has two commercial modes:

- `FIXED_SUPPLIER_PRICE`: supplier price is fixed, business margin is sale price minus supplier price;
- `COMMISSION`: supplier remains economic owner, business earns commission/percentage.

Consignment must support:

- return to supplier;
- supplier-loss disposal;
- business-loss disposal;
- conversion to owned inventory.

## Readiness Checklist

Workspace readiness is policy-driven:

| Key | Meaning |
|---|---|
| `source_ready` | supplier/funding source valid |
| `items_ready` | item lines valid |
| `expenses_ready` | expenses valid or absent |
| `settlement_ready` | supplier terms valid |
| `capital_ready` | partnership capital valid if required |
| `receive_ready` | goods can be received |

## Domain Invariants

- Products enter inventory only through procurement receive batches or initial stock.
- Payments are append-only financial facts.
- Receive batches are append-only warehouse facts.
- Lot snapshots are immutable.
- Supplier settlement and funding source are different axes.
- Landed expenses belong with item cost, not with supplier payment terms.
- All significant operations publish `OutboxEvent`.

## Related Domains

- Inventory: lots, stock, FIFO.
- Partnerships: investment agreement, capital contribution, batch allocation.
- Suppliers: settlement, payable, payment schedule.
- Finance: cash accounts, cash entries, journal entries.
- Sales: FIFO sale lines and profit distribution from lot snapshots.
