# E07 Policy Matrix

> Target E07 policy artifact.
>
> This matrix drives backend validation and frontend workspace state for the new
> controlled radical reset architecture. If implementation needs a temporary
> compatibility path, it must not weaken this matrix.

## Funding × Settlement

| Funding | Settlement | Allowed | Required | Payment Source | Notes |
|---|---|---:|---|---|---|
| `OWN_FUNDS` | `PREPAID` | yes | items | `CashAccount` | supplier optional |
| `OWN_FUNDS` | `PARTIAL` | yes | supplier, paid amount, payable remainder | `CashAccount` | creates payment + payable |
| `OWN_FUNDS` | `DEFERRED` | yes | supplier, deadline | payable later via `CashAccount` | creates payable |
| `OWN_FUNDS` | `INSTALLMENT` | yes | supplier, schedule | payable later via `CashAccount` | generator + manual edit |
| `OWN_FUNDS` | `CONSIGNMENT` | yes | supplier, consignment mode | depends on mode | fixed price or commission |
| `PARTNERSHIP` | `PREPAID` | yes | investment agreement, capital, items | capital pool | MVP partnership path |
| `PARTNERSHIP` | `PARTIAL` | no | — | — | future hybrid model only |
| `PARTNERSHIP` | `DEFERRED` | no | — | — | future hybrid model only |
| `PARTNERSHIP` | `INSTALLMENT` | no | — | — | future hybrid model only |
| `PARTNERSHIP` | `CONSIGNMENT` | no | — | — | future hybrid model only |

## Status × Action

| Status | Edit source | Edit items | Pay | Receive | Amend terms | View history |
|---|---:|---:|---:|---:|---:|---:|
| `DRAFT/OPEN` no financial facts | yes | yes | yes | if ready | direct edit | yes |
| `OPEN` with payments/capital | limited | draft only | yes | if ready | direct edit if no receive | yes |
| `PARTIALLY_RECEIVED` | no | draft/new only | yes | yes | amendment | yes |
| `RECEIVED` | no | no | payable payments only | no | amendment | yes |
| `CLOSED` | no | no | no except settlement flows | no | no | yes |
| `CANCELLED` | no | no | no | no | no | yes |

## Section Visibility

| Section | Own Funds | Partnership |
|---|---:|---:|
| Overview | yes | yes |
| Source | yes | yes |
| Items & Landed Cost | yes | yes |
| Settlement | yes | only `PREPAID` in MVP |
| Capital | hidden | yes |
| Receive | yes | yes |
| History | yes | yes |

## Readiness Keys

| Key | Required For | Rule |
|---|---|---|
| `source_ready` | any payment/receive | funding selected; supplier present when required |
| `items_ready` | payment/receive | at least one valid item |
| `expenses_ready` | receive | expenses valid or absent; partial receive targets valid |
| `settlement_ready` | receive | terms valid for funding policy |
| `capital_ready` | partnership payment/receive | agreement and sufficient capital/allocation |
| `payment_ready` | receive | required item/expense costs paid or payable path valid |
| `receive_ready` | receive | warehouse selected, cost preview valid, policy allows action |

## Backend Requirements

- Backend must reject blocked combinations even if frontend hides them.
- Backend and frontend must use equivalent policy rules.
- Policy changes must update this matrix and E07 checklist.
