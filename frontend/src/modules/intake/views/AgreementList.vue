<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FileText, Plus, RefreshCcw } from 'lucide-vue-next'
import { fetchInvestmentAgreements, type InvestmentAgreementListItem } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const agreements = ref<InvestmentAgreementListItem[]>([])
const loading = ref(false)
const error = ref('')

const totals = computed(() => agreements.value.reduce((acc, item) => {
  acc.budget += Number.parseFloat(item.planned_budget || '0') || 0
  acc.open += item.status === 'OPEN' || item.status === 'ACTIVE' ? 1 : 0
  return acc
}, { budget: 0, open: 0 }))

function balanceLabel(item: InvestmentAgreementListItem): string {
  const parts = Object.entries(item.balances || {})
    .filter(([, amount]) => Math.abs(Number.parseFloat(amount || '0')) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : formatPrice(0, item.currency)
}

function subtitle(item: InvestmentAgreementListItem): string {
  const who = item.investor_names?.[0] || item.supplier_name || t('procurements.supplierMissing')
  return `${who} · ${t('procurements.procurementsCount', { count: item.procurements_count })}`
}

function statusLabel(status: string): string {
  if (status === 'ACTIVE') return t('domain.agreementStatus.ACTIVE')
  if (status === 'OPEN') return t('domain.agreementStatus.OPEN')
  if (status === 'CLOSED') return t('domain.agreementStatus.CLOSED')
  if (status === 'CANCELLED') return t('domain.agreementStatus.CANCELLED')
  return status
}

function statusVariant(status: string): 'default' | 'secondary' | 'outline' | 'destructive' {
  if (status === 'ACTIVE') return 'default'
  if (status === 'OPEN') return 'secondary'
  if (status === 'CANCELLED') return 'destructive'
  return 'outline'
}

function modeLabel(mode: string): string {
  return mode === 'AGREED' ? 'Держим доли' : 'Пересчёт по факту'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    agreements.value = await fetchInvestmentAgreements()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('procurements.loadAgreementsFailed')
    toast.error(error.value)
  } finally {
    loading.value = false
  }
}

function goToCreate(): void {
  router.push({ name: 'agreement-create' })
}

onMounted(load)
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
      <div class="mx-auto flex w-full max-w-[var(--max-content-width)] items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <h1 class="text-lg font-semibold text-foreground">{{ t('procurements.agreementsTitle') }}</h1>
        <div class="flex items-center gap-2">
          <Button variant="outline" size="icon" type="button" :aria-label="t('procurements.refreshAgreements')" :disabled="loading" @click="load">
            <RefreshCcw :class="loading && 'animate-spin'" />
          </Button>
          <Button size="sm" type="button" @click="goToCreate">
            <Plus data-icon="inline-start" />
            {{ t('procurements.new') }}
          </Button>
        </div>
      </div>
    </header>

    <section class="mx-auto flex w-full max-w-[var(--max-content-width)] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
      <div class="grid grid-cols-2 gap-3">
        <div class="rounded-2xl border border-border bg-background p-4">
          <p class="text-xs text-muted-foreground">{{ t('procurements.activeAgreements') }}</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-foreground">{{ totals.open }}</p>
        </div>
        <div class="rounded-2xl border border-border bg-background p-4">
          <p class="text-xs text-muted-foreground">{{ t('procurements.plannedBudget') }}</p>
          <p class="mt-1 text-xl font-semibold tabular-nums text-foreground">{{ formatPrice(totals.budget, 'USD') }}</p>
        </div>
      </div>

      <div v-if="loading && agreements.length === 0" class="grid gap-3">
        <Skeleton class="h-16 rounded-2xl" />
        <Skeleton class="h-16 rounded-2xl" />
        <Skeleton class="h-16 rounded-2xl" />
      </div>

      <div v-else-if="error" class="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-center text-sm text-destructive">
        {{ error }}
        <Button variant="outline" size="sm" type="button" class="mt-3" @click="load">{{ t('common.retry') }}</Button>
      </div>

      <div v-else-if="agreements.length === 0" class="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-4 py-12 text-center">
        <FileText class="size-8 text-muted-foreground" :stroke-width="1.5" />
        <strong class="text-foreground">{{ t('procurements.noAgreements') }}</strong>
        <span class="max-w-xs text-sm text-muted-foreground">{{ t('procurements.noAgreementsHint') }}</span>
        <Button size="sm" type="button" class="mt-2" @click="goToCreate">
          <Plus data-icon="inline-start" />
          {{ t('procurements.new') }}
        </Button>
      </div>

      <div v-else class="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-background">
        <button
          v-for="agreement in agreements"
          :key="agreement.id"
          class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition hover:bg-muted/50"
          type="button"
          @click="router.push({ name: 'agreement-detail', params: { id: agreement.id } })"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="font-medium text-foreground">{{ t('procurements.agreementTitle', { id: agreement.id }) }}</span>
              <Badge :variant="statusVariant(agreement.status)">{{ statusLabel(agreement.status) }}</Badge>
              <Badge variant="outline" class="font-normal text-muted-foreground">{{ modeLabel(agreement.reconciliation_mode ?? 'FACTUAL') }}</Badge>
            </div>
            <p class="mt-0.5 truncate text-sm text-muted-foreground">{{ subtitle(agreement) }}</p>
          </div>
          <div class="shrink-0 text-right">
            <p class="font-semibold tabular-nums text-foreground">{{ balanceLabel(agreement) }}</p>
            <p class="text-xs text-muted-foreground">{{ t('procurements.freeBalance') }}</p>
          </div>
        </button>
      </div>
    </section>
  </main>
</template>
