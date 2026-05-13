<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import BaseSelect from '@/components/base/BaseSelect.vue'

interface SupplierOption {
  value: number
  label: string
}

defineProps<{
  supplierOptions: SupplierOption[]
  selectedSupplierId: number | null
  isLoadingRefs: boolean
}>()

const emit = defineEmits<{
  openQuickSupplier: []
  updateSelectedSupplierId: [value: number | null]
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <div class="section-header">
      <h2 class="section-title">{{ t('suppliers.supplier') }}</h2>
      <button class="btn-add-small" type="button" @click="emit('openQuickSupplier')">
        <Plus :size="14" :stroke-width="2.5" />
        {{ t('procurements.create.addSupplier') }}
      </button>
    </div>
    <div class="field-group">
      <label class="field-label">{{ t('procurements.create.supplierCanChooseLater') }}</label>
      <BaseSelect
        :model-value="selectedSupplierId"
        :options="supplierOptions"
        :title="t('procurements.create.supplierSelectTitle')"
        :placeholder="t('procurements.supplierMissing')"
        :disabled="isLoadingRefs"
        @update:model-value="emit('updateSelectedSupplierId', $event as number | null)"
      />
    </div>
    <p class="empty-inline">
      {{ t('procurements.create.warehouseChosenLater') }}
    </p>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); flex-wrap: wrap; }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.btn-add-small { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-1); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-medium); white-space: nowrap; }
.field-group { display:grid; gap: var(--space-2); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.empty-inline { color: var(--color-text-secondary); font-size: var(--text-sm); }
</style>
