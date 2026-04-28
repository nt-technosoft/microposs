<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Save } from 'lucide-vue-next'
import { createInvestmentAgreement } from '@/api/partnerships'
import { fetchPartners, type Partner } from '@/api/core'
import { useIdempotency } from '@/composables/useIdempotency'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const toast = useToast()
const { generateRequestId } = useIdempotency()

const partners = ref<Partner[]>([])
const investorId = ref<number | null>(null)
const operatorId = ref<number | null>(null)
const plannedBudget = ref('15000')
const currency = ref('USD')
const investorCapitalPercent = ref('70')
const investorProfitPercentInput = ref('40')
const notes = ref('')
const saving = ref(false)
const error = ref('')

function parseDisplayNumber(value: string): number {
  const parsed = Number(value || 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatPercentPreview(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : '—'
}

const plannedBudgetValue = computed(() => parseDisplayNumber(plannedBudget.value))
const investorCapitalPercentValue = computed(() => parseDisplayNumber(investorCapitalPercent.value))
const investorProfitPercentValue = computed(() => parseDisplayNumber(investorProfitPercentInput.value))
const operatorCapitalPercentValue = computed(() => Math.max(0, 100 - investorCapitalPercentValue.value))
const operatorProfitPercentValue = computed(() => Math.max(0, 100 - investorProfitPercentValue.value))
const investorCapital = computed(() => plannedBudgetValue.value * investorCapitalPercentValue.value / 100)
const operatorCapital = computed(() => Math.max(0, Number(plannedBudget.value || 0) - investorCapital.value))
const investorProfitShare = computed(() => investorProfitPercentValue.value / 100)
const operatorProfitShare = computed(() => Math.max(0, 1 - investorProfitShare.value))
const mudarabaRatio = computed(() => {
  if (investorCapitalPercentValue.value <= 0) return Number.NaN
  return investorProfitPercentValue.value / investorCapitalPercentValue.value
})
const investorOptions = computed(() => partners.value.filter((partner) => partner.role === 'INVESTOR'))
const operatorOptions = computed(() => partners.value.filter((partner) => partner.role === 'OPERATOR'))
const investorPartnerName = computed(() => investorOptions.value.find((partner) => partner.id === investorId.value)?.display_name ?? 'Инвестор')
const operatorPartnerName = computed(() => operatorOptions.value.find((partner) => partner.id === operatorId.value)?.display_name ?? 'Бизнес')

function isPercentOutOfRange(value: number): boolean {
  return !Number.isFinite(value) || value < 0 || value > 100
}

const ratioError = computed(() => {
  if (plannedBudgetValue.value <= 0) return 'Укажите бюджет договора'
  if (isPercentOutOfRange(investorCapitalPercentValue.value)) return 'Доля капитала инвестора должна быть от 0 до 100%'
  if (isPercentOutOfRange(investorProfitPercentValue.value)) return 'Доля прибыли инвестора должна быть от 0 до 100%'
  if (!Number.isFinite(mudarabaRatio.value)) return 'Невозможно рассчитать коэффициент при нулевой доле капитала инвестора'
  if (mudarabaRatio.value < 0 || mudarabaRatio.value > 1) return 'Доля прибыли инвестора не может превышать его долю капитала'
  return ''
})

async function load(): Promise<void> {
  partners.value = await fetchPartners()
  investorId.value = investorOptions.value[0]?.id ?? null
  operatorId.value = operatorOptions.value[0]?.id ?? null
}

async function submit(): Promise<void> {
  error.value = ''
  if (!investorId.value || !operatorId.value) {
    error.value = 'Выберите инвестора и бизнес'
    return
  }
  if (ratioError.value) {
    error.value = ratioError.value
    return
  }
  saving.value = true
  try {
    const agreement = await createInvestmentAgreement({
      client_request_id: generateRequestId(),
      planned_budget: plannedBudgetValue.value.toFixed(2),
      currency: currency.value,
      mudaraba_ratio: mudarabaRatio.value.toFixed(6),
      notes: notes.value,
      partners: [
        {
          partner_id: investorId.value,
          role: 'INVESTOR',
          planned_capital_share: investorCapital.value.toFixed(2),
          profit_share: investorProfitShare.value.toFixed(6),
        },
        {
          partner_id: operatorId.value,
          role: 'OPERATOR',
          planned_capital_share: operatorCapital.value.toFixed(2),
          profit_share: operatorProfitShare.value.toFixed(6),
        },
      ],
    })
    toast.success('Инвестдоговор создан')
    router.push({ name: 'agreement-detail', params: { id: agreement.id } })
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось создать договор'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" />
      </button>
      <h1>Новый инвестдоговор</h1>
      <span />
    </header>

    <main class="content">
      <section class="panel">
        <h2>Участники</h2>
        <label>
          <span>Инвестор</span>
          <select v-model.number="investorId">
            <option :value="null">Выберите инвестора</option>
            <option v-for="partner in investorOptions" :key="partner.id" :value="partner.id">{{ partner.display_name }}</option>
          </select>
        </label>
        <label>
          <span>Бизнес</span>
          <select v-model.number="operatorId">
            <option :value="null">Выберите бизнес</option>
            <option v-for="partner in operatorOptions" :key="partner.id" :value="partner.id">{{ partner.display_name }}</option>
          </select>
        </label>
      </section>

      <section class="panel">
        <h2>Формула</h2>
        <div class="grid-2">
          <label>
            <span>Бюджет</span>
            <input v-model="plannedBudget" inputmode="decimal" />
          </label>
          <label>
            <span>Валюта</span>
            <select v-model="currency">
              <option value="USD">USD</option>
              <option value="UZS">UZS</option>
            </select>
          </label>
        </div>
        <div class="grid-2">
          <label>
            <span>Капитал инвестора, %</span>
            <input v-model="investorCapitalPercent" inputmode="decimal" />
          </label>
          <label>
            <span>Прибыль инвестора, %</span>
            <input v-model="investorProfitPercentInput" inputmode="decimal" />
          </label>
        </div>
        <div class="summary-grid">
          <div class="summary-card">
            <span class="summary-kicker">{{ investorPartnerName }}</span>
            <strong>{{ investorCapital.toFixed(2) }} {{ currency }}</strong>
            <small>капитал {{ formatPercentPreview(investorCapitalPercentValue) }}% · прибыль {{ formatPercentPreview(investorProfitPercentValue) }}%</small>
          </div>
          <div class="summary-card">
            <span class="summary-kicker">{{ operatorPartnerName }}</span>
            <strong>{{ operatorCapital.toFixed(2) }} {{ currency }}</strong>
            <small>капитал {{ formatPercentPreview(operatorCapitalPercentValue) }}% · прибыль {{ formatPercentPreview(operatorProfitPercentValue) }}%</small>
          </div>
        </div>
        <div class="formula-strip">
          <span>Коэффициент Mudaraba рассчитывается автоматически</span>
          <strong class="tabular-nums">{{ Number.isFinite(mudarabaRatio) ? mudarabaRatio.toFixed(6) : '—' }}</strong>
        </div>
        <p v-if="ratioError" class="error error-inline">{{ ratioError }}</p>
      </section>

      <section class="panel">
        <h2>Заметка</h2>
        <textarea v-model="notes" rows="3" placeholder="Например, первая партия товара по договору Устоз + бизнес" />
      </section>

      <p v-if="error" class="error">{{ error }}</p>
      <button class="primary" type="button" :disabled="saving" @click="submit">
        <Save :size="18" />
        {{ saving ? 'Сохраняю...' : 'Создать договор' }}
      </button>
    </main>
  </div>
</template>

<style scoped>
.page { min-height: 100%; background: var(--color-bg-primary); }
.topbar { position: sticky; top: 0; z-index: var(--z-sticky); display: grid; grid-template-columns: 40px 1fr 40px; align-items: center; gap: var(--space-2); min-height: var(--header-height); padding: 0 var(--space-4); border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
h1 { margin: 0; text-align: center; font-size: var(--text-lg); font-weight: var(--font-semibold); }
.icon-btn { width: 40px; height: 40px; display: grid; place-items: center; border: 0; background: transparent; color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-3); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-4)); }
.panel { display: grid; gap: var(--space-3); padding: var(--space-4); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); }
h2 { margin: 0; font-size: var(--text-base); font-weight: var(--font-semibold); }
label { display: grid; gap: 6px; }
label span { color: var(--color-text-secondary); font-size: var(--text-sm); }
input, select, textarea { width: 100%; min-height: 42px; border: 1px solid var(--color-border-default); border-radius: var(--radius-md); padding: 0 var(--space-3); background: var(--color-bg-primary); color: var(--color-text-primary); font: inherit; }
textarea { padding-top: var(--space-2); resize: vertical; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
.summary-card { display: grid; gap: 4px; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-elevated); }
.summary-kicker { color: var(--color-text-secondary); font-size: var(--text-xs); }
.summary-card strong { color: var(--color-text-primary); font-size: var(--text-base); }
.summary-card small { color: var(--color-text-secondary); font-size: var(--text-xs); line-height: 1.4; }
.formula-strip { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-elevated); }
.formula-strip span { color: var(--color-text-secondary); font-size: var(--text-xs); line-height: 1.4; }
.formula-strip strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.primary { min-height: 48px; display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 0; border-radius: var(--radius-lg); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.primary:disabled { opacity: .55; }
.error { margin: 0; color: var(--color-danger); font-size: var(--text-sm); }
.error-inline { margin-top: calc(var(--space-2) * -1); }
</style>
