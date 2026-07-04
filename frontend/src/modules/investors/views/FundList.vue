<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ClipboardList, Landmark, Plus, RefreshCcw, Users } from 'lucide-vue-next'

import { createInvestmentFund, fetchInvestmentFunds, fetchPartnershipActionQueue, type InvestmentFund, type PartnershipActionQueueItem } from '@/api/partnerships'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

const router = useRouter()
const auth = useAuthStore()
const toast = useToast()
const funds = ref<InvestmentFund[]>([])
const actions = ref<PartnershipActionQueueItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const showCreate = ref(false)
const name = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const visibility = ref<'PRIVATE_INVITE' | 'PUBLIC_LISTING'>('PRIVATE_INVITE')
const feePercent = ref('0')
const targetAmount = ref('')
const minContributionAmount = ref('')
const payoutIntervalDays = ref('30')
const payoutMinimum = ref('0')
const payoutSpacingDays = ref('30')
const payoutReserve = ref('0')
const allowPartialPayout = ref(true)
let controller: AbortController | null = null

const detailRouteName = 'investor-fund-detail'
const myFunds = computed(() => funds.value.filter((fund) => fund.viewer_role !== 'PUBLIC'))
const publicFunds = computed(() => funds.value.filter((fund) => fund.viewer_role === 'PUBLIC'))
const managerLabel = computed(() => (
  auth.user?.investment_profile?.display_name
  || auth.user?.full_name
  || auth.user?.username
  || 'Текущий инвестор'
))

function formatStatus(status: InvestmentFund['status']): string {
  return { DRAFT: 'Черновик', RAISING: 'Сбор капитала', DEPLOYED: 'Закрыт для взносов', CLOSED: 'Закрыт' }[status]
}

function managerName(fund: InvestmentFund): string {
  return fund.manager_profile_name || fund.manager_partner_name || 'Управляющий'
}

function collectedAmount(fund: InvestmentFund): number {
  return Number(fund.position?.paid_in ?? 0)
}

