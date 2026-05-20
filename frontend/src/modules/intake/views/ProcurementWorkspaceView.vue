<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProcurementWorkspaceStore } from '@/modules/intake/stores/procurementWorkspace'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useProcurementWorkspaceStore()
const { procurement, isLoading, error } = storeToRefs(store)

async function ensureWorkspace(): Promise<void> {
  const id = route.params.id ? Number(route.params.id) : null
  if (id) {
    await store.load(id)
  } else {
    const draftId = await store.createDraft({})
    await router.replace({ name: 'procurement-detail', params: { id: draftId } })
  }
}

onMounted(ensureWorkspace)
watch(() => route.params.id, ensureWorkspace)
onBeforeUnmount(() => store.$reset())
</script>

<template>
  <div class="workspace">
    <!-- Header сюда в B-2 -->
    <header class="workspace-header-placeholder">
      <button class="back-btn" @click="router.back()" aria-label="Назад">←</button>
      <h1>{{ procurement ? `Приход #${procurement.id}` : 'Новый приход' }}</h1>
    </header>

    <main class="workspace-body">
      <div v-if="isLoading" class="state state-loading">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state state-empty">Нет данных</div>
      <div v-else class="cards-container">
        <!-- Карточки добавляются в B-3 .. B-9 -->
        <div class="card-placeholder">Карточки появятся в следующих slice-ах</div>
      </div>
    </main>

    <!-- Bottom action bar сюда в B-2 -->
    <footer class="workspace-action-bar-placeholder">
      <button class="action-btn" disabled>Сохранить черновик</button>
    </footer>
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: var(--color-bg-secondary);
}

.workspace-header-placeholder {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
  backdrop-filter: blur(14px);
}

.workspace-header-placeholder h1 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: center;
}

.back-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 24px;
}

.workspace-body {
  overflow-y: auto;
  padding: var(--space-4);
  padding-bottom: var(--space-8);
}

.cards-container {
  display: grid;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
}

.card-placeholder {
  padding: var(--space-4);
  background: var(--color-bg-primary);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  text-align: center;
}

.state {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--color-text-secondary);
}

.state-error {
  color: var(--color-error);
}

.workspace-action-bar-placeholder {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-subtle);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
}

.action-btn {
  flex: 1;
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--color-brand-600);
  color: white;
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
}

.action-btn:disabled {
  opacity: 0.55;
}
</style>
