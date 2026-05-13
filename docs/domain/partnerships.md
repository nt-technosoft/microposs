# Partnerships — Target Investment Layer

> E07 target document. Previous implementation details remain available in Git history. Current work must follow `docs/roadmap/E07-procurement-workspace.md`.

## Purpose

The partnerships domain manages investment relationships, capital commitments, actual contributions, allocations into procurement batches, profit/loss rules and investor-facing reporting.

It must not be modeled as a procurement type. Procurement consumes investment capital; it does not define the full investment relationship.

## Core Concepts

### InvestmentProfile

Investor identity and eligibility profile.

Future marketplace data may include:

- investor status;
- business relation state;
- risk/visibility permissions;
- rating/limits;
- KYC or certification metadata if needed.

### BusinessInvestorRelation

Relationship between a business and investor.

Can originate from:

- manual owner entry;
- accepted marketplace offer;
- invite flow.

### InvestmentOffer

Future marketplace proposal.

Direction may be:

- business invites investor;
- investor offers capital to business.

An offer does not fund procurement directly. Accepted offer creates an `InvestmentAgreement`.

### InvestmentAgreement

Approved investment contract.

Holds:

- business;
- partners;
- operator;
- planned budget;
- currency;
- profit rule;
- loss rule;
- legal/contract type label if needed;
- status;
- close constraints.

`MUSHARAKA` and `MUDARABA` may exist as contract/legal modes, not as primary procurement UI types.

### CapitalCommitment

Planned capital promise.

Example: investor plans 70%, operator plans 30%.

Commitment is not a cash movement.

### CapitalContribution

Actual capital movement into the investment pool or procurement capital pool.

Example: plan was 70/30, but actual batch funding becomes 68/32 or 72/28.

Contribution is append-only and must carry:

- partner;
- amount;
- currency;
- FX snapshot;
- date;
- source reference.

### InvestmentAllocation

Allocation of available capital to a procurement workspace or a specific receive batch.

This is the bridge from investment layer to inventory/procurement layer.

Target rule: procurement-level allocation may reserve capital, but receive-batch allocation is what creates the immutable factual snapshot used by lots.

### BatchCapitalSnapshot

Immutable capital/profit snapshot attached to a receive batch and copied into created lots.

Different batches of one procurement may have different snapshots.

## Profit Model

Target model keeps the existing essential formula:

```text
investor_profit = gross_profit * capital_share * mudaraba_ratio
operator_profit = gross_profit - sum(investor_profit)
```

The formula is evaluated from `Lot.contract_snapshot`.

This means:

- planned agreement is a plan;
- batch allocation is factual;
- lot snapshot is the source of truth for future sale profit;
- current agreement edits never rewrite existing lots.

## Partnership Procurement Flow

1. Business and investor have or create `InvestmentAgreement`.
2. Agreement defines commitments and profit/loss rules.
3. Participants contribute actual capital.
4. Procurement chooses funding source `PARTNERSHIP`.
5. Procurement links to agreement.
6. Items and expenses are funded through explicit capital allocations.
7. Receive batch finalizes factual capital allocation.
8. Lots receive immutable snapshot.
9. Sales accrue partner profit through FIFO lot slices.

## Partial Receipts

Partial receipts are mandatory.

Example:

- agreement plan: 70/30;
- first batch actual funding: 68/32;
- second batch actual funding: 72/28.

Each batch must create its own snapshot. Sales from lots in batch one use 68/32. Sales from lots in batch two use 72/28.

## Ledger

Partner ledger is append-only.

Events:

| Event | Meaning |
|---|---|
| `CAPITAL_COMMITTED` | planned promise, optional accounting impact |
| `CAPITAL_IN` | actual contribution |
| `CAPITAL_ALLOCATED` | capital used for procurement/batch |
| `CAPITAL_RETURNED` | unused capital returned |
| `PROFIT_ACCRUED` | profit from sale |
| `PROFIT_REVERSED` | sale return reverses profit |
| `LOSS_INCURRED` | loss/writeoff allocated |
| `DIVIDEND_PAID` | payout to partner |

Not every ledger event must be a DB enum immediately, but the domain model must distinguish these facts.

## Closing Rules

An investment agreement cannot close while any active lot tied to its snapshots remains economically active.

Close requires:

- no active inventory tied to agreement;
- pending profits/losses settled or explicitly carried;
- capital returned or settlement documented;
- all payouts recorded as append-only payments.

## Marketplace Compatibility

Marketplace should produce investment agreements, not procurement records.

Flow:

1. Investor sees limited business metrics.
2. Investor sends offer or accepts invitation.
3. Business accepts.
4. Agreement is created.
5. Procurement can use agreement as funding source.

This keeps investor discovery separate from purchase execution.

## MVP Rules

- Partnership funding supports `PREPAID` supplier settlement only.
- Partnership + supplier credit is blocked until a dedicated hybrid model exists.
- `MUSHARAKA` is not a separate procurement card.
- Quick agreement creation from workspace is allowed for manual/offline business workflows.

## Related Domains

- Procurement: consumes investment capital and creates receive batches.
- Inventory: stores lot snapshots.
- Sales: accrues profit from snapshots.
- Finance: records capital movements, payouts and journal entries.
- Reports: exposes investor dashboard and agreement profitability.
