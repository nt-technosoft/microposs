# E07 Entity Mapping — Old to Target

> Target E07 mapping artifact.
>
> This is not a migration promise and not a compatibility contract. It maps old
> responsibilities to the new controlled radical reset architecture so business
> meaning is not lost.

## Procurement

| Current | Target | Decision |
|---|---|---|
| `Procurement` | `Procurement` workspace root / purchase document | keep name for now |
| `procurement_type=OWN_FUNDS` | `FundingSource.OWN_FUNDS` | keep concept, move meaning out of "type" UX |
| `procurement_type=PARTNERSHIP` | `FundingSource.PARTNERSHIP` | keep concept |
| `procurement_type=MUSHARAKA` | contract/legal mode | hide from primary procurement UI |
| `ProcurementItem` | `ProcurementItem` | keep, tighten locking/corrections |
| `ProcurementExpense` | landed cost expense | keep, move UI next to items |
| `ProcurementExpenseTarget` | expense target | keep, important for partial receipt |
| `ProcurementReceiveBatch` | `ReceiveBatch` | preserve responsibility; target language is receive batch |
| `ProcurementReceiveBatchCapitalAllocation` | batch capital snapshot rows | keep/strengthen |
| `ProcurementTerms` | `SupplierSettlement` | likely rename conceptually first, code later |
| `ProcurementTermsAmendment` | settlement amendment | keep concept |
| `ProcurementBalance` | partnership capital pool/allocation reference | do not use for own funds; target core may replace with explicit allocation docs |

## Partnerships

| Current | Target | Decision |
|---|---|---|
| `InvestmentAgreement` | investment agreement | keep and expand |
| `AgreementPartner` | partner participation / commitment basis | split conceptually into partner + commitment |
| `AgreementContribution` | `CapitalContribution` | rename conceptually |
| `AgreementAllocation` | `InvestmentAllocation` | keep/rename conceptually |
| `InvestmentContract` on procurement | funding agreement snapshot/config | likely absorb into agreement/allocation model |
| `ContractPartner` | batch/agreement participant split | clarify during backend design |
| `PartnerLedgerEntry` | partner economic ledger | keep and expand event semantics |
| legacy `InvestorContract` | legacy/bridge | avoid new work unless needed for compatibility |

## Suppliers

| Current | Target | Decision |
|---|---|---|
| `Supplier` | supplier | keep |
| `SupplierPayable` | supplier obligation/payable | keep |
| `SupplierPayment` | payment document to supplier | keep, align with generic payment concept |
| `PaymentSchedule` | installment schedule | keep |
| `ConsignmentAgreement` | consignment terms | keep/extend for fixed price + commission modes |
| `ConsignmentReturn` | consignment return document | keep |

## Finance

| Current | Target | Decision |
|---|---|---|
| `CashAccount` | business cash/bank account | keep |
| `CashEntry` | append-only cash movement | keep |
| `JournalEntry` | immutable accounting entry | keep |
| `CurrencyExchange` | cash account FX movement | keep |
| `record_supplier_payment_journal` | payable payment journal | keep/strengthen |
| receipt journal helpers | procurement document journal rules | refactor |

## Inventory/Sales

| Current | Target | Decision |
|---|---|---|
| `Lot` | immutable inventory lot | keep |
| `Lot.contract_snapshot` | lot economic ownership/profit snapshot | keep as core invariant |
| `LotStock` | physical stock by location | keep |
| `SaleLine.lot` | FIFO lot slice | keep |
| `profit_distribution_snapshot` | sale-line profit split | keep |

## Frontend

| Current | Target | Decision |
|---|---|---|
| `IntakeCreate.vue` | reference only | replace with new workspace |
| `IntakeDetail.vue` | reference only | replace with new workspace |
| create components | reference/reusable pieces | selectively reuse only if they fit target UX |
| detail payment/balance sheets | reference/reusable pieces | selectively reuse only if they fit target UX |
| local scattered conditions | `useProcurementWorkspaceState` | replace |
