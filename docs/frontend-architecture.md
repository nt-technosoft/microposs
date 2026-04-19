# MicroPOS — Frontend Architecture

> Legacy note: much of the detailed structure below reflects the pre-wipe frontend and is no longer the implementation source of truth. For the current restart baseline, use `docs/ux/05-frontend-restart-bootstrap.md`, `docs/ux/15-route-screen-matrix.md`, `docs/ux/18-foundation-keep-delete-plan.md`, `docs/ux/19-frontend-cleanup-execution.md`, and the actual scaffold under `frontend/src/`.

## Current canonical restart baseline

- Stack now starts from Vue 3 + Vite + TypeScript + Pinia + Vue Router.
- Current HTTP layer is a typed `fetch` client, not Axios.
- Canonical route language is `/procurements/*`, not `/intake/*`.
- Canonical investor cabinet routes are `/investor`, `/investor/procurements`, `/investor/procurements/:id`.
- Current scaffold foundation exists in:
  - `frontend/src/main.ts`
  - `frontend/src/App.vue`
  - `frontend/src/router/index.ts`
  - `frontend/src/router/routes.ts`
  - `frontend/src/stores/auth.ts`
  - `frontend/src/stores/session.ts`
  - `frontend/src/stores/ui.ts`
  - `frontend/src/api/client.ts`
- This file should be treated as historical architecture context until it is fully rewritten.

## Immediate rewrite priority

1. Preserve only concepts still aligned with vacuum-model and current UX docs.
2. Do not reuse old route/module naming that contradicts `docs/ux/*`.
3. Treat old `intake`, `contracts`, and legacy shared component descriptions as non-authoritative unless they match the new scaffold and route matrix.

## Historical snapshot

## Tech Stack

```
Framework:     Vue.js 3.4+ (Composition API, <script setup>)
Build:         Vite 5
Language:      TypeScript (strict mode)
State:         Pinia (per-domain stores)
Router:        Vue Router 4 (history mode)
HTTP:          Axios (typed API client)
Forms:         VeeValidate + Zod schemas
i18n:          Vue I18n (ru, uz, en)
Icons:         Lucide Vue Next
Animations:    @vueuse/motion or CSS transitions
PWA:           vite-plugin-pwa (offline-ready)
CSS:           CSS Modules + Design Tokens (CSS Custom Properties)
Testing:       Vitest + Vue Test Utils
```

## Directory Structure

