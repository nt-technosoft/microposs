<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight, AlertCircle, CheckCircle2 } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
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

const userPickedTiming = ref(false)

// For display only: show PREPAID as default when no timing is explicitly set
const effectiveTiming = computed(() => currentTiming.value ?? 'PREPAID')

const isFilled = computed(() => !!procDoc.value.supplier_id && !!currentTiming.value)

const ALL_TIMINGS = [
  { key: 'PREPAID', label: 'Предоплата', hint: 'Оплата поставщику до получения товара.' },
  { key: 'AT_RECEIPT', label: 'По получению', hint: 'Оплата в момент получения товара.' },
  { key: 'PARTIAL', label: 'Частичная', hint: 'Часть суммы сейчас, остаток позже.' },
  { key: 'DEFERRED', label: 'Отсрочка', hint: 'Оплата позже оговорённым сроком.' },
  { key: 'INSTALLMENT', label: 'Рассрочка', hint: 'Оплата по графику платежей.' },
  { key: 'ON_SALE', label: 'На реализации', hint: 'Оплата по мере продажи товара.' },
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

// Calm summary: collapse to a fact line once supplier + timing are set; tap to edit.
const editing = ref(false)
const showControls = computed(() => !isFilled.value || editing.value)

const supplierName = computed(
  () => procDoc.value.supplier_name ?? (procDoc.value.supplier_id ? `Поставщик #${procDoc.value.supplier_id}` : ''),
)
const timingLabel = computed(
  () => ALL_TIMINGS.find((t) => t.key === effectiveTiming.value)?.label ?? '',
)
const timingConsequence = computed(
  () => ALL_TIMINGS.find((t) => t.key === effectiveTiming.value)?.hint ?? '',
)

function timingDisabled(key: string): boolean {
  return SUPPLIER_REQUIRED.has(key) && !procDoc.value.supplier_id
}

function setTiming(type: string): void {
  if (type === effectiveTiming.value || timingDisabled(type)) return
  userPickedTiming.value = true
  emit('update-settlement', { type })
}

watch(
  () => procDoc.value.supplier_id,
  (newId, oldId) => {
    if (newId && !oldId && !userPickedTiming.value) {
      emit('update-settlement', { type: 'AT_RECEIPT' })
    }
  },
)
</script>

<template>
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">Поставщик и условия</CardTitle>
      <CheckCircle2 v-if="isFilled" class="size-[18px] text-positive" />
      <AlertCircle v-else class="size-[18px] text-warning" />
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <!-- Calm summary (filled, not editing): supplier · terms + plain-language line -->
      <button
        v-if="!showControls"
        type="button"
        class="flex w-full flex-col gap-1 rounded-[10px] border border-neutral-200 px-3.5 py-3 text-left transition-colors hover:border-green-300 hover:bg-green-50/40"
        @click="editing = true"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="min-w-0 truncate text-sm font-semibold text-foreground">
            {{ supplierName }} · {{ timingLabel }}
          </span>
          <ChevronRight class="size-4 shrink-0 text-neutral-400" />
        </div>
        <span class="text-xs text-neutral-500">{{ timingConsequence }}</span>
      </button>

      <!-- Controls (empty, or editing) -->
      <template v-else>
        <!-- Supplier -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Поставщик</span>
          <button
            v-if="!procDoc.supplier_id"
            type="button"
            class="flex w-full items-center justify-between gap-2 rounded-[10px] border border-dashed border-neutral-300 px-3.5 py-3 text-sm font-medium text-green-700 transition-colors hover:bg-green-50/40"
            @click="emit('open-supplier-picker')"
          >
            Выбрать поставщика
            <ChevronRight class="size-4" />
          </button>
          <button
            v-else
            type="button"
            class="flex w-full items-center justify-between gap-2 rounded-[10px] border border-neutral-200 px-3.5 py-3 transition-colors hover:border-green-300 hover:bg-green-50/40"
            @click="emit('open-supplier-picker')"
          >
            <span class="min-w-0 truncate text-sm font-semibold text-foreground">{{ supplierName }}</span>
            <ChevronRight class="size-4 shrink-0 text-neutral-400" />
          </button>
        </div>

        <!-- Payment terms -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Тип оплаты</span>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="t in visibleTimings"
              :key="t.key"
              type="button"
              :disabled="timingDisabled(t.key)"
              :class="cn(
                'rounded-full border px-3 py-1.5 text-sm transition-colors',
                effectiveTiming === t.key
                  ? 'border-primary bg-primary/5 font-medium text-foreground'
                  : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
                timingDisabled(t.key) && 'cursor-not-allowed opacity-40 hover:bg-transparent',
              )"
              @click="setTiming(t.key)"
            >{{ t.label }}</button>
          </div>
          <p class="text-xs text-neutral-500">{{ timingConsequence }}</p>
          <p v-if="hasDisabledTimings" class="text-xs text-neutral-400">
            Для частичной / отсрочки / рассрочки / на реализации сначала выберите поставщика.
          </p>
        </div>

        <button
          v-if="isFilled"
          type="button"
          class="self-start text-xs font-medium text-neutral-500 transition-colors hover:text-foreground"
          @click="editing = false"
        >
          Свернуть
        </button>
      </template>
    </CardContent>
  </Card>
</template>
