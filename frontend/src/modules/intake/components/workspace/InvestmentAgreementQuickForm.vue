<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Calculator, Copy, HandCoins, RefreshCcw, Send, UserPlus } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import WorkspaceQuickPartnerSheet from './WorkspaceQuickPartnerSheet.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
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
const selectedInvestorIds = ref<number[]>([])
const investorAmounts = ref<Record<number, string>>({})
const currency = ref<'USD' | 'UZS'>('USD')
const investorCapitalPercent = ref('')
const investorProfitPercentInput = ref('')
const simulatedInvestorCapitalPercentDraft = ref('')
const notes = ref('')
const reviewAt = ref('')
const payoutIntervalDays = ref('30')
const payoutMinimum = ref('0')
const payoutSpacingDays = ref('30')
const payoutReserve = ref('0')
const allowPartialPayout = ref(true)
// E14: reconciliation policy is fixed here, at agreement creation. AGREED (Путь 2)
// is the product default; the receive only reflects this choice later.
const reconciliationMode = ref<'AGREED' | 'FACTUAL'>('AGREED')
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
const selectedInvestors = computed(() => investorOptions.value.filter((partner) => selectedInvestorIds.value.includes(partner.id)))

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

const investorPlannedAmountValue = computed(() => selectedInvestors.value.reduce(
  (total, partner) => total + parseNumber(investorAmounts.value[partner.id] ?? ''),
  0,
))
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
  if (!selectedInvestorIds.value.length) return 'Выберите хотя бы одного инвестора'
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
    selectedInvestorIds.value = selectedInvestorIds.value.filter((id) => investorOptions.value.some((partner) => partner.id === id))
  } catch (loadError) {
    error.value = loadError instanceof Error ? loadError.message : 'Не удалось загрузить инвесторов'
  } finally {
    isLoading.value = false
  }
}

function toggleInvestor(id: number): void {
  if (selectedInvestorIds.value.includes(id)) {
    selectedInvestorIds.value = selectedInvestorIds.value.filter((value) => value !== id)
    return
  }
  selectedInvestorIds.value = [...selectedInvestorIds.value, id]
  if (!investorAmounts.value[id]) investorAmounts.value = { ...investorAmounts.value, [id]: '' }
}

function setInvestorAmount(id: number, value: string): void {
  investorAmounts.value = { ...investorAmounts.value, [id]: value }
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
      planned_budget: plannedBudgetValue.value.toFixed(2),
      mudaraba_ratio: mudarabaRatio.value.toFixed(6),
      currency: currency.value,
      notes: notes.value,
      review_at: reviewAt.value ? new Date(`${reviewAt.value}T00:00:00`).toISOString() : null,
      reconciliation_mode: reconciliationMode.value,
      offline_agreed_at: new Date().toISOString(),
      offline_agreement_reference: 'offline-confirmed',
      payout_policy: {
        review_interval_days: Number(payoutIntervalDays.value || 30),
        minimum_available_amount: payoutMinimum.value || '0',
        minimum_days_between_payouts: Number(payoutSpacingDays.value || 30),
        reserve_amount: payoutReserve.value || '0',
        grace_period_days: 0,
        allow_partial: allowPartialPayout.value,
      },
      partners: [
        ...selectedInvestors.value.map((partner) => {
          const amount = parseNumber(investorAmounts.value[partner.id] ?? '')
          const capitalRatio = investorPlannedAmountValue.value > 0 ? amount / investorPlannedAmountValue.value : 0
          return {
            partner_id: partner.id,
            role: 'INVESTOR',
            planned_capital_share: amount.toFixed(2),
            profit_share: ((investorProfitPercentValue.value / 100) * capitalRatio).toFixed(6),
          }
        }),
        {
          partner_id: operatorPartner.value?.id as number,
          role: 'OPERATOR',
          planned_capital_share: operatorCapital.value.toFixed(2),
          profit_share: (1 - investorProfitPercentValue.value / 100).toFixed(6),
        },
      ],
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
  selectedInvestorIds.value = [...selectedInvestorIds.value, partner.id]
  investorAmounts.value = { ...investorAmounts.value, [partner.id]: '' }
}

onMounted(loadPartners)
</script>

