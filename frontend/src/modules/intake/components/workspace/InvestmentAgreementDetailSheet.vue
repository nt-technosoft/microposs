<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { fetchInvestmentAgreement, type InvestmentAgreementDetail } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'

const props = defineProps<{
  open: boolean
  agreementId: number | null
  currentProcurementId: number | null
}>()

const emit = defineEmits<{
  close: []
}>()

const agreement = ref<InvestmentAgreementDetail | null>(null)
const isLoading = ref(false)
const error = ref('')
const simulatedInvestorCapitalPercentDraft = ref('')

const investorPartner = computed(() => agreement.value?.partners.find((partner) => partner.role === 'INVESTOR') ?? null)
const operatorPartner = computed(() => agreement.value?.partners.find((partner) => partner.role === 'OPERATOR') ?? null)
const plannedBudget = computed(() => Number(agreement.value?.planned_budget ?? 0))
const investorCapitalPercent = computed(() => {
  if (!investorPartner.value || plannedBudget.value <= 0) return 0
  return (Number(investorPartner.value.planned_capital_share || 0) / plannedBudget.value) * 100
})
const operatorCapitalPercent = computed(() => Math.max(0, 100 - investorCapitalPercent.value))
const investorProfitPercent = computed(() => Number(investorPartner.value?.profit_share ?? 0) * 100)
const operatorProfitPercent = computed(() => Math.max(0, 100 - investorProfitPercent.value))
const mudarabaRatio = computed(() => Number(agreement.value?.mudaraba_ratio ?? 0))
const simulatedInvestorCapitalPercent = computed(() => {
  if (simulatedInvestorCapitalPercentDraft.value !== '') return clampPercent(simulatedInvestorCapitalPercentDraft.value)
  return investorCapitalPercent.value
})
const simulatedInvestorProfitPercent = computed(() => Math.min(100, Math.max(0, simulatedInvestorCapitalPercent.value * mudarabaRatio.value)))
const simulatedOperatorProfitPercent = computed(() => Math.max(0, 100 - simulatedInvestorProfitPercent.value))
const simulationRangeStyle = computed(() => ({ '--split': `${simulatedInvestorCapitalPercent.value}%` }))
const otherProcurements = computed(() => (
  agreement.value?.procurements.filter((procurement) => procurement.id !== props.currentProcurementId) ?? []
))

function clampPercent(value: string | number): number {
  const parsed = typeof value === 'number' ? value : Number(value || 0)
  return Math.min(100, Math.max(0, Number.isFinite(parsed) ? parsed : 0))
}

function formatPercent(value: number): string {
  return `${(Number.isFinite(value) ? value : 0).toFixed(2)}%`
}

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function balanceLabel(): string {
  if (!agreement.value) return '—'
  const amount = Number(agreement.value.balances?.[agreement.value.currency] ?? 0)
  return formatPrice(Number.isFinite(amount) ? amount : 0, agreement.value.currency)
}

async function loadAgreement(): Promise<void> {
  if (!props.open || !props.agreementId) return
  isLoading.value = true
  error.value = ''
  try {
    agreement.value = await fetchInvestmentAgreement(props.agreementId)
    simulatedInvestorCapitalPercentDraft.value = ''
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить инвестдоговор'
  } finally {
    isLoading.value = false
  }
}

watch(() => [props.open, props.agreementId] as const, loadAgreement, { immediate: true })
</script>

