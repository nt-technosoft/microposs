<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { CheckCircle2 } from 'lucide-vue-next'
import ReceiveBatchHistoryRow from './ReceiveBatchHistoryRow.vue'
import ReceiveBatchConfirmSheet from './ReceiveBatchConfirmSheet.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useToast } from '@/composables/useToast'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const toast = useToast()
const receiveSheetOpen = ref(false)

const { items } = useActiveLines(toRef(props, 'procurement'))
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
  <Card v-if="!isCancelled && items.length" class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">{{ isAtReceipt ? 'Приёмка и оплата' : 'Приёмка' }}</CardTitle>
      <CheckCircle2 v-if="isFull" class="size-[18px] text-positive" />
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <div class="flex flex-col gap-1.5 rounded-[10px] bg-neutral-50 px-3.5 py-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Запланировано</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">{{ Math.round(totalPlanned).toLocaleString('ru-RU') }} шт.</span>
        </div>
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Принято</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">
            {{ Math.round(totalReceived).toLocaleString('ru-RU') }} шт.
            <span v-if="batches.length" class="text-xs font-normal text-neutral-500">({{ receivedPercent }}%)</span>
          </span>
        </div>
        <div v-if="!isFull && batches.length" class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Осталось</span>
          <span class="text-sm font-semibold tabular-nums text-warning">{{ Math.round(remainingQty).toLocaleString('ru-RU') }} шт.</span>
        </div>
        <p v-if="isAtReceipt" class="pt-0.5 text-xs text-neutral-500">Оплата: при приёмке (по получению).</p>
      </div>

      <template v-if="batches.length">
        <p class="text-xs font-medium uppercase tracking-wide text-neutral-500">Приёмки ({{ batches.length }})</p>
        <div class="flex flex-col gap-2">
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

      <Button v-if="!isFull && !isReceived" variant="outline" class="w-full" @click="receiveSheetOpen = true">
        {{ btnLabel }}
      </Button>
      <p v-else-if="isFull" class="text-sm font-medium text-positive">Принято полностью.</p>
    </CardContent>
  </Card>

  <ReceiveBatchConfirmSheet
    v-model:open="receiveSheetOpen"
    :procurement="procurement"
    @dispatch="onBatchDispatch"
  />
</template>
