<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'

interface Option {
  value: number | null
  label: string
}

defineProps<{
  open: boolean
  quickProductName: string
  quickProductCategoryId: number | null
  quickProductBasePrice: string
  quickProductError: string | null
  isCreatingQuickProduct: boolean
  categoryOptions: Option[]
}>()

const emit = defineEmits<{
  close: []
  submit: []
  updateQuickProductName: [value: string]
  updateQuickProductCategoryId: [value: number | null]
  updateQuickProductBasePrice: [value: string]
}>()

const { t } = useI18n()
</script>

<template>
  <AppBottomSheet :open="open" :title="t('procurements.create.quickProductTitle')" @close="emit('close')">
    <form class="quick-product-form" @submit.prevent="emit('submit')">
      <div v-if="quickProductError" class="error-box">
        <AlertCircle :size="18" :stroke-width="1.75" />
        <span>{{ quickProductError }}</span>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('products.nameLabel') }} *</label>
        <input
          :value="quickProductName"
          class="input-field"
          type="text"
          :placeholder="t('procurements.create.productNamePlaceholder')"
          @input="emit('updateQuickProductName', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('products.categoryName') }}</label>
        <BaseSelect
          :model-value="quickProductCategoryId"
          :options="[{ value: null, label: t('products.noCategory') }, ...categoryOptions]"
          :title="t('products.chooseCategory')"
          :placeholder="t('products.noCategory')"
          @update:model-value="emit('updateQuickProductCategoryId', $event as number | null)"
        />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('products.basePrice') }}</label>
        <input
          :value="quickProductBasePrice"
          class="input-field"
          type="number"
          min="0"
          placeholder="0"
          @input="emit('updateQuickProductBasePrice', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <button class="btn-primary" type="submit" :disabled="isCreatingQuickProduct">
        {{ isCreatingQuickProduct ? t('procurements.create.creating') : t('procurements.create.createAndAdd') }}
      </button>
    </form>
  </AppBottomSheet>
</template>

<style scoped>
.quick-product-form { display:grid; gap: var(--space-3); }
.error-box { display:flex; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-lg); background: var(--color-error-bg); color: var(--color-danger); }
.field-group { display:grid; gap: var(--space-2); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.input-field { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.btn-primary { width:100%; height: 48px; border:none; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
</style>
