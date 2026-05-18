<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import type { ProductVariant } from '@/types/models'
import type { SelectOption } from './types'

defineProps<{
  open: boolean
  search: string
  category: number | null
  categoryOptions: SelectOption<number | null>[]
  variants: ProductVariant[]
  variantDisplay: (variant: ProductVariant) => string
}>()

const emit = defineEmits<{
  close: []
  updateSearch: [value: string]
  updateCategory: [value: number | null]
  newProduct: []
  select: [variant: ProductVariant]
}>()
</script>

<template>
  <AppBottomSheet :open="open" title="Выбор товара" @close="emit('close')">
    <div class="sheet-body">
      <div class="sheet-actions">
        <input
          class="input-field"
          type="text"
          placeholder="Поиск товара"
          :value="search"
          @input="emit('updateSearch', ($event.target as HTMLInputElement).value)"
        />
        <button class="soft-action" type="button" @click="emit('newProduct')">
          <Plus :size="14" :stroke-width="2.4" />
          Новый
        </button>
      </div>
      <BaseSelect
        :model-value="category"
        :options="categoryOptions"
        title="Категория"
        placeholder="Все категории"
        @update:model-value="(value) => emit('updateCategory', value === null ? null : Number(value))"
      />
      <div class="variant-list">
        <button v-for="variant in variants" :key="variant.id" class="variant-row" type="button" @click="emit('select', variant)">
          <span>{{ variantDisplay(variant) }}</span>
          <strong>{{ variant.price ?? variant.effective_price ?? '0' }}</strong>
        </button>
      </div>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body {
  display: grid;
  gap: 10px;
}

.sheet-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.input-field {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.soft-action {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.variant-list {
  display: grid;
  gap: 8px;
  max-height: 52vh;
  overflow: auto;
}

.variant-row {
  width: 100%;
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  text-align: left;
}

.variant-row span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.variant-row strong {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
}
</style>
