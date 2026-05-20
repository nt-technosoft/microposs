<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProcurementWorkspaceStore } from '@/modules/intake/stores/procurementWorkspace'
import { storeToRefs } from 'pinia'
import { useToast } from '@/composables/useToast'
import ProcurementHeader from '@/modules/intake/components/workspace/ProcurementHeader.vue'
import ProcurementBottomActionBar from '@/modules/intake/components/workspace/ProcurementBottomActionBar.vue'
import ProcurementCardSupplier from '@/modules/intake/components/workspace/ProcurementCardSupplier.vue'
import WorkspaceSupplierPickerSheet from '@/modules/intake/components/workspace/WorkspaceSupplierPickerSheet.vue'

const route = useRoute()
const router = useRouter()
const store = useProcurementWorkspaceStore()
const { procurement, isLoading, error } = storeToRefs(store)
const toast = useToast()

const supplierPickerOpen = ref(false)

async function ensureWorkspace(): Promise<void> {
  const id = route.params.id ? Number(route.params.id) : null
  if (id) {
    await store.load(id)
  } else {
    const draftId = await store.createDraft({})
    await router.replace({ name: 'procurement-detail', params: { id: draftId } })
  }
}

function handleMenuAction(actionKey: string): void {
  toast.info(`Будет реализовано: ${actionKey}`)
}

async function handlePrimaryAction(actionKey: string): Promise<void> {
  try {
    await store.dispatch(actionKey, {})
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Ошибка выполнения действия')
  }
}

async function onUpdateSource(payload: { supplier_id?: number | null; funding_source?: string }): Promise<void> {
  try {
    await store.dispatch('UPDATE_SOURCE', payload as Record<string, unknown>)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Не удалось обновить источник')
  }
}

async function onUpdateSettlement(payload: { type: string }): Promise<void> {
  try {
    await store.dispatch('UPDATE_SETTLEMENT', payload as Record<string, unknown>)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Не удалось обновить условия')
  }
}

function onSupplierSelect(supplierId: number): void {
  supplierPickerOpen.value = false
  onUpdateSource({ supplier_id: supplierId })
}

function onCreateNewSupplier(): void {
  toast.info('Создание поставщика — будет реализовано')
}

onMounted(ensureWorkspace)
watch(() => route.params.id, ensureWorkspace)
onBeforeUnmount(() => store.$reset())
</script>

<template>
  <div class="workspace">
    <ProcurementHeader
      :procurement-id="procurement?.id ?? null"
      :status="procurement?.status ?? null"
      :title="procurement?.display.title ?? 'Новый приход'"
      :subtitle="procurement?.display.subtitle ?? null"
      @back="router.back()"
      @menu-action="handleMenuAction"
    />

    <main class="workspace-body">
      <div v-if="isLoading" class="state state-loading">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state state-empty">Нет данных</div>
      <div v-else class="cards-container">
        <ProcurementCardSupplier
          :procurement="procurement"
          @update-source="onUpdateSource"
          @update-settlement="onUpdateSettlement"
          @open-supplier-picker="supplierPickerOpen = true"
        />
      </div>
    </main>

    <ProcurementBottomActionBar
      :action-key="procurement?.display.next_action.key ?? null"
      :action-label="procurement?.display.next_action.label ?? null"
      :reason="procurement?.display.next_action.reason ?? null"
      @click="handlePrimaryAction"
    />

    <WorkspaceSupplierPickerSheet
      v-model:open="supplierPickerOpen"
      :selected-id="procurement?.documents.procurement.supplier_id ?? null"
      @select="onSupplierSelect"
      @create-new="onCreateNewSupplier"
    />
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  background: var(--color-bg-secondary);
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

.state {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--color-text-secondary);
}

.state-error { color: var(--color-error); }
</style>
