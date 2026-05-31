<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import WorkspaceVariantPickerSheet from './WorkspaceVariantPickerSheet.vue'
import WorkspaceQuickProductSheet from './WorkspaceQuickProductSheet.vue'
import { useFxRate } from '@/composables/useFxRate'
import { useDebounce } from '@/composables/useDebounce'
import { fetchVariants, fetchCategories, createProduct, fetchProductVariants } from '@/api/catalog'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'
import type { ProductVariant } from '@/types/models'
import type { SelectOption } from './types'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type SavePayload = { id?: number; product_variant_id: number; quantity: number; unit_purchase_price: number; currency: string; fx_rate: string }

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload; editingItemId: number | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; save: [payload: SavePayload]; delete: [itemId: number]; split: [itemId: number] }>()

const variantId = ref<number | null>(null)
const variantName = ref('')
const qty = ref('1')
const price = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const fxRateLocal = ref('1')

const vpOpen = ref(false); const vpSearch = ref(''); const vpCategory = ref<number | null>(null)
const vpVariants = ref<ProductVariant[]>([]); const catOptions = ref<SelectOption<number | null>[]>([])

const qpOpen = ref(false); const qpName = ref(''); const qpCatId = ref<number | null>(null)
const qpBasePrice = ref(''); const qpError = ref<string | null>(null); const qpSaving = ref(false)

const { rate: fetchedFx, load: loadFx } = useFxRate()

const editItem = computed<Item | null>(() =>
  props.editingItemId ? (props.procurement.documents.items.find((i) => i.id === props.editingItemId) ?? null) : null,
)
const canSplit = computed(
  () => !!editItem.value
    && props.procurement.status === 'OPEN'
    && !editItem.value.locked_reason
    && Math.round(parseFloat(editItem.value.quantity) || 0) > 1,
)
const lockedCurrency = computed<'UZS' | 'USD' | null>(() => {
  const currencies = new Set(
    [
      ...props.procurement.documents.items
        .filter((item) => item.lifecycle_state !== 'CANCELLED' && item.id !== props.editingItemId)
        .map((item) => item.currency === 'USD' ? 'USD' : 'UZS'),
      ...props.procurement.documents.expenses
        .filter((expense) => expense.lifecycle_state !== 'CANCELLED')
        .map((expense) => expense.currency === 'USD' ? 'USD' : 'UZS'),
    ],
  )
  return currencies.size === 1 ? ([...currencies][0] as 'UZS' | 'USD') : null
})
const allowedCurrencies = computed<Array<'UZS' | 'USD'>>(() =>
  lockedCurrency.value ? [lockedCurrency.value] : ['USD', 'UZS'],
)
const variantDisplay = (v: ProductVariant) => v.product_name ?? v.display_sku ?? v.sku ?? String(v.id)

watch(fetchedFx, (r) => { if (r) fxRateLocal.value = r })
watch(currency, async (cur) => {
  if (cur === 'USD') { if (fxRateLocal.value === '1' || !fxRateLocal.value) await loadFx() }
  else fxRateLocal.value = '1'
})

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  const it = editItem.value
  if (it) {
    variantId.value = it.product_variant_id; variantName.value = it.product_variant_name
    qty.value = String(Math.round(parseFloat(it.quantity) || 0)); price.value = it.unit_purchase_price
    currency.value = it.currency === 'USD' ? 'USD' : 'UZS'
    fxRateLocal.value = it.fx_rate
  } else {
    variantId.value = null; variantName.value = ''; qty.value = '1'
    price.value = ''; currency.value = lockedCurrency.value ?? (props.procurement.documents.procurement.primary_currency === 'USD' ? 'USD' : 'UZS'); fxRateLocal.value = currency.value === 'USD' ? fxRateLocal.value : '1'
  }
  if (!catOptions.value.length) loadCategories()
})

async function loadCategories(): Promise<void> {
  const cats = await fetchCategories()
  catOptions.value = [{ value: null, label: 'Все категории' }, ...cats.map((c) => ({ value: c.id, label: c.name }))]
}

async function loadVariants(): Promise<void> {
  vpVariants.value = await fetchVariants({ active: true, search: vpSearch.value || undefined, category: vpCategory.value ?? undefined })
}

