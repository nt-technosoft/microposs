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

  function addItem(item: CartItem) {
    const existing = items.value.find(
      (i) =>
        i.product_variant.id === item.product_variant.id &&
        i.lot_id === item.lot_id &&
        i.unit_price === item.unit_price,
    )

    if (existing) {
      // Create new array (immutability)
      items.value = items.value.map((i) =>
        i === existing ? { ...i, quantity: i.quantity + item.quantity } : i,
      )
    } else {
      items.value = [...items.value, { ...item }]
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
    items.value = items.value.map((item, i) =>
      i === index ? { ...item, quantity } : item,
    )
    saveToStorage()
  }

  function clear() {
    items.value = []
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
    itemCount,
    total,
    isEmpty,
    addItem,
    removeItem,
    updateQuantity,
    clear,
  }
})
