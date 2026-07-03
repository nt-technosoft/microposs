import { computed, ref } from 'vue'
import { fetchLatestFxRate, refreshOfficialFxRate, type ExchangeRateItem } from '@/api/finance'
import { translateNow } from '@/i18n'

interface UseFxRateOptions {
  baseCurrency?: string
  quoteCurrency?: string
}

function normalizeCurrency(value: string | null | undefined, fallback: string): string {
  return String(value || fallback).trim().toUpperCase()
}

function apiErrorMessage(error: unknown, fallback: string): string {
  const response = error as { response?: { data?: { detail?: string } } }
  return response.response?.data?.detail || (error instanceof Error ? error.message : fallback)
}

function isMissingRateError(error: unknown): boolean {
  const response = error as { response?: { status?: number; data?: { code?: string } } }
  return response.response?.status === 404 && response.response?.data?.code === 'fx_rate_missing'
}

const fxRateCache = new Map<string, ExchangeRateItem>()
const pendingFxRateLoads = new Map<string, Promise<ExchangeRateItem>>()

function cacheKey(baseCurrency: string, quoteCurrency: string, onDate?: string): string {
  return `${baseCurrency}/${quoteCurrency}/${onDate || 'latest'}`
}

export function useFxRate(options: UseFxRateOptions = {}) {
  const baseCurrency = normalizeCurrency(options.baseCurrency, 'USD')
  const quoteCurrency = normalizeCurrency(options.quoteCurrency, 'UZS')
  const rate = ref('')
  const rateDate = ref('')
  const source = ref('')
  const isLoading = ref(false)
  const error = ref('')

  const hasRate = computed(() => {
    const parsed = Number.parseFloat(rate.value)
    return Number.isFinite(parsed) && parsed > 0
  })

  function clear(): void {
    rate.value = ''
    rateDate.value = ''
    source.value = ''
    error.value = ''
  }

  function applyRate(latest: ExchangeRateItem): string {
    rate.value = String(latest.rate)
    rateDate.value = latest.rate_date
    source.value = latest.source
    error.value = ''
    return rate.value
  }

  async function load(onDate?: string): Promise<string> {
    const key = cacheKey(baseCurrency, quoteCurrency, onDate)
    const cached = fxRateCache.get(key)
    if (cached) return applyRate(cached)

    isLoading.value = true
    error.value = ''
    try {
      let pending = pendingFxRateLoads.get(key)
      if (!pending) {
        pending = (async () => {
          try {
            return await fetchLatestFxRate({
              base_currency: baseCurrency,
              quote_currency: quoteCurrency,
              ...(onDate ? { on_date: onDate } : {}),
            })
          } catch (err: unknown) {
            if (!isMissingRateError(err)) throw err
            const refreshed = await refreshOfficialFxRate({
              base_currency: baseCurrency,
              quote_currency: quoteCurrency,
              ...(onDate ? { rate_date: onDate } : {}),
            })
            return refreshed.rate
          }
        })()
        pendingFxRateLoads.set(key, pending)
      }
      const latest = await pending
      fxRateCache.set(key, latest)
      if (!onDate) {
        fxRateCache.set(cacheKey(baseCurrency, quoteCurrency, latest.rate_date), latest)
      }
      return applyRate(latest)
    } catch (err: unknown) {
      clear()
      error.value = apiErrorMessage(
        err,
        translateNow('finance.rateMissing', { base: baseCurrency, quote: quoteCurrency }),
      )
      throw err
    } finally {
      pendingFxRateLoads.delete(key)
      isLoading.value = false
    }
  }

  const initialCached = fxRateCache.get(cacheKey(baseCurrency, quoteCurrency))
  if (initialCached) {
    applyRate(initialCached)
  }

  function rateForCurrency(currency: string | null | undefined): string {
    const normalized = normalizeCurrency(currency, quoteCurrency)
    if (normalized === quoteCurrency) return '1'
    if (normalized === baseCurrency) return rate.value
    return ''
  }

  return {
    baseCurrency,
    quoteCurrency,
    rate,
    rateDate,
    source,
    isLoading,
    error,
    hasRate,
    load,
    clear,
    rateForCurrency,
  }
}
