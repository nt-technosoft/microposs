<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, Package, Trash2 } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]

const props = defineProps<{ item: Item; isEditable?: boolean }>()
const emit = defineEmits<{ click: [id: number]; delete: [id: number] }>()

const isConsigned = computed(() => props.item.goods_ownership === 'CONSIGNED')

const qtyDisplay = computed(() => Math.round(parseFloat(props.item.quantity) || 0).toLocaleString('ru-RU'))
const unitDisplay = computed(
  () => `${(parseFloat(props.item.unit_purchase_price) || 0).toLocaleString('ru-RU')} ${props.item.currency}`,
)
const totalDisplay = computed(() => {
  const total = (parseFloat(props.item.quantity) || 0) * (parseFloat(props.item.unit_purchase_price) || 0)
  return total.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
})
const suspiciousUsdFx = computed(() =>
  props.item.currency === 'USD'
  && (!Number.isFinite(Number.parseFloat(props.item.fx_rate)) || Number.parseFloat(props.item.fx_rate) <= 1),
)
const landedCost = computed(() =>
  suspiciousUsdFx.value
    ? (props.item.estimated_landed_cost_per_unit_uzs ?? props.item.actual_landed_cost_per_unit_uzs ?? null)
    : (props.item.estimated_landed_cost_per_unit ?? props.item.actual_landed_cost_per_unit ?? null),
)
const landedCurrency = computed(() => suspiciousUsdFx.value ? 'UZS' : props.item.currency)
const landedDisplay = computed(() => {
  if (!landedCost.value) return ''
  const value = parseFloat(landedCost.value)
  if (!Number.isFinite(value) || value <= 0) return ''
  return value.toLocaleString('ru-RU', { maximumFractionDigits: landedCurrency.value === 'USD' ? 2 : 0 })
})
</script>

<template>
  <div
    role="button"
    tabindex="0"
    class="flex w-full items-center gap-2 rounded-[10px] border border-neutral-200 px-3.5 py-3 text-left transition-colors hover:border-green-300 hover:bg-green-50/40"
    @click="emit('click', item.id)"
    @keydown.enter="emit('click', item.id)"
  >
    <div class="min-w-0 flex-1">
      <div class="flex min-w-0 items-center gap-1.5">
        <span class="min-w-0 truncate text-sm font-medium text-foreground">{{ item.product_variant_name }}</span>
        <span
          v-if="isConsigned"
          class="inline-flex shrink-0 items-center gap-1 rounded-full bg-green-100 px-1.5 py-0.5 text-[11px] font-medium text-green-700"
        >
          <Package class="size-3" /> Реал.
        </span>
      </div>
      <div class="mt-0.5 text-xs tabular-nums text-neutral-500">
        {{ qtyDisplay }} шт × {{ unitDisplay }}
      </div>
      <div v-if="landedDisplay" class="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
        <span>Себестоимость</span>
        <span class="font-medium tabular-nums text-foreground">{{ landedDisplay }} {{ landedCurrency }}/шт</span>
        <span class="text-neutral-400">вкл. расходы</span>
        <span v-if="suspiciousUsdFx" class="text-amber-600">проверьте курс USD</span>
      </div>
    </div>
    <span class="shrink-0 text-sm font-semibold tabular-nums text-foreground">
      {{ totalDisplay }} {{ item.currency }}
    </span>
    <button
      v-if="isEditable"
      type="button"
      class="grid size-8 shrink-0 place-items-center rounded-lg text-neutral-400 transition-colors hover:bg-negative/10 hover:text-negative"
      aria-label="Удалить позицию"
      @click.stop="emit('delete', item.id)"
    >
      <Trash2 class="size-4" />
    </button>
    <ChevronRight v-else class="size-4 shrink-0 text-neutral-400" />
  </div>
</template>
