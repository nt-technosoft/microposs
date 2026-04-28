/**
 * Cart store — the most critical store for POS UX.
 * Persisted to localStorage for crash recovery.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CartItem } from '@/types/models'
import { PricingMode } from '@/types/enums'

export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>(loadFromStorage())
  const posSessionId = ref<number | null>(null)
  const locationId = ref<number | null>(inferLocationId(items.value))

  const itemCount = computed(() =>
    items.value.reduce((sum, item) => sum + item.quantity, 0),
  )

  const total = computed(() =>
    items.value
      .reduce(
        (sum, item) => sum + parseFloat(item.unit_price) * item.quantity,
        0,
      )
      .toFixed(2),
  )

  const totalsByCurrency = computed(() => {
    const totals = new Map<string, number>()
    for (const item of items.value) {
      const currency = normalizeCurrency(item.operation_currency)
      const nativeUnit = nativeUnitPrice(item)
      totals.set(currency, (totals.get(currency) || 0) + nativeUnit * item.quantity)
    }
    return Array.from(totals.entries())
      .map(([currency, amount]) => ({ currency, amount: amount.toFixed(2) }))
      .sort((left, right) => left.currency.localeCompare(right.currency))
  })

  const isEmpty = computed(() => items.value.length === 0)

  const hasAvailabilityIssues = computed(() =>
    items.value.some((item) => {
      const available = item.available_stock
      return typeof available === 'number' && item.quantity > available
    }),
  )

  const hasLocationMismatch = computed(() =>
    locationId.value !== null
    && items.value.some((item) => item.location_id !== locationId.value),
  )

  function inferLocationId(source: CartItem[]): number | null {
    const firstLocation = source.find((item) => item.location_id !== undefined)?.location_id
    return typeof firstLocation === 'number' ? firstLocation : null
  }

  function setLocation(nextLocationId: number | null) {
    const hasItemsForAnotherLocation = nextLocationId !== null
      && items.value.some((item) => item.location_id !== undefined && item.location_id !== nextLocationId)
    if (
      (locationId.value !== null && nextLocationId !== null && locationId.value !== nextLocationId)
      || hasItemsForAnotherLocation
    ) {
      clear()
      locationId.value = nextLocationId
      return
    }
    locationId.value = nextLocationId
  }

  function maxAllowed(item: CartItem): number {
    const available = item.available_stock
    return typeof available === 'number' && Number.isFinite(available)
      ? Math.max(0, available)
      : 9999
  }

  function normalizeCurrency(currency: string | null | undefined): 'UZS' | 'USD' {
    return String(currency || 'UZS').toUpperCase() === 'USD' ? 'USD' : 'UZS'
  }

  function nativeUnitPrice(item: CartItem): number {
    const native = Number.parseFloat(String(item.operation_unit_price ?? ''))
    if (Number.isFinite(native) && native > 0) return native
    return Number.parseFloat(item.unit_price) || 0
  }

  function functionalFromNative(nativeAmount: number, currency: 'UZS' | 'USD', fxRate: string | number | null | undefined): string {
    if (currency === 'UZS') return nativeAmount.toFixed(2)
    const fx = Number.parseFloat(String(fxRate || '0'))
    if (!Number.isFinite(fx) || fx <= 0) return '0.00'
    return (nativeAmount * fx).toFixed(2)
  }

  function addItem(item: CartItem) {
    if (item.location_id !== undefined) {
      setLocation(item.location_id)
    }

    const existing = items.value.find(
      (i) =>
        i.product_variant.id === item.product_variant.id &&
        i.lot_id === item.lot_id &&
        i.unit_price === item.unit_price &&
        normalizeCurrency(i.operation_currency) === normalizeCurrency(item.operation_currency),
    )

    if (existing) {
      const available = maxAllowed(item)
      const nextQuantity = Math.min(existing.quantity + item.quantity, available)
      // Create new array (immutability)
      items.value = items.value.map((i) =>
        i === existing
          ? {
              ...i,
              quantity: nextQuantity,
              location_id: item.location_id ?? i.location_id,
              available_stock: item.available_stock ?? i.available_stock,
            }
          : i,
      )
    } else {
      items.value = [...items.value, { ...item, quantity: Math.min(item.quantity, maxAllowed(item)) }]
    }
    saveToStorage()
  }

  function removeItem(index: number) {
    items.value = items.value.filter((_, i) => i !== index)
    saveToStorage()
  }

  function updateQuantity(index: number, quantity: number) {
    if (quantity <= 0) {
      removeItem(index)
      return
    }
    const current = items.value[index]
    const nextQuantity = current ? Math.min(quantity, maxAllowed(current)) : quantity
    items.value = items.value.map((item, i) =>
      i === index ? { ...item, quantity: nextQuantity } : item,
    )
    saveToStorage()
  }

  function updateItemCurrency(index: number, currency: 'UZS' | 'USD', fxRate?: string | number | null) {
    const current = items.value[index]
    if (!current) return
    const nextCurrency = normalizeCurrency(currency)
    const currentFunctional = Number.parseFloat(current.unit_price) || 0
    const fx = nextCurrency === 'USD' ? Number.parseFloat(String(fxRate || current.fx_rate || '0')) : 1
    if (nextCurrency === 'USD' && (!Number.isFinite(fx) || fx <= 0)) return
    const native = nextCurrency === 'USD' ? currentFunctional / fx : currentFunctional
    items.value = items.value.map((item, i) => i === index
      ? {
          ...item,
          operation_currency: nextCurrency,
          operation_unit_price: native.toFixed(2),
          fx_rate: nextCurrency === 'USD' ? fx.toFixed(6) : '1',
        }
      : item)
    saveToStorage()
  }

  function updateItemNativePrice(index: number, nativePrice: number, fxRate?: string | number | null) {
    const current = items.value[index]
    if (!current || !Number.isFinite(nativePrice) || nativePrice <= 0) return
    const currency = normalizeCurrency(current.operation_currency)
    const fx = currency === 'USD' ? (fxRate ?? current.fx_rate) : '1'
    const unitPrice = functionalFromNative(nativePrice, currency, fx)
    items.value = items.value.map((item, i) => i === index
      ? {
          ...item,
          operation_unit_price: nativePrice.toFixed(2),
          fx_rate: currency === 'USD' ? String(fx) : '1',
          unit_price: unitPrice,
          price_changed: unitPrice !== item.base_price,
        }
      : item)
    saveToStorage()
  }

  function clear() {
    items.value = []
    locationId.value = null
    saveToStorage()
  }

  function saveToStorage() {
    localStorage.setItem('microposs_cart', JSON.stringify(items.value))
  }

  function loadFromStorage(): CartItem[] {
    const stored = localStorage.getItem('microposs_cart')
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as Partial<CartItem>[]
        if (!Array.isArray(parsed)) return []
        return parsed
          .filter((item): item is Partial<CartItem> & { product_variant: CartItem['product_variant']; product_name: string } => (
            item !== null
            && typeof item === 'object'
            && item.product_variant !== undefined
            && typeof item.product_name === 'string'
          ))
          .map((item) => ({
            product_variant: item.product_variant,
            product_name: item.product_name,
            pricing_mode: item.pricing_mode ?? PricingMode.DEFAULT_EDITABLE,
            lot_id: item.lot_id ?? null,
            location_id: typeof item.location_id === 'number' ? item.location_id : null,
            available_stock: typeof item.available_stock === 'number' ? item.available_stock : null,
            quantity: Number.isFinite(item.quantity) ? Number(item.quantity) : 1,
            operation_currency: normalizeCurrency(item.operation_currency),
            operation_unit_price: String(item.operation_unit_price ?? item.unit_price ?? '0'),
            fx_rate: String(item.fx_rate ?? '1'),
            unit_price: String(item.unit_price ?? '0'),
            base_price: String(item.base_price ?? item.unit_price ?? '0'),
            price_changed: Boolean(item.price_changed),
            discount_reason_id: item.discount_reason_id ?? null,
          }))
      } catch {
        return []
      }
    }
    return []
  }

  return {
    items,
    posSessionId,
    locationId,
    itemCount,
    total,
    totalsByCurrency,
    isEmpty,
    hasAvailabilityIssues,
    hasLocationMismatch,
    setLocation,
    addItem,
    removeItem,
    updateQuantity,
    updateItemCurrency,
    updateItemNativePrice,
    clear,
  }
})
