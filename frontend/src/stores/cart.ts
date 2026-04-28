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

  function addItem(item: CartItem) {
    if (item.location_id !== undefined) {
      setLocation(item.location_id)
    }

    const existing = items.value.find(
      (i) =>
        i.product_variant.id === item.product_variant.id &&
        i.lot_id === item.lot_id &&
        i.unit_price === item.unit_price,
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
    isEmpty,
    hasAvailabilityIssues,
    hasLocationMismatch,
    setLocation,
    addItem,
    removeItem,
    updateQuantity,
    clear,
  }
})
