<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ChevronDown, LogOut, Settings } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const props = withDefaults(defineProps<{
  compact?: boolean
  align?: 'start' | 'center' | 'end'
}>(), {
  compact: false,
  align: 'end',
})

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const displayName = computed(() => auth.user?.full_name || auth.user?.username || '')
const businessName = computed(() => auth.user?.active_business?.name || auth.user?.tenant_name || '')
const initials = computed(() => {
  const parts = displayName.value.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return 'M'
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join('')
})

function openSettings() {
  router.push({ name: 'settings' })
}

function logout() {
  auth.logout()
  router.replace({ name: 'login' })
}
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        :size="compact ? 'icon-lg' : 'lg'"
        class="min-w-0 justify-start data-[state=open]:bg-muted"
        :class="compact ? 'rounded-xl' : 'h-auto w-full gap-2.5 px-2 py-2'"
        :aria-label="displayName"
      >
        <span
          class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-xs font-semibold text-primary-foreground"
          aria-hidden="true"
        >
          {{ initials }}
        </span>
        <span v-if="!compact" class="min-w-0 flex-1 text-left">
          <span class="block truncate text-sm font-semibold">{{ displayName }}</span>
          <span class="block truncate text-xs font-normal text-muted-foreground">{{ businessName }}</span>
        </span>
        <ChevronDown v-if="!compact" data-icon="inline-end" />
      </Button>
    </DropdownMenuTrigger>

    <DropdownMenuContent :align="align" class="w-64">
      <DropdownMenuLabel class="flex flex-col gap-0.5 px-2 py-2">
        <span class="truncate text-sm font-semibold">{{ displayName }}</span>
        <span class="truncate text-xs font-normal text-muted-foreground">{{ businessName }}</span>
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuItem @select="openSettings">
          <Settings />
          {{ t('nav.settings') }}
        </DropdownMenuItem>
      </DropdownMenuGroup>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuItem variant="destructive" @select="logout">
          <LogOut />
          {{ t('settings.logout') }}
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
