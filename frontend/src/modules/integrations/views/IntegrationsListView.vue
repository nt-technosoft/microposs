<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Plus } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useIntegrationsStore } from '@/stores/integrations'
import CreateKeyModal from '../components/CreateKeyModal.vue'
import RevokeConfirmDialog from '../components/RevokeConfirmDialog.vue'

const store = useIntegrationsStore()

const createOpen = ref(false)
const revokeTarget = ref<{ id: string; prefix: string } | null>(null)

onMounted(() => store.load())
onBeforeUnmount(() => store.cancel())

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
}

const STATUS_LABEL: Record<string, string> = {
  active: 'Активен',
  revoked: 'Отозван',
  expired: 'Истёк',
}
function statusClass(status: string): string {
  if (status === 'active') return 'bg-positive/10 text-positive'
  if (status === 'revoked') return 'bg-negative/10 text-negative'
  return 'bg-neutral-100 text-neutral-500'
}

async function onRevoke(): Promise<void> {
  if (!revokeTarget.value) return
  await store.revoke(revokeTarget.value.id)
  revokeTarget.value = null
}
</script>

<template>
  <div class="mx-auto flex max-w-[680px] flex-col gap-4 p-4">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-xl font-semibold text-foreground">Интеграции</h1>
      <Button class="gap-1.5" @click="createOpen = true">
        <Plus :size="18" :stroke-width="2" />
        Добавить ключ
      </Button>
    </header>

    <p v-if="store.isLoading" class="py-10 text-center text-sm text-neutral-500">Загрузка…</p>
    <p v-else-if="store.error" class="py-10 text-center text-sm text-negative">{{ store.error }}</p>
    <p v-else-if="!store.credentials.length" class="py-10 text-center text-sm text-neutral-500">
      Нет ключей. Создайте первый.
    </p>

    <div v-else class="flex flex-col gap-2.5">
      <div
        v-for="c in store.credentials"
        :key="c.id"
        class="flex flex-col gap-3 rounded-[14px] border border-neutral-200 bg-surface p-4"
      >
        <div class="flex items-center justify-between gap-3">
          <span class="text-sm font-semibold text-foreground">{{ c.vendor }}</span>
          <span :class="cn('shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium', statusClass(c.status))">
            {{ STATUS_LABEL[c.status] ?? c.status }}
          </span>
        </div>

        <code class="block truncate font-mono text-xs text-neutral-600">{{ c.prefix }}…</code>

        <div class="flex flex-col gap-1 border-t border-neutral-100 pt-3">
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs text-neutral-400">Создан</span>
            <span class="text-xs tabular-nums text-neutral-600">{{ formatDate(c.created_at) }}</span>
          </div>
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs text-neutral-400">Последнее использование</span>
            <span class="text-xs tabular-nums text-neutral-600">{{ formatDate(c.last_used_at) }}</span>
          </div>
        </div>

        <button
          v-if="c.status === 'active'"
          type="button"
          class="h-10 rounded-[10px] border border-negative/30 text-sm font-medium text-negative transition-colors hover:bg-negative/5"
          @click="revokeTarget = { id: c.id, prefix: c.prefix }"
        >
          Отозвать
        </button>
      </div>
    </div>

    <CreateKeyModal
      v-model:open="createOpen"
      @created="store.load()"
    />

    <RevokeConfirmDialog
      :open="!!revokeTarget"
      :prefix="revokeTarget?.prefix ?? ''"
      @update:open="revokeTarget = null"
      @confirm="onRevoke"
    />
  </div>
</template>