<template>
  <div class="flex flex-col gap-4">
    <Card class="rounded-2xl bg-background">
      <CardHeader class="gap-3">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <CardTitle class="text-base">Инвестор</CardTitle>
          </div>
          <Badge variant="secondary" class="shrink-0">1 шаг</Badge>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" type="button" @click="quickPartnerOpen = true">
            <UserPlus data-icon="inline-start" />
            Создать
          </Button>
          <Button variant="outline" size="sm" type="button" @click="inviteOpen = true">
            <Send data-icon="inline-start" />
            Пригласить
          </Button>
        </div>
      </CardHeader>

      <CardContent class="flex flex-col gap-3">
        <p v-if="isLoading" class="text-sm text-muted-foreground">Загрузка инвесторов…</p>
        <div v-else-if="investorOptions.length === 0" class="rounded-xl bg-muted/60 p-3">
          <p class="text-sm font-medium text-foreground">Нет активных инвесторов</p>
          <p class="mt-1 text-sm leading-relaxed text-muted-foreground">
            Создайте инвестора или отправьте приглашение. После принятия он появится в списке.
          </p>
        </div>
        <div v-else class="grid gap-2 sm:grid-cols-2">
          <button
            v-for="partner in investorOptions"
            :key="partner.id"
            :aria-pressed="selectedInvestorIds.includes(partner.id)"
            class="flex min-h-16 items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2 text-left transition hover:bg-muted/50 aria-pressed:border-primary aria-pressed:bg-primary/5"
            type="button"
            @click="toggleInvestor(partner.id)"
          >
            <span class="min-w-0">
              <span class="block truncate text-sm font-medium text-foreground">{{ partner.display_name }}</span>
              <span class="mt-0.5 block text-xs text-muted-foreground">
                {{ selectedInvestorIds.includes(partner.id) ? 'Входит в инвесторский пул' : 'Активный инвестор' }}
              </span>
            </span>
            <span
              class="grid size-3.5 shrink-0 place-items-center rounded-full border"
              :class="selectedInvestorIds.includes(partner.id) ? 'border-primary bg-primary' : 'border-muted-foreground/30'"
              aria-hidden="true"
            />
          </button>
        </div>
        <div v-if="selectedInvestors.length" class="grid gap-2 border-t border-border pt-3">
          <label v-for="partner in selectedInvestors" :key="partner.id" class="grid grid-cols-[1fr_minmax(8rem,0.75fr)] items-center gap-3">
            <span class="truncate text-sm font-medium text-foreground">{{ partner.display_name }}</span>
            <MoneyCurrencyInput
              :model-value="investorAmounts[partner.id] ?? ''"
              :currency="currency"
              size="md"
              :currencies="['USD', 'UZS']"
              :aria-label="`Плановый взнос ${partner.display_name}`"
              @update:model-value="setInvestorAmount(partner.id, String($event))"
              @update:currency="currency = $event as 'USD' | 'UZS'"
            />
          </label>
          <p class="text-xs text-muted-foreground">Доля прибыли задаётся для общего пула и автоматически распределяется пропорционально фактическому капиталу участников.</p>
        </div>
      </CardContent>
    </Card>

    <Card class="rounded-2xl bg-background">
      <CardHeader>
        <div class="flex items-start justify-between gap-3">
          <div>
            <CardTitle class="text-base">Формула договора</CardTitle>
          </div>
          <Calculator class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </div>
      </CardHeader>
      <CardContent class="flex flex-col gap-4">
        <label class="flex flex-col gap-2">
          <span class="text-sm font-medium text-muted-foreground">Инвесторский пул планирует вложить</span>
          <div class="rounded-xl border border-border bg-muted/30 px-3 py-2.5 text-lg font-semibold tabular-nums text-foreground">
            {{ formatPrice(investorPlannedAmountValue, currency) }}
          </div>
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="flex flex-col gap-2">
            <span class="text-sm font-medium text-muted-foreground">Капитал инвестора, %</span>
            <Input v-model="investorCapitalPercent" inputmode="decimal" placeholder="напр. 70" class="h-10" />
          </label>
          <label class="flex flex-col gap-2">
            <span class="text-sm font-medium text-muted-foreground">Прибыль инвестора, %</span>
            <Input v-model="investorProfitPercentInput" inputmode="decimal" placeholder="напр. 40" class="h-10" />
          </label>
        </div>

        <div class="grid grid-cols-3 gap-px overflow-hidden rounded-xl bg-border text-center">
          <div class="bg-primary px-2 py-2 text-primary-foreground">
            <p class="text-[11px] opacity-80">Пул инвесторов</p>
            <p class="text-sm font-semibold tabular-nums">{{ formatPrice(investorCapital, currency) }}</p>
          </div>
          <div class="bg-background px-2 py-2">
            <p class="text-[11px] text-muted-foreground">Бизнес</p>
            <p class="text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(operatorCapital, currency) }}</p>
          </div>
          <div class="bg-background px-2 py-2">
            <p class="text-[11px] text-muted-foreground">Итого</p>
            <p class="text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(plannedBudgetValue, currency) }}</p>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Развилка договора: определяет, нужен ли блок «План-факт» ниже -->
    <Card class="rounded-2xl bg-background">
      <CardContent class="flex flex-col gap-3 pt-4">
        <span class="text-sm font-medium text-foreground">Если внесут не ровно по договору</span>
        <div class="grid gap-2 sm:grid-cols-2">
          <button
            type="button"
            class="rounded-xl border p-3 text-left transition"
            :class="reconciliationMode === 'AGREED' ? 'border-primary bg-primary/5' : 'border-border'"
            @click="reconciliationMode = 'AGREED'"
          >
            <span class="block text-sm font-semibold text-foreground">Держим договорные доли</span>
            <span class="mt-1 block text-xs text-muted-foreground">Разницу показываем как капитальную позицию партнёра (долг/переплата).</span>
          </button>
          <button
            type="button"
            class="rounded-xl border p-3 text-left transition"
            :class="reconciliationMode === 'FACTUAL' ? 'border-primary bg-primary/5' : 'border-border'"
            @click="reconciliationMode = 'FACTUAL'"
          >
            <span class="block text-sm font-semibold text-foreground">Пересчёт по факту</span>
            <span class="mt-1 block text-xs text-muted-foreground">Доли следуют реально внесённому. Без долга.</span>
          </button>
        </div>
      </CardContent>
    </Card>

    <!-- План-факт: только при пересчёте по факту (при «держим доли» он не нужен) -->
    <Card v-if="reconciliationMode === 'FACTUAL'" class="rounded-2xl bg-background">
      <CardHeader>
        <div class="flex items-start justify-between gap-3">
          <div>
            <CardTitle class="text-base">Доли при фактическом вкладе</CardTitle>
          </div>
          <HandCoins class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </div>
      </CardHeader>
      <CardContent class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-3">
          <span class="text-sm font-medium text-muted-foreground">Фактическая доля капитала инвестора</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPercent(simulatedInvestorCapitalPercent) }}</span>
        </div>
        <input
          class="h-2 w-full cursor-pointer accent-primary"
          type="range"
          min="0"
          max="100"
          step="0.1"
          :value="simulatedInvestorCapitalPercent"
          :style="simulationRangeStyle"
          @input="(event) => setSimulationCapitalPercent((event.target as HTMLInputElement).value)"
        />
        <div class="grid grid-cols-2 gap-2">
          <div class="rounded-xl border border-border bg-primary/5 p-3">
            <p class="text-xs font-semibold text-foreground">Инвестор</p>
            <div class="mt-2 flex items-baseline justify-between gap-2">
              <span class="text-xs text-muted-foreground">капитал</span>
              <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPercent(simulatedInvestorCapitalPercent) }}</span>
            </div>
            <div class="mt-1 flex items-baseline justify-between gap-2">
              <span class="text-xs text-muted-foreground">прибыль</span>
              <span class="text-lg font-semibold tabular-nums text-primary">{{ formatPercent(simulatedInvestorProfitPercent) }}</span>
            </div>
          </div>
          <div class="rounded-xl border border-border bg-muted/40 p-3">
            <p class="text-xs font-semibold text-foreground">Бизнес</p>
            <div class="mt-2 flex items-baseline justify-between gap-2">
              <span class="text-xs text-muted-foreground">капитал</span>
              <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPercent(100 - simulatedInvestorCapitalPercent) }}</span>
            </div>
            <div class="mt-1 flex items-baseline justify-between gap-2">
              <span class="text-xs text-muted-foreground">прибыль</span>
              <span class="text-lg font-semibold tabular-nums text-foreground">{{ formatPercent(simulatedOperatorProfitPercent) }}</span>
            </div>
          </div>
        </div>

        <div class="flex items-start justify-between gap-3 rounded-xl bg-muted/60 p-3">
          <p class="text-sm leading-relaxed" :class="hasSimulationDelta ? 'text-foreground' : 'text-muted-foreground'">
            <span v-if="hasSimulationDelta">{{ simulationExplanation }}</span>
            <span v-else>Сейчас симуляция совпадает с планом договора.</span>
          </p>
          <Button variant="ghost" size="sm" type="button" class="shrink-0" @click="resetSimulation">
            <RefreshCcw data-icon="inline-start" />
            Сбросить
          </Button>
        </div>
      </CardContent>
    </Card>

    <Card class="rounded-2xl bg-background">
      <CardContent class="flex flex-col gap-2 pt-4">
        <label class="flex flex-col gap-2">
          <span class="text-sm font-medium text-muted-foreground">Дата пересмотра договора</span>
          <Input v-model="reviewAt" type="date" class="h-10" />
          <span class="text-xs text-muted-foreground">Это напоминание и точка выбора сценария, а не автоматическое закрытие.</span>
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="flex flex-col gap-1"><span class="text-sm font-medium text-muted-foreground">Проверка выплат, дней</span><Input v-model="payoutIntervalDays" inputmode="numeric" class="h-10" /></label>
          <label class="flex flex-col gap-1"><span class="text-sm font-medium text-muted-foreground">Мин. накопление</span><Input v-model="payoutMinimum" inputmode="decimal" class="h-10" /></label>
          <label class="flex flex-col gap-1"><span class="text-sm font-medium text-muted-foreground">Пауза между выплатами</span><Input v-model="payoutSpacingDays" inputmode="numeric" class="h-10" /></label>
          <label class="flex flex-col gap-1"><span class="text-sm font-medium text-muted-foreground">Резерв</span><Input v-model="payoutReserve" inputmode="decimal" class="h-10" /></label>
        </div>
        <label class="flex items-center gap-2 text-sm text-muted-foreground"><input v-model="allowPartialPayout" type="checkbox" />Разрешить частичную выплату</label>
        <label class="flex flex-col gap-2">
          <span class="text-sm font-medium text-muted-foreground">Заметка</span>
          <Textarea
            v-model="notes"
            rows="3"
            placeholder="Например, первая партия товара по договору"
            class="min-h-24"
          />
      </label>
      </CardContent>
    </Card>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>
    <Button size="lg" type="button" :disabled="saving" class="h-11 rounded-xl" @click="submit">
      {{ saving ? 'Создание…' : 'Создать договор' }}
    </Button>

    <WorkspaceQuickPartnerSheet
      v-model:open="quickPartnerOpen"
      @created="onPartnerCreated"
    />

    <AppBottomSheet :open="inviteOpen" title="Пригласить инвестора" @close="inviteOpen = false">
      <div class="flex flex-col gap-3">
        <Input v-model="inviteName" placeholder="Имя инвестора" class="h-10" />
        <Input v-model="inviteEmail" type="email" placeholder="Email, если есть" class="h-10" />
        <Button type="button" :disabled="isInviting" class="h-10" @click="createInvite">
          <Send data-icon="inline-start" />
          {{ isInviting ? 'Создание…' : 'Создать ссылку приглашения' }}
        </Button>
        <Separator />
        <div v-if="createdInvite" class="rounded-xl bg-muted/60 p-3">
          <p class="break-all text-xs text-muted-foreground">{{ inviteUrl(createdInvite) }}</p>
          <Button variant="ghost" size="sm" type="button" class="mt-2" @click="copyInvite(createdInvite)">
            <Copy data-icon="inline-start" />
            Скопировать
          </Button>
        </div>
      </div>
    </AppBottomSheet>
  </div>
</template>
