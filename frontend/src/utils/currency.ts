/**
 * Currency formatting utilities.
 */

const DEFAULT_CURRENCY = 'UZS'

const formatters = new Map<string, Intl.NumberFormat>()

function getFormatter(currency: string): Intl.NumberFormat {
  if (!formatters.has(currency)) {
    formatters.set(
      currency,
      new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency,
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      }),
    )
  }
  return formatters.get(currency)!
}

export function formatPrice(
  amount: number | string,
  currency: string = DEFAULT_CURRENCY,
): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return '—'
  return getFormatter(currency).format(num)
}

export function formatPriceCompact(
  amount: number | string,
  currency: string = DEFAULT_CURRENCY,
): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return '—'

  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M ${currency}`
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(0)}K ${currency}`
  }
  return getFormatter(currency).format(num)
}
