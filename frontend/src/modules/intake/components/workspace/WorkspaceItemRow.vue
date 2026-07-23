<script setup lang="ts">
import { RefreshCcw, Trash2 } from 'lucide-vue-next'
import type { ProductVariant } from '@/types/models'
import type { DraftLineRow } from './types'

defineProps<{
  line: DraftLineRow
  error?: string | null
  canRemove: boolean
  variantDisplay: (variant: ProductVariant) => string
}>()

const emit = defineEmits<{
  openVariantPicker: [lineId: string]
  remove: [lineId: string]
  update: [lineId: string, field: 'variant' | 'quantity' | 'cost_per_unit' | 'currency' | 'fx_rate', value: string | ProductVariant | null]
  toggleCurrency: [lineId: string]
}>()
</script>

<template>
  <div class="line-row" :class="{ locked: line.locked_reason, invalid: Boolean(error) }">
    <div class="line-row-top">
      <button class="picker-btn line-product-btn" type="button" :disabled="Boolean(line.locked_reason)" @click="emit('openVariantPicker', line.id)">
        {{ line.variant ? variantDisplay(line.variant) : 'Выбрать товар' }}
      </button>
      <button
        v-if="!line.locked_reason && canRemove"
        class="icon-danger"
        type="button"
        aria-label="Удалить товар"
        @click="emit('remove', line.id)"
      >
        <Trash2 :size="16" :stroke-width="2" />
      </button>
    </div>

    <div class="line-row-main">
      <label class="field-group">
        <span class="micro-label">Кол-во</span>
        <input
          class="input-field line-input"
          type="number"
          min="0"
          :value="line.quantity"
          :disabled="Boolean(line.locked_reason)"
          @input="(event) => emit('update', line.id, 'quantity', (event.target as HTMLInputElement).value)"
        />
      </label>

      <label class="field-group">
        <span class="micro-label">Цена закупки</span>
        <div class="money-field">
          <input
            class="input-field line-input money-input"
            type="number"
            min="0"
            step="0.000001"
            placeholder="0"
            :value="line.cost_per_unit"
            :disabled="Boolean(line.locked_reason)"
            @input="(event) => emit('update', line.id, 'cost_per_unit', (event.target as HTMLInputElement).value)"
          />
          <button class="currency-toggle" type="button" :disabled="Boolean(line.locked_reason)" @click="emit('toggleCurrency', line.id)">
            <span>{{ line.currency }}</span>
            <RefreshCcw :size="13" :stroke-width="2" />
          </button>
        </div>
      </label>
    </div>

    <p v-if="line.locked_reason" class="locked-note">Товар уже имеет финансовые или складские факты и не редактируется напрямую.</p>
    <p v-if="error" class="error-note">{{ error }}</p>
  </div>
</template>

<style scoped>
.line-row {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
}

.line-row.locked {
  background: var(--color-bg-elevated);
}

.line-row.invalid {
  border-color: rgba(239, 68, 68, 0.42);
}

.line-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.line-product-btn,
.picker-btn {
  min-height: 42px;
  width: 100%;
  padding: 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  text-align: left;
  font-weight: var(--font-semibold);
}

.picker-btn:disabled {
  opacity: 0.72;
  background: var(--color-bg-sunken);
}

.icon-danger {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(239, 68, 68, 0.18);
  border-radius: var(--radius-md);
  background: rgba(239, 68, 68, 0.06);
  color: var(--color-danger);
  flex: 0 0 auto;
}

.line-row-main {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.35fr);
  gap: 8px;
}

.field-group {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.micro-label {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
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

.input-field:disabled {
  opacity: 0.72;
  background: var(--color-bg-sunken);
}

.money-field {
  position: relative;
}

.money-input {
  padding-right: 92px;
}

.currency-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 8px;
  border: 1px solid var(--color-border-default);
  border-radius: calc(var(--radius-md) - 2px);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
}

.locked-note,
.error-note {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.error-note {
  color: var(--color-danger);
}
</style>
