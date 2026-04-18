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

  // Intake (Receipt)
  {
    path: '/intake',
    name: 'intake-list',
    component: () => import('@/modules/intake/views/IntakeList.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/intake/create',
    name: 'intake-create',
    component: () => import('@/modules/intake/views/IntakeCreate.vue'),
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/intake/:id',
    name: 'intake-detail',
    component: () => import('@/modules/intake/views/IntakeDetail.vue'),
    meta: { roles: ['owner', 'warehouse'] },
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

  // Investor cabinet
  {
    path: '/investor',
    name: 'investor-dashboard',
    component: () => import('@/modules/investors/views/InvestorDashboard.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
  {
    path: '/investor/contracts/:id',
    name: 'investor-contract',
    component: () => import('@/modules/investors/views/ContractDetail.vue'),
    meta: { roles: ['investor'], layout: 'investor' },
  },
]

export default routes
