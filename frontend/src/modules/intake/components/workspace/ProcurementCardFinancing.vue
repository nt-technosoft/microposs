<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, AlertCircle, ChevronRight } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import WorkspaceAgreementPickerSheet from './WorkspaceAgreementPickerSheet.vue'
import CapitalAllocationEditSheet from './CapitalAllocationEditSheet.vue'
import InvestmentAgreementDetailSheet from './InvestmentAgreementDetailSheet.vue'
import InvestmentAgreementQuickForm from './InvestmentAgreementQuickForm.vue'
import { useToast } from '@/composables/useToast'
import type { ProcurementWorkspacePayload, InvestmentAgreementDetail } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'link-agreement': [agreementId: number]
  'save-allocations': [allocations: Array<{ partner_id: number; amount: string }>]
}>()

const toast = useToast()

const pickerOpen = ref(false)
const createFormOpen = ref(false)
const detailSheetOpen = ref(false)
const allocationEditOpen = ref(false)

const investment = computed(() => props.procurement.documents.investment)

const hasAllocations = computed(() =>
  (investment.value?.allocations.length ?? 0) > 0,
)

const requiredByCurrency = computed((): Record<string, number> => {
  const totals: Record<string, number> = {}
  for (const it of props.procurement.documents.items) {
    const qty = parseFloat(it.quantity) || 0
    const price = parseFloat(it.unit_purchase_price) || 0
    const cur = it.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + qty * price
  }
  for (const ex of props.procurement.documents.expenses) {
    const amount = parseFloat(ex.amount) || 0
    const cur = ex.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + amount
  }
  return totals
})

const hasShortage = computed(() => false)

const isFilled = computed(() => hasAllocations.value)

function onAgreementSelect(id: number): void {
  emit('link-agreement', id)
}

function onCreateNew(): void {
  pickerOpen.value = false
  createFormOpen.value = true
}

function onAgreementCreated(agreement: InvestmentAgreementDetail): void {
  createFormOpen.value = false
  emit('link-agreement', agreement.id)
}

function onSaveAllocations(allocations: Array<{ partner_id: number; amount: string }>): void {
  emit('save-allocations', allocations)
}

function onRequestContribution(): void {
  toast.info('Запрос вклада инвестора — будет реализовано')
}
</script>

<template>
  <div class="financing-card">
    <div class="card-header">
      <span class="card-title">Финансирование</span>
      <CheckCircle v-if="isFilled" class="status-ok" :size="18" :stroke-width="2" />
      <AlertCircle v-else class="status-warn" :size="18" :stroke-width="2" />
    </div>

    <!-- No agreement linked -->
    <template v-if="!investment">
      <p class="hint-text">Партнёрский приход требует инвестиционный договор.</p>
      <button class="action-btn" type="button" @click="pickerOpen = true">
        Выбрать договор →
      </button>
    </template>

    <!-- Agreement linked -->
    <template v-else>
      <button class="agreement-row" type="button" @click="detailSheetOpen = true">
        <span class="agreement-label">{{ investment.agreement_label || `Договор #${investment.agreement_id}` }}</span>
        <ChevronRight :size="16" :stroke-width="2" class="chevron" />
      </button>

      <!-- No allocations yet -->
      <template v-if="!hasAllocations">
        <div class="partners-list">
          <div v-for="p in investment.partners" :key="p.partner_id" class="partner-row">
            <span class="partner-name">{{ p.partner_name }}</span>
            <span class="partner-share">{{ Math.round(parseFloat(p.profit_share) * 100) }}%</span>
          </div>
        </div>

        <div class="coverage-row">
          <span class="coverage-label">К покрытию</span>
          <span class="coverage-value">
            <template v-for="(amount, cur) in requiredByCurrency" :key="cur">
              <span style="font-variant-numeric: tabular-nums">{{ amount.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ cur }}</span>
            </template>
          </span>
        </div>

        <button class="action-btn" type="button" @click="onRequestContribution">
          Запросить вклад инвестора
        </button>
      </template>

      <!-- Allocations set -->
      <template v-else>
        <div class="allocations-list">
          <div v-for="a in investment.allocations" :key="a.id" class="allocation-row">
            <span class="alloc-partner">
              {{ investment.partners.find(p => p.partner_id === a.partner_id)?.partner_name ?? `#${a.partner_id}` }}
            </span>
            <span class="alloc-amount">{{ parseFloat(a.amount).toLocaleString('ru-RU') }} {{ a.currency }}</span>
          </div>
        </div>
        <div class="coverage-row">
          <span class="coverage-label">К списанию из договора</span>
          <span class="coverage-value">
            <template v-for="(amount, cur) in requiredByCurrency" :key="cur">
              <span style="font-variant-numeric: tabular-nums">{{ amount.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ cur }}</span>
            </template>
          </span>
        </div>
      </template>
    </template>
  </div>

  <WorkspaceAgreementPickerSheet
    v-model:open="pickerOpen"
    :selected-agreement-id="investment?.agreement_id ?? null"
    @select="onAgreementSelect"
    @create-new="onCreateNew"
  />

  <AppBottomSheet :open="createFormOpen" title="Новый договор" @close="createFormOpen = false">
    <InvestmentAgreementQuickForm @created="onAgreementCreated" />
  </AppBottomSheet>

  <InvestmentAgreementDetailSheet
    :open="detailSheetOpen"
    :agreement-id="investment?.agreement_id ?? null"
    :current-procurement-id="procurement.id"
    @close="detailSheetOpen = false"
  />

  <CapitalAllocationEditSheet
    v-model:open="allocationEditOpen"
    :procurement="procurement"
    @save="onSaveAllocations"
  />
</template>

<style scoped>
.financing-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.status-ok { color: var(--color-success); }
.status-warn { color: var(--color-warning); }
.hint-text { font-size: var(--text-sm); color: var(--color-text-secondary); margin: 0; }
.agreement-row { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-secondary); cursor: pointer; text-align: left; }
.agreement-label { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.chevron { color: var(--color-text-tertiary); flex-shrink: 0; }
.partners-list { display: grid; gap: var(--space-2); }
.partner-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.partner-name { font-size: var(--text-sm); color: var(--color-text-primary); }
.partner-share { font-size: var(--text-xs); color: var(--color-text-secondary); font-weight: var(--font-semibold); }
.coverage-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.coverage-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.coverage-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.shortage-notice { padding: var(--space-3); background: color-mix(in srgb, var(--color-warning) 10%, transparent); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--color-warning); font-weight: var(--font-semibold); }
.available-row { padding: var(--space-2) var(--space-3); font-size: var(--text-sm); color: var(--color-success); font-weight: var(--font-semibold); }
.allocations-list { display: grid; gap: var(--space-2); }
.allocation-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.alloc-partner { font-size: var(--text-sm); color: var(--color-text-primary); }
.alloc-amount { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.action-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.secondary-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
