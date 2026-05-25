<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { useFxRate } from '@/composables/useFxRate'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]
type SavePayload = { id?: number; expense_type: string; amount: number; currency: string; fx_rate: string; allocation_method: string; target_item_ids: number[] }

const EXPENSE_TYPES = [
  { key: 'LOGISTICS', label: 'Логистика' },
  { key: 'CUSTOMS', label: 'Таможня' },
  { key: 'FEE', label: 'Комиссия' },
  { key: 'OTHER', label: 'Прочее' },
] as const

const ALLOC_METHODS = [
  { key: 'BY_VALUE', label: 'По стоимости' },
  { key: 'BY_QUANTITY', label: 'По количеству' },
] as const

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload; editingExpenseId: number | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; save: [payload: SavePayload]; delete: [expenseId: number] }>()

const expenseType = ref('LOGISTICS')
const amount = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const fxRateLocal = ref('1')
const allocMethod = ref('BY_VALUE')
const targetScope = ref<'all' | 'selected'>('all')
const selectedTargets = ref<number[]>([])

const { rate: fetchedFx, load: loadFx } = useFxRate()

const editExpense = computed<Expense | null>(() =>
  props.editingExpenseId
    ? (props.procurement.documents.expenses.find((e) => e.id === props.editingExpenseId) ?? null)
    : null,
)
const items = computed(() => props.procurement.documents.items)

watch(fetchedFx, (r) => { if (r) fxRateLocal.value = r })
watch(currency, async (cur) => {
  if (cur === 'USD') { if (fxRateLocal.value === '1' || !fxRateLocal.value) await loadFx() }
  else fxRateLocal.value = '1'
})

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  const ex = editExpense.value
  if (ex) {
    expenseType.value = ex.expense_type; amount.value = ex.amount
    currency.value = ex.currency === 'USD' ? 'USD' : 'UZS'; fxRateLocal.value = ex.fx_rate
    allocMethod.value = ex.allocation_method
    if (ex.target_item_ids.length) { targetScope.value = 'selected'; selectedTargets.value = [...ex.target_item_ids] }
    else { targetScope.value = 'all'; selectedTargets.value = [] }
  } else {
    expenseType.value = 'LOGISTICS'; amount.value = ''; currency.value = 'UZS'
    fxRateLocal.value = '1'; allocMethod.value = 'BY_VALUE'
    targetScope.value = 'all'; selectedTargets.value = []
  }
})

function toggleTarget(itemId: number): void {
  selectedTargets.value = selectedTargets.value.includes(itemId)
    ? selectedTargets.value.filter((id) => id !== itemId)
    : [...selectedTargets.value, itemId]
}

function onSave(): void {
  emit('save', {
    ...(props.editingExpenseId ? { id: props.editingExpenseId } : {}),
    expense_type: expenseType.value,
    amount: parseFloat(amount.value) || 0,
    currency: currency.value,
    fx_rate: fxRateLocal.value,
    allocation_method: allocMethod.value,
    target_item_ids: targetScope.value === 'selected' ? [...selectedTargets.value] : [],
  })
  emit('update:open', false)
}

function onDelete(): void {
  if (!props.editingExpenseId) return
  emit('delete', props.editingExpenseId)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Расход" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="section-label">Тип расхода</div>
      <div class="chips-row">
        <button v-for="t in EXPENSE_TYPES" :key="t.key" class="chip" :class="{ active: expenseType === t.key }" type="button" @click="expenseType = t.key">{{ t.label }}</button>
      </div>

      <div class="section-label">Сумма</div>
      <MoneyCurrencyInput v-model:model-value="amount" v-model:currency="currency" />

      <div class="section-label">Метод распределения</div>
      <div class="chips-row">
        <button v-for="m in ALLOC_METHODS" :key="m.key" class="chip" :class="{ active: allocMethod === m.key }" type="button" @click="allocMethod = m.key">{{ m.label }}</button>
      </div>

      <div class="section-label">Распределить на</div>
      <div class="chips-row">
        <button class="chip" :class="{ active: targetScope === 'all' }" type="button" @click="targetScope = 'all'">Все товары</button>
        <button class="chip" :class="{ active: targetScope === 'selected' }" :disabled="!items.length" type="button" @click="targetScope = 'selected'">Выбранные</button>
      </div>

      <div v-if="targetScope === 'selected' && items.length" class="items-checklist">
        <label v-for="item in items" :key="item.id" class="check-row">
          <input type="checkbox" :checked="selectedTargets.includes(item.id)" @change="toggleTarget(item.id)" />
          <span class="check-label">{{ item.product_variant_name }}</span>
        </label>
      </div>

      <button class="primary-btn" type="button" :disabled="!amount" @click="onSave">Сохранить</button>
      <button v-if="editingExpenseId" class="danger-btn" type="button" @click="onDelete">Удалить расход</button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.chips-row { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chip { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-full); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); cursor: pointer; }
.chip.active { border-color: var(--color-brand-600); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.chip:disabled { opacity: .55; cursor: not-allowed; }
.items-checklist { display: grid; gap: var(--space-2); padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); max-height: 30vh; overflow-y: auto; }
.check-row { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; }
.check-label { font-size: var(--text-sm); color: var(--color-text-primary); }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.danger-btn { min-height: 44px; border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent); border-radius: var(--radius-lg); background: transparent; color: var(--color-error); font-weight: var(--font-semibold); cursor: pointer; }
</style>
