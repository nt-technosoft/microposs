import { translateNow } from '@/i18n'

/**
 * Human-friendly labels for system values coming from import/API.
 * We keep source values intact in DB and only normalize display text.
 */

const LOCATION_KEYS: Record<string, string> = {
  ASOSIY: 'domain.locationFallback.ASOSIY',
  'MAIN WAREHOUSE': 'domain.locationFallback.MAIN_WAREHOUSE',
  WAREHOUSE: 'domain.locationFallback.WAREHOUSE',
  DOKON: 'domain.locationFallback.DOKON',
  'MAIN STORE': 'domain.locationFallback.MAIN_STORE',
  STORE: 'domain.locationFallback.STORE',
}

const RECONCILIATION_LABEL_KEYS: Record<string, string> = {
  cash_balance: 'domain.reconciliation.cash_balance',
  inventory_by_location: 'domain.reconciliation.inventory_by_location',
  receivables_total_uzs: 'domain.reconciliation.receivables_total_uzs',
  payables_total_uzs: 'domain.reconciliation.payables_total_uzs',
  sales_revenue_uzs: 'domain.reconciliation.sales_revenue_uzs',
  sales_cogs_uzs: 'domain.reconciliation.sales_cogs_uzs',
  gross_profit_uzs: 'domain.reconciliation.gross_profit_uzs',
}

const GAP_CATEGORY_KEYS: Record<string, string> = {
  parse: 'domain.gapCategory.parse',
  mapping: 'domain.gapCategory.mapping',
  domain: 'domain.gapCategory.domain',
  other: 'domain.gapCategory.other',
}

function normalizeKey(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toUpperCase()
}

export function toRussianLocationLabel(name: string): string {
  const normalized = normalizeKey(name)
  const key = LOCATION_KEYS[normalized]
  return key ? translateNow(key) : name
}

export function toRussianReconciliationKey(key: string): string {
  const labelKey = RECONCILIATION_LABEL_KEYS[key]
  return labelKey ? translateNow(labelKey) : key
}

export function toRussianGapCategory(key: string): string {
  const labelKey = GAP_CATEGORY_KEYS[key]
  return labelKey ? translateNow(labelKey) : key
}
