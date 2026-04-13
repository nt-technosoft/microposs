# MicroPOS — System Architecture

## 1. High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                      CLIENTS                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │
│  │ MicroPOS │  │ Full POS │  │ Investor Cabinet      │  │
│  │ (Mobile) │  │ (Desktop)│  │ (Separate SPA)        │  │
│  └────┬─────┘  └────┬─────┘  └──────────┬────────────┘  │
│       │              │                   │               │
└───────┼──────────────┼───────────────────┼───────────────┘
        │              │                   │
        ▼              ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                    API GATEWAY                          │
│              Django REST Framework                      │
│         JWT Auth (simplejwt) + Tenant Middleware         │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                 MODULAR MONOLITH                        │
│                                                         │
│  ┌─────────┐ ┌───────────┐ ┌───────┐ ┌─────────┐       │
│  │ Catalog │ │ Inventory │ │ Sales │ │ Finance │       │
│  └─────────┘ └───────────┘ └───────┘ └─────────┘       │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐             │
│  │ Investors │ │ Suppliers │ │ Customers │             │
│  └───────────┘ └───────────┘ └───────────┘             │
│  ┌──────┐ ┌───────────┐ ┌──────┐                       │
│  │ Risk │ │ Analytics │ │ Core │                       │
│  └──────┘ └───────────┘ └──────┘                       │
│                                                         │
│  Cross-domain: Services Layer + OutboxEvent             │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ PostgreSQL   │ │    Redis     │ │   Celery     │
│   16         │ │ Cache+Broker │ │  Workers     │
└──────────────┘ └──────────────┘ └──────────────┘
```

## 2. Backend Structure

```
backend/
├── config/                    # Django project settings
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py           # Common settings
│   │   ├── development.py    # Dev overrides
│   │   ├── production.py     # Prod overrides
│   │   └── test.py           # Test overrides
│   ├── urls.py               # Root URL configuration
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py             # Celery configuration
│
├── apps/
│   ├── core/                  # Foundation layer
│   │   ├── models.py         # BaseModel, OutboxEvent, Business
│   │   ├── mixins.py         # TenantMixin, ImmutableMixin
│   │   ├── middleware.py     # TenantMiddleware, RequestIDMiddleware
│   │   ├── permissions.py    # Role-based permissions
│   │   ├── exceptions.py     # Custom exception classes
│   │   ├── pagination.py     # Standard pagination
│   │   ├── utils.py          # Shared utilities
│   │   └── managers.py       # SoftDeleteManager, TenantManager
│   │
│   ├── catalog/               # Products domain
│   │   ├── models.py         # Category, Product, ProductVariant,
│   │   │                     # Attribute, AttributeValue, Characteristic
│   │   ├── services.py       # Catalog business logic
│   │   ├── serializers.py    # DRF serializers
│   │   ├── views.py          # ViewSets
│   │   ├── urls.py           # URL patterns
│   │   ├── filters.py        # Django-filter filtersets
│   │   └── signals.py        # Post-save signals (category template apply)
│   │
│   ├── inventory/             # Warehouse & stock domain
│   │   ├── models.py         # Warehouse, Location, Receipt, ReceiptLine,
│   │   │                     # ReceiptParticipant, Lot, StockMovement
│   │   ├── services.py       # Receipt confirmation, lot creation,
│   │   │                     # stock transfer, inventory check
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── validators.py     # Participant ratio validation
│   │
│   ├── sales/                 # POS & sales domain
│   │   ├── models.py         # Sale, SaleLine, PosSession, DiscountReason,
│   │   │                     # SaleReturn, SaleReturnLine
│   │   ├── services.py       # Sale creation, FIFO lot selection,
│   │   │                     # profit distribution, returns
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── validators.py     # Credit sale validation
│   │
│   ├── finance/               # Accounting domain
│   │   ├── models.py         # Account (CoA), JournalEntry, JournalLine,
│   │   │                     # DailySummary, CashFlowSummary
│   │   ├── services.py       # Journal entry creation rules,
│   │   │                     # P&L aggregation, Cash Flow
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── chart_of_accounts.py  # Default CoA setup
│   │
│   ├── investors/             # Investor relations domain
│   │   ├── models.py         # Investor, InvestorContract,
│   │   │                     # InvestorProfitRecord, InvestorSummary
│   │   ├── services.py       # Contract management, profit calculation,
│   │   │                     # contract closure, settlement
│   │   ├── serializers.py
│   │   ├── views.py          # Investor cabinet views
│   │   └── urls.py
│   │
│   ├── suppliers/             # Supplier domain
│   │   ├── models.py         # Supplier, SupplierPayment,
│   │   │                     # ConsignmentAgreement
│   │   ├── services.py       # A/P management, consignment tracking
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── customers/             # Customer domain
│   │   ├── models.py         # Customer, CustomerPayment,
│   │   │                     # CustomerDebtRecord
│   │   ├── services.py       # A/R management, debt tracking
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── risk/                  # Risk management domain
│   │   ├── models.py         # RiskEvent, InventoryCheck,
│   │   │                     # InventoryCheckLine
│   │   ├── services.py       # Risk event creation, loss distribution,
│   │   │                     # inventory reconciliation
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   │
│   └── analytics/             # Read-only analytics domain
│       ├── models.py         # DailyPnL, InvestorDashboard,
│       │                     # ProductPerformance, AgingReport
│       ├── services.py       # Aggregation logic
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       └── tasks.py          # Celery tasks for aggregation
│
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
└── pytest.ini
```

## 3. Domain Interaction Map

```
                    ┌──────────┐
                    │   Core   │
                    │ (Base,   │
                    │ Outbox,  │
                    │ Tenant)  │
                    └────┬─────┘
                         │ inherited by all
         ┌───────────────┼───────────────────┐
         │               │                   │
    ┌────▼────┐    ┌─────▼─────┐      ┌──────▼──────┐
    │ Catalog │◄───│ Inventory │──────│   Sales     │
    │         │    │           │      │             │
    └─────────┘    └─────┬─────┘      └──────┬──────┘
                         │                   │
                    ┌────▼────┐         ┌────▼─────┐
                    │ Finance │◄────────│          │
                    │         │         │          │
                    └────┬────┘         └──────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼─────┐  ┌──────▼────┐   ┌──────▼──────┐
    │Investors │  │ Suppliers │   │  Customers  │
    └──────────┘  └───────────┘   └─────────────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                    ┌────▼────┐
                    │  Risk   │
                    └────┬────┘
                         │
                    ┌────▼──────┐
                    │ Analytics │ (reads from all)
                    └───────────┘

