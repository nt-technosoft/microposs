/**
 * Route definitions for MicroPOS.
 */

import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  // Auth
  {
    path: '/login',
    name: 'login',
    component: () => import('@/modules/auth/views/LoginView.vue'),
    meta: { requiresAuth: false, layout: 'blank' },
  },
  {
    path: '/register-business',
    name: 'business-registration',
    component: () => import('@/modules/auth/views/BusinessRegistrationView.vue'),
    meta: { requiresAuth: false, layout: 'blank' },
  },
  {
    path: '/investor/invite/:token',
    name: 'investor-invite',
    component: () => import('@/modules/investors/views/InvestorInviteAccept.vue'),
    meta: { requiresAuth: false, layout: 'blank' },
  },

  // Sales (default tab)
  {
    path: '/',
    redirect: '/sales',
  },
  {
    path: '/sales',
    name: 'sales-catalog',
    component: () => import('@/modules/sales/views/SalesCatalog.vue'),
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/product/:id',
    name: 'product-detail',
    component: () => import('@/modules/sales/views/ProductDetail.vue'),
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/cart',
    name: 'cart',
    component: () => import('@/modules/sales/views/CartView.vue'),
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/checkout',
    name: 'checkout',
    component: () => import('@/modules/sales/views/CheckoutView.vue'),
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/history',
    name: 'sales-history',
    component: () => import('@/modules/sales/views/SalesHistory.vue'),
    meta: { roles: ['owner', 'cashier'] },
  },

  // Products
  {
    path: '/products',
    name: 'products',
    component: () => import('@/modules/products/views/ProductList.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/products/create',
    name: 'product-create',
    component: () => import('@/modules/products/views/ProductCreate.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/products/:id',
    name: 'product-edit',
    component: () => import('@/modules/products/views/ProductEdit.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/categories',
    name: 'categories',
    component: () => import('@/modules/products/views/CategoryList.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/stock/transfers',
    name: 'stock-transfers',
    component: () => import('@/modules/inventory/views/StockTransfersView.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },

  // Procurements (rendered by restored intake views until full slice rewrite)
  {
    path: '/procurements/agreements',
    name: 'agreement-list',
    component: () => import('@/modules/intake/views/AgreementList.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/procurements/agreements/create',
    name: 'agreement-create',
    component: () => import('@/modules/intake/views/AgreementCreate.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/procurements/agreements/:id',
    name: 'agreement-detail',
    component: () => import('@/modules/intake/views/AgreementDetail.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/procurements',
    name: 'procurement-list',
    component: () => import('@/modules/intake/views/IntakeList.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/procurements/create',
    name: 'procurement-create',
    component: () => import('@/modules/intake/views/IntakeCreate.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/procurements/:id/edit',
    name: 'procurement-edit',
    component: () => import('@/modules/intake/views/IntakeCreate.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/procurements/:id',
    name: 'procurement-detail',
    component: () => import('@/modules/intake/views/IntakeDetail.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/intake',
    redirect: '/procurements',
  },
  {
    path: '/intake/create',
    redirect: '/procurements/create',
  },
  {
    path: '/intake/:id/edit',
    redirect: (to) => `/procurements/${to.params.id}/edit`,
  },
  {
    path: '/intake/:id',
    redirect: (to) => `/procurements/${to.params.id}`,
  },

  // Reports
  {
    path: '/reports',
    name: 'reports',
    component: () => import('@/modules/reports/views/ReportsDashboard.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/reports/reconciliation',
    name: 'reports-reconciliation',
    component: () => import('@/modules/reports/views/ReconciliationView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/reports/procurements/:id',
    name: 'reports-procurement-profitability',
    component: () => import('@/modules/reports/views/ProcurementProfitabilityView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/reports/agreements/:id',
    name: 'reports-agreement-profitability',
    component: () => import('@/modules/reports/views/AgreementProfitabilityView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/reports/audit/sales/:id',
    name: 'reports-sale-explanation',
    component: () => import('@/modules/reports/views/SaleExplanationView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/finance/exchange',
    name: 'finance-exchange',
    component: () => import('@/modules/finance/views/CurrencyExchangeView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/investors/manage',
    name: 'owner-investors',
    component: () => import('@/modules/investors/views/OwnerInvestors.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/platform-admin',
    name: 'platform-admin-requests',
    component: () => import('@/modules/platformAdmin/views/PlatformAdminRequestsView.vue'),
    meta: { roles: ['platform_admin'], layout: 'blank' },
  },

  // More section
  {
    path: '/customers',
    name: 'customers',
    component: () => import('@/modules/more/views/CustomersView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/suppliers',
    name: 'suppliers',
    component: () => import('@/modules/more/views/SuppliersView.vue'),
    meta: { roles: ['owner'] },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/modules/more/views/SettingsView.vue'),
    meta: { roles: ['owner', 'cashier', 'warehouse', 'investor'] },
  },
  {
    path: '/settings/map',
    name: 'settings-page-map',
    component: () => import('@/modules/more/views/PageMapView.vue'),
    meta: { roles: ['owner', 'cashier', 'warehouse', 'investor'] },
  },

  // Investor cabinet (canonical procurement-centric routes)
  {
    path: '/investor',
    name: 'investor-dashboard',
    component: () => import('@/modules/investors/views/InvestorDashboard.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/procurements',
    name: 'investor-procurements',
    component: () => import('@/modules/investors/views/InvestorDashboard.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/agreements',
    name: 'investor-agreements',
    component: () => import('@/modules/investors/views/InvestorDashboard.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/agreements/:id',
    name: 'investor-agreement',
    component: () => import('@/modules/investors/views/InvestorAgreementDetail.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/procurements/:id',
    name: 'investor-procurement',
    component: () => import('@/modules/investors/views/ContractDetail.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/contracts/:id',
    redirect: (to) => `/investor/procurements/${to.params.id}`,
  },
]

export default routes
