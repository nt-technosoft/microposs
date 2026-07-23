<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import BaseModal from '@/components/base/BaseModal.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const selectedBatchId = ref<number | null>(null)
const reason = ref('')
const reasonError = ref(false)

const batches = computed(() => props.procurement.documents.receive_batches ?? [])

const selectedBatch = computed(() =>
  batches.value.find((b) => b.id === selectedBatchId.value) ?? null,
)

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  reason.value = ''
  reasonError.value = false
  selectedBatchId.value = batches.value.length === 1 ? batches.value[0].id : null
})

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function onConfirm(): void {
  if (!selectedBatchId.value) return
  if (!reason.value.trim()) { reasonError.value = true; return }
  emit('dispatch', 'REVERSE_BATCH', { batch_id: selectedBatchId.value, reason: reason.value.trim() })
  emit('update:open', false)
}
</script>

<template>
  <BaseModal
    :open="open"
    title="Отменить приёмку"
    size="sm"
    @close="emit('update:open', false)"
  >
    <div class="body">
      <div v-if="!batches.length" class="empty-text">Нет приёмок для отмены.</div>

      <template v-else>
        <!-- Batch selector -->
        <div class="field-label">Приёмка</div>
        <div class="batch-list">
          <button
            v-for="b in batches"
            :key="b.id"
            class="batch-row"
            :class="{ selected: selectedBatchId === b.id }"
            type="button"
            @click="selectedBatchId = b.id"
          >
            <div class="batch-info">
              <span class="batch-date">{{ fmtDate(b.received_at) }}</span>
              <span class="batch-meta">{{ b.warehouse_name }} · {{ b.lines.length }} позиций</span>
            </div>
            <span class="batch-total">{{ parseFloat(b.inventory_total_uzs).toLocaleString('ru-RU') }} сум</span>
          </button>
        </div>

        <!-- Selected batch lines preview -->
        <template v-if="selectedBatch">
          <div class="field-label">Будет реверсировано</div>
          <div class="lines-preview">
            <div v-for="line in selectedBatch.lines" :key="line.id" class="line-row">
              <span class="line-name">{{ line.product_variant_name }}</span>
              <span class="line-qty">{{ line.quantity }}</span>
            </div>
          </div>
          <div class="warning-box">
            <AlertTriangle :size="14" :stroke-width="2" />
            <span>Лоты будут удалены из остатков. Если товары уже проданы — реверс заблокирован бэкендом.</span>
          </div>
        </template>

        <!-- Reason -->
        <div class="field-label">Причина <span class="required">*</span></div>
        <textarea
          v-model="reason"
          class="reason-input"
          :class="{ error: reasonError }"
          rows="2"
          placeholder="Укажите причину…"
          @input="reasonError = false"
        />
        <div v-if="reasonError" class="error-text">Причина обязательна</div>
      </template>
    </div>

    <template #footer>
      <button class="btn-cancel" type="button" @click="emit('update:open', false)">Назад</button>
      <button
        v-if="batches.length"
        class="btn-confirm"
        type="button"
        :disabled="!selectedBatchId"
        @click="onConfirm"
      >Отменить приёмку</button>
    </template>
  </BaseModal>
</template>

<style scoped>
.body { display: grid; gap: var(--space-3); }
.empty-text { font-size: var(--text-sm); color: var(--color-text-secondary); }
.field-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.batch-list { display: grid; gap: var(--space-2); }
.batch-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; text-align: left; }
.batch-row.selected { border-color: var(--color-brand-600); background: var(--color-brand-50); }
.batch-info { display: flex; flex-direction: column; gap: 2px; }
.batch-date { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.batch-meta { font-size: var(--text-xs); color: var(--color-text-secondary); }
.batch-total { font-size: var(--text-sm); color: var(--color-text-secondary); white-space: nowrap; }
.lines-preview { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); max-height: 120px; overflow-y: auto; }
.line-row { display: flex; align-items: center; justify-content: space-between; }
.line-name { font-size: var(--text-sm); color: var(--color-text-primary); }
.line-qty { font-size: var(--text-sm); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.warning-box { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-3); background: color-mix(in srgb, #F59E0B 10%, transparent); border: 1px solid color-mix(in srgb, #F59E0B 25%, transparent); border-radius: var(--radius-md); font-size: var(--text-xs); color: #92400E; }
.required { color: var(--color-error); }
.reason-input { width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); resize: vertical; font-family: inherit; }
.reason-input.error { border-color: var(--color-error); }
.error-text { font-size: var(--text-xs); color: var(--color-error); }
.btn-cancel { flex: 1; min-height: 44px; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: transparent; color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.btn-confirm { flex: 1; min-height: 44px; border: 0; border-radius: var(--radius-lg); background: var(--color-error); color: white; font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.btn-confirm:disabled { opacity: .55; cursor: not-allowed; }
</style>
