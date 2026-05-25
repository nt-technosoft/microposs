<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, Trash2, Package } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]

const props = defineProps<{ item: Item; isEditable: boolean }>()
const emit = defineEmits<{ click: [id: number]; delete: [id: number] }>()

const isConsigned = computed(() => props.item.goods_ownership === 'CONSIGNED')

const unitDisplay = computed(() => {
  const price = parseFloat(props.item.unit_purchase_price) || 0
  return `${price.toLocaleString('ru-RU')} ${props.item.currency}`
})

const totalInCurrency = computed(() => {
  const qty = parseFloat(props.item.quantity) || 0
  const price = parseFloat(props.item.unit_purchase_price) || 0
  return (qty * price).toLocaleString('ru-RU', { maximumFractionDigits: 2, minimumFractionDigits: 0 })
})

function tryDelete(): void {
  if (window.confirm(`Удалить «${props.item.product_variant_name}»?`)) {
    emit('delete', props.item.id)
  }
}
</script>

<template>
  <div class="item-row" role="button" tabindex="0" @click="emit('click', item.id)" @keydown.enter="emit('click', item.id)">
    <div class="item-main">
      <div class="item-name-row">
        <span class="item-name">{{ item.product_variant_name }}</span>
        <span v-if="isConsigned" class="consign-badge">
          <Package :size="11" :stroke-width="2" /> Реал.
        </span>
      </div>
      <div class="item-calc">
        {{ item.quantity }} шт × {{ unitDisplay }} = <span style="font-variant-numeric: tabular-nums">{{ totalInCurrency }}</span> {{ item.currency }}
      </div>
    </div>
    <div class="item-actions" @click.stop @keydown.stop>
      <button v-if="isEditable" class="delete-btn" type="button" @click="tryDelete">
        <Trash2 :size="14" :stroke-width="2" />
      </button>
      <ChevronRight class="chevron" :size="16" :stroke-width="2" />
    </div>
  </div>
</template>

<style scoped>
.item-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  cursor: pointer;
}

.item-main { flex: 1; min-width: 0; display: grid; gap: 3px; }

.item-name-row { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }

.item-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.consign-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  flex-shrink: 0;
}

.item-calc { font-size: var(--text-xs); color: var(--color-text-secondary); }

.item-actions { display: flex; align-items: center; gap: var(--space-1); flex-shrink: 0; }

.delete-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-md);
  background: rgba(239, 68, 68, 0.06);
  color: var(--color-error);
  cursor: pointer;
}

.chevron { color: var(--color-text-tertiary); }
</style>