async function load(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  try {
    await auth.ensureUserLoaded()
    const [fundRows, actionRows] = await Promise.all([
      fetchInvestmentFunds(),
      fetchPartnershipActionQueue().catch(() => []),
    ])
    funds.value = fundRows
    actions.value = actionRows
  } catch (cause) {
    if ((cause as { name?: string })?.name !== 'CanceledError') error.value = getApiErrorMessage(cause, 'Не удалось загрузить фонды')
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!name.value.trim()) {
    error.value = 'Укажите название фонда.'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const fund = await createInvestmentFund({
      name: name.value.trim(),
      currency: currency.value,
      target_amount: targetAmount.value || null,
      min_contribution_amount: minContributionAmount.value || '0',
      visibility: visibility.value,
      manager_profit_share: String((Number(feePercent.value || 0) / 100).toFixed(6)),
      offline_agreed_at: new Date().toISOString(),
      offline_agreement_reference: 'offline-confirmed',
      payout_policy: {
        review_interval_days: Number(payoutIntervalDays.value || 30),
        minimum_available_amount: payoutMinimum.value || '0',
        minimum_days_between_payouts: Number(payoutSpacingDays.value || 30),
        reserve_amount: payoutReserve.value || '0',
        allow_partial: allowPartialPayout.value,
      },
    })
    toast.success('Фонд создан: заявки участников принимаются до первого размещения.')
    router.push({ name: detailRouteName, params: { id: fund.id } })
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Не удалось создать фонд')
  } finally {
    saving.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
      <div class="mx-auto flex min-h-14 w-full max-w-[var(--max-content-width)] items-center justify-between gap-3 px-4 sm:px-6">
        <div class="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon" type="button" aria-label="Назад" @click="router.back()"><ArrowLeft /></Button>
          <div><h1 class="text-lg font-semibold text-foreground">Фонды инвестора</h1><p class="text-xs text-muted-foreground">Личный кабинет фондов, заявок и действий</p></div>
        </div>
        <div class="flex gap-2"><Button variant="outline" size="icon" type="button" :disabled="loading" @click="load"><RefreshCcw :class="loading && 'animate-spin'" /></Button><Button size="sm" type="button" @click="showCreate = !showCreate"><Plus data-icon="inline-start" /> Новый</Button></div>
      </div>
    </header>

    <section class="mx-auto flex w-full max-w-[var(--max-content-width)] flex-col gap-4 px-4 py-4 sm:px-6">
      <form v-if="showCreate" class="grid gap-4 border-y border-border py-4 md:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]" @submit.prevent="submit">
        <div class="grid gap-3"><h2 class="font-semibold text-foreground">Условия фонда</h2><Input v-model="name" placeholder="Название фонда" /><label class="grid gap-1 text-sm text-muted-foreground">Валюта<select v-model="currency" class="h-10 rounded-md border border-input bg-background px-3 text-foreground"><option value="UZS">UZS</option><option value="USD">USD</option></select></label><label class="grid gap-1 text-sm text-muted-foreground">Видимость<select v-model="visibility" class="h-10 rounded-md border border-input bg-background px-3 text-foreground"><option value="PRIVATE_INVITE">Закрытый по ссылке</option><option value="PUBLIC_LISTING">Публичный список</option></select></label><label class="grid gap-1 text-sm text-muted-foreground">Целевой капитал<Input v-model="targetAmount" inputmode="decimal" placeholder="Напр. 100000" /></label><label class="grid gap-1 text-sm text-muted-foreground">Минимальный взнос<Input v-model="minContributionAmount" inputmode="decimal" placeholder="Напр. 5000" /></label><label class="grid gap-1 text-sm text-muted-foreground">Вознаграждение управляющего от прибыли, %<Input v-model="feePercent" inputmode="decimal" placeholder="0" /></label><div class="grid grid-cols-2 gap-3"><label class="grid gap-1 text-sm text-muted-foreground">Проверка выплат, дней<Input v-model="payoutIntervalDays" inputmode="numeric" /></label><label class="grid gap-1 text-sm text-muted-foreground">Мин. накопление<Input v-model="payoutMinimum" inputmode="decimal" /></label><label class="grid gap-1 text-sm text-muted-foreground">Пауза между выплатами<Input v-model="payoutSpacingDays" inputmode="numeric" /></label><label class="grid gap-1 text-sm text-muted-foreground">Резерв фонда<Input v-model="payoutReserve" inputmode="decimal" /></label></div><label class="flex items-center gap-2 text-sm text-muted-foreground"><input v-model="allowPartialPayout" type="checkbox" />Разрешить частичную выплату</label></div>
        <div class="grid content-start gap-3"><div class="grid gap-1 text-sm text-muted-foreground">Управляющий<span class="h-10 rounded-md border border-border bg-muted/50 px-3 py-2 text-foreground">{{ managerLabel }}</span></div><div class="rounded-xl bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">Фонд принадлежит вашему инвестиционному профилю. Участники не добавляются вручную: они открывают invite/public фонд, видят условия и подают заявку с суммой участия.</div><p class="text-xs leading-relaxed text-muted-foreground">После первого размещения фонд закроется для новых заявок и взносов.</p><p v-if="error" class="text-sm text-destructive">{{ error }}</p><Button type="submit" :disabled="saving">{{ saving ? 'Создание…' : 'Создать фонд' }}</Button></div>
      </form>

      <section v-if="actions.length" class="grid gap-2 border-y border-border py-4">
        <h2 class="flex items-center gap-2 font-semibold text-foreground"><ClipboardList class="size-4 text-primary" /> Очередь действий</h2>
        <button
          v-for="action in actions.slice(0, 5)"
          :key="action.id"
          class="rounded-xl bg-muted/60 p-3 text-left"
          type="button"
          @click="action.fund_id && router.push({ name: detailRouteName, params: { id: action.fund_id } })"
        >
          <span class="block text-sm font-medium text-foreground">{{ action.title }}</span>
          <span class="mt-0.5 block text-xs text-muted-foreground">{{ action.subtitle }}</span>
        </button>
      </section>

      <div v-if="loading" class="py-10 text-sm text-muted-foreground">Загрузка фондов…</div>
      <p v-else-if="error && !showCreate" class="text-sm text-destructive">{{ error }}</p>
      <div v-else-if="!funds.length" class="flex flex-col items-center gap-2 border border-dashed border-border py-14 text-center"><Landmark class="size-8 text-muted-foreground" /><strong>Фондов пока нет</strong><span class="max-w-sm text-sm text-muted-foreground">Создайте фонд, отправьте invite link или опубликуйте его в investor cabinet.</span></div>
      <template v-else>
        <section class="grid gap-2">
          <h2 class="font-semibold text-foreground">Мои фонды</h2>
          <div v-if="!myFunds.length" class="border-y border-border py-4 text-sm text-muted-foreground">Вы пока не управляете фондом и не состоите в фонде.</div>
          <div v-else class="divide-y divide-border border-y border-border">
            <button v-for="fund in myFunds" :key="fund.id" class="flex w-full items-center justify-between gap-4 py-4 text-left transition hover:bg-muted/40" type="button" @click="router.push({ name: detailRouteName, params: { id: fund.id } })"><span class="min-w-0"><span class="flex items-center gap-2 font-medium text-foreground"><Users class="size-4 text-primary" />{{ fund.name }}</span><span class="mt-1 block text-sm text-muted-foreground">{{ formatStatus(fund.status) }} · {{ fund.active_members_count }} участников · {{ fund.pending_applications_count }} заявок · управляющий {{ managerName(fund) }}</span></span><strong class="shrink-0 tabular-nums text-foreground">{{ formatPrice(collectedAmount(fund), fund.currency) }}</strong></button>
          </div>
        </section>

        <section class="grid gap-2">
          <h2 class="font-semibold text-foreground">Публичные фонды</h2>
          <div v-if="!publicFunds.length" class="border-y border-border py-4 text-sm text-muted-foreground">Нет публичных фондов для заявки.</div>
          <div v-else class="divide-y divide-border border-y border-border">
            <button v-for="fund in publicFunds" :key="fund.id" class="flex w-full items-center justify-between gap-4 py-4 text-left transition hover:bg-muted/40" type="button" @click="router.push({ name: detailRouteName, params: { id: fund.id } })"><span class="min-w-0"><span class="flex items-center gap-2 font-medium text-foreground"><Users class="size-4 text-primary" />{{ fund.name }}</span><span class="mt-1 block text-sm text-muted-foreground">{{ formatStatus(fund.status) }} · {{ fund.active_members_count }} участников · собрано {{ formatPrice(collectedAmount(fund), fund.currency) }} · управляющий {{ managerName(fund) }}</span></span><strong class="shrink-0 tabular-nums text-foreground">{{ fund.permissions.can_apply ? 'Подать заявку' : 'Открыть' }}</strong></button>
          </div>
        </section>
      </template>
    </section>
  </main>
</template>
