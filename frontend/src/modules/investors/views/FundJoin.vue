<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Landmark } from 'lucide-vue-next'

import { fetchPartners, type Partner } from '@/api/core'
import { fetchInvestmentFundByInvite, submitFundApplication, type InvestmentFund } from '@/api/partnerships'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()

const fund = ref<InvestmentFund | null>(null)
const partners = ref<Partner[]>([])
const partnerId = ref<number | null>(null)
const amount = ref('')
const message = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const token = computed(() => String(route.params.token || ''))
const investorPartners = computed(() => partners.value.filter((partner) => partner.is_active && partner.role === 'INVESTOR'))

function authInvestorPartners(): Partner[] {
  return (auth.user?.partner_profiles ?? [])
    .filter((partner) => partner.role === 'INVESTOR')
    .map((partner) => ({
      id: partner.id,
      role: partner.role,
      display_name: partner.display_name,
      is_active: true,
      user: auth.user?.id ?? null,
    }))
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const fundRow = await fetchInvestmentFundByInvite(token.value)
    let partnerRows = authInvestorPartners()
    try {
      partnerRows = await fetchPartners({ role: 'INVESTOR', is_active: true })
    } catch {
      // Invite links must remain usable for authenticated investors even when
      // the generic tenant-scoped partner list is unavailable before they
      // become a fund member. Use the current user's investor profile instead.
    }
    fund.value = fundRow
    partners.value = partnerRows
    partnerId.value ||= partnerRows[0]?.id ?? null
    amount.value ||= fundRow.min_contribution_amount !== '0.00' ? fundRow.min_contribution_amount : ''
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Не удалось открыть фонд')
  } finally {
    loading.value = false
  }
}

async function apply(): Promise<void> {
  if (!fund.value || !partnerId.value || Number(amount.value) <= 0) return
  saving.value = true
  error.value = ''
  try {
    await submitFundApplication(fund.value.id, {
      partner_id: partnerId.value,
      requested_amount: amount.value,
      message: message.value,
    })
    toast.success('Заявка отправлена управляющему фонда')
    router.push({ name: 'investor-funds' })
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Не удалось отправить заявку')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
      <div class="mx-auto flex min-h-14 w-full max-w-[var(--max-content-width)] items-center gap-2 px-4 sm:px-6">
        <Button variant="ghost" size="icon" type="button" aria-label="Назад" @click="router.back()"><ArrowLeft /></Button>
        <div>
          <h1 class="text-lg font-semibold text-foreground">Вступление в фонд</h1>
          <p class="text-xs text-muted-foreground">Условия видны до отправки заявки</p>
        </div>
      </div>
    </header>

    <section class="mx-auto grid w-full max-w-[var(--max-content-width)] gap-4 px-4 py-5 sm:px-6">
      <p v-if="loading" class="text-sm text-muted-foreground">Загрузка фонда…</p>
      <p v-else-if="error && !fund" class="text-sm text-destructive">{{ error }}</p>
      <template v-else-if="fund">
        <section class="rounded-2xl border border-border p-4">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-sm text-muted-foreground">{{ fund.visibility === 'PUBLIC_LISTING' ? 'Публичный фонд' : 'Закрытый фонд по ссылке' }}</p>
              <h2 class="mt-1 text-xl font-semibold text-foreground">{{ fund.name }}</h2>
            </div>
            <Landmark class="size-6 text-primary" />
          </div>
          <div class="mt-4 grid gap-2 text-sm text-muted-foreground">
            <span>Цель: <strong class="text-foreground">{{ fund.target_amount ? formatPrice(fund.target_amount, fund.currency) : 'не задана' }}</strong></span>
            <span>Минимальный взнос: <strong class="text-foreground">{{ formatPrice(fund.min_contribution_amount, fund.currency) }}</strong></span>
            <span>Управляющий: <strong class="text-foreground">{{ fund.manager_partner_name }}</strong></span>
          </div>
        </section>

        <form class="grid gap-3 rounded-2xl border border-border p-4" @submit.prevent="apply">
          <label class="grid gap-1 text-sm text-muted-foreground">
            Инвесторский профиль
            <select v-model="partnerId" class="h-10 rounded-md border border-input bg-background px-3 text-foreground">
              <option v-for="partner in investorPartners" :key="partner.id" :value="partner.id">{{ partner.display_name }}</option>
            </select>
          </label>
          <label class="grid gap-1 text-sm text-muted-foreground">
            Сумма заявки
            <Input v-model="amount" inputmode="decimal" :placeholder="fund.min_contribution_amount" />
          </label>
          <label class="grid gap-1 text-sm text-muted-foreground">
            Комментарий
            <textarea v-model="message" class="min-h-24 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground" placeholder="Например, готов внести в течение недели" />
          </label>
          <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
          <Button type="submit" :disabled="saving || !partnerId">{{ saving ? 'Отправка…' : 'Отправить заявку' }}</Button>
        </form>
      </template>
    </section>
  </main>
</template>
