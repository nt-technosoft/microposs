<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, AlertCircle, Plus } from 'lucide-vue-next'
import ProcurementItemRow from './ProcurementItemRow.vue'
import ProcurementItemEditSheet from './ProcurementItemEditSheet.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type ActionItem = { id?: number; product_variant_id: number; quantity: number; unit_purchase_price: number; currency: string; fx_rate: string; goods_ownership: 'OWNED' | 'CONSIGNED' }

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update-items': [items: ActionItem[]]
  'delete-item': [itemId: number]
}>()

const editSheetOpen = ref(false)
const editingItemId = ref<number | null>(null)

const items = computed(() => props.procurement.documents.items)
const canEdit = computed(() => props.procurement.status === 'OPEN')
const isFilled = computed(() => props.procurement.readiness['items_ready']?.ok ?? items.value.length > 0)

const totalUzs = computed(() =>
  items.value.reduce((sum, it) => {
    const qty = parseFloat(it.quantity) || 0
    const price = parseFloat(it.unit_purchase_price) || 0
    const fx = parseFloat(it.fx_rate) || 1
    return sum + qty * price * fx
  }, 0),
)

const totalDisplay = computed(() =>
  Math.round(totalUzs.value).toLocaleString('ru-RU'),
)

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
    goods_ownership: it.goods_ownership,
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
      />
    </div>

    <div v-if="items.length" class="totals-row">
      <span class="totals-label">Итого</span>
      <span class="totals-value">{{ totalDisplay }} UZS</span>
    </div>

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
</style>
