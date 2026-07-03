<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Landmark, Plus, RefreshCcw, Users } from 'lucide-vue-next'

import { fetchPartners, type Partner } from '@/api/core'
import { createInvestmentFund, fetchInvestmentFunds, fetchPartnershipActionQueue, type InvestmentFund, type PartnershipActionQueueItem } from '@/api/partnerships'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const toast = useToast()
const funds = ref<InvestmentFund[]>([])
const actions = ref<PartnershipActionQueueItem[]>([])
const partners = ref<Partner[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const showCreate = ref(false)
const name = ref('')
const managerId = ref<number | null>(null)
const currency = ref<'UZS' | 'USD'>('UZS')
const visibility = ref<'PRIVATE_INVITE' | 'PUBLIC_LISTING'>('PRIVATE_INVITE')
const feePercent = ref('0')
const targetAmount = ref('')
const minContributionAmount = ref('')
const reviewAt = ref('')
const payoutIntervalDays = ref('30')
const payoutMinimum = ref('0')
const payoutSpacingDays = ref('30')
const payoutReserve = ref('0')
const allowPartialPayout = ref(true)
let controller: AbortController | null = null

const isInvestorCabinet = computed(() => route.name === 'investor-funds')
const activePartners = computed(() => partners.value.filter((partner) => partner.is_active))
const managerOptions = computed(() => activePartners.value.filter((partner) => partner.role === 'OPERATOR' || partner.role === 'INVESTOR'))
const detailRouteName = computed(() => isInvestorCabinet.value ? 'investor-fund-detail' : 'fund-detail')

function formatStatus(status: InvestmentFund['status']): string {
  return { DRAFT: 'Черновик', RAISING: 'Сбор капитала', DEPLOYED: 'Закрыт для взносов', CLOSED: 'Закрыт' }[status]
}

function authPartnerRows(): Partner[] {
  return (auth.user?.partner_profiles ?? []).map((profile) => ({
    id: profile.id,
    role: profile.role,
    display_name: profile.display_name,
    is_active: true,
    user: auth.user?.id ?? null,
  }))
}

async function load(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  try {
    if (isInvestorCabinet.value) {
      await auth.ensureUserLoaded()
      const fundRows = await fetchInvestmentFunds()
      const partnerRows = authPartnerRows()
      funds.value = fundRows
      partners.value = partnerRows
      actions.value = []
      if (!managerId.value) managerId.value = partnerRows[0]?.id ?? null
    } else {
      const [fundRows, partnerRows, actionRows] = await Promise.all([
        fetchInvestmentFunds(),
        fetchPartners({ is_active: true }, controller.signal),
        fetchPartnershipActionQueue(),
      ])
      funds.value = fundRows
      partners.value = partnerRows
      actions.value = actionRows
      if (!managerId.value) managerId.value = partnerRows.find((partner) => partner.role === 'OPERATOR')?.id ?? null
    }
  } catch (cause) {
    if ((cause as { name?: string })?.name !== 'CanceledError') error.value = getApiErrorMessage(cause, 'Не удалось загрузить фонды')
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!name.value.trim() || !managerId.value) {
    error.value = 'Укажите название и управляющего фонда.'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const fund = await createInvestmentFund({
      name: name.value.trim(),
      manager_partner_id: managerId.value,
      member_partner_ids: [],
      currency: currency.value,
      target_amount: targetAmount.value || null,
      min_contribution_amount: minContributionAmount.value || '0',
      visibility: visibility.value,
      manager_profit_share: String((Number(feePercent.value || 0) / 100).toFixed(6)),
      review_at: reviewAt.value ? new Date(`${reviewAt.value}T00:00:00`).toISOString() : null,
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
    router.push({ name: detailRouteName.value, params: { id: fund.id } })
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
          <div><h1 class="text-lg font-semibold text-foreground">Инвестиционные фонды</h1><p class="text-xs text-muted-foreground">Закрытый капитал и прозрачные позиции участников</p></div>
        </div>
        <div class="flex gap-2"><Button variant="outline" size="icon" type="button" :disabled="loading" @click="load"><RefreshCcw :class="loading && 'animate-spin'" /></Button><Button size="sm" type="button" @click="showCreate = !showCreate"><Plus data-icon="inline-start" /> Новый</Button></div>
      </div>
    </header>

    <section class="mx-auto flex w-full max-w-[var(--max-content-width)] flex-col gap-4 px-4 py-4 sm:px-6">
      <form v-if="showCreate" class="grid gap-4 border-y border-border py-4 md:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]" @submit.prevent="submit">
        <div class="grid gap-3"><h2 class="font-semibold text-foreground">Условия фонда</h2><Input v-model="name" placeholder="Название фонда" /><label class="grid gap-1 text-sm text-muted-foreground">Валюта<select v-model="currency" class="h-10 rounded-md border border-input bg-background px-3 text-foreground"><option value="UZS">UZS</option><option value="USD">USD</option></select></label><label class="grid gap-1 text-sm text-muted-foreground">Видимость<select v-model="visibility" class="h-10 rounded-md border border-input bg-background px-3 text-foreground"><option value="PRIVATE_INVITE">Закрытый по ссылке</option><option value="PUBLIC_LISTING">Публичный список</option></select></label><label class="grid gap-1 text-sm text-muted-foreground">Целевой капитал<Input v-model="targetAmount" inputmode="decimal" placeholder="Напр. 100000" /></label><label class="grid gap-1 text-sm text-muted-foreground">Минимальный взнос<Input v-model="minContributionAmount" inputmode="decimal" placeholder="Напр. 5000" /></label><label class="grid gap-1 text-sm text-muted-foreground">Вознаграждение управляющего от прибыли, %<Input v-model="feePercent" inputmode="decimal" placeholder="0" /></label><label class="grid gap-1 text-sm text-muted-foreground">Дата пересмотра<Input v-model="reviewAt" type="date" /></label><div class="grid grid-cols-2 gap-3"><label class="grid gap-1 text-sm text-muted-foreground">Проверка выплат, дней<Input v-model="payoutIntervalDays" inputmode="numeric" /></label><label class="grid gap-1 text-sm text-muted-foreground">Мин. накопление<Input v-model="payoutMinimum" inputmode="decimal" /></label><label class="grid gap-1 text-sm text-muted-foreground">Пауза между выплатами<Input v-model="payoutSpacingDays" inputmode="numeric" /></label><label class="grid gap-1 text-sm text-muted-foreground">Резерв фонда<Input v-model="payoutReserve" inputmode="decimal" /></label></div><label class="flex items-center gap-2 text-sm text-muted-foreground"><input v-model="allowPartialPayout" type="checkbox" />Разрешить частичную выплату</label></div>
        <div class="grid content-start gap-3"><label class="grid gap-1 text-sm text-muted-foreground">Управляющий<select v-model="managerId" class="h-10 rounded-md border border-input bg-background px-3 text-foreground"><option :value="null" disabled>Выберите участника</option><option v-for="partner in managerOptions" :key="partner.id" :value="partner.id">{{ partner.display_name }}</option></select></label><div class="rounded-xl bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">Участники не добавляются вручную при создании. Они открывают invite/public фонд, видят условия и подают заявку с суммой участия. Управляющий потом approve/reject/partial approve.</div><p class="text-xs leading-relaxed text-muted-foreground">После первого размещения фонд закроется для новых заявок и выходов.</p><p v-if="error" class="text-sm text-destructive">{{ error }}</p><Button type="submit" :disabled="saving">{{ saving ? 'Создание…' : 'Создать фонд' }}</Button></div>
      </form>

      <section v-if="actions.length" class="grid gap-2 border-y border-border py-4">
        <h2 class="font-semibold text-foreground">Очередь действий</h2>
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
      <div v-else class="divide-y divide-border border-y border-border">
        <button v-for="fund in funds" :key="fund.id" class="flex w-full items-center justify-between gap-4 py-4 text-left transition hover:bg-muted/40" type="button" @click="router.push({ name: detailRouteName, params: { id: fund.id } })"><span class="min-w-0"><span class="flex items-center gap-2 font-medium text-foreground"><Users class="size-4 text-primary" />{{ fund.name }}</span><span class="mt-1 block text-sm text-muted-foreground">{{ formatStatus(fund.status) }} · {{ fund.members.filter((m) => m.status === 'ACTIVE').length }} участников · {{ fund.applications.filter((a) => a.status === 'PENDING').length }} заявок · управляющий {{ fund.manager_partner_name }}</span></span><strong class="shrink-0 tabular-nums text-foreground">{{ formatPrice(fund.positions.reduce((sum, row) => sum + Number(row.paid_in || 0), 0), fund.currency) }}</strong></button>
      </div>
    </section>
  </main>
</template>
