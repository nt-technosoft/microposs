<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  hasForeignCurrency: boolean
  grandTotal: number
  expenseTotal: number
  procurementTotal: number
  formatPrice: (value: number, currency?: string) => string
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <h2 class="section-title">{{ t('common.total') }}</h2>
    <div v-if="hasForeignCurrency" class="summary-hint">
      {{ t('procurements.create.totalUzsHint') }}
    </div>
    <div class="summary-card">
      <span>{{ t('products.title') }}</span>
      <strong class="tabular-nums">{{ formatPrice(grandTotal) }}</strong>
    </div>
    <div class="summary-card summary-card-muted">
      <span>{{ t('procurements.expenses') }}</span>
      <strong class="tabular-nums">{{ formatPrice(expenseTotal) }}</strong>
    </div>
    <div class="summary-card">
      <span>{{ t('procurements.create.toPay') }}</span>
      <strong class="tabular-nums">{{ formatPrice(procurementTotal) }}</strong>
    </div>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.summary-hint { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.summary-card { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-brand-50); color: var(--color-brand-700); }
.summary-card-muted { background: var(--color-bg-elevated); color: var(--color-text-primary); border:1px solid var(--color-border-subtle); }
</style>
