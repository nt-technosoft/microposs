<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { CheckCircle2, AlertCircle, Plus } from 'lucide-vue-next'
import ProcurementItemRow from './ProcurementItemRow.vue'
import ProcurementItemEditSheet from './ProcurementItemEditSheet.vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type ActionItem = { id?: number; product_variant_id: number; quantity: number; unit_purchase_price: number; currency: string; fx_rate: string }

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update-items': [items: ActionItem[]]
  'delete-item': [itemId: number]
  'split-item': [payload: { item_id: number; quantity: number }]
}>()

const { items, itemTotalsByCurrency: totalsByCurrency } = useActiveLines(toRef(props, 'procurement'))

const editSheetOpen = ref(false)
const editingItemId = ref<number | null>(null)

const splitSheetOpen = ref(false)
const splittingItemId = ref<number | null>(null)
const splitQty = ref('')

const splittingItem = computed(() => items.value.find((it) => it.id === splittingItemId.value) ?? null)
const splitMax = computed(() =>
  splittingItem.value ? Math.round(parseFloat(splittingItem.value.quantity)) - 1 : undefined,
)

const canEdit = computed(() => props.procurement.status === 'OPEN')
const isFilled = computed(() => props.procurement.readiness['items_ready']?.ok ?? items.value.length > 0)

function formatTotal(amount: number, currency: string): string {
  const formatted = amount % 1 === 0
    ? Math.round(amount).toLocaleString('ru-RU')
    : amount.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
  return `${formatted} ${currency}`
}

function openAdd(): void {
  if (!canEdit.value) return
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
  if (!canEdit.value) return
  const base = items.value.map(toActionItem)
  if (payload.id) {
    emit('update-items', base.map((it) => (it.id === payload.id ? payload : it)))
  } else {
    emit('update-items', [...base, payload])
  }
}

function onSheetDelete(itemId: number): void {
  if (!canEdit.value) return
  emit('delete-item', itemId)
}

function openSplit(itemId: number): void {
  if (!canEdit.value) return
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
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">Товары</CardTitle>
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium tabular-nums text-neutral-500">{{ items.length }}</span>
        <CheckCircle2 v-if="isFilled" class="size-[18px] text-positive" />
        <AlertCircle v-else class="size-[18px] text-warning" />
      </div>
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <p v-if="!items.length" class="py-4 text-center text-sm text-neutral-500">
        Нет товаров. Добавьте первый.
      </p>

      <div v-else class="flex flex-col gap-2">
        <ProcurementItemRow
          v-for="item in items"
          :key="item.id"
          :item="item"
          :is-editable="canEdit && !item.locked_reason"
          @click="openEdit(item.id)"
          @delete="onSheetDelete"
        />
      </div>

      <div
        v-for="(amount, currency) in totalsByCurrency"
        :key="currency"
        class="flex items-center justify-between border-t border-neutral-200 pt-3"
      >
        <span class="text-sm text-neutral-500">Итого</span>
        <span class="text-base font-semibold tabular-nums text-foreground">{{ formatTotal(amount, currency) }}</span>
      </div>

      <button
        v-if="canEdit"
        type="button"
        class="flex w-full items-center justify-center gap-2 rounded-[10px] border border-dashed border-neutral-300 px-3.5 py-3 text-sm font-medium text-green-700 transition-colors hover:bg-green-50/40"
        @click="openAdd"
      >
        <Plus class="size-4" />
        Добавить товар
      </button>
    </CardContent>
  </Card>

  <ProcurementItemEditSheet
    v-model:open="editSheetOpen"
    :procurement="procurement"
    :editing-item-id="editingItemId"
    @save="onSheetSave"
    @delete="onSheetDelete"
    @split="openSplit"
  />

  <AppBottomSheet :open="splitSheetOpen" title="Разделить позицию" @close="splitSheetOpen = false">
    <div class="flex flex-col gap-3">
      <p v-if="splittingItem" class="text-sm font-medium text-foreground">{{ splittingItem.product_variant_name }}</p>
      <p class="text-xs text-neutral-500">
        Сколько единиц отделить в отдельную строку (не более {{ splitMax }} шт.).
      </p>
      <Input
        v-model="splitQty"
        type="number"
        min="1"
        :max="splitMax"
        step="1"
        inputmode="numeric"
        placeholder="Количество"
      />
      <Button class="w-full" :disabled="!splitQty || parseFloat(splitQty) <= 0" @click="onSplitConfirm">
        Разделить
      </Button>
    </div>
  </AppBottomSheet>
</template>
