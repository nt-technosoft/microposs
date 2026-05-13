<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ProductVariant } from '@/types/models'

defineProps<{
  variant: ProductVariant
}>()

const { t } = useI18n()
</script>

<template>
  <span v-if="variant.supplier_preferred" class="supplier-badge">
    {{ t('procurements.create.preferredSupplierProduct') }}
    <template v-if="variant.supplier_last_unit_price">
      · {{ variant.supplier_last_unit_price }} {{ variant.supplier_last_currency || '' }}
    </template>
  </span>
</template>

<style scoped>
.supplier-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  max-width: 100%;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: 12px;
  font-weight: var(--font-semibold);
  white-space: nowrap;
}
</style>
