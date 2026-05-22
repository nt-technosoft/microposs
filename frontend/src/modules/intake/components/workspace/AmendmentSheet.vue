<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]

interface DraftItem {
  id: number; name: string; qty: string; price: string
  currency: string; fx_rate: string; product_variant_id: number
  cancelled: boolean
}

interface DraftExpense {
  id: number; expense_type: string; amount: string; currency: string
  fx_rate: string; allocation_method: string; target_item_ids: number[]; cancelled: boolean
}

const EXPENSE_TYPE_LABELS: Record<string, string> = {
  LOGISTICS: 'Логистика', CUSTOMS: 'Таможня', FEE: 'Комиссия',
}

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  target: 'items' | 'expenses'
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const activeTarget = ref<'items' | 'expenses'>('items')
const draftItems = ref<DraftItem[]>([])
const draftExpenses = ref<DraftExpense[]>([])
const reason = ref('')
const reasonError = ref(false)
const isSaving = ref(false)

const amendableItems = computed(() =>
  draftItems.value.filter((i) => !['RECEIVED', 'CANCELLED'].includes(
    props.procurement.documents.items.find((pi) => pi.id === i.id)?.lifecycle_state ?? '',
  )),
)

const amendableExpenses = computed(() =>
  draftExpenses.value.filter((e) => !['RECEIVED', 'CANCELLED'].includes(
    props.procurement.documents.expenses.find((pe) => pe.id === e.id)?.lifecycle_state ?? '',
  )),
)

const activeCount = computed(() =>
  activeTarget.value === 'items'
    ? amendableItems.value.filter((i) => !i.cancelled).length
    : amendableExpenses.value.filter((e) => !e.cancelled).length,
)

function fromItem(i: Item): DraftItem {
  return {
    id: i.id, name: i.product_variant_name, qty: i.quantity,
    price: i.unit_purchase_price, currency: i.currency, fx_rate: i.fx_rate,
    product_variant_id: i.product_variant_id,
    cancelled: false,
  }
}

function fromExpense(e: Expense): DraftExpense {
  return {
    id: e.id, expense_type: e.expense_type, amount: e.amount, currency: e.currency,
    fx_rate: e.fx_rate, allocation_method: e.allocation_method,
    target_item_ids: [...e.target_item_ids], cancelled: false,
  }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  activeTarget.value = props.target
  draftItems.value = props.procurement.documents.items.map(fromItem)
  draftExpenses.value = props.procurement.documents.expenses.map(fromExpense)
  reason.value = ''
  reasonError.value = false
})

function buildItemPayload(): Record<string, unknown>[] {
  const active = draftItems.value
    .filter((i) => !i.cancelled)
    .map((i) => ({
      id: i.id, product_variant_id: i.product_variant_id,
      quantity: parseFloat(i.qty) || 0, unit_purchase_price: parseFloat(i.price) || 0,
      currency: i.currency, fx_rate: i.fx_rate,
    }))
  const cancelled = draftItems.value
    .filter((i) => i.cancelled)
    .map((i) => ({ id: i.id, _cancel: true }))
  return [...active, ...cancelled]
}

function buildExpensePayload(): Record<string, unknown>[] {
  return draftExpenses.value
    .filter((e) => !e.cancelled)
    .map((e) => ({
      id: e.id, expense_type: e.expense_type,
      amount: parseFloat(e.amount) || 0, currency: e.currency, fx_rate: e.fx_rate,
      allocation_method: e.allocation_method, target_item_ids: e.target_item_ids,
    }))
}

