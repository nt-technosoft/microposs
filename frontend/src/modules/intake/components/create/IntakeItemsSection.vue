<script setup lang="ts">
import { Plus, RefreshCcw, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import type { LineRow } from '@/modules/intake/types'
import type { ProductVariant } from '@/types/models'

const props = defineProps<{
  lines: LineRow[]
  variantDisplay: (variant: ProductVariant) => string
  normalizeCurrency: (value: unknown) => string
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
}>()

const emit = defineEmits<{
  openQuickProduct: [lineId?: string | null]
  addLine: []
  openVariantPicker: [lineId: string]
  removeLine: [lineId: string]
  updateLine: [lineId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null]
  toggleLineCurrency: [lineId: string]
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <div class="section-header">
      <h2 class="section-title">{{ t('products.title') }}</h2>
      <div class="section-actions">
        <button class="btn-add-small" type="button" @click="emit('openQuickProduct', null)">
          <Plus :size="14" :stroke-width="2.5" />
          {{ t('products.createProduct') }}
        </button>
        <button class="btn-add-small" type="button" @click="emit('addLine')">
          <Plus :size="14" :stroke-width="2.5" />
          {{ t('procurements.create.addLine') }}
        </button>
      </div>
    </div>

    <div v-if="lines.length === 0" class="empty-inline">
      {{ t('procurements.create.itemsCanAddAfterOpen') }}
    </div>

    <div v-else class="line-list">
      <div v-for="line in lines" :key="line.id" class="line-row">
        <div class="line-row-top">
          <button class="picker-btn line-product-btn" type="button" @click="emit('openVariantPicker', line.id)">
            {{ line.variant ? variantDisplay(line.variant) : t('products.selectVariant') }}
          </button>
          <button class="btn-delete line-delete" type="button" :aria-label="t('procurements.create.removeLine')" @click="emit('removeLine', line.id)">
            <Trash2 :size="16" :stroke-width="2" />
          </button>
        </div>

        <div class="line-row-main">
          <div class="field-group">
            <label class="micro-label">{{ t('common.quantity') }}</label>
            <input
              type="number"
              class="input-field line-input"
              :value="line.quantity"
              min="0"
              placeholder="1"
              :aria-label="t('common.quantity')"
              @input="emit('updateLine', line.id, 'quantity', ($event.target as HTMLInputElement).value)"
            />
          </div>

          <div class="field-group line-price-cell">
            <label class="micro-label">{{ t('procurements.create.purchasePrice') }}</label>
            <div class="money-field">
              <input
                type="number"
                class="input-field line-input money-input"
                :value="line.cost_per_unit"
                min="0"
                step="0.000001"
                :placeholder="t('products.price')"
                :aria-label="t('procurements.create.purchasePrice')"
                @input="emit('updateLine', line.id, 'cost_per_unit', ($event.target as HTMLInputElement).value)"
              />
              <button
                type="button"
                class="currency-toggle"
                :aria-label="t('procurements.create.changeLineCurrency', { currency: normalizeCurrency(line.currency) })"
                @click="emit('toggleLineCurrency', line.id)"
              >
                <span class="currency-toggle-code">{{ normalizeCurrency(line.currency) }}</span>
                <RefreshCcw :size="14" :stroke-width="2" />
              </button>
            </div>
          </div>
        </div>

        <div v-if="showFxField(line.currency)" class="line-row-extra">
          <div class="field-group">
            <label class="micro-label">{{ t('procurements.create.rateLabel', { currency: formatCurrencyTotalLabel(line.currency) }) }}</label>
            <input
              type="number"
              class="input-field line-input"
              :value="line.fx_rate"
              min="0"
              step="0.0001"
              :placeholder="t('procurements.create.enterRate')"
              :aria-label="t('procurements.create.fxRate')"
              @input="emit('updateLine', line.id, 'fx_rate', ($event.target as HTMLInputElement).value)"
            />
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); flex-wrap: wrap; }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.section-actions { display:flex; align-items:center; justify-content:flex-end; gap: var(--space-2); flex-wrap:wrap; margin-left:auto; }
.btn-add-small { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-1); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-medium); white-space: nowrap; }
.empty-inline { color: var(--color-text-secondary); font-size: var(--text-sm); }
.line-list { display:grid; gap: var(--space-1); border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-elevated); overflow:hidden; }
.line-row { display:grid; gap: var(--space-2); padding: var(--space-3); border-bottom:1px solid var(--color-border-subtle); }
.line-row:last-child { border-bottom:none; }
.line-row-top { display:grid; grid-template-columns: minmax(0, 1fr) 36px; gap: var(--space-2); align-items:start; }
.line-row-main { display:grid; grid-template-columns: minmax(92px, 0.65fr) minmax(0, 1.35fr); gap: var(--space-2); align-items:start; }
.line-row-extra { display:grid; gap: var(--space-2); }
.line-price-cell { min-width: 0; }
.field-group { display:grid; gap: var(--space-2); }
.micro-label { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.input-field,.picker-btn { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.picker-btn { color: var(--color-text-secondary); }
.line-product-btn { min-height:40px; padding: var(--space-2) var(--space-3); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.line-input { min-height:40px; padding: var(--space-2) var(--space-3); }
.money-field { position: relative; }
.money-input { padding-right: 88px; }
.currency-toggle { position: absolute; top: 50%; right: 6px; transform: translateY(-50%); height: 30px; display:inline-flex; align-items:center; justify-content:center; gap: 6px; padding: 0 10px; border:1px solid var(--color-border-default); border-radius: calc(var(--radius-md) - 2px); background: var(--color-bg-primary); color: var(--color-text-primary); font-weight: var(--font-semibold); white-space: nowrap; z-index: 1; }
.currency-toggle-code { font-size: var(--text-sm); line-height: 1; }
.currency-toggle:hover { border-color: var(--color-brand-500); color: var(--color-brand-700); }
.btn-delete { display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-500); }
.line-delete { width:36px; height:36px; justify-content:center; border-radius: var(--radius-md); color: var(--color-text-tertiary); }
.line-delete:hover { color: var(--color-error); background: var(--color-error-bg); }

@media (max-width: 520px) {
  .section-actions { width:100%; margin-left:0; justify-content:flex-start; }
  .line-row-main { grid-template-columns: minmax(88px, 0.62fr) minmax(0, 1.38fr); }
  .money-input { padding-right: 82px; }
  .currency-toggle { right: 5px; padding: 0 8px; }
}
</style>