```
frontend/
├── public/
│   ├── favicon.svg
│   └── manifest.json          # PWA manifest
│
├── src/
│   ├── main.ts                # App entry point
│   ├── App.vue                # Root component
│   │
│   ├── assets/
│   │   ├── styles/
│   │   │   ├── tokens.css     # Design tokens (colors, spacing, etc.)
│   │   │   ├── reset.css      # Minimal CSS reset
│   │   │   ├── typography.css # Type scale, font setup
│   │   │   ├── animations.css # Shared animation keyframes
│   │   │   └── utilities.css  # Utility classes (minimal)
│   │   ├── fonts/             # Inter font files (self-hosted)
│   │   └── illustrations/    # Empty state SVGs
│   │
│   ├── components/            # Shared UI components
│   │   ├── base/              # Atomic components
│   │   │   ├── BaseButton.vue
│   │   │   ├── BaseInput.vue
│   │   │   ├── BaseSelect.vue
│   │   │   ├── BaseChip.vue
│   │   │   ├── BaseCard.vue
│   │   │   ├── BaseBadge.vue
│   │   │   ├── BaseAvatar.vue
│   │   │   ├── BaseIcon.vue   # Lucide wrapper
│   │   │   └── BaseToggle.vue
│   │   │
│   │   ├── feedback/          # User feedback
│   │   │   ├── AppToast.vue
│   │   │   ├── AppDialog.vue
│   │   │   ├── AppBottomSheet.vue
│   │   │   ├── AppSkeleton.vue
│   │   │   ├── AppEmptyState.vue
│   │   │   └── AppLoadingSpinner.vue
│   │   │
│   │   ├── layout/            # Layout components
│   │   │   ├── AppHeader.vue
│   │   │   ├── AppBottomNav.vue
│   │   │   ├── AppSidebar.vue     # Desktop only
│   │   │   ├── AppFloatingCart.vue
│   │   │   └── AppPageWrapper.vue
│   │   │
│   │   ├── data/              # Data display
│   │   │   ├── DataTable.vue
│   │   │   ├── DataList.vue
│   │   │   ├── PriceDisplay.vue   # Formatted price with currency
│   │   │   ├── StatusBadge.vue
│   │   │   └── MetricCard.vue
│   │   │
│   │   └── forms/             # Form components
│   │       ├── PriceInput.vue     # Currency-aware input
│   │       ├── QuantityControl.vue # [-] qty [+]
│   │       ├── SearchInput.vue
│   │       └── DatePicker.vue
│   │
│   ├── composables/           # Shared composables
│   │   ├── useAuth.ts         # JWT auth state
│   │   ├── useTenant.ts       # Current business context
│   │   ├── useCart.ts         # Cart state & actions
│   │   ├── useToast.ts       # Toast notifications
│   │   ├── useBottomSheet.ts  # Bottom sheet control
│   │   ├── useBreakpoint.ts   # Responsive breakpoint detection
│   │   ├── useIdempotency.ts  # client_request_id generation
│   │   └── useDebounce.ts     # Search debounce
│   │
│   ├── api/                   # API layer
│   │   ├── client.ts          # Axios instance + interceptors
│   │   ├── types.ts           # Shared API types
│   │   ├── catalog.ts         # Catalog endpoints
│   │   ├── inventory.ts       # Inventory endpoints
│   │   ├── sales.ts           # Sales endpoints
│   │   ├── finance.ts         # Finance endpoints
│   │   ├── investors.ts       # Investor endpoints
│   │   ├── suppliers.ts       # Supplier endpoints
│   │   ├── customers.ts       # Customer endpoints
│   │   └── auth.ts            # Auth endpoints
│   │
│   ├── stores/                # Pinia stores
│   │   ├── auth.ts            # Auth state, user, role
│   │   ├── catalog.ts         # Products, categories, variants
│   │   ├── cart.ts            # Current sale cart
│   │   ├── sales.ts           # Sales history, POS session
│   │   ├── inventory.ts       # Stock levels, locations
│   │   └── ui.ts              # Theme, locale, layout state
│   │
│   ├── modules/               # Feature modules (pages + domain components)
│   │   ├── sales/             # Sales/POS module
│   │   │   ├── views/
│   │   │   │   ├── SalesCatalog.vue      # Product grid + search + categories
│   │   │   │   ├── ProductDetail.vue     # Variant selection + price
│   │   │   │   ├── CartView.vue          # Current receipt review
│   │   │   │   ├── CheckoutView.vue      # Payment method selection
│   │   │   │   ├── SaleComplete.vue      # Success screen
│   │   │   │   └── SalesHistory.vue      # Past sales list
│   │   │   └── components/
│   │   │       ├── ProductCard.vue       # Catalog product card
│   │   │       ├── VariantSelector.vue   # Attribute chips
│   │   │       ├── VariantListSheet.vue  # All variants bottom sheet
│   │   │       ├── PriceEditor.vue       # Per pricing mode
│   │   │       ├── DiscountReasonPicker.vue
│   │   │       ├── CartItem.vue          # Single cart line
│   │   │       ├── LotSelector.vue       # Manual lot pick
│   │   │       ├── PaymentMethodPicker.vue
│   │   │       └── CustomerSelector.vue  # For credit sales
│   │   │
│   │   ├── products/          # Product management module
│   │   │   ├── views/
│   │   │   │   ├── ProductList.vue
│   │   │   │   ├── ProductCreate.vue
│   │   │   │   ├── ProductEdit.vue
│   │   │   │   ├── CategoryList.vue
│   │   │   │   └── CategoryEdit.vue
│   │   │   └── components/
│   │   │       ├── ProductForm.vue
│   │   │       ├── VariantManager.vue
│   │   │       ├── AttributeEditor.vue
│   │   │       └── PricingModeSelector.vue
│   │   │
│   │   ├── intake/            # Receipt/Intake module
│   │   │   ├── views/
│   │   │   │   ├── IntakeList.vue
│   │   │   │   ├── IntakeCreate.vue      # Type selection first
│   │   │   │   ├── IntakeDetail.vue
│   │   │   │   └── IntakeConfirm.vue
│   │   │   └── components/
│   │   │       ├── IntakeTypeSelector.vue
│   │   │       ├── ParticipantEditor.vue  # Investor shares
│   │   │       ├── IntakeLineEditor.vue
│   │   │       ├── SupplierPicker.vue
│   │   │       └── PayableTermsEditor.vue
│   │   │
│   │   ├── reports/           # Reports module
│   │   │   ├── views/
│   │   │   │   ├── ReportsDashboard.vue
│   │   │   │   ├── PnLReport.vue
│   │   │   │   ├── CashFlowReport.vue
│   │   │   │   ├── StockReport.vue
│   │   │   │   └── SalesReport.vue
│   │   │   └── components/
│   │   │       ├── PeriodSelector.vue
│   │   │       ├── ReportCard.vue
│   │   │       └── SimpleChart.vue
│   │   │
│   │   ├── more/              # Settings & extras module
│   │   │   ├── views/
│   │   │   │   ├── MoreMenu.vue
│   │   │   │   ├── CustomersView.vue
│   │   │   │   ├── SuppliersView.vue
│   │   │   │   ├── WarehousesView.vue
│   │   │   │   ├── PosSessionView.vue
│   │   │   │   ├── DiscountReasonsView.vue
│   │   │   │   └── SettingsView.vue
│   │   │   └── components/
│   │   │       ├── CustomerForm.vue
│   │   │       ├── SupplierForm.vue
│   │   │       └── SessionReconciliation.vue
│   │   │
│   │   ├── investors/         # Investor cabinet (separate entry)
│   │   │   ├── views/
│   │   │   │   ├── InvestorDashboard.vue
│   │   │   │   ├── ContractList.vue
│   │   │   │   ├── ContractDetail.vue
│   │   │   │   └── LotHistory.vue
│   │   │   └── components/
│   │   │       ├── InvestorMetrics.vue
│   │   │       ├── ContractCard.vue
│   │   │       └── LotPerformanceCard.vue
│   │   │
│   │   └── auth/              # Authentication
│   │       └── views/
│   │           ├── LoginView.vue
│   │           └── SetupView.vue   # Initial business setup
│   │
│   ├── router/
│   │   ├── index.ts           # Router instance
│   │   ├── routes.ts          # Route definitions
│   │   └── guards.ts         # Auth & role guards
│   │
│   ├── types/                 # Global TypeScript types
│   │   ├── models.ts          # Domain model interfaces
│   │   ├── enums.ts           # ReceiptType, PricingMode, etc.
│   │   └── api.ts             # API response types
│   │
│   └── utils/
│       ├── currency.ts        # Price formatting
│       ├── date.ts            # Date formatting
│       └── validators.ts      # Zod schemas
│
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
└── .env.example
```

