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

const currency = computed(() => agreement.value?.currency ?? 'UZS')
const investorPartner = computed(() => agreement.value?.partners.find((p) => p.role === 'INVESTOR') ?? null)
const plannedBudget = computed(() => Number(agreement.value?.planned_budget ?? 0) || 0)

// Three budget states: planned (target) vs contributed (actually deposited by
// all parties) vs available (left to draw). Once contributed ≥ planned the
// plan stops being a meaningful ceiling, so the track switches to contributed.
const availableAmount = computed(() => Number(agreement.value?.balances?.[currency.value] ?? 0) || 0)
const contributedAmount = computed(() => {
  if (!agreement.value) return 0
  return agreement.value.contributions
    .filter((c) => c.currency === currency.value)
    .reduce((sum, c) => sum + (Number(c.amount) || 0), 0)
})
const usedAmount = computed(() => Math.max(0, contributedAmount.value - availableAmount.value))
const trackBase = computed(() => Math.max(plannedBudget.value, contributedAmount.value, 1))
const availablePercent = computed(() => Math.min(100, (availableAmount.value / trackBase.value) * 100))
const usedPercent = computed(() => Math.min(100, (usedAmount.value / trackBase.value) * 100))
const isFunded = computed(() => plannedBudget.value > 0 && contributedAmount.value >= plannedBudget.value)
const overAmount = computed(() => Math.max(0, contributedAmount.value - plannedBudget.value))
const contributedPercentOfPlan = computed(() =>
  plannedBudget.value > 0 ? Math.round((contributedAmount.value / plannedBudget.value) * 100) : 0,
)

const budgetCaption = computed(() => {
  if (!isFunded.value) return `внесено ${contributedPercentOfPlan.value}% от плана`
  if (overAmount.value > 0) return `сверх плана на ${formatPrice(overAmount.value, currency.value)}`
  return 'профинансирован полностью'
})

const mudarabaRatio = computed(() => Number(agreement.value?.mudaraba_ratio ?? 0) || 0)
const totalContributed = computed(() =>
  (agreement.value?.participant_totals ?? []).reduce((sum, p) => sum + (Number(p.contributed_amount) || 0), 0),
)

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0))
}

// Recalculated profit: actual capital shares → profit via the agreement's
// mudaraba coefficient. A projection (final split is frozen per lot at
// receipt), shown only when actual contributions diverge from the plan.
const partyRows = computed(() => {
  const cur = currency.value
  const totals = agreement.value?.participant_totals ?? []
  const total = totalContributed.value
  const investor = totals.find((p) => p.role === 'INVESTOR')
  const investorActualCapitalPercent =
    investor && total > 0 ? (Number(investor.contributed_amount) / total) * 100 : null
  const investorActualProfitPercent =
    investorActualCapitalPercent != null ? clampPercent(investorActualCapitalPercent * mudarabaRatio.value) : null

  return totals.map((p) => {
    const plannedProfit = Math.round((Number(p.planned_profit_share) || 0) * 100)
    let actualProfit: number | null = null
    if (investorActualProfitPercent != null) {
      actualProfit = p.role === 'INVESTOR'
        ? Math.round(investorActualProfitPercent)
        : Math.round(clampPercent(100 - investorActualProfitPercent))
    }
    return {
      key: p.partner_id,
      name: p.role === 'OPERATOR' ? 'Бизнес' : p.partner_name,
      contributed: formatPrice(Number(p.contributed_amount) || 0, cur),
      planned: formatPrice(Number(p.planned_capital_share) || 0, cur),
      plannedProfit,
      actualProfit,
    }
  })
})

const hasProfitDivergence = computed(() =>
  partyRows.value.some((r) => r.actualProfit != null && r.actualProfit !== r.plannedProfit),
)

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function loadAgreement(): Promise<void> {
  if (!props.open || !props.agreementId) return
  isLoading.value = true
  error.value = ''
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
            <p class="text-sm font-semibold text-foreground">
              #{{ agreement.id }} · {{ investorPartner?.partner_name ?? 'Инвестор' }}
            </p>
            <p class="mt-0.5 text-xs text-neutral-500">{{ dateLabel(agreement.opened_at) }}</p>
          </div>
          <span class="shrink-0 rounded-full bg-neutral-100 px-2.5 py-1 text-xs font-medium text-neutral-600">
            {{ agreement.status }}
          </span>
        </div>

        <!-- Budget: planned / contributed / available -->
        <div class="flex flex-col gap-3 rounded-[10px] border border-neutral-200 p-3">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs font-medium text-neutral-500">Бюджет договора</span>
            <span class="text-xs text-neutral-400">{{ budgetCaption }}</span>
          </div>
          <div class="flex h-2 overflow-hidden rounded-full bg-neutral-200">
            <div class="bg-green-600" :style="{ width: `${availablePercent}%` }" />
            <div class="bg-neutral-400" :style="{ width: `${usedPercent}%` }" />
          </div>
          <div class="flex flex-col gap-1.5 pt-0.5">
            <div v-if="!isFunded" class="flex items-baseline justify-between gap-2">
              <span class="text-sm text-neutral-600">Запланировано</span>
              <span class="text-sm font-medium tabular-nums text-foreground">{{ formatPrice(plannedBudget, currency) }}</span>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <span class="text-sm text-neutral-600">Внесено</span>
              <span class="text-sm font-medium tabular-nums text-foreground">{{ formatPrice(contributedAmount, currency) }}</span>
            </div>
            <div class="flex items-baseline justify-between gap-2">
              <span class="flex items-center gap-1.5 text-sm text-neutral-600">
                <span class="size-2 rounded-full bg-green-600" aria-hidden="true" /> Доступно
              </span>
              <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(availableAmount, currency) }}</span>
            </div>
          </div>
        </div>

        <!-- Shares: contributed / planned + profit (planned → actual on divergence) -->
        <div class="flex flex-col gap-2.5">
          <div class="flex items-center justify-between text-xs text-neutral-500">
            <span class="font-medium">Доли по договору</span>
            <span>внёс / план · прибыль</span>
          </div>
          <div
            v-for="party in partyRows"
            :key="party.key"
            class="flex items-center justify-between gap-3"
          >
            <span class="min-w-0 truncate text-sm font-medium text-foreground">{{ party.name }}</span>
            <div class="flex shrink-0 items-baseline gap-3 text-sm tabular-nums">
              <span class="text-foreground">
                {{ party.contributed }}<span class="text-xs text-neutral-400"> / {{ party.planned }}</span>
              </span>
              <span class="text-right text-neutral-600">
                <template v-if="hasProfitDivergence && party.actualProfit != null">
                  <span class="text-neutral-400">{{ party.plannedProfit }}%</span>
                  <span class="text-neutral-400"> → </span>
                  <span class="font-medium text-foreground">{{ party.actualProfit }}%</span>
                </template>
                <template v-else>{{ party.plannedProfit }}%</template>
              </span>
            </div>
          </div>
          <p v-if="hasProfitDivergence" class="text-xs text-neutral-400">
            → ожидаемая доля прибыли при текущих фактических вкладах
          </p>
        </div>
      </template>
    </div>
  </AppBottomSheet>
</template>
