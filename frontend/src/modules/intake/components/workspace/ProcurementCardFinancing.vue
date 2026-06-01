<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle2, AlertCircle, ChevronRight, Handshake, Plus } from 'lucide-vue-next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import WorkspaceAgreementPickerSheet from './WorkspaceAgreementPickerSheet.vue'
import InvestmentAgreementDetailSheet from './InvestmentAgreementDetailSheet.vue'
import InvestmentAgreementQuickForm from './InvestmentAgreementQuickForm.vue'
import PartnershipBudgetTopUpSheet from './PartnershipBudgetTopUpSheet.vue'
import PartnershipPoolConvertSheet from './PartnershipPoolConvertSheet.vue'
import { ArrowLeftRight } from 'lucide-vue-next'
import { formatPrice } from '@/utils/currency'
import type { ProcurementWorkspacePayload, InvestmentAgreementDetail } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'link-agreement': [agreementId: number]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const pickerOpen = ref(false)
const createFormOpen = ref(false)
const detailSheetOpen = ref(false)
const topUpOpen = ref(false)
const convertOpen = ref(false)

const investment = computed(() => props.procurement.documents.investment)
const isFilled = computed(() => (investment.value?.allocations.length ?? 0) > 0)

const currency = computed(() => investment.value?.currency ?? 'UZS')
const investor = computed(() => investment.value?.partners.find((p) => p.role === 'INVESTOR') ?? null)
const budget = computed(() => Number.parseFloat(investment.value?.planned_budget ?? '0') || 0)
const investorCapital = computed(() => Number.parseFloat(investor.value?.planned_capital_share ?? '0') || 0)
const investorCapitalPercent = computed(() => (budget.value > 0 ? Math.round((investorCapital.value / budget.value) * 100) : 0))
const investorProfitPercent = computed(() => Math.round((Number.parseFloat(investor.value?.profit_share ?? '0') || 0) * 100))

const unallocatedByCurrency = computed<Record<string, number>>(() => {
  const out: Record<string, number> = {}
  for (const perCurrency of Object.values(investment.value?.available_by_partner ?? {})) {
    for (const [cur, amount] of Object.entries(perCurrency)) {
      out[cur] = (out[cur] ?? 0) + (Number.parseFloat(amount) || 0)
    }
  }
  return out
})

const poolCurrency = computed(() => investment.value?.pool?.currency ?? currency.value)
const poolBalance = computed(() => Number.parseFloat(investment.value?.pool?.balance ?? '0') || 0)
const poolPercent = computed(() =>
  budget.value > 0 ? Math.min(100, Math.max(0, (poolBalance.value / budget.value) * 100)) : 0,
)

const investorName = computed(() => investor.value?.partner_name ?? 'Инвестор')

// E12: physical currency sub-pools (base + converted). Show when the pool
// actually holds more than just the base currency, so the user sees what's
// available to pay costs in each currency.
const currencyPools = computed(() => investment.value?.currency_pools ?? [])
const showCurrencyPools = computed(
  () => currencyPools.value.some((p) => !p.is_base && (Number.parseFloat(p.balance) || 0) > 0),
)