## Routing Structure

```typescript
// Main app routes (MicroPOS)
/login
/setup                       // Initial business setup

// Sales (default tab)
/sales                       // Catalog view
/sales/product/:id           // Product detail + variant select
/sales/cart                  // Cart review
/sales/checkout              // Payment
/sales/history               // Past sales
/sales/:id                   // Sale detail
/sales/:id/return            // Return flow

// Products
/products                    // Product list
/products/create             // New product
/products/:id                // Edit product
/categories                  // Category list
/categories/:id              // Edit category

// Intake (Receipt)
/intake                      // Receipt list
/intake/create               // New receipt
/intake/:id                  // Receipt detail
/intake/:id/confirm          // Confirm receipt

// Reports
/reports                     // Dashboard
/reports/pnl                 // P&L
/reports/cashflow            // Cash Flow
/reports/stock               // Stock report
/reports/sales               // Sales report

// More section
/customers                   // Customer list
/customers/:id               // Customer detail
/suppliers                   // Supplier list
/suppliers/:id               // Supplier detail
/warehouses                  // Locations
/session                     // POS session
/settings                    // App settings

// Investor cabinet (separate guard)
/investor                    // Dashboard
/investor/contracts          // Contract list
/investor/contracts/:id      // Contract detail
```

## Role-Based Access

```typescript
enum UserRole {
  OWNER = 'owner',           // Full access
  CASHIER = 'cashier',       // Sales tab only ("Simple seller")
  WAREHOUSE = 'warehouse',   // Products + Intake only
  INVESTOR = 'investor',     // Investor cabinet only
}

// Route meta for guards
{ meta: { roles: ['owner', 'cashier'] } }
```

## State Management Strategy

```
Pinia Stores:

auth.ts
  - user, token, role, tenant
  - login(), logout(), refreshToken()

cart.ts (most critical for UX)
  - items: CartItem[]
  - addItem(), removeItem(), updateQuantity()
  - total, itemCount (getters)
  - clear(), checkout()
  - Persisted to localStorage for crash recovery

catalog.ts
  - products, categories, search results
  - Cached with TTL, invalidated on mutations

sales.ts
  - currentSession: PosSession | null
  - recentSales: Sale[]
  - openSession(), closeSession()

inventory.ts
  - stockByLocation
  - lowStockAlerts

ui.ts
  - theme: 'light' | 'dark'
  - locale: 'ru' | 'uz' | 'en'
  - bottomSheetState
  - toastQueue
```

## API Client Pattern

```typescript
// api/client.ts
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { 'Content-Type': 'application/json' }
});

// Request interceptor: attach JWT + tenant
api.interceptors.request.use(config => {
  const auth = useAuthStore();
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`;
  }
  return config;
});

// Response interceptor: handle 401, refresh token
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      await refreshOrLogout();
    }
    return Promise.reject(error);
  }
);

// api/sales.ts — typed endpoints
export const salesApi = {
  create: (data: CreateSaleRequest) =>
    api.post<Sale>('/api/sales/', data),

  getById: (id: number) =>
    api.get<Sale>(`/api/sales/${id}/`),

  processReturn: (saleId: number, data: ReturnRequest) =>
    api.post<SaleReturn>(`/api/sales/${saleId}/return/`, data),
};
```

## Performance Targets

```
First Contentful Paint:  < 1.5s
Largest Contentful Paint: < 2.5s
Cumulative Layout Shift:  < 0.1
First Input Delay:        < 100ms
Bundle size (initial):    < 200KB gzipped
```

## PWA Strategy

```
- Service worker for offline product catalog cache
- Background sync for sales created offline
- App manifest with theme colors matching design system
- Install prompt after 3rd session
```
