<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, Sparkles } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Button } from '@/components/ui/button'
import AgreementRecalcSimulator from './AgreementRecalcSimulator.vue'
import { fetchInvestmentAgreement, type InvestmentAgreementDetail } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { statusLabel } from '@/modules/intake/utils/procurementListPresentation'

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
const simulatorOpen = ref(false)

const currency = computed(() => agreement.value?.currency ?? 'UZS')
const investorPartner = computed(() => agreement.value?.partners.find((p) => p.role === 'INVESTOR') ?? null)
const investorName = computed(() => investorPartner.value?.partner_name ?? 'Инвестор')
const plannedBudget = computed(() => Number(agreement.value?.planned_budget ?? 0) || 0)
const mudarabaRatio = computed(() => Number(agreement.value?.mudaraba_ratio ?? 0) || 0)

// Budget states: planned vs contributed (deposited by all) vs available.
const availableAmount = computed(() => Number(agreement.value?.balances?.[currency.value] ?? 0) || 0)
const totals = computed(() => agreement.value?.participant_totals ?? [])
const totalContributed = computed(() => totals.value.reduce((sum, p) => sum + (Number(p.contributed_amount) || 0), 0))
const contributedAmount = computed(() => totalContributed.value)
const trackBase = computed(() => Math.max(plannedBudget.value, contributedAmount.value, 1))
const availablePercent = computed(() => Math.min(100, (availableAmount.value / trackBase.value) * 100))
const usedAmount = computed(() => Math.max(0, contributedAmount.value - availableAmount.value))
const usedPercent = computed(() => Math.min(100, (usedAmount.value / trackBase.value) * 100))
const isFunded = computed(() => plannedBudget.value > 0 && contributedAmount.value >= plannedBudget.value)
const isUnderFunded = computed(() => plannedBudget.value > 0 && contributedAmount.value < plannedBudget.value)
const overAmount = computed(() => Math.max(0, contributedAmount.value - plannedBudget.value))
const contributedPercentOfPlan = computed(() =>
  plannedBudget.value > 0 ? Math.round((contributedAmount.value / plannedBudget.value) * 100) : 0,
)
const budgetCaption = computed(() => {
  if (!isFunded.value) return `внесено ${contributedPercentOfPlan.value}% от плана`
  if (overAmount.value > 0) return `сверх плана на ${formatPrice(overAmount.value, currency.value)}`
  return 'профинансирован полностью'
})

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0))
}

const investorPlannedCapitalPercent = computed(() => {
  const planned = Number(investorPartner.value?.planned_capital_share ?? 0) || 0
  return plannedBudget.value > 0 ? (planned / plannedBudget.value) * 100 : 0
})
const investorActualCapitalPercent = computed(() => {
  const investorRow = totals.value.find((p) => p.role === 'INVESTOR')
  if (!investorRow || totalContributed.value <= 0) return null
  return (Number(investorRow.contributed_amount) / totalContributed.value) * 100
})
// Investor profit recalculated from actual capital share via mudaraba ratio.
const investorActualProfit = computed(() =>
  investorActualCapitalPercent.value != null
    ? clampPercent(investorActualCapitalPercent.value * mudarabaRatio.value)
    : null,
)

const partyRows = computed(() => {
  const cur = currency.value
  const total = totalContributed.value
  return totals.value.map((p) => {
    const contributedNum = Number(p.contributed_amount) || 0
    const plannedNum = Number(p.planned_capital_share) || 0
    const planCapPct = plannedBudget.value > 0 ? Math.round((plannedNum / plannedBudget.value) * 100) : null
    const factCapPct = total > 0 ? Math.round((contributedNum / total) * 100) : null
    let factProfit: number | null = null
    if (investorActualProfit.value != null) {
      factProfit = p.role === 'INVESTOR'
        ? Math.round(investorActualProfit.value)
        : Math.round(clampPercent(100 - investorActualProfit.value))
    }
    // Neutral deviation marker (not good/bad): did the actual share land above
    // or below the agreed share?
    let capDirection: 'up' | 'down' | null = null
    if (factCapPct != null && planCapPct != null && factCapPct !== planCapPct) {
      capDirection = factCapPct > planCapPct ? 'up' : 'down'
    }
    return {
      key: p.partner_id,
      name: p.role === 'OPERATOR' ? 'Бизнес' : p.partner_name,
      // plan (the agreement)
      planCapPct,
      planProfit: Math.round((Number(p.planned_profit_share) || 0) * 100),
      planMoney: formatPrice(plannedNum, cur),
      // fact (current reality)
      factMoney: formatPrice(contributedNum, cur),
      factCapPct,
      factProfit,
      capDirection,
    }
  })
})

