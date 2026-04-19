import type { RouteRecordRaw } from 'vue-router'

import LoginView from '@/modules/auth/views/LoginView.vue'
import InvestorDashboardView from '@/modules/investor/views/InvestorDashboardView.vue'
import InvestorProcurementDetailView from '@/modules/investor/views/InvestorProcurementDetailView.vue'
import InvestorProcurementsView from '@/modules/investor/views/InvestorProcurementsView.vue'
import ProcurementDetailView from '@/modules/procurements/views/ProcurementDetailView.vue'
import ProcurementsListView from '@/modules/procurements/views/ProcurementsListView.vue'
import SalesCatalogView from '@/modules/sales/views/SalesCatalogView.vue'
import SalesCartView from '@/modules/sales/views/SalesCartView.vue'
import SalesCheckoutView from '@/modules/sales/views/SalesCheckoutView.vue'
import SettingsView from '@/modules/settings/views/SettingsView.vue'

const authenticatedRoles = ['owner', 'cashier', 'warehouse', 'investor'] as const

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/sales',
    name: 'sales-catalog',
    component: SalesCatalogView,
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/cart',
    name: 'sales-cart',
    component: SalesCartView,
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/sales/checkout',
    name: 'sales-checkout',
    component: SalesCheckoutView,
    meta: { roles: ['owner', 'cashier'] },
  },
  {
    path: '/procurements',
    name: 'procurements-list',
    component: ProcurementsListView,
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/procurements/:id',
    name: 'procurement-detail',
    component: ProcurementDetailView,
    meta: { roles: ['owner', 'warehouse'] },
  },
  {
    path: '/investor',
    name: 'investor-dashboard',
    component: InvestorDashboardView,
    meta: { roles: ['investor'] },
  },
  {
    path: '/investor/procurements',
    name: 'investor-procurements',
    component: InvestorProcurementsView,
    meta: { roles: ['investor'] },
  },
  {
    path: '/investor/procurements/:id',
    name: 'investor-procurement-detail',
    component: InvestorProcurementDetailView,
    meta: { roles: ['investor'] },
  },
  {
    path: '/settings',
    name: 'settings',
    component: SettingsView,
    meta: { roles: [...authenticatedRoles] },
  },
  {
    path: '/',
    redirect: '/login',
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/login',
  },
]
