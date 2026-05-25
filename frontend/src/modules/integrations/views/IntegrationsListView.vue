<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Plus } from 'lucide-vue-next'
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

async function onRevoke(): Promise<void> {
  if (!revokeTarget.value) return
  await store.revoke(revokeTarget.value.id)
  revokeTarget.value = null
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <h1 class="page-title">Интеграции</h1>
      <button class="add-btn" type="button" @click="createOpen = true">
        <Plus :size="18" :stroke-width="2" />
        Добавить ключ
      </button>
    </header>

    <div v-if="store.isLoading" class="state-msg">Загрузка…</div>
    <div v-else-if="store.error" class="state-msg state-error">{{ store.error }}</div>
    <div v-else-if="!store.credentials.length" class="state-msg">Нет ключей. Создайте первый.</div>

    <div v-else class="table-wrap">
      <table class="creds-table">
        <thead>
          <tr>
            <th>Провайдер</th>
            <th>Префикс</th>
            <th>Статус</th>
            <th>Создан</th>
            <th>Последнее использование</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in store.credentials" :key="c.id" class="cred-row">
            <td class="vendor-cell">{{ c.vendor }}</td>
            <td class="mono-cell">{{ c.prefix }}…</td>
            <td>
              <span class="status-badge" :class="`status-${c.status}`">{{ c.status }}</span>
            </td>
            <td class="date-cell">{{ formatDate(c.created_at) }}</td>
            <td class="date-cell">{{ formatDate(c.last_used_at) }}</td>
            <td class="action-cell">
              <button
                v-if="c.status === 'active'"
                class="revoke-btn"
                type="button"
                @click="revokeTarget = { id: c.id, prefix: c.prefix }"
              >
                Отозвать
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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

<style scoped>
.page { padding: var(--space-4); max-width: 900px; margin: 0 auto; display: grid; gap: var(--space-4); }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.page-title { font-size: var(--text-xl); font-weight: var(--font-semibold); color: var(--color-text-primary); margin: 0; }
.add-btn { display: inline-flex; align-items: center; gap: var(--space-1); padding: var(--space-2) var(--space-3); border: 0; border-radius: var(--radius-md); background: var(--color-brand-500); color: var(--color-text-inverse); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.state-msg { padding: var(--space-8); text-align: center; color: var(--color-text-secondary); font-size: var(--text-sm); }
.state-error { color: var(--color-error); }
.table-wrap { overflow-x: auto; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); }
.creds-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.creds-table th { padding: var(--space-3) var(--space-4); text-align: left; font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: .04em; color: var(--color-text-secondary); border-bottom: 1px solid var(--color-border-subtle); white-space: nowrap; }
.cred-row td { padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--color-border-subtle); color: var(--color-text-primary); vertical-align: middle; }
.cred-row:last-child td { border-bottom: none; }
.vendor-cell { font-weight: var(--font-semibold); }
.mono-cell { font-family: var(--font-mono, monospace); font-size: var(--text-xs); font-variant-numeric: tabular-nums; }
.date-cell { font-size: var(--text-xs); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.status-badge { display: inline-block; padding: 2px var(--space-2); border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.status-active { background: color-mix(in srgb, var(--color-success) 12%, transparent); color: var(--color-success); }
.status-revoked { background: color-mix(in srgb, var(--color-error) 10%, transparent); color: var(--color-error); }
.status-expired { background: color-mix(in srgb, var(--color-text-secondary) 10%, transparent); color: var(--color-text-secondary); }
.action-cell { text-align: right; }
.revoke-btn { padding: var(--space-1) var(--space-2); border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent); border-radius: var(--radius-sm); background: transparent; color: var(--color-error); font-size: var(--text-xs); cursor: pointer; }
</style>
