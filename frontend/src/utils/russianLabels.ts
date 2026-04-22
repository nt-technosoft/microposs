/**
 * Human-friendly Russian labels for system values coming from import/API.
 * We keep source values intact in DB and only normalize display text.
 */

const LOCATION_LABELS: Record<string, string> = {
  ASOSIY: 'Основной склад',
  'MAIN WAREHOUSE': 'Основной склад',
  WAREHOUSE: 'Склад',
  DOKON: 'Основной магазин',
  'MAIN STORE': 'Основной магазин',
  STORE: 'Магазин',
}

const RECONCILIATION_KEYS: Record<string, string> = {
  cash_balance: 'Остатки по кассе и банку',
  inventory_by_location: 'Остатки по складам',
  receivables_total_uzs: 'Дебиторская задолженность',
  payables_total_uzs: 'Кредиторская задолженность',
  sales_revenue_uzs: 'Выручка от продаж',
  sales_cogs_uzs: 'Себестоимость продаж',
  gross_profit_uzs: 'Валовая прибыль',
}

const GAP_CATEGORIES: Record<string, string> = {
  parse: 'Ошибки чтения',
  mapping: 'Ошибки сопоставления',
  domain: 'Нарушение доменных правил',
  other: 'Прочие ошибки',
}

function normalizeKey(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toUpperCase()
}

export function toRussianLocationLabel(name: string): string {
  const normalized = normalizeKey(name)
  return LOCATION_LABELS[normalized] ?? name
}

export function toRussianReconciliationKey(key: string): string {
  return RECONCILIATION_KEYS[key] ?? key
}

export function toRussianGapCategory(key: string): string {
  return GAP_CATEGORIES[key] ?? key
}
