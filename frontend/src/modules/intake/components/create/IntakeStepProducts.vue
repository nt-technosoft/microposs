<script setup lang="ts">
import type { ProductVariant } from '@/types/models'
import type { LineRow } from '@/modules/intake/types'
import IntakeItemsSection from '@/modules/intake/components/create/IntakeItemsSection.vue'

defineProps<{
  lines: LineRow[]
  variantDisplay: (variant: ProductVariant) => string
  normalizeCurrency: (value: unknown) => string
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
}>()

const emit = defineEmits<{
  openQuickProduct: [lineId?: string | null]
  addLine: []
  openVariantPicker: [rowId: string]
  removeLine: [rowId: string]
  updateLine: [rowId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null]
  toggleLineCurrency: [rowId: string]
}>()
</script>

<template>
  <IntakeItemsSection
    :lines="lines"
    :variant-display="variantDisplay"
      :normalize-currency="normalizeCurrency"
      :show-fx-field="showFxField"
      :format-currency-total-label="formatCurrencyTotalLabel"
      @open-quick-product="emit('openQuickProduct', $event)"
      @add-line="emit('addLine')"
      @open-variant-picker="emit('openVariantPicker', $event)"
      @remove-line="emit('removeLine', $event)"
      @update-line="(rowId, field, value) => emit('updateLine', rowId, field, value)"
      @toggle-line-currency="emit('toggleLineCurrency', $event)"
    />
</template>
