<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, ChevronRight, Handshake, PackageOpen, Wallet } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatMoneyByCurrency } from '@/modules/intake/utils/procurementListStats'
import type { AttentionSignals, AttentionView, FilterChip, ProcurementView } from './types'

const props = defineProps<{
  activeView: ProcurementView
  filters: FilterChip[]
  signals: AttentionSignals
}>()

const emit = defineEmits<{
  selectView: [value: ProcurementView]
  openAgreements: []
}>()

interface Tile {
  key: AttentionView
  label: string
  icon: typeof Wallet
  count: number
  sub: string
  tone: 'warning' | 'info' | 'negative'
}

const TILE_TONE: Record<Tile['tone'], { icon: string; active: string; count: string }> = {
  warning: { icon: 'text-warning', active: 'border-warning bg-warning/10', count: 'text-foreground' },
  info: { icon: 'text-info', active: 'border-info bg-info/10', count: 'text-foreground' },
  negative: { icon: 'text-negative', active: 'border-negative bg-negative/10', count: 'text-negative' },
}

const tiles = computed<Tile[]>(() => [
  {
    key: 'to_pay',
    label: 'К оплате',
    icon: Wallet,
    count: props.signals.toPay.count,
    sub: props.signals.toPay.count > 0 ? formatMoneyByCurrency(props.signals.toPay.remaining) : 'нет долга',
    tone: 'warning',
  },
  {
    key: 'to_receive',
    label: 'К приёмке',
    icon: PackageOpen,
    count: props.signals.toReceive.count,
    sub: 'ждут приёмки',
    tone: 'info',
  },
  {
    key: 'overdue',
    label: 'Просрочено',
    icon: AlertTriangle,
    count: props.signals.overdue.count,
    sub: 'по дедлайну',
    tone: 'negative',
  },
])

function tileClass(tile: Tile): string {
  const active = props.activeView === tile.key
  const idle = tile.count === 0 && !active
  return cn(
    'flex min-w-0 flex-col items-start gap-1 rounded-[14px] border px-3 py-2.5 text-left transition-colors',
    active
      ? TILE_TONE[tile.tone].active
      : 'border-neutral-200 bg-surface',
    idle ? 'opacity-55' : 'cursor-pointer hover:bg-neutral-50',
  )
}

function onTile(tile: Tile): void {
  if (tile.count === 0 && props.activeView !== tile.key) return
  emit('selectView', tile.key)
}

function filterClass(value: ProcurementView): string {
  const active = props.activeView === value
  return cn(
    'h-9 shrink-0 rounded-full px-3 text-sm',
    active
      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
      : 'bg-transparent text-neutral-500 hover:bg-neutral-100 hover:text-foreground',
  )
}
</script>

<template>
  <section class="procurement-workbench flex flex-col gap-3">
    <div class="procurement-workbench__signals grid grid-cols-3 gap-2">
      <button
        v-for="tile in tiles"
        :key="tile.key"
        type="button"
        :class="tileClass(tile)"
        :aria-pressed="activeView === tile.key"
        @click="onTile(tile)"
      >
        <span class="flex items-center gap-1.5 text-xs font-medium text-neutral-600">
          <component :is="tile.icon" class="size-4" :class="TILE_TONE[tile.tone].icon" />
          {{ tile.label }}
        </span>
        <strong class="text-xl font-semibold leading-none tabular-nums" :class="TILE_TONE[tile.tone].count">
          {{ tile.count }}
        </strong>
        <span class="w-full truncate text-xs tabular-nums text-neutral-500">{{ tile.sub }}</span>
      </button>
    </div>

    <div class="procurement-workbench__filters flex items-center gap-2">
      <div class="flex flex-1 gap-2 overflow-x-auto pb-1 scrollbar-none lg:flex-col lg:items-stretch lg:overflow-visible" role="group" aria-label="Фильтр приходов">
        <Button
          v-for="chip in filters"
          :key="chip.value"
          variant="ghost"
          :class="[filterClass(chip.value), 'lg:justify-start']"
          @click="emit('selectView', chip.value)"
        >
          {{ chip.label }}
        </Button>
      </div>

      <Button
        variant="ghost"
        class="h-9 shrink-0 gap-1 rounded-full px-3 text-sm text-neutral-600 hover:bg-neutral-100 hover:text-foreground lg:w-full lg:justify-start"
        @click="emit('openAgreements')"
      >
        <Handshake class="size-4" />
        <span class="hidden sm:inline">Договоры</span>
        <ChevronRight class="size-4" />
      </Button>
    </div>
  </section>
</template>

<style scoped>
@media (min-width: 1024px) {
  .procurement-workbench__signals {
    grid-template-columns: 1fr;
  }

  .procurement-workbench__filters {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
