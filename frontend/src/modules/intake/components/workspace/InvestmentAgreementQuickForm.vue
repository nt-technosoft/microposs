<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Copy, Send, UserPlus } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import WorkspaceQuickPartnerSheet from './WorkspaceQuickPartnerSheet.vue'
import { createInvestorInvite, fetchPartners, type InvestorInvite, type Partner } from '@/api/core'
import { createInvestmentAgreement, type InvestmentAgreementDetail } from '@/api/partnerships'
import { useIdempotency } from '@/composables/useIdempotency'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

const emit = defineEmits<{
  created: [agreement: InvestmentAgreementDetail]
}>()

const toast = useToast()
const { generateRequestId } = useIdempotency()

const partners = ref<Partner[]>([])
const investorId = ref<number | null>(null)
const investorPlannedAmount = ref('10000')
const currency = ref<'USD' | 'UZS'>('USD')
const investorCapitalPercent = ref('70')
const investorProfitPercentInput = ref('40')
const simulatedInvestorCapitalPercentDraft = ref('')
const notes = ref('')
const saving = ref(false)
const isLoading = ref(false)
const error = ref('')
const inviteOpen = ref(false)
const inviteName = ref('')
const inviteEmail = ref('')
const isInviting = ref(false)
const createdInvite = ref<InvestorInvite | null>(null)
const quickPartnerOpen = ref(false)

const investorOptions = computed(() => partners.value.filter((partner) => partner.role === 'INVESTOR' && partner.is_active))
const operatorPartner = computed(() => partners.value.find((partner) => partner.role === 'OPERATOR' && partner.is_active) ?? null)
const selectedInvestor = computed(() => investorOptions.value.find((partner) => partner.id === investorId.value) ?? null)

