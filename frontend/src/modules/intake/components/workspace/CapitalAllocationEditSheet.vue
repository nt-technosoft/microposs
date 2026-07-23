<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Allocation = { partner_id: number; amount: string }

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [allocations: Allocation[]]
}>()

const amounts = ref<Allocation[]>([])

const investment = computed(() => props.procurement.documents.investment)

const requiredUzs = computed(() => {
  const items = props.procurement.documents.items
  const expenses = props.procurement.documents.expenses
  const itemsTotal = items.reduce((s, it) => {
    return s + (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_purchase_price) || 0) * (parseFloat(it.fx_rate) || 1)
  }, 0)
  const expTotal = expenses.reduce((s, ex) => {
    return s + (parseFloat(ex.amount) || 0) * (parseFloat(ex.fx_rate) || 1)
  }, 0)
  return Math.round(itemsTotal + expTotal)
})

function availableForPartner(partnerId: number): number {
  const inv = investment.value
  if (!inv) return 0
  const val = inv.available_by_partner[String(partnerId)]?.['UZS'] ?? '0'
  return parseFloat(val) || 0
}

function prefill(): void {
  const inv = investment.value
  if (!inv) return
  amounts.value = inv.partners.map((p) => ({
    partner_id: p.partner_id,
    amount: String(Math.round(requiredUzs.value * (parseFloat(p.planned_capital_share) || 0))),
  }))
}

watch(() => props.open, (isOpen) => { if (isOpen) prefill() })

const sumAllocated = computed(() =>
  amounts.value.reduce((s, a) => s + (parseFloat(a.amount) || 0), 0),
)

const sumMatch = computed(() => Math.round(sumAllocated.value) === requiredUzs.value)

function amountForPartner(partnerId: number): string {
  return amounts.value.find((a) => a.partner_id === partnerId)?.amount ?? ''
}

function setAmount(partnerId: number, val: string): void {
  const idx = amounts.value.findIndex((a) => a.partner_id === partnerId)
  if (idx >= 0) amounts.value[idx] = { partner_id: partnerId, amount: val }
}

function partnerExceedsAvailable(partnerId: number): boolean {
  const amt = parseFloat(amounts.value.find((a) => a.partner_id === partnerId)?.amount ?? '0') || 0
  return amt > availableForPartner(partnerId)
}

const canSave = computed(() =>
  sumMatch.value &&
  !investment.value?.partners.some((p) => partnerExceedsAvailable(p.partner_id)),
)

function onSave(): void {
  emit('save', amounts.value.map((a) => ({ ...a })))
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Распределение капитала" @close="emit('update:open', false)">
    <div class="sheet-body" v-if="investment">
      <div class="required-row">
        <span class="label">К покрытию</span>
        <span class="value">{{ requiredUzs.toLocaleString('ru-RU') }} UZS</span>
      </div>

      <div v-for="p in investment.partners" :key="p.partner_id" class="partner-block">
        <div class="partner-header">
          <span class="partner-name">{{ p.partner_name }}</span>
          <span class="partner-share">{{ Math.round(parseFloat(p.planned_capital_share) * 100) }}%</span>
        </div>
        <div class="available-line">
          Доступно: {{ availableForPartner(p.partner_id).toLocaleString('ru-RU') }} UZS
          <span v-if="partnerExceedsAvailable(p.partner_id)" class="warn-text"> ⚠ превышает</span>
        </div>
        <div class="amount-row">
          <input
            class="amount-input"
            type="number"
            min="0"
            step="1"
            :value="amountForPartner(p.partner_id)"
            @input="setAmount(p.partner_id, ($event.target as HTMLInputElement).value)"
          />
          <span class="currency-tag">UZS</span>
        </div>
      </div>

      <div class="sum-row" :class="{ ok: sumMatch, mismatch: !sumMatch }">
        Итого: {{ Math.round(sumAllocated).toLocaleString('ru-RU') }} UZS
        <span v-if="sumMatch"> ✓ совпадает</span>
        <span v-else> ⚠ не совпадает</span>
      </div>

      <button class="primary-btn" type="button" :disabled="!canSave" @click="onSave">
        Сохранить распределение
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.required-row { display: flex; justify-content: space-between; padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.partner-block { display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); }
.partner-header { display: flex; align-items: center; justify-content: space-between; }
.partner-name { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.partner-share { font-size: var(--text-xs); color: var(--color-text-secondary); }
.available-line { font-size: var(--text-xs); color: var(--color-text-secondary); }
.warn-text { color: var(--color-warning); font-weight: var(--font-semibold); }
.amount-row { display: flex; align-items: center; gap: var(--space-2); }
.amount-input { flex: 1; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.currency-tag { font-size: var(--text-sm); color: var(--color-text-secondary); font-weight: var(--font-semibold); }
.sum-row { padding: var(--space-3); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: var(--font-semibold); font-variant-numeric: tabular-nums; }
.sum-row.ok { background: color-mix(in srgb, var(--color-success) 10%, transparent); color: var(--color-success); }
.sum-row.mismatch { background: color-mix(in srgb, var(--color-warning) 10%, transparent); color: var(--color-warning); }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