const procurements = computed(() => agreement.value?.procurements ?? [])

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function loadAgreement(): Promise<void> {
  if (!props.open || !props.agreementId) return
  isLoading.value = true
  error.value = ''
  simulatorOpen.value = false
  try {
    agreement.value = await fetchInvestmentAgreement(props.agreementId)
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
    <div class="flex flex-col gap-4">
      <p v-if="isLoading" class="text-sm text-neutral-500">Загрузка договора…</p>
      <p v-else-if="error" class="text-sm text-negative">{{ error }}</p>

      <template v-else-if="agreement">
        <!-- Identity -->
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-foreground">Инвестдоговор #{{ agreement.id }}</p>
            <p class="mt-0.5 text-xs text-neutral-500">{{ investorName }} · {{ dateLabel(agreement.opened_at) }}</p>
          </div>
          <span class="shrink-0 rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-600">
            {{ agreement.status }}
          </span>
        </div>

        <!-- Budget: planned / contributed / available -->
        <div class="flex flex-col gap-3 rounded-[10px] border border-neutral-200 p-3">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs font-medium text-neutral-500">Бюджет договора</span>
            <span class="text-xs" :class="isUnderFunded ? 'text-warning' : 'text-neutral-400'">{{ budgetCaption }}</span>
          </div>
          <div class="flex h-2 overflow-hidden rounded-full bg-neutral-200">
            <div class="bg-green-600" :style="{ width: `${availablePercent}%` }" />
            <div :class="isFunded ? 'bg-green-600' : 'bg-neutral-400'" :style="{ width: `${usedPercent}%` }" />
          </div>
          <div class="flex flex-col gap-1.5 pt-0.5">
            <div v-if="!isFunded" class="flex items-baseline justify-between gap-2">
              <span class="text-sm text-neutral-600">Запланировано</span>
              <span class="text-sm font-medium tabular-nums text-foreground">{{ formatPrice(plannedBudget, currency) }}</span>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <span class="flex items-center gap-1.5 text-sm text-neutral-600">
                <span class="size-2 rounded-full" :class="isFunded ? 'bg-green-600' : 'bg-neutral-400'" aria-hidden="true" /> Внесено
              </span>
              <span class="text-sm font-medium tabular-nums" :class="isUnderFunded ? 'text-warning' : 'text-foreground'">{{ formatPrice(contributedAmount, currency) }}</span>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <span class="flex items-center gap-1.5 text-sm text-neutral-600">
                <span class="size-2 rounded-full bg-green-600" aria-hidden="true" /> Доступно
              </span>
              <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(availableAmount, currency) }}</span>
            </div>
          </div>
        </div>

        <!-- Plan: the fixed agreement. Same fr columns as the fact block below
             so деньги/капитал/прибыль line up vertically for comparison. -->
        <div class="flex flex-col gap-2 rounded-[10px] border border-neutral-200 p-3">
          <span class="text-xs font-medium text-neutral-500">По договору</span>
          <div class="grid grid-cols-[1.1fr_1fr_0.7fr_0.7fr] items-baseline gap-x-3 gap-y-1.5 text-sm">
            <span></span>
            <span class="text-right text-xs text-neutral-400">план</span>
            <span class="text-right text-xs text-neutral-400">капитал</span>
            <span class="text-right text-xs text-neutral-400">прибыль</span>
            <template v-for="party in partyRows" :key="`plan-${party.key}`">
              <span class="min-w-0 truncate font-medium text-foreground">{{ party.name }}</span>
              <span class="whitespace-nowrap text-right tabular-nums text-foreground">{{ party.planMoney }}</span>
              <span class="text-right tabular-nums text-foreground">{{ party.planCapPct != null ? `${party.planCapPct}%` : '—' }}</span>
              <span class="text-right tabular-nums text-foreground">{{ party.planProfit }}%</span>
            </template>
          </div>
        </div>

        <!-- Fact: current reality. Identical column template → aligned with plan. -->
        <div class="flex flex-col gap-2 rounded-[10px] border border-neutral-200 p-3">
          <span class="text-xs font-medium text-neutral-500">Фактически</span>
          <div class="grid grid-cols-[1.1fr_1fr_0.7fr_0.7fr] items-baseline gap-x-3 gap-y-1.5 text-sm">
            <span></span>
            <span class="text-right text-xs text-neutral-400">внёс</span>
            <span class="text-right text-xs text-neutral-400">капитал</span>
            <span class="text-right text-xs text-neutral-400">прибыль</span>
            <template v-for="party in partyRows" :key="`fact-${party.key}`">
              <span class="min-w-0 truncate font-medium text-foreground">{{ party.name }}</span>
              <span class="whitespace-nowrap text-right tabular-nums text-foreground">{{ party.factMoney }}</span>
              <span
                class="text-right tabular-nums"
                :class="party.capDirection ? 'font-medium text-warning' : 'text-foreground'"
              >
                {{ party.factCapPct != null ? `${party.factCapPct}%` : '—' }}<span
                  v-if="party.capDirection"
                  :title="party.capDirection === 'up' ? 'выше плана' : 'ниже плана'"
                >{{ party.capDirection === 'up' ? ' ▴' : ' ▾' }}</span>
              </span>
              <span class="text-right font-semibold tabular-nums text-foreground">{{ party.factProfit != null ? `${party.factProfit}%` : '—' }}</span>
            </template>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <Button
            variant="ghost"
            size="sm"
            class="self-start text-neutral-600"
            :aria-expanded="simulatorOpen"
            @click="simulatorOpen = !simulatorOpen"
          >
            <Sparkles data-icon="inline-start" />
            Как считается прибыль
            <ChevronDown data-icon="inline-end" :class="['transition-transform', simulatorOpen ? 'rotate-180' : '']" />
          </Button>

          <AgreementRecalcSimulator
            v-if="simulatorOpen"
            :investor-name="investorName"
            operator-name="Бизнес"
            :planned-capital-percent="investorPlannedCapitalPercent"
            :actual-capital-percent="investorActualCapitalPercent"
            :mudaraba-ratio="mudarabaRatio"
          />
        </div>

        <!-- Procurements under this agreement -->
        <div class="flex flex-col gap-2 border-t border-neutral-200 pt-3">
          <span class="text-xs font-medium text-neutral-500">Приходы по договору</span>
          <p v-if="procurements.length === 0" class="text-sm text-neutral-500">
            Приходов по этому договору пока нет.
          </p>
          <div v-else class="flex flex-col gap-1.5">
            <div
              v-for="p in procurements"
              :key="p.id"
              class="flex items-center justify-between gap-3 rounded-[10px] bg-neutral-50 px-3 py-2"
            >
              <div class="min-w-0">
                <span class="font-mono text-sm text-foreground">#{{ p.id }}</span>
                <span
                  v-if="p.id === currentProcurementId"
                  class="ml-1.5 rounded-full bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700"
                >текущий</span>
                <span class="ml-1.5 text-xs text-neutral-500">{{ dateLabel(p.opened_at) }} · {{ statusLabel(p.status) }}</span>
              </div>
              <strong class="shrink-0 text-sm font-medium tabular-nums text-foreground">
                {{ formatPrice(Number(p.total_amount) || 0, currency) }}
              </strong>
            </div>
          </div>
        </div>
      </template>
    </div>
  </AppBottomSheet>
</template>
