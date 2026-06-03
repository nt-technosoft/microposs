<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft,
  FilePenLine,
  MoreHorizontal,
  RotateCcw,
  XCircle,
  type LucideIcon,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { procurementStatusLabel, procurementStatusMeta } from '@/utils/domainLabels'
import { ProcurementStatus } from '@/types/enums'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type MenuAction = {
  key: string
  label: string
  hint: string
  icon: LucideIcon
  visible: boolean
  destructive?: boolean
}

const props = defineProps<{
  procurementId: number | null
  status: string | null
  title: string
  subtitle: string | null
  procurement?: ProcurementWorkspacePayload | null
}>()

const emit = defineEmits<{
  back: []
  'menu-action': [actionKey: string]
}>()

const menuOpen = ref(false)

function onMenuAction(key: string): void {
  menuOpen.value = false
  emit('menu-action', key)
}

function statusColorClass(status: string | null): string | undefined {
  return status ? procurementStatusMeta[status as ProcurementStatus]?.colorClass : undefined
}

const menuActions = computed<MenuAction[]>(() => {
  const p = props.procurement
  if (!p) return []

  const hasReceive = p.documents.receive_batches.length > 0
  const hasPayments = p.documents.payments.length > 0
  const status = p.status

  return [
    {
      key: 'amend_items',
      label: 'Корректировать товары',
      hint: hasReceive ? 'Создать документ изменения без трогания принятых лотов' : 'Исправить строки до приемки',
      icon: FilePenLine,
      visible: status === 'OPEN' || status === 'PARTIALLY_RECEIVED',
    },
    {
      key: 'amend_expenses',
      label: 'Корректировать расходы',
      hint: hasReceive ? 'Изменить только незафиксированную часть расходов' : 'Исправить расходы до приемки',
      icon: FilePenLine,
      visible: status === 'OPEN' || status === 'PARTIALLY_RECEIVED',
    },
    {
      key: 'reverse_receive',
      label: 'Отменить приемку',
      hint: 'Вернуть партию, если лоты еще не продавались',
      icon: RotateCcw,
      visible: hasReceive,
    },
    {
      key: 'cancel',
      label: 'Отменить приход',
      hint: 'Только если нет оплат и приемок',
      icon: XCircle,
      visible: status === 'OPEN' && !hasPayments && !hasReceive,
      destructive: true,
    },
  ].filter((action) => action.visible)
})
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-border/70 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
    <div class="mx-auto grid min-h-14 w-full max-w-[1200px] grid-cols-[44px_minmax(0,1fr)_44px] items-center gap-2 px-3 sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        class="size-10 rounded-full"
        aria-label="Назад"
        @click="emit('back')"
      >
        <ArrowLeft class="size-5" />
      </Button>

      <div class="min-w-0 text-center">
        <div class="flex min-w-0 items-center justify-center gap-2">
          <h1 class="truncate text-base font-semibold leading-tight text-foreground sm:text-lg">
            {{ title }}
          </h1>
          <Badge
            v-if="status && statusColorClass(status)"
            variant="outline"
            :class="cn('h-6 shrink-0 rounded-full px-2 text-[11px] font-medium', statusColorClass(status))"
          >
            {{ procurementStatusLabel(status) }}
          </Badge>
        </div>
        <p v-if="subtitle" class="mt-0.5 truncate text-xs text-muted-foreground">
          {{ subtitle }}
        </p>
      </div>

      <DropdownMenu v-model:open="menuOpen">
        <DropdownMenuTrigger as-child>
          <Button
            variant="ghost"
            size="icon"
            class="size-10 rounded-full"
            aria-label="Действия"
          >
            <MoreHorizontal class="size-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-[300px] rounded-[14px] p-1.5">
          <DropdownMenuItem
            v-for="action in menuActions"
            :key="action.key"
            :class="cn(
              'flex cursor-pointer items-start gap-3 rounded-[10px] px-3 py-2.5',
              action.destructive && 'text-destructive focus:text-destructive',
            )"
            @select.prevent="onMenuAction(action.key)"
          >
            <component
              :is="action.icon"
              :class="cn('mt-0.5 size-4 shrink-0 text-muted-foreground', action.destructive && 'text-destructive')"
            />
            <span class="min-w-0">
              <span class="block text-sm font-medium leading-tight">{{ action.label }}</span>
              <span class="mt-0.5 block text-xs leading-snug text-muted-foreground">{{ action.hint }}</span>
            </span>
          </DropdownMenuItem>
          <div v-if="!menuActions.length" class="px-3 py-3 text-sm text-muted-foreground">
            Нет доступных действий
          </div>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </header>
</template>
