<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Handshake, Wallet } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'
import { ProcurementType } from '@/types/enums'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'
import {
  fundingLabel,
  fundingToneClass,
  statusDotClass,
  statusLabel,
  supplierLabel,
} from '@/modules/intake/utils/procurementListPresentation'
import { isOverdue } from '@/modules/intake/utils/procurementListStats'

const props = defineProps<{
  procurement: ProcurementWorkspacePayload
}>()

defineEmits<{
  open: [id: number]
}>()

const { t, locale } = useI18n()

const supplier = computed(() => supplierLabel(props.procurement))
const total = computed(() => formatPrice(props.procurement.summaries.items_total_uzs))
const itemCount = computed(() => t('procurements.lineCount', { count: props.procurement.documents.items.length }))
const updatedAt = computed(() => formatShortDate(props.procurement.display.updated_at))
const isPartnership = computed(() => props.procurement.policy.funding_source === ProcurementType.PARTNERSHIP)
const overdue = computed(() => isOverdue(props.procurement))

function formatShortDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(intlLocale(locale.value), { day: '2-digit', month: 'short' })
}

function settlementLabel(type: string | null | undefined): string {
  if (!type) return 'Условия не выбраны'
  const key = `procurements.create.termsType.${type}`
  const translated = t(key)
  return translated === key ? type : translated
}
</script>

<template>
  <div
    role="button"
    tabindex="0"
    class="group grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-3.5 transition-colors hover:bg-neutral-50 focus-visible:bg-neutral-50 focus-visible:outline-none sm:px-5"
    @click="$emit('open', procurement.id)"
    @keydown.enter="$emit('open', procurement.id)"
    @keydown.space.prevent="$emit('open', procurement.id)"
  >
    <span
      class="size-2.5 shrink-0 rounded-full"
      :class="statusDotClass(procurement.status)"
      aria-hidden="true"
    />

    <div class="min-w-0">
      <p class="truncate text-sm font-medium text-foreground">
        {{ supplier }}
      </p>
      <div class="mt-1 flex items-center gap-1.5 text-xs text-neutral-500">
        <span class="font-mono">#{{ procurement.id }}</span>
        <span aria-hidden="true">·</span>
        <span class="inline-flex items-center gap-1" :class="fundingToneClass(procurement.policy.funding_source)">
          <component :is="isPartnership ? Handshake : Wallet" class="size-3.5" />
          {{ fundingLabel(procurement.policy.funding_source) }}
        </span>
        <span aria-hidden="true">·</span>
        <span class="truncate">{{ settlementLabel(procurement.policy.settlement_type) }}</span>
        <span class="hidden sm:inline" aria-hidden="true">·</span>
        <span class="hidden whitespace-nowrap sm:inline">{{ itemCount }}</span>
      </div>
    </div>

    <div class="flex flex-col items-end gap-1 text-right">
      <strong class="text-sm font-semibold tabular-nums text-foreground">{{ total }}</strong>
      <span v-if="overdue" class="text-xs font-medium text-negative">Просрочено</span>
      <span v-else class="text-xs text-neutral-400">
        {{ statusLabel(procurement.status) }} · {{ updatedAt }}
      </span>
    </div>

    <ChevronRight
      class="size-4 shrink-0 text-neutral-300 transition-transform group-hover:translate-x-0.5 group-hover:text-neutral-500"
    />
  </div>
</template>
