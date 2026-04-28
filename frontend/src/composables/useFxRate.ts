import { computed, ref } from 'vue'
import { fetchLatestFxRate } from '@/api/finance'

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

  async function load(onDate?: string): Promise<string> {
    isLoading.value = true
    error.value = ''
    try {
      const latest = await fetchLatestFxRate({
        base_currency: baseCurrency,
        quote_currency: quoteCurrency,
        ...(onDate ? { on_date: onDate } : {}),
      })
      rate.value = String(latest.rate)
      rateDate.value = latest.rate_date
      source.value = latest.source
      return rate.value
    } catch (err: unknown) {
      clear()
      error.value = apiErrorMessage(
        err,
        `Курс ${baseCurrency}/${quoteCurrency} не найден. Синхронизируйте курс или укажите вручную.`,
      )
      throw err
    } finally {
      isLoading.value = false
    }
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
