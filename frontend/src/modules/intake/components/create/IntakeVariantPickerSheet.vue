<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import ProductSupplierBadge from '@/components/composite/ProductSupplierBadge.vue'
import type { ProductVariant } from '@/types/models'

interface Option {
  value: number | null
  label: string
}

const props = defineProps<{
  open: boolean
  variantSearch: string
  categoryOptions: Option[]
  selectedCategory: number | null
  filteredVariants: ProductVariant[]
  variantDisplay: (variant: ProductVariant) => string
}>()

const emit = defineEmits<{
  close: []
  updateVariantSearch: [value: string]
  openQuickProduct: []
  updateSelectedCategory: [value: number | null]
  selectVariant: [variant: ProductVariant]
}>()

const { t } = useI18n()
const searchDraft = ref(props.variantSearch)
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

function updateSearchDraft(value: string): void {
  searchDraft.value = value
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
  searchDebounceTimer = setTimeout(() => {
    emit('updateVariantSearch', value)
  }, 300)
}

watch(
  () => props.variantSearch,
  (value) => {
    if (value !== searchDraft.value) {
      searchDraft.value = value
    }
  },
)

onBeforeUnmount(() => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer)
  }
})
</script>

<template>
  <AppBottomSheet :open="open" :title="t('products.selectVariant')" @close="emit('close')">
    <div class="sheet-body">
      <div class="sheet-actions">
        <input
          :value="searchDraft"
          class="input-field"
          type="text"
          :placeholder="t('procurements.create.searchProduct')"
          @input="updateSearchDraft(($event.target as HTMLInputElement).value)"
        />
        <button class="btn-add-small" type="button" @click="emit('openQuickProduct')">
          <Plus :size="14" :stroke-width="2.5" />
          {{ t('common.new') }}
        </button>
      </div>
      <BaseSelect
        :model-value="selectedCategory"
        :options="[{ value: null, label: t('products.allCategories') }, ...categoryOptions]"
        :title="t('products.categoryName')"
        :placeholder="t('procurements.create.categoryFilter')"
        @update:model-value="emit('updateSelectedCategory', $event as number | null)"
      />
      <div class="variant-list">
        <button v-for="variant in filteredVariants" :key="variant.id" class="variant-row" @click="emit('selectVariant', variant)">
          <span class="variant-main">
            <span>{{ variantDisplay(variant) }}</span>
            <ProductSupplierBadge :variant="variant" />
          </span>
          <span class="tabular-nums price">{{ variant.price ?? variant.effective_price ?? '0' }}</span>
        </button>
      </div>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display:grid; gap: var(--space-3); }
.sheet-actions { display:grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-2); align-items:center; }
.input-field { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.btn-add-small { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-1); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-medium); white-space: nowrap; }
.variant-list { display:grid; gap: var(--space-2); max-height: 40vh; overflow:auto; }
.variant-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); text-align:left; }
.variant-main { min-width:0; display:grid; gap: 6px; color: var(--color-text-primary); font-weight: var(--font-medium); }
.price { flex: 0 0 auto; color: var(--color-text-secondary); font-size: var(--text-sm); }

@media (max-width: 520px) {
  .sheet-actions { grid-template-columns: 1fr; }
}
</style>
