import type { Component } from 'vue'
import {
  ArrowLeftRight,
  BarChart3,
  BookOpenCheck,
  Boxes,
  CircleDollarSign,
  FileText,
  Handshake,
  History,
  Map,
  Package,
  PackagePlus,
  Plug,
  ReceiptText,
  Settings,
  ShoppingBag,
  Tags,
  Truck,
  Users,
  Wallet,
} from 'lucide-vue-next'
import { UserRole } from '@/types/enums'

export type BusinessNavSection =
  | 'sales'
  | 'products'
  | 'procurements'
  | 'finance'
  | 'relationships'
  | 'settings'

export type BusinessNavigationSurface = 'desktop' | 'mobile'

export interface AppNavItem {
  id: string
  labelKey: string
  icon: Component
  to: { name: string }
  routeNames: readonly string[]
  section: BusinessNavSection
  roles: readonly UserRole[]
  mobilePrimary: boolean
  mobileLabelKey?: string
  mobileParentId?: string
}

export interface AppNavSection {
  id: BusinessNavSection
  labelKey: string
}

export interface BusinessNavigationOptions {
  role?: UserRole | null
  simpleSellerMode?: boolean
  surface?: BusinessNavigationSurface
}

const BUSINESS_ROLES = [UserRole.OWNER, UserRole.CASHIER, UserRole.WAREHOUSE] as const
const SALES_ROLES = [UserRole.OWNER, UserRole.CASHIER] as const
const STOCK_ROLES = [UserRole.OWNER, UserRole.WAREHOUSE] as const
const OWNER_ONLY = [UserRole.OWNER] as const

export const businessNavigationSections: readonly AppNavSection[] = [
  { id: 'sales', labelKey: 'nav.sales' },
  { id: 'products', labelKey: 'nav.products' },
  { id: 'procurements', labelKey: 'nav.procurements' },
  { id: 'finance', labelKey: 'nav.finance' },
  { id: 'relationships', labelKey: 'settings.management' },
  { id: 'settings', labelKey: 'nav.settings' },
]

/**
 * One navigation source for the authenticated business workspace.
 *
 * Route guards remain authoritative. The registry only describes presentation,
 * role visibility and active-state grouping for the shell surfaces.
 */
