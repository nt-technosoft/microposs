import type { InvestorDashboardAggregate, InvestorLedgerTotals } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import { getStoredLocale, translateNow } from '@/i18n'

type AggregateLike = Pick<InvestorDashboardAggregate, 'by_currency' | 'functional_uzs'>

const currencyPriority = ['USD', 'UZS']

function nonZero(value: string | undefined): boolean {
  return Math.abs(Number.parseFloat(value ?? '0')) > 0.000001
}

function normalizeStatus(value: string | null | undefined): string {
  return String(value ?? '').trim().toUpperCase()
}

function intlLocale(): string {
  const locale = getStoredLocale()
  if (locale === 'en') return 'en-US'
  if (locale === 'uz') return 'uz-Latn-UZ'
  return 'ru-RU'
}

export function formatAggregateAmount(
  aggregate: AggregateLike | null | undefined,
  field: keyof InvestorLedgerTotals,
  preferredCurrency?: string,
): string {
  if (!aggregate) return formatPrice('0', 'UZS')

  const currencies = Object.keys(aggregate.by_currency ?? {}).sort((a, b) => {
    const aIndex = currencyPriority.indexOf(a)
    const bIndex = currencyPriority.indexOf(b)
    return (aIndex === -1 ? 99 : aIndex) - (bIndex === -1 ? 99 : bIndex)
  })

  if (preferredCurrency && nonZero(aggregate.by_currency?.[preferredCurrency]?.[field])) {
    return formatPrice(aggregate.by_currency[preferredCurrency][field], preferredCurrency)
  }

  const parts = currencies
    .map((currency) => ({ currency, amount: aggregate.by_currency[currency][field] }))
    .filter(({ amount }) => nonZero(amount))

  if (parts.length === 0) {
    return formatPrice(aggregate.functional_uzs?.[field] ?? '0', 'UZS')
  }

  return parts
    .map(({ currency, amount }) => formatPrice(amount, currency))
    .join(' + ')
}

export function formatFunctionalAmount(
  aggregate: AggregateLike | null | undefined,
  field: keyof InvestorLedgerTotals,
): string {
  return formatPrice(aggregate?.functional_uzs?.[field] ?? '0', 'UZS')
}

export function formatBalanceLabel(balances: Record<string, string> | null | undefined): string {
  const parts = Object.entries(balances ?? {})
    .filter(([, amount]) => Math.abs(Number(amount || 0)) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
}

export function formatShortDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString(intlLocale(), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(intlLocale(), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatRatioPercent(value: string | number | null | undefined): string {
  const parsed = Number(value ?? 0)
  if (!Number.isFinite(parsed)) return '0%'
  return `${(parsed * 100).toLocaleString(intlLocale(), { maximumFractionDigits: 2 })}%`
}

export function procurementTypeLabel(type: string | null | undefined): string {
  const normalized = String(type ?? '').trim().toUpperCase()
  if (normalized === 'PARTNERSHIP') return translateNow('domain.procurementType.PARTNERSHIP')
  if (normalized === 'MUSHARAKA') return translateNow('domain.procurementType.MUSHARAKA')
  if (normalized === 'OWN_FUNDS') return translateNow('domain.procurementType.OWN_FUNDS')
  if (normalized === 'DISTRIBUTOR') return translateNow('domain.procurementType.DISTRIBUTOR')
  return type || '—'
}

export function procurementStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeStatus(status)
  if (normalized === 'OPEN') return translateNow('domain.procurementStatus.OPEN')
  if (normalized === 'PARTIALLY_RECEIVED') return translateNow('domain.procurementStatus.PARTIALLY_RECEIVED')
  if (normalized === 'RECEIVED') return translateNow('domain.procurementStatus.RECEIVED')
  if (normalized === 'CLOSED') return translateNow('domain.procurementStatus.CLOSED')
  if (normalized === 'CANCELLED') return translateNow('domain.procurementStatus.CANCELLED')
  return status || '—'
}

export function procurementStatusTone(status: string | null | undefined): string {
  const normalized = normalizeStatus(status)
  if (normalized === 'RECEIVED' || normalized === 'CLOSED') return 'success'
  if (normalized === 'OPEN' || normalized === 'PARTIALLY_RECEIVED') return 'warning'
  if (normalized === 'CANCELLED') return 'danger'
  return 'muted'
}

export function agreementStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeStatus(status)
  if (normalized === 'OPEN' || normalized === 'ACTIVE') return translateNow('domain.procurementStatus.OPEN')
  if (normalized === 'CLOSED') return translateNow('domain.procurementStatus.CLOSED')
  if (normalized === 'CANCELLED') return translateNow('domain.procurementStatus.CANCELLED')
  return status || '—'
}

export function agreementStatusTone(status: string | null | undefined): string {
  const normalized = normalizeStatus(status)
  if (normalized === 'OPEN' || normalized === 'ACTIVE') return 'success'
  if (normalized === 'CLOSED') return 'muted'
  if (normalized === 'CANCELLED') return 'danger'
  return 'warning'
}

export function ledgerEntryLabel(entryType: string): string {
  const normalized = String(entryType ?? '').trim().toUpperCase()
  if (normalized === 'CAPITAL_IN') return translateNow('domain.ledgerType.CAPITAL_IN')
  if (normalized === 'CAPITAL_OUT') return translateNow('domain.ledgerType.CAPITAL_OUT')
  if (normalized === 'PROFIT_ACCRUED') return translateNow('domain.ledgerType.PROFIT_ACCRUED')
  if (normalized === 'DIVIDEND_PAID') return translateNow('domain.ledgerType.DIVIDEND_PAID')
  if (normalized === 'LOSS_INCURRED') return translateNow('domain.ledgerType.LOSS_INCURRED')
  if (normalized === 'PROFIT_REVERSED') return translateNow('domain.ledgerType.PROFIT_REVERSED')
  return entryType
}

export function ledgerEntryTone(entryType: string): 'positive' | 'negative' | 'neutral' {
  const normalized = String(entryType ?? '').trim().toUpperCase()
  if (normalized === 'CAPITAL_IN' || normalized === 'PROFIT_ACCRUED') return 'positive'
  if (normalized === 'LOSS_INCURRED' || normalized === 'PROFIT_REVERSED') return 'negative'
  return 'neutral'
}
