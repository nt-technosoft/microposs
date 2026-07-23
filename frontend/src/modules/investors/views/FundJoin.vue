<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Landmark, LogIn } from 'lucide-vue-next'

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
const amount = ref('')
const message = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const token = computed(() => String(route.params.token || ''))
const activeApplication = computed(() => fund.value?.applications.find((application) => ['PENDING', 'APPROVED'].includes(application.status)) ?? null)
const previousApplication = computed(() => {
  if (activeApplication.value) return null
  return fund.value?.applications.find((application) => ['REJECTED', 'CANCELLED'].includes(application.status)) ?? null
})
const collectedAmount = computed(() => Number(fund.value?.position?.paid_in ?? 0))
const managerName = computed(() => fund.value?.manager_profile_name || fund.value?.manager_partner_name || 'Управляющий')
const managerFeePercent = computed(() => Number(fund.value?.current_terms?.manager_profit_share || 0) * 100)
const reviewDate = computed(() => fund.value?.current_terms?.review_at ? new Date(fund.value.current_terms.review_at).toLocaleDateString('ru-RU') : 'не задан')

function applyLogin(): void {
  router.push({ name: 'login', query: { redirect: route.fullPath } })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    if (auth.isAuthenticated) {
      await auth.ensureUserLoaded().catch(() => undefined)
    }
    const fundRow = await fetchInvestmentFundByInvite(token.value)
    fund.value = fundRow
    amount.value ||= fundRow.min_contribution_amount !== '0.00' ? fundRow.min_contribution_amount : ''
  } catch (cause) {
    error.value = getApiErrorMessage(cause, 'Не удалось открыть фонд')
  } finally {
    loading.value = false
  }
}

async function apply(): Promise<void> {
  if (!auth.isAuthenticated) {
    applyLogin()
    return
  }
  if (!fund.value || Number(amount.value) <= 0) return
  saving.value = true
  error.value = ''
  try {
    await submitFundApplication(fund.value.id, {
      requested_amount: amount.value,
      invite_token: token.value,
      message: message.value,
    })
    toast.success('Заявка отправлена управляющему фонда')
    await load()
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
            <span>Собрано: <strong class="text-foreground">{{ formatPrice(collectedAmount, fund.currency) }}</strong></span>
            <span>Участников: <strong class="text-foreground">{{ fund.active_members_count }}</strong></span>
            <span>Минимальный взнос: <strong class="text-foreground">{{ formatPrice(fund.min_contribution_amount, fund.currency) }}</strong></span>
            <span>Управляющий: <strong class="text-foreground">{{ managerName }}</strong></span>
            <span>Manager fee: <strong class="text-foreground">{{ managerFeePercent.toFixed(2) }}%</strong></span>
            <span>Пересмотр: <strong class="text-foreground">{{ reviewDate }}</strong></span>
          </div>
        </section>

        <section v-if="activeApplication" class="grid gap-2 rounded-2xl border border-border p-4">
          <h2 class="font-semibold text-foreground">Ваша заявка</h2>
          <p class="text-sm text-muted-foreground">
            Статус: <strong class="text-foreground">{{ activeApplication.status }}</strong> ·
            сумма {{ formatPrice(activeApplication.requested_amount, activeApplication.currency) }}
          </p>
          <p v-if="activeApplication.approved_amount !== '0.00'" class="text-sm text-muted-foreground">
            Одобрено: <strong class="text-foreground">{{ formatPrice(activeApplication.approved_amount, activeApplication.currency) }}</strong>
          </p>
        </section>

        <section v-else-if="!auth.isAuthenticated" class="grid gap-3 rounded-2xl border border-border p-4">
          <h2 class="font-semibold text-foreground">Подать заявку</h2>
          <p class="text-sm text-muted-foreground">Войдите в investor cabinet, чтобы отправить сумму участия управляющему фонда.</p>
          <Button type="button" @click="applyLogin"><LogIn data-icon="inline-start" /> Войти и подать заявку</Button>
        </section>

        <form v-else-if="fund.permissions.can_apply" class="grid gap-3 rounded-2xl border border-border p-4" @submit.prevent="apply">
          <p v-if="previousApplication" class="text-sm text-muted-foreground">
            Предыдущая заявка: <strong class="text-foreground">{{ previousApplication.status }}</strong>. Можно отправить новую.
          </p>
          <label class="grid gap-1 text-sm text-muted-foreground">
            Сумма заявки
            <Input v-model="amount" inputmode="decimal" :placeholder="fund.min_contribution_amount" />
          </label>
          <label class="grid gap-1 text-sm text-muted-foreground">
            Комментарий
            <textarea v-model="message" class="min-h-24 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground" placeholder="Например, готов внести в течение недели" />
          </label>
          <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
          <Button type="submit" :disabled="saving || Number(amount) <= 0">{{ saving ? 'Отправка…' : 'Отправить заявку' }}</Button>
        </form>

        <section v-else class="rounded-2xl border border-border p-4 text-sm text-muted-foreground">
          Фонд сейчас не принимает новые заявки.
        </section>
      </template>
    </section>
  </main>
</template>
