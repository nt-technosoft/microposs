# MicroPOS — Data Models & Relationships

## Entity-Relationship Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          CORE                                    │
│  Business (Tenant)  ──►  User  ──►  UserRole                   │
│  OutboxEvent                                                     │
└──────────────────────────────┬──────────────────────────────────┘
                               │ tenant_id on everything
┌──────────────────────────────▼──────────────────────────────────┐
│                         CATALOG                                  │
│                                                                  │
│  Category ──► Product ──► ProductVariant                        │
│     │            │            │                                   │
│     │            ├── ProductAttribute                            │
│     │            └── ProductCharacteristic                       │
│     │                                                            │
│     ├── CategoryAttribute (template)                            │
│     └── default_pricing_mode                                    │
│                                                                  │
│  Attribute ──► AttributeValue                                   │
│  DiscountReason                                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        INVENTORY                                 │
│                                                                  │
│  Location (warehouse/store)                                     │
│     │                                                            │
│  Receipt ──► ReceiptLine ──► Lot                                │
│     │                           │                                │
│     ├── ReceiptParticipant      ├── product_variant (FK)        │
│     │   (investor/business)     ├── location (FK)               │
│     │                           ├── quantity_initial             │
│     ├── receipt_type            ├── quantity_remaining           │
│     ├── status (draft/confirmed)├── cost_per_unit (snapshot)    │
│     └── supplier (FK, optional) └── is_active                   │
│                                                                  │
│  StockMovement (log of all movements)                           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                          SALES                                   │
│                                                                  │
│  PosSession (shift)                                             │
│     │                                                            │
│  Sale ──► SaleLine                                              │
│     │        │                                                   │
│     │        ├── lot (FK) ◄── ALWAYS references a Lot           │
│     │        ├── unit_price                                      │
│     │        ├── base_price (snapshot)                           │
│     │        ├── price_changed (bool)                            │
│     │        └── discount_reason (FK, optional)                 │
│     │                                                            │
│     ├── payment_method (cash/card/credit)                       │
│     ├── customer (FK, required if credit)                       │
│     ├── pos_session (FK)                                        │
│     ├── client_request_id (UUID, idempotent)                    │
│     └── status (draft/completed)                                │
│                                                                  │
│  SaleReturn ──► SaleReturnLine                                  │
│     │               │                                            │
│     │               ├── sale_line (FK)                           │
│     │               ├── quantity                                 │
│     │               └── condition (good/damaged)                │
│     └── sale (FK)                                               │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                         FINANCE                                  │
│                                                                  │
│  Account (Chart of Accounts)                                    │
│     │                                                            │
│  JournalEntry ──► JournalLine                                   │
│     │                 │                                          │
│     │                 ├── account (FK)                           │
│     │                 ├── debit (Decimal)                        │
│     │                 └── credit (Decimal)                      │
│     │                                                            │
│     ├── operation_type (sale/receipt/payment/return/writeoff)   │
│     ├── operation_id (generic FK)                               │
│     └── status (confirmed) ◄── IMMUTABLE                       │
│                                                                  │
│  DailySummary (aggregated P&L per day)                          │
│  CashFlowSummary (aggregated cash flow per day)                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        INVESTORS                                 │
│                                                                  │
│  Investor ──► InvestorContract                                  │
│                  │                                               │
│                  ├── contract_type (MUDARABA/MUSHARAKA)          │
│                  ├── default_profit_ratio                        │
│                  ├── status (active/closed)                      │
│                  ├── final_settlement                            │
│                  └── closed_at                                   │
│                                                                  │
│  InvestorProfitRecord (per sale line)                            │
│     ├── contract (FK)                                            │
│     ├── sale_line (FK)                                          │
│     ├── amount                                                   │
│     └── type (profit/loss/capital_return)                       │
│                                                                  │
│  InvestorSummary (denormalized dashboard data)                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    SUPPLIERS & CUSTOMERS                          │
│                                                                  │
│  Supplier                          Customer                      │
│     │                                 │                          │
│     ├── SupplierPayment              ├── CustomerPayment        │
│     ├── ConsignmentAgreement         ├── outstanding_balance    │
│     └── outstanding_balance          └── CustomerDebtRecord     │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                           RISK                                   │
│                                                                  │
│  RiskEvent                                                       │
│     ├── event_type (writeoff/damage/loss/return/stock_mismatch) │
│     ├── lot (FK)                                                │
│     ├── quantity                                                 │
│     ├── affects_investor (bool, auto-computed)                  │
│     ├── negligence (bool, default=False)                        │
│     └── responsible_user (FK)                                   │
│                                                                  │
│  InventoryCheck ──► InventoryCheckLine                          │
│     │                    │                                       │
│     │                    ├── product_variant (FK)                │
│     │                    ├── expected_quantity                   │
│     │                    ├── actual_quantity                     │
│     │                    └── difference                          │
│     └── location (FK)                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Critical Indexes

```sql
-- Lot (most queried for sales)
CREATE INDEX idx_lot_sale_lookup
  ON lot (product_variant_id, location_id, is_active, quantity_remaining)
  WHERE is_active = TRUE AND quantity_remaining > 0;

CREATE INDEX idx_lot_receipt ON lot (receipt_id);

-- SaleLine
CREATE INDEX idx_saleline_lot ON sale_line (lot_id);
CREATE INDEX idx_saleline_sale ON sale_line (sale_id);

-- Receipt
CREATE INDEX idx_receipt_tenant_type ON receipt (tenant_id, receipt_type, status);

-- OutboxEvent (Celery worker poll)
CREATE INDEX idx_outbox_unprocessed
  ON outbox_event (processed_at, tenant_id)
  WHERE processed_at IS NULL;

-- JournalEntry
CREATE INDEX idx_journal_tenant_date ON journal_entry (tenant_id, created_at);

-- All soft-delete models
-- Manager auto-filters deleted_at IS NULL, index supports this
CREATE INDEX idx_<model>_active ON <model> (deleted_at) WHERE deleted_at IS NULL;
```

## Key Constraints

```
1. Receipt.receipt_type — immutable after creation
2. Receipt — immutable after status = 'confirmed'
3. Sale — immutable after status = 'completed'
4. JournalEntry — immutable after creation (always confirmed)
5. Lot.cost_per_unit — snapshot, never changes
6. SaleLine.base_price — snapshot of price at sale time
7. ReceiptParticipant: SUM(profit_ratio) = 1.0 per receipt
8. Sale.customer_id — NOT NULL when payment_method = 'credit'
9. InvestorContract — cannot close with active lots
10. Unique constraint: (tenant_id, client_request_id) per operation
```