function parseNumber(value: string): number {
  const parsed = Number(value || 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function clampPercent(value: string | number): number {
  const parsed = typeof value === 'number' ? value : parseNumber(value)
  return Math.min(100, Math.max(0, Number.isFinite(parsed) ? parsed : 0))
}

function formatPercent(value: number): string {
  return `${(Number.isFinite(value) ? value : 0).toFixed(2)}%`
}

const investorPlannedAmountValue = computed(() => parseNumber(investorPlannedAmount.value))
const investorCapitalPercentValue = computed(() => clampPercent(investorCapitalPercent.value))
const investorProfitPercentValue = computed(() => clampPercent(investorProfitPercentInput.value))
const operatorCapitalPercentValue = computed(() => Math.max(0, 100 - investorCapitalPercentValue.value))
const operatorProfitPercentValue = computed(() => Math.max(0, 100 - investorProfitPercentValue.value))
const plannedBudgetValue = computed(() => {
  if (investorCapitalPercentValue.value <= 0) return 0
  return investorPlannedAmountValue.value / (investorCapitalPercentValue.value / 100)
})
const investorCapital = computed(() => investorPlannedAmountValue.value)
const operatorCapital = computed(() => Math.max(0, plannedBudgetValue.value - investorCapital.value))
const mudarabaRatio = computed(() => {
  if (investorCapitalPercentValue.value <= 0) return Number.NaN
  return investorProfitPercentValue.value / investorCapitalPercentValue.value
})
const simulatedInvestorCapitalPercent = computed(() => (
  simulatedInvestorCapitalPercentDraft.value
    ? clampPercent(simulatedInvestorCapitalPercentDraft.value)
    : investorCapitalPercentValue.value
))
const simulatedInvestorProfitPercent = computed(() => {
  if (!Number.isFinite(mudarabaRatio.value)) return 0
  return Math.min(100, Math.max(0, simulatedInvestorCapitalPercent.value * mudarabaRatio.value))
})
const simulatedOperatorProfitPercent = computed(() => Math.max(0, 100 - simulatedInvestorProfitPercent.value))
const simulationCapitalDelta = computed(() => simulatedInvestorCapitalPercent.value - investorCapitalPercentValue.value)
const hasSimulationDelta = computed(() => Math.abs(simulationCapitalDelta.value) > 0.05)
const simulationExplanation = computed(() => {
  const direction = simulationCapitalDelta.value > 0 ? 'выше' : 'ниже'
  return `Если фактическая доля инвестора будет ${direction} плана: ${formatPercent(simulatedInvestorCapitalPercent.value)} вместо ${formatPercent(investorCapitalPercentValue.value)}, его доля прибыли будет ${formatPercent(simulatedInvestorProfitPercent.value)} вместо ${formatPercent(investorProfitPercentValue.value)}.`
})
const simulationRangeStyle = computed(() => ({ '--split': `${simulatedInvestorCapitalPercent.value}%` }))

const ratioError = computed(() => {
  if (!investorId.value) return 'Выберите инвестора'
  if (!operatorPartner.value) return 'Для бизнеса не найден оператор. Его нужно создать в базовых данных.'
  if (investorPlannedAmountValue.value <= 0) return 'Укажите сумму, которую планирует вложить инвестор'
  if (investorCapitalPercentValue.value <= 0) return 'Доля капитала инвестора должна быть больше 0'
  if (!Number.isFinite(mudarabaRatio.value) || mudarabaRatio.value < 0 || mudarabaRatio.value > 1) return 'Формула прибыли не сходится с долей капитала'
  return ''
})

async function loadPartners(): Promise<void> {
  isLoading.value = true
  try {
    partners.value = await fetchPartners({ is_active: true })
    investorId.value = investorOptions.value[0]?.id ?? null
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить инвесторов'
  } finally {
    isLoading.value = false
  }
}

function setSimulationCapitalPercent(value: string): void {
  simulatedInvestorCapitalPercentDraft.value = value
}

function resetSimulation(): void {
  simulatedInvestorCapitalPercentDraft.value = ''
}

function inviteUrl(invite: InvestorInvite): string {
  return `${window.location.origin}${invite.invite_path}`
}

async function copyInvite(invite: InvestorInvite): Promise<void> {
  await navigator.clipboard.writeText(inviteUrl(invite))
  toast.success('Ссылка приглашения скопирована')
}

async function createInvite(): Promise<void> {
  isInviting.value = true
  error.value = ''
  try {
    const invite = await createInvestorInvite({
      display_name: inviteName.value.trim(),
      email: inviteEmail.value.trim(),
    })
    createdInvite.value = invite
    await copyInvite(invite)
  } catch (inviteError) {
    error.value = inviteError instanceof Error ? inviteError.message : 'Не удалось создать приглашение'
  } finally {
    isInviting.value = false
  }
}

async function submit(): Promise<void> {
  error.value = ''
  if (ratioError.value) {
    error.value = ratioError.value
    return
  }
  saving.value = true
  try {
    const agreement = await createInvestmentAgreement({
      client_request_id: generateRequestId(),
      investor_partner_id: investorId.value as number,
      investor_planned_amount: investorPlannedAmountValue.value.toFixed(2),
      investor_capital_percent: investorCapitalPercentValue.value.toFixed(4),
      investor_profit_percent: investorProfitPercentValue.value.toFixed(4),
      currency: currency.value,
      notes: notes.value,
    })
    toast.success('Инвестдоговор создан')
    emit('created', agreement)
  } catch (submitError) {
    error.value = submitError instanceof Error ? submitError.message : 'Не удалось создать инвестдоговор'
  } finally {
    saving.value = false
  }
}

function onPartnerCreated(partner: Partner): void {
  partners.value = [...partners.value, partner]
  investorId.value = partner.id
}

onMounted(loadPartners)
</script>

<template>
  <div class="agreement-form">
    <section class="form-panel">
      <div class="panel-head">
        <div>
          <h2>Инвестор</h2>
          <p>Бизнес участвует в договоре автоматически. Выберите только внешнего инвестора.</p>
        </div>
        <div class="panel-head-actions">
          <button class="ghost-action" type="button" @click="quickPartnerOpen = true">
            <UserPlus :size="15" :stroke-width="2" />
            Создать
          </button>
          <button class="ghost-action" type="button" @click="inviteOpen = true">
            <Send :size="15" :stroke-width="2" />
            Пригласить
          </button>
        </div>
      </div>

      <div v-if="isLoading" class="muted">Загрузка инвесторов…</div>
      <div v-else-if="investorOptions.length === 0" class="empty-box">
        <strong>Нет активных инвесторов</strong>
        <span>Создайте приглашение. После принятия инвестор появится в списке.</span>
      </div>
      <div v-else class="investor-list">
        <button
          v-for="partner in investorOptions"
          :key="partner.id"
          class="investor-card"
          :class="{ active: investorId === partner.id }"
          type="button"
          @click="investorId = partner.id"
        >
          <span>{{ partner.display_name }}</span>
          <small>{{ investorId === partner.id ? 'Выбран для договора' : 'Активный инвестор' }}</small>
        </button>
      </div>
    </section>

    <section class="form-panel">
      <h2>Формула</h2>
      <p class="panel-note">
        Договор строится от реального намерения инвестора. Общий объём и вклад бизнеса система считает сама.
      </p>
      <div class="money-row">
        <label class="field-group">
          <span>Инвестор планирует вложить</span>
          <MoneyCurrencyInput
            v-model="investorPlannedAmount"
            v-model:currency="currency"
            size="lg"
            aria-label="Сумма, которую инвестор планирует вложить"
          />
        </label>
      </div>

      <div class="grid-2">
        <label class="field-group">
          <span>Капитал инвестора, %</span>
          <input v-model="investorCapitalPercent" class="input-field" inputmode="decimal" />
        </label>
        <label class="field-group">
          <span>Прибыль инвестора, %</span>
          <input v-model="investorProfitPercentInput" class="input-field" inputmode="decimal" />
        </label>
      </div>

      <div class="summary-grid">
        <div class="summary-card">
          <span>{{ selectedInvestor?.display_name ?? 'Инвестор' }}</span>
          <strong>{{ formatPrice(investorCapital, currency) }}</strong>
          <small>плановый вклад инвестора</small>
        </div>
        <div class="summary-card">
          <span>Бизнесу внести</span>
          <strong>{{ formatPrice(operatorCapital, currency) }}</strong>
          <small>чтобы сохранить долю {{ formatPercent(operatorCapitalPercentValue) }}</small>
        </div>
      </div>

      <div class="formula-strip formula-strip--stacked">
        <span>Ориентировочный общий объём договора</span>
        <strong>{{ formatPrice(plannedBudgetValue, currency) }}</strong>
      </div>
      <div class="formula-strip">
        <span>Коэффициент Mudaraba для будущего пересчёта</span>
        <strong>{{ Number.isFinite(mudarabaRatio) ? mudarabaRatio.toFixed(6) : '—' }}</strong>
      </div>
    </section>

    <section class="recalculation-panel">
      <div class="recalculation-copy">
        <strong>Если фактическая доля отличается от плана</strong>
        <span>При приёмке система фиксирует фактическую долю капитала партии и пересчитывает прибыль по коэффициенту договора.</span>
      </div>
      <div class="split-control">
        <div class="split-header">
          <span>Фактическая доля капитала инвестора</span>
          <strong>{{ formatPercent(simulatedInvestorCapitalPercent) }}</strong>
        </div>
        <input
          class="split-range"
          type="range"
          min="0"
          max="100"
          step="0.1"
          :value="simulatedInvestorCapitalPercent"
          :style="simulationRangeStyle"
          @input="(event) => setSimulationCapitalPercent((event.target as HTMLInputElement).value)"
        />
        <div class="range-labels">
          <span>Бизнес {{ formatPercent(100 - simulatedInvestorCapitalPercent) }}</span>
          <span>Инвестор {{ formatPercent(simulatedInvestorCapitalPercent) }}</span>
        </div>
      </div>
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
      <div class="recalculation-note" :class="{ active: hasSimulationDelta }">
        <span v-if="hasSimulationDelta">
          {{ simulationExplanation }}
        </span>
        <span v-else>Сейчас симуляция совпадает с планом договора.</span>
        <button type="button" @click="resetSimulation">Сбросить</button>
      </div>
    </section>

    <section class="form-panel">
      <label class="field-group">
        <span>Заметка</span>
        <textarea v-model="notes" class="input-field textarea-field" rows="3" placeholder="Например, первая партия товара по договору" />
      </label>
    </section>

    <p v-if="error" class="error-note">{{ error }}</p>
    <button class="primary-action" type="button" :disabled="saving" @click="submit">
      {{ saving ? 'Создание…' : 'Создать договор' }}
    </button>

    <WorkspaceQuickPartnerSheet
      v-model:open="quickPartnerOpen"
      @created="onPartnerCreated"
    />

    <AppBottomSheet :open="inviteOpen" title="Пригласить инвестора" @close="inviteOpen = false">
      <div class="invite-sheet">
        <input v-model="inviteName" class="input-field" placeholder="Имя инвестора" />
        <input v-model="inviteEmail" class="input-field" type="email" placeholder="Email, если есть" />
        <button class="primary-action" type="button" :disabled="isInviting" @click="createInvite">
          <Send :size="16" :stroke-width="2" />
          {{ isInviting ? 'Создание…' : 'Создать ссылку приглашения' }}
        </button>
        <div v-if="createdInvite" class="invite-result">
          <span>{{ inviteUrl(createdInvite) }}</span>
          <button type="button" @click="copyInvite(createdInvite)">
            <Copy :size="14" :stroke-width="2" />
            Скопировать
          </button>
        </div>
      </div>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.agreement-form,
.form-panel,
.recalculation-panel,
.invite-sheet {
  display: grid;
  gap: 12px;
}

.form-panel,
.recalculation-panel {
  padding: 14px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

h2,
.panel-head h2 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.panel-head p,
.panel-note,
.muted,
.empty-box span,
.recalculation-copy span,
.error-note {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.panel-note {
  margin: -4px 0 2px;
}

.panel-head-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.ghost-action {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.investor-list {
  display: grid;
  gap: 8px;
}

.investor-card {
  display: grid;
  gap: 3px;
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  text-align: left;
}

.investor-card.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.investor-card span,
.empty-box strong,
.recalculation-copy strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.investor-card small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.empty-box {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.grid-2,
.money-row,
.summary-grid,
.simulation-result {
  display: grid;
  gap: 8px;
}

.grid-2,
.summary-grid,
.simulation-result {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.money-row {
  grid-template-columns: 1fr;
}

.field-group {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.field-group span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.input-field {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font: inherit;
}

.textarea-field {
  min-height: 88px;
  padding-top: 10px;
  resize: vertical;
}

.summary-card,
.formula-strip,
.simulation-result > div,
.recalculation-note {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.summary-card span,
.formula-strip span,
.simulation-result span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.summary-card strong,
.formula-strip strong,
.simulation-result strong {
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.summary-card small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: 1.35;
}

.formula-strip,
.split-header,
.recalculation-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.formula-strip--stacked {
  align-items: flex-start;
}

.recalculation-copy {
  display: grid;
  gap: 5px;
}

.split-control {
  display: grid;
  gap: 8px;
}

.split-header {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.split-header strong {
  color: var(--color-text-primary);
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

.range-labels {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.recalculation-note {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.recalculation-note.active {
  background: var(--color-accent-50);
  color: var(--color-accent-700);
}

.recalculation-note button {
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
}

.primary-action {
  min-height: 46px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-weight: var(--font-semibold);
}

.primary-action:disabled {
  opacity: 0.58;
}

.error-note {
  color: var(--color-danger);
}

.invite-result {
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.invite-result span {
  overflow-wrap: anywhere;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.invite-result button {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
}

@media (max-width: 340px) {
  .grid-2,
  .summary-grid,
  .simulation-result {
    grid-template-columns: 1fr;
  }
}
</style>