<template>
  <AppBottomSheet :open="open" title="Инвестдоговор" @close="emit('close')">
    <div class="detail-sheet">
      <div v-if="isLoading" class="muted">Загрузка договора…</div>
      <p v-else-if="error" class="error-note">{{ error }}</p>

      <template v-else-if="agreement">
        <section class="hero-row">
          <div>
            <strong>#{{ agreement.id }} · {{ investorPartner?.partner_name ?? 'Инвестор' }}</strong>
            <span>{{ dateLabel(agreement.opened_at) }}</span>
          </div>
          <b>{{ agreement.status }}</b>
        </section>

        <section class="metric-grid">
          <div>
            <span>Бюджет</span>
            <strong>{{ formatPrice(Number(agreement.planned_budget || 0), agreement.currency) }}</strong>
          </div>
          <div>
            <span>Доступно</span>
            <strong>{{ balanceLabel() }}</strong>
          </div>
        </section>

        <section class="formula-grid">
          <div>
            <span>{{ investorPartner?.partner_name ?? 'Инвестор' }}</span>
            <strong>{{ formatPrice(Number(investorPartner?.planned_capital_share || 0), agreement.currency) }}</strong>
            <small>капитал {{ formatPercent(investorCapitalPercent) }} · прибыль {{ formatPercent(investorProfitPercent) }}</small>
          </div>
          <div>
            <span>{{ operatorPartner?.partner_name ?? 'Бизнес' }}</span>
            <strong>{{ formatPrice(Number(operatorPartner?.planned_capital_share || 0), agreement.currency) }}</strong>
            <small>капитал {{ formatPercent(operatorCapitalPercent) }} · прибыль {{ formatPercent(operatorProfitPercent) }}</small>
          </div>
        </section>

        <section class="recalculation-panel">
          <div class="recalculation-copy">
            <strong>Симуляция фактических долей</strong>
            <span>Если фактический вклад партии отличается от плана, прибыль пересчитывается по коэффициенту договора.</span>
          </div>
          <div class="split-header">
            <span>Фактическая доля инвестора</span>
            <strong>{{ formatPercent(simulatedInvestorCapitalPercent) }}</strong>
          </div>
          <input
            v-model="simulatedInvestorCapitalPercentDraft"
            class="split-range"
            type="range"
            min="0"
            max="100"
            step="0.1"
            :style="simulationRangeStyle"
          />
          <div class="simulation-result">
            <div>
              <span>Прибыль инвестора</span>
              <strong>{{ formatPercent(simulatedInvestorProfitPercent) }}</strong>
            </div>
            <div>
              <span>Прибыль бизнеса</span>
              <strong>{{ formatPercent(simulatedOperatorProfitPercent) }}</strong>
            </div>
          </div>
        </section>

        <section class="linked-procurements">
          <h3>Другие приходы по договору</h3>
          <p v-if="otherProcurements.length === 0" class="muted">Других приходов по этому договору пока нет.</p>
          <div v-else class="procurement-list">
            <article v-for="procurement in otherProcurements" :key="procurement.id" class="procurement-row">
              <div>
                <strong>#{{ procurement.id }}</strong>
                <span>{{ dateLabel(procurement.opened_at) }} · {{ procurement.status }}</span>
              </div>
              <b>{{ formatPrice(Number(procurement.total_amount || 0), agreement.currency) }}</b>
            </article>
          </div>
        </section>
      </template>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.detail-sheet,
.recalculation-panel,
.linked-procurements,
.procurement-list {
  display: grid;
  gap: 12px;
}

.hero-row,
.metric-grid > div,
.formula-grid > div,
.simulation-result > div,
.procurement-row {
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
}

.hero-row,
.procurement-row,
.split-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hero-row div,
.procurement-row div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.hero-row strong,
.procurement-row strong,
.recalculation-copy strong,
.linked-procurements h3 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.hero-row span,
.procurement-row span,
.metric-grid span,
.formula-grid span,
.formula-grid small,
.simulation-result span,
.recalculation-copy span,
.muted,
.error-note {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.hero-row b {
  color: var(--color-brand-700);
  font-size: var(--text-xs);
}

.metric-grid,
.formula-grid,
.simulation-result {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-grid > div,
.formula-grid > div,
.simulation-result > div {
  display: grid;
  gap: 4px;
}

.metric-grid strong,
.formula-grid strong,
.simulation-result strong,
.procurement-row b,
.split-header strong {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-variant-numeric: tabular-nums;
}

.recalculation-panel {
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
}

.recalculation-copy {
  display: grid;
  gap: 4px;
}

.split-range {
  width: 100%;
  height: 8px;
  border-radius: var(--radius-full);
  appearance: none;
  background: linear-gradient(to right, var(--color-accent-400) 0 var(--split), var(--color-brand-500) var(--split) 100%);
  outline: none;
}

.split-range::-webkit-slider-thumb {
  width: 22px;
  height: 22px;
  border: 2px solid var(--color-brand-600);
  border-radius: var(--radius-full);
  appearance: none;
  background: var(--color-bg-elevated);
  box-shadow: 0 2px 8px rgba(17, 24, 39, 0.16);
}

.error-note {
  color: var(--color-danger);
}

@media (max-width: 430px) {
  .formula-grid,
  .simulation-result {
    grid-template-columns: 1fr;
  }
}
</style>
