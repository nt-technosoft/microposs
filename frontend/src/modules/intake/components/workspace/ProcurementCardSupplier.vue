<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, AlertCircle, CheckCircle } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update-source': [payload: { supplier_id?: number | null; funding_source?: string }]
  'update-settlement': [payload: { type: string }]
  'open-supplier-picker': []
}>()

const source = computed(() => props.procurement.documents.source)
const settlement = computed(() => props.procurement.documents.settlement)
const procDoc = computed(() => props.procurement.documents.procurement)

const currentTiming = computed(() => settlement.value?.type ?? null)
const isPartnership = computed(() => (source.value.funding_source ?? 'OWN_FUNDS') === 'PARTNERSHIP')

const isFilled = computed(() => !!procDoc.value.supplier_id && !!currentTiming.value)

const ALL_TIMINGS = [
  { key: 'PREPAID', label: 'Предоплата' },
  { key: 'AT_RECEIPT', label: 'По получению' },
  { key: 'PARTIAL', label: 'Частичная' },
  { key: 'DEFERRED', label: 'Отсрочка' },
  { key: 'INSTALLMENT', label: 'Рассрочка' },
  { key: 'ON_SALE', label: 'На реализации' },
] as const

const SUPPLIER_REQUIRED = new Set(['PARTIAL', 'DEFERRED', 'INSTALLMENT', 'ON_SALE'])

const visibleTimings = computed(() =>
  isPartnership.value
    ? ALL_TIMINGS.filter((t) => t.key === 'PREPAID' || t.key === 'AT_RECEIPT')
    : ALL_TIMINGS,
)

const hasDisabledTimings = computed(() =>
  !isPartnership.value &&
  !procDoc.value.supplier_id &&
  visibleTimings.value.some((t) => SUPPLIER_REQUIRED.has(t.key)),
)

function timingDisabled(key: string): boolean {
  return SUPPLIER_REQUIRED.has(key) && !procDoc.value.supplier_id
}

function setTiming(type: string): void {
  if (type === currentTiming.value || timingDisabled(type)) return
  emit('update-settlement', { type })
}
</script>

<template>
  <div class="supplier-card">
    <div class="card-header">
      <span class="card-title">Поставщик и оплата</span>
      <CheckCircle v-if="isFilled" class="status-icon status-ok" :size="18" :stroke-width="2" />
      <AlertCircle v-else class="status-icon status-warn" :size="18" :stroke-width="2" />
    </div>

    <!-- Supplier selection -->
    <div class="section-label">Поставщик</div>
    <button
      v-if="!procDoc.supplier_id"
      class="select-supplier-btn"
      type="button"
      @click="emit('open-supplier-picker')"
    >
      Выбрать поставщика
      <ChevronRight :size="16" :stroke-width="2" />
    </button>
    <button
      v-else
      class="supplier-filled-row"
      type="button"
      @click="emit('open-supplier-picker')"
    >
      <div class="supplier-info">
        <span class="supplier-name">{{ procDoc.supplier_name ?? `Поставщик #${procDoc.supplier_id}` }}</span>
      </div>
      <ChevronRight :size="16" :stroke-width="2" class="chevron" />
    </button>

    <!-- Payment timing chips -->
    <div class="section-label">Тип оплаты</div>
    <div class="timing-chips">
      <button
        v-for="t in visibleTimings"
        :key="t.key"
        class="timing-chip"
        :class="{ active: currentTiming === t.key, disabled: timingDisabled(t.key) }"
        :disabled="timingDisabled(t.key)"
        type="button"
        @click="setTiming(t.key)"
      >{{ t.label }}</button>
    </div>
    <p v-if="hasDisabledTimings" class="timing-hint">
      Для отсрочки / рассрочки / частичной / на реализации нужно сначала выбрать поставщика.
    </p>

  </div>
</template>

<style scoped>
.supplier-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.status-icon { flex-shrink: 0; }
.status-ok { color: var(--color-success); }
.status-warn { color: #F59E0B; }

.section-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.select-supplier-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-3);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-brand-700);
  font-size: var(--text-sm, 0.875rem);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

.supplier-filled-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  cursor: pointer;
}

.supplier-info { display: flex; flex-direction: column; gap: 2px; }
.supplier-name {
  font-size: var(--text-sm, 0.875rem);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chevron { flex-shrink: 0; color: var(--color-text-tertiary); }

.timing-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }

.timing-chip {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm, 0.875rem);
  cursor: pointer;
}

.timing-chip.active {
  border-color: var(--color-brand-600);
  background: var(--color-brand-600);
  color: white;
  font-weight: var(--font-semibold);
}

.timing-chip.disabled, .timing-chip:disabled {
  opacity: .4;
  cursor: not-allowed;
}

.timing-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.5;
}

</style>