Arrow = service call or FK reference (NOT direct model import for logic)
```

## 4. Data Flow: Sale Lifecycle

```
1. Customer selects product
   │
2. System resolves ProductVariant → checks stock
   │
3. FIFO lot selection (or manual)
   │  Lot.objects.filter(variant, location, is_active=True)
   │  .order_by('receipt__date')
   │
4. Price handling (by PricingMode)
   │  ASK_EACH_SALE / DEFAULT_EDITABLE / FIXED_LOCKED
   │
5. Add to cart (SaleLine with lot_id)
   │
6. Checkout
   │  ├─ Validate credit sale (customer required)
   │  ├─ Check idempotency (client_request_id)
   │  └─ SELECT FOR UPDATE on lots (race condition protection)
   │
7. Create Sale + SaleLines
   │
8. Update Lot.quantity_remaining
   │
9. Calculate profit distribution per line
   │  ├─ BUSINESS_OWNED → 100% business
   │  ├─ MUDARABA → by profit_ratio (investor/business)
   │  ├─ MUSHARAKA → by profit_ratio (all participants)
   │  ├─ CONSIGNMENT → margin/commission rule
   │  └─ SUPPLIER_PURCHASE → 100% business
   │
10. Create JournalEntries
    │  ├─ Debit: Cash/Bank/AR
    │  ├─ Credit: Revenue
    │  ├─ Debit: COGS
    │  └─ Credit: Inventory
    │
11. Write OutboxEvent('sale.completed')
    │
12. Celery picks up → updates analytics/investor summaries
```

## 5. Key Technical Decisions

### Database Locking Strategy
- `SELECT FOR UPDATE` on Lot rows during sale to prevent overselling
- Transaction wraps entire sale operation

### Idempotency
- `client_request_id` (UUID) on all financial POST endpoints
- Unique constraint on `(tenant_id, client_request_id)` per operation type
- Duplicate request returns existing object with 200

### Event Processing
- OutboxEvent table with `processed_at` tracking
- Celery beat polls every 10s for unprocessed events
- Each event triggers domain-specific aggregation tasks

### Multi-tenant Isolation
- `tenant_id` field + DB index on all business models
- TenantMiddleware extracts tenant from JWT claims
- TenantQuerySet auto-filters by tenant_id
- No cross-tenant data leaks possible at ORM level
