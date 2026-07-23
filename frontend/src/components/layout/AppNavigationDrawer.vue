<script setup lang="ts">
import { computed } from 'vue'
import { BriefcaseBusiness } from 'lucide-vue-next'
import type { AppNavItem } from './navigation'
import { useAuthStore } from '@/stores/auth'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import AppAccountMenu from './AppAccountMenu.vue'
import AppNavigationPanel from './AppNavigationPanel.vue'

defineProps<{
  items: AppNavItem[]
}>()

const open = defineModel<boolean>('open', { required: true })
const auth = useAuthStore()
const businessName = computed(() => auth.user?.active_business?.name || auth.user?.tenant_name || 'MicroPOS')
</script>

<template>
  <Sheet :open="open" @update:open="open = $event">
    <SheetContent side="left" class="w-[320px] gap-0 p-0 sm:max-w-[320px]">
      <SheetHeader class="flex-row items-center gap-3 border-b border-border/70 px-4 py-3 text-left">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <BriefcaseBusiness class="size-5" aria-hidden="true" />
        </span>
        <span class="min-w-0">
          <SheetTitle class="truncate text-sm">{{ businessName }}</SheetTitle>
          <SheetDescription class="truncate text-xs">Рабочее пространство</SheetDescription>
        </span>
      </SheetHeader>

      <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4">
        <AppNavigationPanel :items="items" @navigate="open = false" />
      </div>

      <div class="shrink-0 border-t border-border/70 p-2">
        <AppAccountMenu align="start" />
      </div>
    </SheetContent>
  </Sheet>
</template>