export const businessNavigationItems: readonly AppNavItem[] = [
  {
    id: 'sales',
    labelKey: 'nav.sales',
    icon: ShoppingBag,
    to: { name: 'sales-catalog' },
    routeNames: ['sales-catalog', 'product-detail', 'cart', 'checkout'],
    section: 'sales',
    roles: SALES_ROLES,
    mobilePrimary: true,
  },
  {
    id: 'sales-history',
    labelKey: 'sales.history',
    icon: History,
    to: { name: 'sales-history' },
    routeNames: ['sales-history'],
    section: 'sales',
    roles: SALES_ROLES,
    mobilePrimary: false,
    mobileParentId: 'sales',
  },
  {
    id: 'products',
    labelKey: 'nav.products',
    icon: Package,
    to: { name: 'products' },
    routeNames: ['products', 'product-create', 'product-edit'],
    section: 'products',
    roles: STOCK_ROLES,
    mobilePrimary: true,
  },
  {
    id: 'categories',
    labelKey: 'products.categories',
    icon: Tags,
    to: { name: 'categories' },
    routeNames: ['categories'],
    section: 'products',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'products',
  },
  {
    id: 'stock-transfers',
    labelKey: 'settings.quickLinks.transfers',
    icon: Boxes,
    to: { name: 'stock-transfers' },
    routeNames: ['stock-transfers'],
    section: 'products',
    roles: STOCK_ROLES,
    mobilePrimary: false,
    mobileParentId: 'products',
  },
  {
    id: 'procurements',
    labelKey: 'nav.procurements',
    icon: PackagePlus,
    to: { name: 'procurement-list' },
    routeNames: ['procurement-list', 'procurement-create', 'procurement-edit', 'procurement-detail'],
    section: 'procurements',
    roles: STOCK_ROLES,
    mobilePrimary: true,
  },
  {
    id: 'agreements',
    labelKey: 'procurements.agreements',
    icon: FileText,
    to: { name: 'agreement-list' },
    routeNames: ['agreement-list', 'agreement-create', 'agreement-detail'],
    section: 'procurements',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'procurements',
  },
  {
    id: 'reports',
    labelKey: 'nav.reports',
    icon: BarChart3,
    to: { name: 'reports' },
    routeNames: [
      'reports',
      'reports-procurement-profitability',
      'reports-agreement-profitability',
      'reports-sale-explanation',
    ],
    section: 'finance',
    roles: OWNER_ONLY,
    mobilePrimary: true,
  },
  {
    id: 'reconciliation',
    labelKey: 'reports.reconciliation',
    icon: BookOpenCheck,
    to: { name: 'reports-reconciliation' },
    routeNames: ['reports-reconciliation'],
    section: 'finance',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'reports',
  },
  {
    id: 'cash',
    labelKey: 'nav.cash',
    icon: Wallet,
    to: { name: 'cash-accounts' },
    routeNames: ['cash-accounts'],
    section: 'finance',
    roles: OWNER_ONLY,
    mobilePrimary: true,
  },
  {
    id: 'exchange',
    labelKey: 'finance.exchange',
    icon: ArrowLeftRight,
    to: { name: 'finance-exchange' },
    routeNames: ['finance-exchange'],
    section: 'finance',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'cash',
  },
  {
    id: 'investors',
    labelKey: 'investors.ownerTitle',
    icon: Handshake,
    to: { name: 'owner-investors' },
    routeNames: ['owner-investors'],
    section: 'relationships',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
  {
    id: 'customers',
    labelKey: 'customers.title',
    icon: Users,
    to: { name: 'customers' },
    routeNames: ['customers'],
    section: 'relationships',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
  {
    id: 'suppliers',
    labelKey: 'suppliers.title',
    icon: Truck,
    to: { name: 'suppliers' },
    routeNames: ['suppliers'],
    section: 'relationships',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
  {
    id: 'supplier-payables',
    labelKey: 'suppliers.payablesPageTitle',
    icon: ReceiptText,
    to: { name: 'supplier-payables' },
    routeNames: ['supplier-payables'],
    section: 'relationships',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
  {
    id: 'settings',
    labelKey: 'nav.settings',
    icon: Settings,
    to: { name: 'settings' },
    routeNames: ['settings'],
    section: 'settings',
    roles: BUSINESS_ROLES,
    mobilePrimary: true,
    mobileLabelKey: 'nav.more',
  },
  {
    id: 'integrations',
    labelKey: 'settings.quickLinks.integrations',
    icon: Plug,
    to: { name: 'integrations' },
    routeNames: ['integrations'],
    section: 'settings',
    roles: OWNER_ONLY,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
  {
    id: 'page-map',
    labelKey: 'settings.quickLinks.pageMap',
    icon: Map,
    to: { name: 'settings-page-map' },
    routeNames: ['settings-page-map'],
    section: 'settings',
    roles: BUSINESS_ROLES,
    mobilePrimary: false,
    mobileParentId: 'settings',
  },
]

function routeNameAsString(routeName: string | symbol | null | undefined): string | null {
  return typeof routeName === 'string' ? routeName : null
}

export function getBusinessNavigation(options: BusinessNavigationOptions = {}): AppNavItem[] {
  const {
    role = null,
    simpleSellerMode = false,
    surface = 'desktop',
  } = options

  // Preserve the existing compact seller contract: the shell exposes only the
  // sale entry while the router remains responsible for role authorization.
  if (simpleSellerMode) {
    return businessNavigationItems.filter((item) => item.id === 'sales')
  }

  const roleVisible = role
    ? businessNavigationItems.filter((item) => item.roles.includes(role))
    : businessNavigationItems.filter((item) => item.id === 'sales')

  return surface === 'mobile'
    ? roleVisible.filter((item) => item.mobilePrimary)
    : roleVisible
}

export function getBusinessNavigationGroups(items: readonly AppNavItem[]): Array<{
  section: AppNavSection
  items: AppNavItem[]
}> {
  return businessNavigationSections
    .map((section) => ({
      section,
      items: items.filter((item) => item.section === section.id),
    }))
    .filter((group) => group.items.length > 0)
}

export function isBusinessNavigationItemActive(
  item: AppNavItem,
  routeName: string | symbol | null | undefined,
  surface: BusinessNavigationSurface = 'desktop',
): boolean {
  const currentRouteName = routeNameAsString(routeName)
  if (!currentRouteName) return false

  if (item.routeNames.includes(currentRouteName)) return true
  if (surface !== 'mobile' || !item.mobilePrimary) return false
  return findBusinessMobileNavigationItem(currentRouteName)?.id === item.id
}

export function findBusinessNavigationItem(
  routeName: string | symbol | null | undefined,
): AppNavItem | undefined {
  const currentRouteName = routeNameAsString(routeName)
  if (!currentRouteName) return undefined
  return businessNavigationItems.find((item) => item.routeNames.includes(currentRouteName))
}

export function findBusinessMobileNavigationItem(
  routeName: string | symbol | null | undefined,
  items: readonly AppNavItem[] = businessNavigationItems,
): AppNavItem | undefined {
  const exact = findBusinessNavigationItem(routeName)
  if (!exact) return undefined
  if (exact.mobilePrimary) return items.find((item) => item.id === exact.id)
  return items.find((item) => item.id === exact.mobileParentId)
}

export function isBusinessWorkspaceRole(role: UserRole | null | undefined): boolean {
  return role === UserRole.OWNER || role === UserRole.CASHIER || role === UserRole.WAREHOUSE
}
