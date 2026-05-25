<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, AlertCircle, Plus } from 'lucide-vue-next'
import ProcurementItemRow from './ProcurementItemRow.vue'
import ProcurementItemEditSheet from './ProcurementItemEditSheet.vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type ActionItem = { id?: number; product_variant_id: number; quantity: number; unit_purchase_price: number; currency: string; fx_rate: string }

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update-items': [items: ActionItem[]]
  'delete-item': [itemId: number]
  'split-item': [payload: { item_id: number; quantity: number }]
}>()

const editSheetOpen = ref(false)
const editingItemId = ref<number | null>(null)

const splitSheetOpen = ref(false)
const splittingItemId = ref<number | null>(null)
const splitQty = ref('')

const splittingItem = computed(() =>
  items.value.find((it) => it.id === splittingItemId.value) ?? null,
)

const items = computed(() =>
  props.procurement.documents.items.filter((it) => it.lifecycle_state !== 'CANCELLED'),
)
const canEdit = computed(() => props.procurement.status === 'OPEN')
const isFilled = computed(() => props.procurement.readiness['items_ready']?.ok ?? items.value.length > 0)

const totalsByCurrency = computed(() => {
  const map: Record<string, number> = {}
  for (const it of items.value) {
    const cur = (it.currency || 'UZS').toUpperCase()
    const amount = (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_purchase_price) || 0)
    map[cur] = (map[cur] ?? 0) + amount
  }
  return map
})

function formatTotal(amount: number, currency: string): string {
  const formatted = amount % 1 === 0
    ? Math.round(amount).toLocaleString('ru-RU')
    : amount.toFixed(2)
  return `${formatted} ${currency}`
}

function openAdd(): void {
  editingItemId.value = null
  editSheetOpen.value = true
}

function openEdit(itemId: number): void {
  editingItemId.value = itemId
  editSheetOpen.value = true
}

function toActionItem(it: Item): ActionItem {
  return {
    id: it.id,
    product_variant_id: it.product_variant_id,
    quantity: parseFloat(it.quantity) || 0,
    unit_purchase_price: parseFloat(it.unit_purchase_price) || 0,
    currency: it.currency,
    fx_rate: it.fx_rate,
  }
}

function onSheetSave(payload: ActionItem): void {
  const base = items.value.map(toActionItem)
  if (payload.id) {
    emit('update-items', base.map((it) => (it.id === payload.id ? payload : it)))
  } else {
    emit('update-items', [...base, payload])
  }
}

function onSheetDelete(itemId: number): void {
  emit('delete-item', itemId)
}

function openSplit(itemId: number): void {
  splittingItemId.value = itemId
  splitQty.value = ''
  splitSheetOpen.value = true
}

function onSplitConfirm(): void {
  const qty = Math.round(parseFloat(splitQty.value))
  if (!splittingItemId.value || !qty || qty <= 0) return
  emit('split-item', { item_id: splittingItemId.value, quantity: qty })
  splitSheetOpen.value = false
}
</script>

<template>
  <div class="items-card">
    <div class="card-header">
      <span class="card-title">Товары</span>
      <div class="header-right">
        <span class="item-count">{{ items.length }}</span>
        <CheckCircle v-if="isFilled" class="status-ok" :size="18" :stroke-width="2" />
        <AlertCircle v-else class="status-warn" :size="18" :stroke-width="2" />
      </div>
    </div>

    <div v-if="!items.length" class="empty-state">
      Нет товаров. Добавь первый.
    </div>

    <div v-else class="items-list">
      <ProcurementItemRow
        v-for="item in items"
        :key="item.id"
        :item="item"
        :is-editable="canEdit && !item.locked_reason"
        @click="openEdit(item.id)"
        @delete="onSheetDelete"
        @split="openSplit"
      />
    </div>

    <template v-if="Object.keys(totalsByCurrency).length">
      <div v-for="(amount, currency) in totalsByCurrency" :key="currency" class="totals-row">
        <span class="totals-label">Итого</span>
        <span class="totals-value">{{ formatTotal(amount, currency) }}</span>
      </div>
    </template>

    <button class="add-btn" type="button" @click="openAdd">
      <Plus :size="14" :stroke-width="2.5" />
      Добавить товар
    </button>
  </div>

  <ProcurementItemEditSheet
    v-model:open="editSheetOpen"
    :procurement="procurement"
    :editing-item-id="editingItemId"
    @save="onSheetSave"
    @delete="onSheetDelete"
  />

  <AppBottomSheet :open="splitSheetOpen" title="Разделить позицию" @close="splitSheetOpen = false">
    <div class="split-sheet-body">
      <div v-if="splittingItem" class="split-item-name">{{ splittingItem.product_variant_name }}</div>
      <div class="split-hint">Введите количество для отделения в отдельную строку (не более {{ splittingItem ? Math.round(parseFloat(splittingItem.quantity)) - 1 : '' }} шт.).</div>
      <input
        class="split-input"
        type="number"
        min="1"
        :max="splittingItem ? Math.round(parseFloat(splittingItem.quantity)) - 1 : undefined"
        step="1"
        inputmode="numeric"
        placeholder="Количество"
        v-model="splitQty"
      />
      <button class="split-confirm-btn" type="button" :disabled="!splitQty || parseFloat(splitQty) <= 0" @click="onSplitConfirm">
        Разделить
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.items-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.item-count {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

.status-ok { color: var(--color-success); }
.status-warn { color: #F59E0B; }

.empty-state {
  padding: var(--space-4) 0;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.items-list {
  display: grid;
  gap: var(--space-2);
}

.totals-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.totals-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.totals-value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

.split-sheet-body { display: grid; gap: var(--space-3); padding: var(--space-4); }
.split-item-name { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.split-hint { font-size: var(--text-xs); color: var(--color-text-secondary); }
.split-input { width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); font-size: var(--text-base); background: var(--color-bg-secondary); color: var(--color-text-primary); }
.split-confirm-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: none; border-radius: var(--radius-md); background: var(--color-brand-600); color: white; font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.split-confirm-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