const dateLabel = computed(() => {
  if (!investment.value) return ''
  return new Date(investment.value.opened_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
})

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

function onTopUp(): void {
  topUpOpen.value = true
}
</script>

<template>
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">Финансирование</CardTitle>
      <CheckCircle2 v-if="isFilled" class="size-[18px] text-positive" />
      <AlertCircle v-else class="size-[18px] text-warning" />
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <!-- No agreement linked -->
      <template v-if="!investment">
        <p class="text-sm text-neutral-500">Партнёрский приход требует инвестиционный договор.</p>
        <Button class="w-full" @click="pickerOpen = true">
          <Handshake data-icon="inline-start" />
          Выбрать договор
        </Button>
      </template>

      <!-- Agreement linked: one card with all key data, tap → detail -->
      <template v-else>
        <button
          type="button"
          class="flex w-full flex-col gap-3 rounded-[14px] border border-neutral-200 bg-surface p-4 text-left shadow-sm transition-colors hover:border-green-300 hover:bg-green-50/40"
          @click="detailSheetOpen = true"
        >
          <div class="flex items-start gap-3">
            <span class="grid size-9 shrink-0 place-items-center rounded-full bg-green-100 text-green-700">
              <Handshake class="size-[18px]" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex items-center justify-between gap-2">
                <p class="truncate text-sm font-semibold text-foreground">
                  {{ investment.agreement_label }}
                </p>
                <span class="flex shrink-0 items-center gap-0.5 text-xs text-neutral-400">
                  Детально <ChevronRight class="size-3.5" />
                </span>
              </div>
              <p class="mt-0.5 truncate text-xs text-neutral-500">
                {{ investorName }} · создан {{ dateLabel }}
              </p>
            </div>
          </div>

          <div class="flex flex-col gap-3 border-t border-neutral-200 pt-3">
            <div>
              <div class="flex items-baseline justify-between gap-2">
                <span class="text-xs text-neutral-500">Остаток в пуле договора</span>
                <span>
                  <strong class="text-base font-semibold tabular-nums text-foreground">{{ formatPrice(poolBalance, poolCurrency) }}</strong>
                  <span class="text-xs tabular-nums text-neutral-400"> / план {{ formatPrice(budget, currency) }}</span>
                </span>
              </div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-neutral-200">
                <div class="h-full rounded-full bg-green-600" :style="{ width: `${poolPercent}%` }" />
              </div>
            </div>
            <div v-if="unallocatedByCurrency[currency] > 0" class="flex items-center justify-between gap-2">
              <span class="text-xs text-neutral-500">Не выделено в приходы</span>
              <span class="text-sm font-medium tabular-nums text-foreground">
                {{ formatPrice(unallocatedByCurrency[currency], currency) }}
              </span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs text-neutral-500">Доли инвестора</span>
              <span class="text-sm font-medium tabular-nums text-foreground">
                капитал {{ investorCapitalPercent }}% · прибыль {{ investorProfitPercent }}%
              </span>
            </div>
          </div>
        </button>

        <!-- E12: physical pool balances per currency (when converted money is held) -->
        <div v-if="showCurrencyPools" class="flex flex-col gap-1.5 rounded-[10px] border border-neutral-200 px-3 py-2.5">
          <span class="text-xs font-medium text-neutral-500">В пуле по валютам</span>
          <div
            v-for="p in currencyPools"
            :key="p.currency"
            class="flex items-center justify-between gap-2"
          >
            <span class="text-xs text-neutral-500">{{ p.currency }}{{ p.is_base ? ' (договор)' : '' }}</span>
            <span class="text-sm font-medium tabular-nums text-foreground">
              {{ formatPrice(Number.parseFloat(p.balance) || 0, p.currency) }}
            </span>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <Button variant="outline" class="w-full" @click="pickerOpen = true">
            Выбрать другой договор
          </Button>
          <Button variant="ghost" class="w-full text-neutral-600" @click="onTopUp">
            <Plus data-icon="inline-start" />
            Пополнить бюджет договора
          </Button>
          <Button variant="ghost" class="w-full text-neutral-600" @click="convertOpen = true">
            <ArrowLeftRight data-icon="inline-start" />
            Конвертировать валюту пула
          </Button>
        </div>
      </template>
    </CardContent>
  </Card>

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

  <PartnershipBudgetTopUpSheet
    v-model:open="topUpOpen"
    :procurement="procurement"
    @dispatch="(k, p) => emit('dispatch', k, p)"
  />

  <PartnershipPoolConvertSheet
    v-model:open="convertOpen"
    :procurement="procurement"
    @dispatch="(k, p) => emit('dispatch', k, p)"
  />
</template>
