import { computed, type Ref } from 'vue'
import type { ExpenseRow, LineRow } from '@/modules/intake/types'

interface UseIntakeCurrencyOptions {
  lines: Ref<LineRow[]>
  expenses: Ref<ExpenseRow[]>
  contractCurrency: Ref<string>
  latestUsdRate: Ref<string>
}

export function useIntakeCurrency({
  lines,
  expenses,
  contractCurrency,
  latestUsdRate,
}: UseIntakeCurrencyOptions) {
  function normalizeCurrency(value: unknown): string {
    const currency = String(value ?? 'UZS').trim().toUpperCase()
    if (currency === 'USD') return 'USD'
    return 'UZS'
  }

  function defaultFxRateForCurrency(currency: string): string {
    return normalizeCurrency(currency) === 'UZS' ? '1' : latestUsdRate.value
  }

  function nextCurrency(currency: string): string {
    return normalizeCurrency(currency) === 'UZS' ? 'USD' : 'UZS'
  }

  function parsePositiveNumber(raw: unknown): number {
    const value = Number.parseFloat(String(raw ?? ''))
    if (!Number.isFinite(value) || value <= 0) return 0
    return value
  }

  function getFxRateValue(currency: string, raw: unknown): number {
    if (normalizeCurrency(currency) === 'UZS') return 1
    return parsePositiveNumber(raw)
  }

  function moneyAmountToUzs(amount: number, currency: string, fxRate: unknown): number {
    const normalizedCurrency = normalizeCurrency(currency)
    if (!Number.isFinite(amount) || amount <= 0) return 0
    if (normalizedCurrency === 'UZS') return amount
    return amount * getFxRateValue(normalizedCurrency, fxRate)
  }

  function setLineCurrency(rowId: string, currencyValue: string | number | boolean | null): void {
    const currency = normalizeCurrency(currencyValue)
    lines.value = lines.value.map((line) => line.id === rowId
      ? {
          ...line,
          currency,
          fx_rate: currency === line.currency
            ? line.fx_rate
            : currency === 'UZS'
              ? '1'
              : defaultFxRateForCurrency(currency),
        }
      : line)
  }

  function toggleLineCurrency(rowId: string): void {
    const line = lines.value.find((item) => item.id === rowId)
    if (!line) return
    setLineCurrency(rowId, nextCurrency(line.currency))
  }

  function setExpenseCurrency(rowId: string, currencyValue: string | number | boolean | null): void {
    const currency = normalizeCurrency(currencyValue)
    expenses.value = expenses.value.map((expense) => expense.id === rowId
      ? {
          ...expense,
          currency,
          fx_rate: currency === expense.currency
            ? expense.fx_rate
            : currency === 'UZS'
              ? '1'
              : defaultFxRateForCurrency(currency),
        }
      : expense)
  }

  function toggleExpenseCurrency(rowId: string): void {
    const expense = expenses.value.find((item) => item.id === rowId)
    if (!expense) return
    setExpenseCurrency(rowId, nextCurrency(expense.currency))
  }

  function showFxField(currency: string): boolean {
    return normalizeCurrency(currency) !== 'UZS'
  }

  function formatCurrencyTotalLabel(currency: string): string {
    return normalizeCurrency(currency) === 'USD' ? 'USD -> UZS' : 'UZS'
  }

  const grandTotal = computed(() => lines.value.reduce((sum, line) => {
    const lineAmount = (parseFloat(line.quantity) || 0) * (parseFloat(line.cost_per_unit) || 0)
    return sum + moneyAmountToUzs(lineAmount, line.currency, line.fx_rate)
  }, 0))

  const expenseTotal = computed(() => expenses.value.reduce((sum, expense) => {
    return sum + moneyAmountToUzs(parseFloat(expense.amount) || 0, expense.currency, expense.fx_rate)
  }, 0))

  const procurementTotal = computed(() => grandTotal.value + expenseTotal.value)

  const procurementTotalInContractCurrency = computed(() => {
    const totalUzs = procurementTotal.value
    if (normalizeCurrency(contractCurrency.value) === 'UZS') return totalUzs
    const fx = parsePositiveNumber(latestUsdRate.value)
    if (fx <= 0) return 0
    return totalUzs / fx
  })

  const hasForeignCurrency = computed(() => {
    return lines.value.some((line) => normalizeCurrency(line.currency) !== 'UZS')
      || expenses.value.some((expense) => normalizeCurrency(expense.currency) !== 'UZS')
  })

  return {
    normalizeCurrency,
    defaultFxRateForCurrency,
    nextCurrency,
    parsePositiveNumber,
    getFxRateValue,
    moneyAmountToUzs,
    setLineCurrency,
    toggleLineCurrency,
    setExpenseCurrency,
    toggleExpenseCurrency,
    showFxField,
    formatCurrencyTotalLabel,
    grandTotal,
    expenseTotal,
    procurementTotal,
    procurementTotalInContractCurrency,
    hasForeignCurrency,
  }
}
