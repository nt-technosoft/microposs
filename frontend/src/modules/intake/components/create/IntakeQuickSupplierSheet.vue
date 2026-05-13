<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'

defineProps<{
  open: boolean
  quickSupplierName: string
  quickSupplierPhone: string
  quickSupplierEmail: string
  quickSupplierError: string | null
  isCreatingQuickSupplier: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: []
  updateQuickSupplierName: [value: string]
  updateQuickSupplierPhone: [value: string]
  updateQuickSupplierEmail: [value: string]
}>()

const { t } = useI18n()
</script>

<template>
  <AppBottomSheet :open="open" :title="t('procurements.create.quickSupplierTitle')" @close="emit('close')">
    <form class="quick-product-form" @submit.prevent="emit('submit')">
      <div v-if="quickSupplierError" class="error-box">
        <AlertCircle :size="18" :stroke-width="1.75" />
        <span>{{ quickSupplierError }}</span>
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('products.characteristicName') }} *</label>
        <input
          :value="quickSupplierName"
          class="input-field"
          type="text"
          :placeholder="t('procurements.create.supplierNamePlaceholder')"
          @input="emit('updateQuickSupplierName', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div class="field-group">
        <label class="field-label">{{ t('auth.phone') }}</label>
        <input
          :value="quickSupplierPhone"
          class="input-field"
          type="text"
          placeholder="+998 90 000 00 00"
          @input="emit('updateQuickSupplierPhone', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div class="field-group">
        <label class="field-label">Email</label>
        <input
          :value="quickSupplierEmail"
          class="input-field"
          type="email"
          placeholder="supplier@mail.com"
          @input="emit('updateQuickSupplierEmail', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <button class="btn-primary" type="submit" :disabled="isCreatingQuickSupplier">
        {{ isCreatingQuickSupplier ? t('procurements.create.creating') : t('procurements.create.createAndChoose') }}
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
