<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
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
    <div class="sheet-body">
      <div class="section-label">Товар</div>
      <button class="variant-btn" type="button" @click="vpOpen = true">
        <span class="variant-btn-text">{{ variantName || 'Выбрать товар' }}</span>
        <ChevronRight :size="14" :stroke-width="2" />
      </button>

      <div class="qty-price-row">
        <div class="field qty-field">
          <div class="section-label">Количество</div>
          <input class="input-field number-input" type="number" min="1" step="1" :value="qty" @input="qty = ($event.target as HTMLInputElement).value" />
        </div>
        <div class="field price-field">
          <div class="section-label">Цена закупки</div>
          <MoneyCurrencyInput v-model:model-value="price" v-model:currency="currency" :currencies="allowedCurrencies" />
        </div>
      </div>
      <div v-if="lockedCurrency" class="currency-lock-hint">
        Валюта прихода уже зафиксирована: {{ lockedCurrency }}.
      </div>

      <button class="primary-btn" type="button" :disabled="!variantId" @click="onSave">Сохранить</button>
      <button v-if="canSplit" class="secondary-btn" type="button" @click="onSplit">Разделить позицию</button>
      <button v-if="editingItemId" class="danger-btn" type="button" @click="onDelete">Удалить строку</button>
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

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.qty-price-row { display: flex; gap: var(--space-3); }
.qty-field { flex: 1; }
.price-field { flex: 2; }
.field { display: grid; gap: var(--space-1); }
.number-input { font-variant-numeric: tabular-nums; }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.variant-btn { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-secondary); color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; text-align: left; }
.variant-btn-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.input-field { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.currency-lock-hint { font-size: var(--text-xs); color: var(--color-text-secondary); }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.secondary-btn { min-height: 44px; border: 1px solid var(--color-border-default); border-radius: var(--radius-lg); background: transparent; color: var(--color-text-primary); font-weight: var(--font-semibold); cursor: pointer; }
.danger-btn { min-height: 44px; border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent); border-radius: var(--radius-lg); background: transparent; color: var(--color-error); font-weight: var(--font-semibold); cursor: pointer; }
</style>
