import { describe, expect, it } from 'vitest'
import { UserRole } from '@/types/enums'
import {
  businessNavigationItems,
  findBusinessMobileNavigationItem,
  findBusinessNavigationItem,
  getBusinessNavigation,
  getBusinessNavigationGroups,
  isBusinessNavigationItemActive,
  isBusinessWorkspaceRole,
} from './navigation'

describe('business navigation registry', () => {
  it('assigns every route name to exactly one desktop item', () => {
    const routeNames = businessNavigationItems.flatMap((item) => item.routeNames)
    expect(new Set(routeNames).size).toBe(routeNames.length)
  })

  it('exposes the full owner workspace and role-limited staff workspaces', () => {
    const ownerIds = getBusinessNavigation({ role: UserRole.OWNER }).map((item) => item.id)
    const cashierIds = getBusinessNavigation({ role: UserRole.CASHIER }).map((item) => item.id)
    const warehouseIds = getBusinessNavigation({ role: UserRole.WAREHOUSE }).map((item) => item.id)

    expect(ownerIds).toContain('reports')
    expect(ownerIds).toContain('supplier-payables')
    expect(cashierIds).toEqual(['sales', 'sales-history', 'settings', 'page-map'])
    expect(warehouseIds).toEqual(['products', 'stock-transfers', 'procurements', 'settings', 'page-map'])
  })

  it('keeps only primary destinations on the mobile surface', () => {
    const ids = getBusinessNavigation({ role: UserRole.OWNER, surface: 'mobile' })
      .map((item) => item.id)

    expect(ids).toEqual(['sales', 'products', 'procurements', 'reports', 'cash', 'settings'])
  })

  it('preserves simple seller mode as a single sale entry', () => {
    expect(getBusinessNavigation({ role: UserRole.OWNER, simpleSellerMode: true }).map((item) => item.id))
      .toEqual(['sales'])
    expect(getBusinessNavigation({ role: UserRole.WAREHOUSE, simpleSellerMode: true }).map((item) => item.id))
      .toEqual(['sales'])
  })

  it('uses exact route names on desktop and section fallback on mobile', () => {
    const sales = businessNavigationItems.find((item) => item.id === 'sales')!
    const history = businessNavigationItems.find((item) => item.id === 'sales-history')!

    expect(isBusinessNavigationItemActive(sales, 'sales-history')).toBe(false)
    expect(isBusinessNavigationItemActive(history, 'sales-history')).toBe(true)
    expect(isBusinessNavigationItemActive(sales, 'sales-history', 'mobile')).toBe(true)
    expect(isBusinessNavigationItemActive(sales, Symbol('sales'), 'mobile')).toBe(false)
  })

  it('maps detail routes back to the correct navigation destination', () => {
    expect(findBusinessNavigationItem('procurement-edit')?.id).toBe('procurements')
    expect(findBusinessNavigationItem('reports-sale-explanation')?.id).toBe('reports')
    expect(findBusinessMobileNavigationItem('categories')?.id).toBe('products')
    expect(findBusinessMobileNavigationItem('finance-exchange')?.id).toBe('cash')
  })

  it('groups only visible sections while preserving registry order', () => {
    const cashierItems = getBusinessNavigation({ role: UserRole.CASHIER })
    const groups = getBusinessNavigationGroups(cashierItems)

    expect(groups.map((group) => group.section.id)).toEqual(['sales', 'settings'])
    expect(groups[0]?.items.map((item) => item.id)).toEqual(['sales', 'sales-history'])
  })

  it('recognizes only roles belonging to the business workspace', () => {
    expect(isBusinessWorkspaceRole(UserRole.OWNER)).toBe(true)
    expect(isBusinessWorkspaceRole(UserRole.CASHIER)).toBe(true)
    expect(isBusinessWorkspaceRole(UserRole.WAREHOUSE)).toBe(true)
    expect(isBusinessWorkspaceRole(UserRole.INVESTOR)).toBe(false)
    expect(isBusinessWorkspaceRole(UserRole.PLATFORM_ADMIN)).toBe(false)
  })
})