const debouncedLoadVariants = useDebounce(loadVariants, 300)
watch([vpSearch, vpCategory], () => { if (vpOpen.value) debouncedLoadVariants() })
watch(vpOpen, (v) => { if (v) { vpSearch.value = ''; vpCategory.value = null; loadVariants() } })

function onVariantSelect(v: ProductVariant): void {
  variantId.value = v.id; variantName.value = variantDisplay(v); vpOpen.value = false
}
function onNewProduct(): void { vpOpen.value = false; qpOpen.value = true }

async function onQpSubmit(): Promise<void> {
  if (!qpName.value.trim()) { qpError.value = 'Название обязательно'; return }
  qpSaving.value = true; qpError.value = null
  try {
    const product = await createProduct({ name: qpName.value.trim(), category_id: qpCatId.value, base_price: qpBasePrice.value || null })
    const variants = await fetchProductVariants(product.id)
    if (variants[0]) { variantId.value = variants[0].id; variantName.value = variantDisplay(variants[0]) }
    qpOpen.value = false; qpName.value = ''; qpCatId.value = null; qpBasePrice.value = ''
  } catch { qpError.value = 'Ошибка создания товара' }
  finally { qpSaving.value = false }
}

function onSave(): void {
  if (!variantId.value) return
  emit('save', {
    ...(props.editingItemId ? { id: props.editingItemId } : {}),
    product_variant_id: variantId.value,
    quantity: parseFloat(qty.value) || 1,
    unit_purchase_price: parseFloat(price.value) || 0,
    currency: currency.value,
    fx_rate: fxRateLocal.value,
  })
  emit('update:open', false)
}

function onDelete(): void {
  if (!props.editingItemId) return
  emit('delete', props.editingItemId)
  emit('update:open', false)
}

function onSplit(): void {
  if (!props.editingItemId) return
  emit('split', props.editingItemId)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Товар" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Товар -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Товар</span>
        <button
          type="button"
          class="flex w-full items-center justify-between gap-2 rounded-[10px] border border-neutral-200 px-3.5 py-3 text-left transition-colors hover:border-green-300 hover:bg-green-50/40"
          @click="vpOpen = true"
        >
          <span class="min-w-0 truncate text-sm font-medium" :class="variantName ? 'text-foreground' : 'text-neutral-400'">{{ variantName || 'Выбрать товар' }}</span>
          <ChevronRight class="size-4 shrink-0 text-neutral-400" />
        </button>
      </div>

      <!-- Количество + Цена -->
      <div class="flex gap-3">
        <div class="flex w-28 shrink-0 flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Количество</span>
          <Input v-model="qty" type="number" min="1" step="1" inputmode="numeric" class="h-11 tabular-nums" />
        </div>
        <div class="flex flex-1 flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Цена закупки</span>
          <MoneyCurrencyInput v-model:model-value="price" v-model:currency="currency" :currencies="allowedCurrencies" />
        </div>
      </div>
      <p v-if="lockedCurrency" class="-mt-1.5 text-xs text-neutral-400">
        Валюта прихода зафиксирована: {{ lockedCurrency }}.
      </p>

      <div class="flex flex-col gap-2 pt-1">
        <Button class="h-12 w-full text-base" :disabled="!variantId" @click="onSave">Сохранить</Button>
        <Button v-if="canSplit" variant="outline" class="w-full" @click="onSplit">Разделить позицию</Button>
        <button
          v-if="editingItemId"
          type="button"
          class="h-11 rounded-[10px] border border-negative/30 text-sm font-medium text-negative transition-colors hover:bg-negative/5"
          @click="onDelete"
        >
          Удалить позицию
        </button>
      </div>
    </div>
  </AppBottomSheet>

  <WorkspaceVariantPickerSheet
    :open="vpOpen" :search="vpSearch" :category="vpCategory"
    :category-options="catOptions" :variants="vpVariants" :variant-display="variantDisplay"
    @close="vpOpen = false" @update-search="vpSearch = $event" @update-category="vpCategory = $event"
    @new-product="onNewProduct" @select="onVariantSelect"
  />

  <WorkspaceQuickProductSheet
    :open="qpOpen" :name="qpName" :category-id="qpCatId" :base-price="qpBasePrice"
    :category-options="catOptions" :error="qpError" :saving="qpSaving"
    @close="qpOpen = false" @update-name="qpName = $event" @update-category-id="qpCatId = $event"
    @update-base-price="qpBasePrice = $event" @submit="onQpSubmit"
  />
</template>
