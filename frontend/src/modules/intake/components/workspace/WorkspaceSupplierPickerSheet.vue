<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Plus, Check } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import WorkspaceQuickSupplierSheet from './WorkspaceQuickSupplierSheet.vue'
import { fetchSuppliers } from '@/api/suppliers'
import { useDebounce } from '@/composables/useDebounce'
import type { Supplier } from '@/types/models'

const props = defineProps<{
  open: boolean
  selectedId?: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [supplierId: number]
}>()

const search = ref('')
const suppliers = ref<Supplier[]>([])
const isLoading = ref(false)
const quickCreateOpen = ref(false)
let abortController: AbortController | null = null

async function loadSuppliers(query: string): Promise<void> {
  abortController?.abort()
  abortController = new AbortController()
  isLoading.value = true
  try {
    const result = await fetchSuppliers({ active: true, search: query || undefined }, abortController.signal)
    suppliers.value = result.results
  } catch (err) {
    if ((err as any)?.name === 'AbortError') return
    suppliers.value = []
  } finally {
    isLoading.value = false
  }
}

const debouncedLoad = useDebounce((q: string) => loadSuppliers(q), 300)

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    search.value = ''
    loadSuppliers('')
  } else {
    abortController?.abort()
    abortController = null
  }
})

watch(search, (q) => { debouncedLoad(q) })

onBeforeUnmount(() => { abortController?.abort() })

function onSelect(supplier: Supplier): void {
  emit('select', supplier.id)
  emit('update:open', false)
}

function onQuickCreated(supplierId: number): void {
  emit('select', supplierId)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Выберите поставщика" @close="emit('update:open', false)">
    <div class="picker-body">
      <input
        v-model="search"
        class="search-input"
        type="search"
        placeholder="Поиск поставщика…"
        autocomplete="off"
      />

      <div v-if="isLoading" class="picker-state">Загрузка…</div>
      <div v-else-if="!suppliers.length" class="picker-state">Поставщики не найдены</div>

      <ul v-else class="supplier-list">
        <li
          v-for="s in suppliers"
          :key="s.id"
          class="supplier-row"
          :class="{ selected: s.id === selectedId }"
          @click="onSelect(s)"
        >
          <div class="supplier-info">
            <span class="supplier-name">{{ s.name }}</span>
            <span v-if="s.phone" class="supplier-phone">{{ s.phone }}</span>
          </div>
          <Check v-if="s.id === selectedId" class="check-icon" :size="16" :stroke-width="2.5" />
        </li>
      </ul>

      <button class="create-btn" type="button" @click="quickCreateOpen = true">
        <Plus :size="14" :stroke-width="2.5" />
        Создать нового поставщика
      </button>
    </div>
  </AppBottomSheet>

  <WorkspaceQuickSupplierSheet
    v-model:open="quickCreateOpen"
    @created="onQuickCreated"
  />
</template>

<style scoped>
.picker-body {
  display: grid;
  gap: var(--space-3);
}

.search-input {
  width: 100%;
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-size: var(--text-sm, 0.875rem);
}

.picker-state {
  padding: var(--space-4) 0;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm, 0.875rem);
}

.supplier-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-2);
  max-height: 48vh;
  overflow-y: auto;
}

.supplier-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  cursor: pointer;
}

.supplier-row.selected {
  border-color: var(--color-brand-600);
  background: var(--color-brand-50);
}

.supplier-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.supplier-name {
  font-size: var(--text-sm, 0.875rem);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.supplier-phone {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.check-icon {
  flex-shrink: 0;
  color: var(--color-brand-600);
}

.create-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-brand-700);
  font-size: var(--text-sm, 0.875rem);
  font-weight: var(--font-semibold);
  width: 100%;
  cursor: pointer;
}
</style>
