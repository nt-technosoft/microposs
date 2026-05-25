<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Batch = ProcurementWorkspacePayload['documents']['receive_batches'][number]
type Item = ProcurementWorkspacePayload['documents']['items'][number]

const REASON_LABELS: Record<string, string> = {
  MISSING_EXPECTED_LATER: 'не привезли, ждём',
  DAMAGED: 'повреждено',
  QUALITY_REJECT: 'брак',
  ACCEPT_AS_SHORTFALL: 'принято со скидкой',
}

const props = defineProps<{ batch: Batch; items: Item[] }>()
const emit = defineEmits<{ click: [batchId: number]; reverse: [batchId: number] }>()

function itemName(itemId: number): string {
  return props.items.find((i) => i.id === itemId)?.product_variant_name ?? `#${itemId}`
}

const totalPlanned = computed(() =>
  props.batch.lines.reduce((s, l) => s + (parseFloat(l.quantity_planned) || 0), 0),
)
const totalReceived = computed(() =>
  props.batch.lines.reduce((s, l) => s + (parseFloat(l.quantity_received) || 0), 0),
)
const hasDiscrepancy = computed(() =>
  props.batch.lines.some((l) => l.discrepancy_reason && l.discrepancy_reason !== 'NONE'),
)

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function fmtQty(val: string): string {
  return String(Math.round(parseFloat(val) || 0))
}
</script>

<template>
  <div class="batch-row" @click="emit('click', batch.id)">
    <div class="batch-header">
      <div class="batch-title">
        <span class="batch-date">{{ fmtDate(batch.received_at) }}</span>
        <span class="batch-id">Приёмка #{{ batch.id }}</span>
      </div>
      <div class="batch-totals">
        <span class="qty-total">{{ fmtQty(String(totalReceived)) }}/{{ fmtQty(String(totalPlanned)) }}</span>
        <AlertTriangle v-if="hasDiscrepancy" class="discrepancy-icon" :size="14" :stroke-width="2.5" />
      </div>
    </div>

    <div class="lines-list">
      <div v-for="line in batch.lines" :key="line.id" class="line-item">
        <span class="line-name">{{ itemName(line.item_id) }}</span>
        <span class="line-qty" :class="{ mismatch: line.discrepancy_reason && line.discrepancy_reason !== 'NONE' }">
          {{ fmtQty(line.quantity_received) }}/{{ fmtQty(line.quantity_planned) }}
        </span>
        <span v-if="line.discrepancy_reason && line.discrepancy_reason !== 'NONE'" class="line-reason">
          — {{ REASON_LABELS[line.discrepancy_reason] ?? line.discrepancy_reason }}
        </span>
      </div>
    </div>

    <div class="batch-footer">
      <span class="batch-value">{{ Math.round(parseFloat(batch.inventory_total_uzs)).toLocaleString('ru-RU') }} UZS</span>
      <span class="attachments-stub">📎 накладная</span>
    </div>
  </div>
</template>

<style scoped>
.batch-row { display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; }
.batch-header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.batch-title { display: flex; flex-direction: column; gap: 2px; }
.batch-date { font-size: var(--text-xs); color: var(--color-text-secondary); }
.batch-id { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.batch-totals { display: flex; align-items: center; gap: var(--space-1); flex-shrink: 0; }
.qty-total { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.discrepancy-icon { color: var(--color-warning); }
.lines-list { display: grid; gap: 2px; }
.line-item { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); flex-wrap: wrap; }
.line-name { color: var(--color-text-secondary); flex-shrink: 0; }
.line-qty { font-variant-numeric: tabular-nums; color: var(--color-text-primary); font-weight: var(--font-semibold); flex-shrink: 0; }
.line-qty.mismatch { color: var(--color-warning); }
.line-reason { color: var(--color-text-tertiary); font-style: italic; }
.batch-footer { display: flex; align-items: center; justify-content: space-between; }
.batch-value { font-size: var(--text-xs); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.attachments-stub { font-size: var(--text-xs); color: var(--color-text-tertiary); }
</style>
