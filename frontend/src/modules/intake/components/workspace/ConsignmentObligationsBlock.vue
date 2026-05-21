<script setup lang="ts">
import { computed } from 'vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{ pay: [] }>()

const payables = computed(() => props.procurement.documents.payables)

const totalRemaining = computed(() =>
  payables.value.reduce((s, p) => s + (parseFloat(p.remaining_amount) || 0), 0),
)

const hasDebt = computed(() => totalRemaining.value > 0)
</script>

<template>
  <div class="consignment-block">
    <div class="block-label">Накопленные обязательства</div>
    <div class="hint-text">По продажам с реализации ({{ payables.length }} позиций)</div>

    <div v-if="!payables.length" class="empty-text">Нет обязательств перед поставщиком.</div>

    <template v-else>
      <div class="debt-row">
        <span class="debt-label">Долг поставщику</span>
        <span class="debt-value">{{ Math.round(totalRemaining).toLocaleString('ru-RU') }} UZS</span>
      </div>

      <div class="payables-list">
        <div v-for="p in payables" :key="p.id" class="payable-row">
          <span class="payable-meta">{{ p.supplier_name ?? `Поставщик #${p.supplier_id}` }}</span>
          <span class="payable-amount">{{ parseFloat(p.remaining_amount).toLocaleString('ru-RU') }} {{ p.currency }}</span>
        </div>
      </div>

      <button v-if="hasDebt" class="pay-btn" type="button" @click="emit('pay')">
        Оплатить накопленное
      </button>
    </template>
  </div>
</template>

<style scoped>
.consignment-block { display: grid; gap: var(--space-2); }
.block-label { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.hint-text { font-size: var(--text-xs); color: var(--color-text-secondary); }
.empty-text { font-size: var(--text-sm); color: var(--color-text-secondary); padding: var(--space-2) 0; }
.debt-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: color-mix(in srgb, var(--color-warning) 10%, transparent); border-radius: var(--radius-md); }
.debt-label { font-size: var(--text-sm); color: var(--color-warning); font-weight: var(--font-semibold); }
.debt-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-warning); font-variant-numeric: tabular-nums; }
.payables-list { display: grid; gap: var(--space-1); }
.payable-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-sm); }
.payable-meta { font-size: var(--text-xs); color: var(--color-text-secondary); }
.payable-amount { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.pay-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
