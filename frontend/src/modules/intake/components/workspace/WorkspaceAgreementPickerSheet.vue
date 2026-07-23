<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { Plus, Check } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatPrice } from '@/utils/currency'
import { fetchInvestmentAgreements, type InvestmentAgreementListItem } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  selectedAgreementId?: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [agreementId: number]
  'create-new': []
}>()

const search = ref('')
const agreements = ref<InvestmentAgreementListItem[]>([])
const isLoading = ref(false)
let abortController: AbortController | null = null

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return agreements.value
  return agreements.value.filter((a) =>
    String(a.id).includes(q) ||
    a.investor_names.some((n) => n.toLowerCase().includes(q)) ||
    a.operator_names.some((n) => n.toLowerCase().includes(q)) ||
    a.notes.toLowerCase().includes(q),
  )
})

async function load(): Promise<void> {
  abortController?.abort()
  abortController = new AbortController()
  isLoading.value = true
  try {
    agreements.value = await fetchInvestmentAgreements()
  } catch {
    agreements.value = []
  } finally {
    isLoading.value = false
  }
}

watch(() => props.open, (isOpen) => {
  if (isOpen) { search.value = ''; load() }
  else { abortController?.abort(); abortController = null }
})

onBeforeUnmount(() => { abortController?.abort() })

function onSelect(a: InvestmentAgreementListItem): void {
  emit('select', a.id)
  emit('update:open', false)
}

function investorLabel(a: InvestmentAgreementListItem): string {
  return a.investor_names.length ? a.investor_names.join(', ') : 'Без инвестора'
}

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function budgetLabel(a: InvestmentAgreementListItem): string {
  return formatPrice(Number.parseFloat(a.planned_budget) || 0, a.currency)
}

function availableLabel(a: InvestmentAgreementListItem): string {
  const amount = Number.parseFloat(a.balances?.[a.currency] ?? '0') || 0
  return formatPrice(amount, a.currency)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Инвестиционный договор" @close="emit('update:open', false)">
    <div class="flex flex-col gap-3">
      <Input
        v-model="search"
        type="search"
        placeholder="Поиск по инвестору или номеру…"
        autocomplete="off"
      />

      <div v-if="isLoading" class="py-4 text-center text-sm text-neutral-500">Загрузка…</div>
      <div v-else-if="!filtered.length" class="py-4 text-center text-sm text-neutral-500">Договоры не найдены</div>

      <ul v-else class="flex max-h-[50vh] flex-col gap-2 overflow-y-auto">
        <li
          v-for="a in filtered"
          :key="a.id"
          :class="cn(
            'flex cursor-pointer items-start gap-3 rounded-[12px] border px-3 py-3 transition-colors',
            a.id === selectedAgreementId
              ? 'border-primary bg-primary/5'
              : 'border-neutral-200 hover:bg-neutral-50',
          )"
          @click="onSelect(a)"
        >
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <div class="flex items-baseline justify-between gap-2">
              <span class="truncate text-sm font-semibold text-foreground">
                Договор #{{ a.id }} · {{ investorLabel(a) }}
              </span>
              <span class="shrink-0 text-xs text-neutral-500">{{ dateLabel(a.opened_at) }}</span>
            </div>

            <span v-if="a.investor_shares" class="text-xs text-neutral-600">
              капитал {{ a.investor_shares.capital_percent }}% · прибыль {{ a.investor_shares.profit_percent }}%
            </span>

            <span class="text-sm tabular-nums text-foreground">
              <strong class="font-semibold">{{ budgetLabel(a) }}</strong>
              <span class="text-xs text-neutral-500"> · доступно {{ availableLabel(a) }}</span>
            </span>
          </div>

          <Check v-if="a.id === selectedAgreementId" class="mt-0.5 size-4 shrink-0 text-primary" :stroke-width="2.5" />
        </li>
      </ul>

      <Button variant="outline" class="w-full" @click="emit('create-new'); emit('update:open', false)">
        <Plus data-icon="inline-start" />
        Создать новый договор
      </Button>
    </div>
  </AppBottomSheet>
</template>
