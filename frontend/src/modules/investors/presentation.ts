import type { InvestorDashboardAggregate, InvestorLedgerTotals } from '@/types/models'
import { formatPrice } from '@/utils/currency'

type AggregateLike = Pick<InvestorDashboardAggregate, 'by_currency' | 'functional_uzs'>

const currencyPriority = ['USD', 'UZS']

function nonZero(value: string | undefined): boolean {
  return Math.abs(Number.parseFloat(value ?? '0')) > 0.000001
}

function normalizeStatus(value: string | null | undefined): string {
  return String(value ?? '').trim().toUpperCase()
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
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU', {
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
  return `${(parsed * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
}

export function procurementTypeLabel(type: string | null | undefined): string {
  const normalized = String(type ?? '').trim().toUpperCase()
  if (normalized === 'PARTNERSHIP') return 'Партнёрский приход'
  if (normalized === 'MUSHARAKA') return 'Мушарака'
  if (normalized === 'OWN_FUNDS') return 'Свои средства'
  if (normalized === 'DISTRIBUTOR') return 'Дистрибьютор'
  return type || '—'
}

export function procurementStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeStatus(status)
  if (normalized === 'OPEN') return 'Открыт'
  if (normalized === 'PARTIALLY_RECEIVED') return 'Частично принят'
  if (normalized === 'RECEIVED') return 'Завершён'
  if (normalized === 'CLOSED') return 'Закрыт'
  if (normalized === 'CANCELLED') return 'Отменён'
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
  if (normalized === 'OPEN' || normalized === 'ACTIVE') return 'Активен'
  if (normalized === 'CLOSED') return 'Закрыт'
  if (normalized === 'CANCELLED') return 'Отменён'
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
  if (normalized === 'CAPITAL_IN') return 'Внос капитала'
  if (normalized === 'CAPITAL_OUT') return 'Возврат капитала'
  if (normalized === 'PROFIT_ACCRUED') return 'Начисление прибыли'
  if (normalized === 'DIVIDEND_PAID') return 'Выплата дивиденда'
  if (normalized === 'LOSS_INCURRED') return 'Убыток списания'
  if (normalized === 'PROFIT_REVERSED') return 'Сторно прибыли'
  return entryType
}

export function ledgerEntryTone(entryType: string): 'positive' | 'negative' | 'neutral' {
  const normalized = String(entryType ?? '').trim().toUpperCase()
  if (normalized === 'CAPITAL_IN' || normalized === 'PROFIT_ACCRUED') return 'positive'
  if (normalized === 'LOSS_INCURRED' || normalized === 'PROFIT_REVERSED') return 'negative'
  return 'neutral'
}