async function onSubmit(): Promise<void> {
  if (!reason.value.trim()) { reasonError.value = true; return }
  isSaving.value = true
  try {
    if (activeTarget.value === 'items') {
      emit('dispatch', 'AMEND_ITEMS', { items: buildItemPayload(), reason: reason.value.trim() })
    } else {
      emit('dispatch', 'AMEND_EXPENSES', { expenses: buildExpensePayload(), reason: reason.value.trim() })
    }
    emit('update:open', false)
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Корректировка" @close="emit('update:open', false)">
    <div class="sheet-body">
      <!-- Target selector -->
      <div class="target-chips">
        <button class="target-chip" :class="{ active: activeTarget === 'items' }" type="button" @click="activeTarget = 'items'">Товары</button>
        <button class="target-chip" :class="{ active: activeTarget === 'expenses' }" type="button" @click="activeTarget = 'expenses'">Расходы</button>
      </div>

      <!-- Items list -->
      <template v-if="activeTarget === 'items'">
        <div v-if="!amendableItems.length" class="empty-text">Нет товаров для корректировки</div>
        <div v-else class="rows-list">
          <div
            v-for="item in amendableItems"
            :key="item.id"
            class="edit-row"
            :class="{ cancelled: item.cancelled }"
          >
            <div class="row-name">{{ item.name }}</div>
            <div class="row-fields">
              <label class="field-label">Кол-во</label>
              <input
                class="mini-input"
                type="number" min="0" step="0.001"
                :value="item.qty"
                :disabled="item.cancelled"
                @input="item.qty = ($event.target as HTMLInputElement).value"
              />
              <label class="field-label">Цена</label>
              <input
                class="mini-input"
                type="number" min="0" step="0.01"
                :value="item.price"
                :disabled="item.cancelled"
                @input="item.price = ($event.target as HTMLInputElement).value"
              />
              <span class="field-currency">{{ item.currency }}</span>
            </div>
            <button class="cancel-btn" type="button" :title="item.cancelled ? 'Восстановить' : 'Отменить строку'" @click="item.cancelled = !item.cancelled">
              <Trash2 :size="14" :stroke-width="2" />
            </button>
          </div>
        </div>
      </template>

      <!-- Expenses list -->
      <template v-else>
        <div v-if="!amendableExpenses.length" class="empty-text">Нет расходов для корректировки</div>
        <div v-else class="rows-list">
          <div
            v-for="expense in amendableExpenses"
            :key="expense.id"
            class="edit-row"
            :class="{ cancelled: expense.cancelled }"
          >
            <div class="row-name">{{ EXPENSE_TYPE_LABELS[expense.expense_type] ?? expense.expense_type }}</div>
            <div class="row-fields">
              <label class="field-label">Сумма</label>
              <input
                class="mini-input"
                type="number" min="0" step="0.01"
                :value="expense.amount"
                :disabled="expense.cancelled"
                @input="expense.amount = ($event.target as HTMLInputElement).value"
              />
              <span class="field-currency">{{ expense.currency }}</span>
            </div>
            <button class="cancel-btn" type="button" :title="expense.cancelled ? 'Восстановить' : 'Отменить расход'" @click="expense.cancelled = !expense.cancelled">
              <Trash2 :size="14" :stroke-width="2" />
            </button>
          </div>
        </div>
      </template>

      <!-- Reason -->
      <div class="section-label">Причина корректировки <span class="required">*</span></div>
      <textarea
        v-model="reason"
        class="reason-input"
        :class="{ error: reasonError }"
        rows="3"
        placeholder="Укажите причину изменений…"
        @input="reasonError = false"
      />
      <div v-if="reasonError" class="error-text">Причина обязательна</div>

      <div class="footer-hint">Изменится: {{ activeCount }} позиций</div>

      <button class="primary-btn" type="button" :disabled="isSaving" @click="onSubmit">
        {{ isSaving ? 'Сохранение…' : 'Применить корректировку' }}
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.target-chips { display: flex; gap: var(--space-2); }
.target-chip { flex: 1; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-full); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); cursor: pointer; text-align: center; }
.target-chip.active { border-color: var(--color-brand-600); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.empty-text { font-size: var(--text-sm); color: var(--color-text-secondary); padding: var(--space-2) 0; }
.rows-list { display: grid; gap: var(--space-2); }
.edit-row { display: grid; gap: var(--space-1); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-secondary); }
.edit-row.cancelled { opacity: .5; }
.row-name { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.row-fields { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.field-label { font-size: var(--text-xs); color: var(--color-text-secondary); }
.mini-input { width: 90px; min-height: 36px; padding: 0 var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-sm); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.mini-input:disabled { opacity: .55; }
.field-currency { font-size: var(--text-xs); color: var(--color-text-secondary); }
.cancel-btn { justify-self: end; padding: var(--space-1); border: 0; background: transparent; color: var(--color-text-tertiary); cursor: pointer; border-radius: var(--radius-sm); }
.cancel-btn:hover { color: var(--color-error); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.required { color: var(--color-error); }
.reason-input { width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); resize: vertical; font-family: inherit; }
.reason-input.error { border-color: var(--color-error); }
.error-text { font-size: var(--text-xs); color: var(--color-error); margin-top: -var(--space-2); }
.footer-hint { font-size: var(--text-xs); color: var(--color-text-secondary); }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
