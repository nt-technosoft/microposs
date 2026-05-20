<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { Plus, Check } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { fetchInvestmentAgreements, type InvestmentAgreementListItem } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  selectedAgreementId?: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [agreementId: number]
  'create-new': []
}>()

const search = ref('')
const agreements = ref<InvestmentAgreementListItem[]>([])
const isLoading = ref(false)
let abortController: AbortController | null = null

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return agreements.value
  return agreements.value.filter((a) =>
    String(a.id).includes(q) ||
    a.investor_names.some((n) => n.toLowerCase().includes(q)) ||
    a.operator_names.some((n) => n.toLowerCase().includes(q)) ||
    a.notes.toLowerCase().includes(q),
  )
})

async function load(): Promise<void> {
  abortController?.abort()
  abortController = new AbortController()
  isLoading.value = true
  try {
    agreements.value = await fetchInvestmentAgreements()
  } catch {
    agreements.value = []
  } finally {
    isLoading.value = false
  }
}

watch(() => props.open, (isOpen) => {
  if (isOpen) { search.value = ''; load() }
  else { abortController?.abort(); abortController = null }
})

onBeforeUnmount(() => { abortController?.abort() })

function onSelect(a: InvestmentAgreementListItem): void {
  emit('select', a.id)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Инвестиционный договор" @close="emit('update:open', false)">
    <div class="picker-body">
      <input
        v-model="search"
        class="search-input"
        type="search"
        placeholder="Поиск по инвестору или номеру…"
        autocomplete="off"
      />

      <div v-if="isLoading" class="picker-state">Загрузка…</div>
      <div v-else-if="!filtered.length" class="picker-state">Договоры не найдены</div>

      <ul v-else class="list">
        <li
          v-for="a in filtered"
          :key="a.id"
          class="agreement-row"
          :class="{ selected: a.id === selectedAgreementId }"
          @click="onSelect(a)"
        >
          <div class="agreement-info">
            <span class="agreement-title">Договор #{{ a.id }}
              <span v-if="a.investor_names.length"> · {{ a.investor_names.join(', ') }}</span>
            </span>
            <span class="agreement-meta">
              {{ parseFloat(a.planned_budget).toLocaleString('ru-RU') }} {{ a.currency }}
              · {{ a.mudaraba_ratio }}
            </span>
          </div>
          <Check v-if="a.id === selectedAgreementId" class="check-icon" :size="16" :stroke-width="2.5" />
        </li>
      </ul>

      <button class="create-btn" type="button" @click="emit('create-new'); emit('update:open', false)">
        <Plus :size="14" :stroke-width="2.5" />
        Создать новый договор
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.picker-body { display: grid; gap: var(--space-3); }
.search-input { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-secondary); color: var(--color-text-primary); font-size: var(--text-sm); }
.picker-state { padding: var(--space-4) 0; text-align: center; color: var(--color-text-secondary); font-size: var(--text-sm); }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); max-height: 50vh; overflow-y: auto; }
.agreement-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; }
.agreement-row.selected { border-color: var(--color-brand-600); background: var(--color-brand-50); }
.agreement-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.agreement-title { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.agreement-meta { font-size: var(--text-xs); color: var(--color-text-secondary); }
.check-icon { flex-shrink: 0; color: var(--color-brand-600); }
.create-btn { display: inline-flex; align-items: center; gap: var(--space-2); width: 100%; padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
