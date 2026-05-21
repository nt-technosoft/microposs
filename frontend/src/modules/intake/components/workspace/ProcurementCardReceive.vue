<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle } from 'lucide-vue-next'
import ReceiveBatchHistoryRow from './ReceiveBatchHistoryRow.vue'
import ReceiveBatchConfirmSheet from './ReceiveBatchConfirmSheet.vue'
import { useToast } from '@/composables/useToast'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const toast = useToast()
const receiveSheetOpen = ref(false)

const items = computed(() => props.procurement.documents.items)
const batches = computed(() => props.procurement.documents.receive_batches)
const settlement = computed(() => props.procurement.documents.settlement)

const isAtReceipt = computed(() => settlement.value?.type === 'AT_RECEIPT')
const isReceived = computed(() => props.procurement.status === 'RECEIVED')
const isCancelled = computed(() => props.procurement.status === 'CANCELLED')

const totalPlanned = computed(() =>
  items.value.reduce((s, it) => s + (parseFloat(it.quantity) || 0), 0),
)
const totalReceived = computed(() =>
  items.value.reduce((s, it) => s + (parseFloat(it.received_quantity) || 0), 0),
)
const remainingQty = computed(() => Math.max(0, totalPlanned.value - totalReceived.value))
const receivedPercent = computed(() =>
  totalPlanned.value > 0 ? Math.round((totalReceived.value / totalPlanned.value) * 100) : 0,
)
const isFull = computed(() => remainingQty.value === 0 && batches.value.length > 0)

const btnLabel = computed(() =>
  isAtReceipt.value ? 'Принять и оплатить' :
  batches.value.length > 0 ? 'Принять оставшееся' : 'Принять товар',
)

function onBatchDispatch(actionKey: string, payload: Record<string, unknown>): void {
  emit('dispatch', actionKey, payload)
}

function onReverseBatch(batchId: number): void {
  toast.info(`Отмена приёмки #${batchId} — будет реализовано (B-13)`)
}
</script>

<template>
  <div v-if="!isCancelled && items.length" class="receive-card">
    <div class="card-header">
      <span class="card-title">{{ isAtReceipt ? 'Приёмка и оплата' : 'Приёмка' }}</span>
      <CheckCircle v-if="isFull" class="status-ok" :size="18" :stroke-width="2" />
    </div>

    <div class="stats-block">
      <div class="stat-row">
        <span class="stat-label">Запланировано</span>
        <span class="stat-value">{{ Math.round(totalPlanned).toLocaleString('ru-RU') }} шт.</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">Принято</span>
        <span class="stat-value">{{ Math.round(totalReceived).toLocaleString('ru-RU') }} шт.
          <span v-if="batches.length" class="pct-hint">({{ receivedPercent }}%)</span>
        </span>
      </div>
      <div v-if="!isFull && batches.length" class="stat-row">
        <span class="stat-label">Осталось</span>
        <span class="stat-value warn">{{ Math.round(remainingQty).toLocaleString('ru-RU') }} шт.</span>
      </div>
      <div v-if="isAtReceipt" class="at-receipt-hint">Оплата: при приёмке (по получению)</div>
    </div>

    <template v-if="batches.length">
      <div class="history-label">Приёмки ({{ batches.length }})</div>
      <div class="history-list">
        <ReceiveBatchHistoryRow
          v-for="batch in batches"
          :key="batch.id"
          :batch="batch"
          :items="items"
          @click="() => {}"
          @reverse="onReverseBatch"
        />
      </div>
    </template>

    <template v-if="!isFull && !isReceived">
      <button class="action-btn" type="button" @click="receiveSheetOpen = true">
        {{ btnLabel }}
      </button>
    </template>

    <div v-else-if="isFull" class="full-notice">Принято полностью.</div>
  </div>

  <ReceiveBatchConfirmSheet
    v-model:open="receiveSheetOpen"
    :procurement="procurement"
    @dispatch="onBatchDispatch"
  />
</template>

<style scoped>
.receive-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.status-ok { color: var(--color-success); }
.stats-block { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.stat-row { display: flex; align-items: center; justify-content: space-between; }
.stat-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.stat-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.stat-value.warn { color: var(--color-warning); }
.pct-hint { font-size: var(--text-xs); color: var(--color-text-secondary); font-weight: var(--font-normal); margin-left: var(--space-1); }
.at-receipt-hint { font-size: var(--text-xs); color: var(--color-text-secondary); padding-top: var(--space-1); }
.history-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.history-list { display: grid; gap: var(--space-2); }
.full-notice { font-size: var(--text-sm); color: var(--color-success); font-weight: var(--font-semibold); }
.action-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
