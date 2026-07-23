<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Package, ShoppingCart, Check, ListTree, ArrowRightLeft, Truck } from 'lucide-vue-next'
import { fetchDiscountReasons, fetchProduct, fetchProductSuppliers, fetchProductVariants, type ProductSupplierHistoryItem } from '@/api/catalog'
import { fetchLots } from '@/api/inventory'
import { createWriteoff, fetchWriteoffPreview, type WriteoffPreview } from '@/api/risk'
import { useFxRate } from '@/composables/useFxRate'
import { useCartStore } from '@/stores/cart'
import { useSessionStore } from '@/stores/session'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import type { Lot, Product, ProductVariant } from '@/types/models'
import { PricingMode } from '@/types/enums'
import QuantityControl from '@/components/forms/QuantityControl.vue'
import PriceDisplay from '@/components/data/PriceDisplay.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import PageChrome from '@/components/layout/PageChrome.vue'
import PageContainer from '@/components/layout/PageContainer.vue'
import ResponsiveOverlay from '@/components/layout/ResponsiveOverlay.vue'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'

// ===== Route + store =====
const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()
const sessionStore = useSessionStore()
const authStore = useAuthStore()
const toast = useToast()
const { t, locale } = useI18n()
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadUsdRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

// ===== State =====
const product = ref<Product | null>(null)
const variants = ref<ProductVariant[]>([])
const supplierHistory = ref<ProductSupplierHistoryItem[]>([])
const discountReasonOptions = ref<Array<{ value: number; label: string }>>([])
const isLoading = ref(true)
const loadError = ref<string | null>(null)

// User's selection: attribute_name → chosen value string
const selectedAttributes = ref<Record<string, string>>({})
const quantity = ref(1)
const unitPriceInput = ref('0')
const selectedCurrency = ref<'UZS' | 'USD'>('UZS')
const selectedDiscountReasonId = ref<number | null>(null)
const variantSheetOpen = ref(false)
const writeoffSheetOpen = ref(false)
const writeoffLots = ref<Lot[]>([])
const selectedWriteoffKey = ref('')
const writeoffQuantity = ref(1)
const writeoffReason = ref(t('products.writeoffReasonDefault'))
const writeoffNegligence = ref(false)
const writeoffPreview = ref<WriteoffPreview | null>(null)
const writeoffLoading = ref(false)
const writeoffSubmitting = ref(false)
const writeoffError = ref('')
const isAdded = ref(false)
let addedTimer: ReturnType<typeof setTimeout> | null = null

// ===== Derived attribute groups =====

/** All unique attribute names across all variants */
const attributeNames = computed((): string[] => {
  const names = new Set<string>()
  variants.value.forEach((v) =>
    v.attribute_values.forEach((av) => names.add(av.attribute_name)),
  )
  return [...names]
})

/** All unique values for each attribute name */
const attributeOptions = computed((): Record<string, string[]> => {
  const result: Record<string, string[]> = {}
  attributeNames.value.forEach((name) => {
    const values = new Set<string>()
    variants.value.forEach((v) => {
      const match = v.attribute_values.find((av) => av.attribute_name === name)
      if (match) values.add(match.value)
    })
    result[name] = [...values]
  })
  return result
})

/** Find variant that exactly matches all currently selected attributes */
const matchedVariant = computed((): ProductVariant | null => {
  if (attributeNames.value.length === 0) return variants.value[0] ?? null

  const selectedKeys = Object.keys(selectedAttributes.value)
  if (selectedKeys.length !== attributeNames.value.length) return null

  return (
    variants.value.find((v) =>
      attributeNames.value.every((name) => {
        const av = v.attribute_values.find((a) => a.attribute_name === name)
        return av?.value === selectedAttributes.value[name]
      }),
    ) ?? null
  )
})

const activeVariants = computed(() =>
  variants.value.filter((variant) => variant.is_active),
)

/** Is a given attribute value selectable (leads to ≥1 active variant)? */
function isValueAvailable(attrName: string, value: string): boolean {
  // Build hypothetical selection with this value applied
  const hypothetical: Record<string, string> = {
    ...selectedAttributes.value,
    [attrName]: value,
  }

  return variants.value.some((v) => {
    if (!v.is_active) return false
    return Object.entries(hypothetical).every(([name, val]) => {
      const av = v.attribute_values.find((a) => a.attribute_name === name)
      return av?.value === val
    })
  })
}

function isValueSelected(attrName: string, value: string): boolean {
  return selectedAttributes.value[attrName] === value
}

function selectAttribute(attrName: string, value: string) {
  if (!isValueAvailable(attrName, value)) return
  selectedAttributes.value = { ...selectedAttributes.value, [attrName]: value }
}

// ===== Effective price & stock =====

const effectivePrice = computed((): string => {
  if (matchedVariant.value?.effective_price) return matchedVariant.value.effective_price
  if (product.value?.base_price) return product.value.base_price
  if (variants.value.length > 0 && variants.value[0]?.effective_price) return variants.value[0].effective_price
  return '0'
})

const pricingMode = computed(() => product.value?.pricing_mode ?? PricingMode.DEFAULT_EDITABLE)
const isPriceEditable = computed(() => pricingMode.value !== PricingMode.FIXED_LOCKED)
const askEachSale = computed(() => pricingMode.value === PricingMode.ASK_EACH_SALE)

const lineBasePrice = computed(() => {
  const parsed = Number.parseFloat(effectivePrice.value)
  return Number.isFinite(parsed) ? parsed : 0
})

const lineUnitPrice = computed(() => {
  if (!isPriceEditable.value) return lineBasePrice.value
  const parsed = Number.parseFloat(unitPriceInput.value)
  if (!Number.isFinite(parsed)) return 0
  if (selectedCurrency.value === 'UZS') return parsed
  const fx = Number.parseFloat(latestUsdRate.value)
  return Number.isFinite(fx) && fx > 0 ? parsed * fx : 0
})

const priceChanged = computed(() => (
  lineUnitPrice.value.toFixed(2) !== lineBasePrice.value.toFixed(2)
))

const lineTotal = computed(() => lineUnitPrice.value * quantity.value)
const operationUnitPrice = computed(() => {
  const parsed = Number.parseFloat(unitPriceInput.value)
  return Number.isFinite(parsed) ? parsed : 0
})
const fxSnapshot = computed(() => (
  selectedCurrency.value === 'USD' ? latestUsdRate.value : '1'
))
const currencyTrace = computed(() => {
  if (selectedCurrency.value !== 'USD') return ''
  const fx = Number.parseFloat(latestUsdRate.value)
  if (!Number.isFinite(fx) || fx <= 0) return latestUsdRateError.value || t('products.usdRateNotLoaded')
  return `${operationUnitPrice.value.toLocaleString(intlLocale(locale.value), { maximumFractionDigits: 2 })} $ · ${t('finance.rate')} ${fx.toLocaleString(intlLocale(locale.value), { maximumFractionDigits: 2 })}`
})

const activeLocationId = computed(() => sessionStore.currentSession?.location?.id ?? null)

const stockLocations = computed(() => (
  matchedVariant.value?.stock_by_location
  ?? product.value?.stock_by_location
  ?? []
))

const explicitShopStock = computed(() =>
  stockLocations.value
    .filter((entry) => String(entry.warehouse_kind).toUpperCase() === 'SHOP')
    .reduce((sum, entry) => sum + Number(entry.quantity || 0), 0),
)

const explicitStorageStock = computed(() =>
  stockLocations.value
    .filter((entry) => String(entry.warehouse_kind).toUpperCase() === 'STORAGE')
    .reduce((sum, entry) => sum + Number(entry.quantity || 0), 0),
)

const stockQuantity = computed((): number | null => {
  if (!activeLocationId.value) return null
  if (matchedVariant.value?.stock_at_location !== undefined && matchedVariant.value.stock_at_location !== null) {
    return matchedVariant.value.stock_at_location
  }
  if (matchedVariant.value?.stock_quantity !== undefined) {
    return matchedVariant.value.stock_quantity
  }
  return null
})

const totalStock = computed((): number => {
  if (Number.isFinite(matchedVariant.value?.total_stock_all_locations)) {
    return Number(matchedVariant.value?.total_stock_all_locations)
  }
  if (Number.isFinite(product.value?.total_stock_all_locations)) {
    return Number(product.value?.total_stock_all_locations)
  }
  if (Number.isFinite(product.value?.total_stock)) {
    return Number(product.value?.total_stock)
  }
  return stockQuantity.value ?? 0
})

const shopStock = computed(() => (
  activeLocationId.value ? (stockQuantity.value ?? 0) : explicitShopStock.value
))

const storageStock = computed(() => {
  if (explicitStorageStock.value > 0) return explicitStorageStock.value
  return Math.max(totalStock.value - shopStock.value, 0)
})

const stockStateLabel = computed(() => {
  if (!activeLocationId.value) {
    if (totalStock.value <= 0) return t('sales.outOfStock')
    if (shopStock.value > 0) return t('products.inShopAvailable')
    return t('products.inStockAvailable')
  }
  if (shopStock.value > 0) return t('products.availableInShop')
  if (storageStock.value > 0) return t('products.availableInWarehouse')
  return t('sales.outOfStock')
})

const canAddToCart = computed((): boolean => {
  if (!product.value) return false
  if (!sessionStore.currentSession?.location?.id) return false
  if (product.value.has_variants && !matchedVariant.value) return false
  if (stockQuantity.value !== null && stockQuantity.value <= 0) return false
  if (lineUnitPrice.value <= 0) return false
  if (askEachSale.value && !unitPriceInput.value.trim()) return false
  if (
    priceChanged.value
    && discountReasonOptions.value.length > 0
    && selectedDiscountReasonId.value === null
  ) return false
  return true
})

const canOpenSessionFromDetail = computed(() => (
  !activeLocationId.value && !!product.value && totalStock.value > 0
))

const categoryLabel = computed((): string | null => {
  if (!product.value) return null
  if (product.value.category && typeof product.value.category === 'object' && 'name' in product.value.category) {
    return product.value.category.name
  }
  const fallback = (product.value as Product & { category_name?: string | null }).category_name
  return fallback ?? null
})

const addButtonLabel = computed((): string => {
  if (!activeLocationId.value) {
    return totalStock.value > 0 ? t('products.openShiftForSale') : t('sales.outOfStock')
  }
  if (!product.value?.has_variants || matchedVariant.value) {
    return t('products.addToCartShort')
  }
  return t('products.selectVariant')
})

const canWriteOff = computed(() => authStore.isOwner && !!matchedVariant.value && totalStock.value > 0)

const writeoffOptions = computed(() => {
  const options: Array<{
    key: string
    lotId: number
    warehouseId: number
    label: string
    quantity: number
  }> = []
  for (const lot of writeoffLots.value) {
    for (const stock of lot.stocks ?? []) {
      if (stock.quantity_remaining <= 0) continue
      options.push({
        key: `${lot.id}:${stock.warehouse}`,
        lotId: lot.id,
        warehouseId: stock.warehouse,
        label: `${stock.warehouse_name} · ${t('products.batchFallback', { id: lot.id })}`,
        quantity: stock.quantity_remaining,
      })
    }
  }
  return options
})

const selectedWriteoffOption = computed(() => (
  writeoffOptions.value.find((option) => option.key === selectedWriteoffKey.value) ?? null
))

function formatStock(stock: number | undefined): string {
  if (!Number.isFinite(stock)) return `0 ${t('common.pieces')}`
  if ((stock ?? 0) <= 0) return t('sales.outOfStock')
  return `${stock} ${t('common.pieces')}`
}

function formatShortDate(value: string | null): string {
  if (!value) return t('common.notSpecified')
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return t('common.notSpecified')
  return new Intl.DateTimeFormat(intlLocale(locale.value), {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  }).format(date)
}

function openVariantSheet(): void {
  if (!product.value?.has_variants) return
  variantSheetOpen.value = true
}

function chooseVariantFromList(variant: ProductVariant): void {
  const nextSelection: Record<string, string> = {}
  variant.attribute_values.forEach((entry) => {
    nextSelection[entry.attribute_name] = entry.value
  })
  selectedAttributes.value = nextSelection
  variantSheetOpen.value = false
}

watch([matchedVariant, lineBasePrice, isPriceEditable], ([variant, basePrice, editable]) => {
  if (!variant) return
  if (!editable) {
    unitPriceInput.value = selectedCurrency.value === 'USD'
      ? convertFunctionalToSelected(basePrice)
      : basePrice.toFixed(2)
    return
  }
  unitPriceInput.value = selectedCurrency.value === 'USD'
    ? convertFunctionalToSelected(basePrice)
    : basePrice.toFixed(2)
}, { immediate: true })

watch(priceChanged, (changed) => {
  if (!changed) {
    selectedDiscountReasonId.value = null
    return
  }
  if (selectedDiscountReasonId.value !== null) return
  const defaultReason = discountReasonOptions.value[0] ?? null
  selectedDiscountReasonId.value = defaultReason?.value ?? null
})

// ===== Add to cart =====

function addToCart() {
  if (!canAddToCart.value || !product.value) return

  const variant =
    matchedVariant.value ?? (product.value.has_variants ? null : variants.value[0] ?? null)

  if (!variant) return

  cartStore.addItem({
    product_variant: variant,
    product_name: product.value.name,
    pricing_mode: pricingMode.value,
    lot_id: null,
    location_id: sessionStore.currentSession?.location?.id ?? null,
    available_stock: stockQuantity.value,
    quantity: quantity.value,
    operation_currency: selectedCurrency.value,
    operation_unit_price: operationUnitPrice.value.toFixed(2),
    fx_rate: fxSnapshot.value,
    unit_price: lineUnitPrice.value.toFixed(2),
    base_price: lineBasePrice.value.toFixed(2),
    price_changed: priceChanged.value,
    discount_reason_id: priceChanged.value ? selectedDiscountReasonId.value : null,
  })

  isAdded.value = true
  if (addedTimer !== null) clearTimeout(addedTimer)
  addedTimer = setTimeout(() => {
    isAdded.value = false
    addedTimer = null
    router.back()
  }, 900)
}

function convertFunctionalToSelected(functionalAmount: number): string {
  if (selectedCurrency.value === 'UZS') return functionalAmount.toFixed(2)
  const fx = Number.parseFloat(latestUsdRate.value)
  if (!Number.isFinite(fx) || fx <= 0) return '0'
  return (functionalAmount / fx).toFixed(2)
}

async function selectSaleCurrency(currency: 'UZS' | 'USD') {
  if (selectedCurrency.value === currency) return
  const currentFunctional = lineUnitPrice.value || lineBasePrice.value
  if (currency === 'USD' && !latestUsdRate.value) {
    try {
      await loadUsdRate()
    } catch {
      toast.error(latestUsdRateError.value || t('products.usdRateMissing'))
      return
    }
  }
  selectedCurrency.value = currency
  unitPriceInput.value = convertFunctionalToSelected(currentFunctional)
}

function handlePrimaryAction() {
  if (canOpenSessionFromDetail.value) {
    router.push({ name: 'sales-catalog', query: { openSession: '1' } })
    return
  }
  addToCart()
}

function goBack() {
  router.back()
}

function goToTransfers() {
  router.push({ name: 'stock-transfers' })
}

async function refreshWriteoffPreview(): Promise<void> {
  const option = selectedWriteoffOption.value
  if (!option) return
  writeoffLoading.value = true
  writeoffError.value = ''
  try {
    writeoffPreview.value = await fetchWriteoffPreview({
      lot_id: option.lotId,
      warehouse_id: option.warehouseId,
      quantity: writeoffQuantity.value,
      reason: writeoffReason.value,
      negligence: writeoffNegligence.value,
    })
  } catch (error) {
    writeoffError.value = error instanceof Error ? error.message : t('products.writeoffCalcFailed')
  } finally {
    writeoffLoading.value = false
  }
}

async function openWriteoffSheet(): Promise<void> {
  if (!matchedVariant.value || !canWriteOff.value) return
  writeoffSheetOpen.value = true
  writeoffLoading.value = true
  writeoffError.value = ''
  try {
    const response = await fetchLots({
      product_variant: matchedVariant.value.id,
      active: true,
    })
    writeoffLots.value = response.results
    selectedWriteoffKey.value = writeoffOptions.value[0]?.key ?? ''
    writeoffQuantity.value = 1
    await refreshWriteoffPreview()
  } catch (error) {
    writeoffError.value = error instanceof Error ? error.message : t('products.writeoffLotsLoadFailed')
  } finally {
    writeoffLoading.value = false
  }
}

function closeWriteoffSheet(): void {
  writeoffSheetOpen.value = false
  writeoffPreview.value = null
  writeoffError.value = ''
}

async function updateWriteoffQuantity(value: string | number): Promise<void> {
  const option = selectedWriteoffOption.value
  const max = option?.quantity ?? 1
  const parsed = Number(value)
  writeoffQuantity.value = Number.isFinite(parsed)
    ? Math.max(1, Math.min(max, Math.floor(parsed)))
    : 1
  await refreshWriteoffPreview()
}

async function submitWriteoff(): Promise<void> {
  const option = selectedWriteoffOption.value
  if (!option || writeoffSubmitting.value) return
  writeoffSubmitting.value = true
  writeoffError.value = ''
  try {
    await createWriteoff({
      lot_id: option.lotId,
      warehouse_id: option.warehouseId,
      quantity: writeoffQuantity.value,
      reason: writeoffReason.value,
      negligence: writeoffNegligence.value,
    })
    toast.success(t('products.writeoffDone'))
    closeWriteoffSheet()
    await loadProduct()
  } catch (error) {
    writeoffError.value = error instanceof Error ? error.message : t('products.writeoffFailed')
  } finally {
    writeoffSubmitting.value = false
  }
}

// ===== Load data =====

async function loadProduct() {
  const id = Number(route.params.id)
  if (Number.isNaN(id)) {
    loadError.value = t('products.invalidProductId')
    isLoading.value = false
    return
  }

  isLoading.value = true
  loadError.value = null

  try {
    const locationId = sessionStore.currentSession?.location?.id
    const [productData, variantsData, supplierData, discountReasons] = await Promise.all([
      fetchProduct(id, {
        location_id: locationId,
      }),
      fetchProductVariants(id, {
        location_id: locationId,
      }),
      fetchProductSuppliers(id),
      fetchDiscountReasons(),
    ])

    product.value = productData
    variants.value = variantsData
    supplierHistory.value = supplierData
    discountReasonOptions.value = discountReasons
      .filter((reason) => reason.is_active !== false)
      .sort((left, right) => Number(right.is_default) - Number(left.is_default))
      .map((reason) => ({
        value: reason.id,
        label: reason.name,
      }))

    // Pre-select first available value for each attribute
    if (productData.has_variants) {
      const firstVariant = variantsData.find((v) => v.is_active) ?? variantsData[0]
      if (firstVariant) {
        const preselect: Record<string, string> = {}
        firstVariant.attribute_values.forEach((av) => {
          preselect[av.attribute_name] = av.value
        })
        selectedAttributes.value = preselect
      }
    }
  } catch {
    loadError.value = t('products.productLoadFailed')
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadProduct()
})
</script>

<template>
  <div class="detail-page">
    <PageChrome
      class="desktop-page-chrome"
      :title="product?.name ?? t('products.product')"
    >
      <template #primary>
        <button class="back-btn" :aria-label="t('common.back')" @click="goBack">
          <ArrowLeft :size="20" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <!-- ===== Header ===== -->
    <header class="detail-header">
      <button class="back-btn" :aria-label="t('common.back')" @click="goBack">
        <ArrowLeft :size="20" :stroke-width="2" />
      </button>
      <h1 class="header-title">
        {{ product?.name ?? t('products.product') }}
      </h1>
      <div class="header-spacer" aria-hidden="true" />
    </header>

    <PageContainer class="detail-container" size="wide" :padded="false">
    <!-- ===== Loading state ===== -->
    <div v-if="isLoading" class="detail-loading" aria-busy="true" :aria-label="t('products.loadingProduct')">
      <div class="skeleton-hero" />
      <div class="skeleton-body">
        <div class="skeleton-line skeleton-line--title" />
        <div class="skeleton-line skeleton-line--meta" />
        <div class="skeleton-chips-group">
          <div v-for="n in 4" :key="n" class="skeleton-chip" />
        </div>
        <div class="skeleton-line skeleton-line--price" />
        <div class="skeleton-line skeleton-line--btn" />
      </div>
    </div>

    <!-- ===== Error state ===== -->
    <div v-else-if="loadError" class="detail-error" role="alert">
      <Package :size="48" :stroke-width="1.25" class="error-icon" />
      <p class="error-message">{{ loadError }}</p>
      <button class="error-retry-btn" @click="loadProduct">
        {{ t('products.retryProduct') }}
      </button>
    </div>

    <!-- ===== Product content ===== -->
    <template v-else-if="product">
      <div class="detail-body">

        <!-- Product image / hero area -->
        <div class="product-hero">
          <div class="product-hero-inner">
            <img
              v-if="product.photo_url"
              :src="product.photo_url"
              :alt="product.name"
              class="hero-photo"
              loading="lazy"
            >
            <Package v-else :size="56" :stroke-width="1" class="hero-icon" />
          </div>
        </div>

        <!-- Info section -->
        <div class="product-info-section">

          <!-- Name -->
          <h2 class="product-name">{{ product.name }}</h2>

          <!-- Category + SKU row -->
          <div class="product-meta">
            <span v-if="categoryLabel" class="meta-category">
              {{ categoryLabel }}
            </span>
            <span
              v-if="categoryLabel && matchedVariant?.sku"
              class="meta-separator"
              aria-hidden="true"
            >·</span>
            <span v-if="matchedVariant?.sku" class="meta-sku">
              {{ matchedVariant.sku }}
            </span>
          </div>

          <!-- Description -->
          <p v-if="product.description" class="product-description">
            {{ product.description }}
          </p>

        </div>

        <!-- ===== Variant selection ===== -->
        <template v-if="product.has_variants && attributeNames.length > 0">
          <div class="variants-section">
            <div
              v-for="attrName in attributeNames"
              :key="attrName"
              class="attr-group"
            >
              <p class="attr-name">{{ attrName }}</p>
              <div class="attr-chips" role="group" :aria-label="`${t('common.select')}: ${attrName}`">
                <button
                  v-for="value in attributeOptions[attrName]"
                  :key="value"
                  class="attr-chip"
                  :class="{
                    'attr-chip--selected': isValueSelected(attrName, value),
                    'attr-chip--disabled': !isValueAvailable(attrName, value),
                  }"
                  :aria-pressed="isValueSelected(attrName, value)"
                  :disabled="!isValueAvailable(attrName, value)"
                  @click="selectAttribute(attrName, value)"
                >
                  {{ value }}
                </button>
              </div>
            </div>

            <button
              type="button"
              class="variants-list-btn"
              @click="openVariantSheet"
            >
              <ListTree :size="16" :stroke-width="2" />
              {{ t('products.variantsList') }}
            </button>
          </div>
        </template>

        <!-- ===== Price + stock ===== -->
        <div class="price-stock-section">
          <div class="price-row">
            <span class="price-label">{{ t('products.price') }}</span>
            <PriceDisplay :amount="lineBasePrice.toFixed(2)" size="lg" />
          </div>

          <div class="mode-row">
            <span class="price-label">{{ t('products.mode') }}</span>
            <span class="mode-badge">
              {{
                pricingMode === PricingMode.FIXED_LOCKED
                  ? t('products.pricingFixed')
                  : pricingMode === PricingMode.ASK_EACH_SALE
                    ? t('products.pricingAskEachSale')
                    : t('products.pricingEditable')
              }}
            </span>
          </div>

          <div class="currency-row" :aria-label="t('products.saleCurrency')">
            <span class="price-label">{{ t('products.currency') }}</span>
            <div class="currency-toggle">
              <button
                type="button"
                :class="{ active: selectedCurrency === 'UZS' }"
                @click="selectSaleCurrency('UZS')"
              >
                UZS
              </button>
              <button
                type="button"
                :class="{ active: selectedCurrency === 'USD' }"
                @click="selectSaleCurrency('USD')"
              >
                USD
              </button>
            </div>
          </div>

          <div v-if="isPriceEditable" class="price-input-wrap">
            <BaseInput
              v-model="unitPriceInput"
              type="number"
              :label="selectedCurrency === 'USD' ? t('products.salePriceUsd') : t('products.salePriceUzs')"
              placeholder="0"
            />
            <p v-if="currencyTrace" class="currency-trace">{{ currencyTrace }}</p>
          </div>

          <div v-if="priceChanged" class="discount-reason-wrap">
            <BaseSelect
              v-model="selectedDiscountReasonId"
              :options="discountReasonOptions"
              :title="t('products.discountReason')"
              :placeholder="t('products.chooseDiscountReason')"
            />
          </div>

          <div class="stock-breakdown" :aria-label="t('products.stocks')">
            <div class="stock-breakdown__header">
              <span class="stock-label">{{ t('products.stocks') }}</span>
              <span
                class="stock-state"
                :class="{ 'stock-state--warning': shopStock <= 0 && totalStock > 0, 'stock-state--empty': totalStock <= 0 }"
              >
                {{ stockStateLabel }}
              </span>
            </div>
            <div class="stock-breakdown__grid">
              <div class="stock-metric">
                <span>{{ t('products.totalStock') }}</span>
                <strong>{{ formatStock(totalStock) }}</strong>
              </div>
              <div class="stock-metric">
                <span>{{ t('products.inShop') }}</span>
                <strong :class="{ 'stock-value--empty': shopStock <= 0 }">{{ formatStock(shopStock) }}</strong>
              </div>
              <div class="stock-metric">
                <span>{{ t('products.inWarehouse') }}</span>
                <strong>{{ formatStock(storageStock) }}</strong>
              </div>
            </div>
            <button
              v-if="shopStock <= 0 && storageStock > 0"
              class="stock-transfer-btn"
              type="button"
              @click="goToTransfers"
            >
              <ArrowRightLeft :size="15" :stroke-width="2" />
              {{ t('products.moveToShop') }}
            </button>
            <button
              v-if="canWriteOff"
              class="stock-writeoff-btn"
              type="button"
              @click="openWriteoffSheet"
            >
              {{ t('products.writeoffProduct') }}
            </button>
          </div>
        </div>

        <section v-if="supplierHistory.length > 0" class="supplier-history-section">
          <div class="supplier-history-head">
            <div>
              <span>{{ t('products.supplierHistoryEyebrow') }}</span>
              <h3>{{ t('products.supplierHistoryTitle') }}</h3>
            </div>
            <Truck :size="18" :stroke-width="1.75" />
          </div>
          <div class="supplier-history-list">
            <article
              v-for="entry in supplierHistory.slice(0, 3)"
              :key="`${entry.supplier_id}-${entry.product_variant_id}`"
              class="supplier-history-row"
            >
              <div>
                <strong>{{ entry.supplier_name }}</strong>
                <small>{{ t('products.lastReceiptDate', { date: formatShortDate(entry.last_received_at) }) }}</small>
              </div>
              <div class="supplier-history-side">
                <b>{{ entry.last_unit_price }} {{ entry.last_currency }}</b>
                <small>{{ t('products.receivedQtyShort', { count: entry.total_received_quantity }) }}</small>
              </div>
            </article>
          </div>
        </section>

        <!-- ===== Quantity + add to cart ===== -->
        <div class="cart-section">
          <div class="qty-row">
            <span class="qty-label">{{ t('products.quantity') }}</span>
            <QuantityControl
              v-model="quantity"
              :min="1"
              :max="stockQuantity ?? 9999"
            />
          </div>

          <button
            class="add-to-cart-btn"
            :class="{
              'add-to-cart-btn--added': isAdded,
              'add-to-cart-btn--disabled': !canAddToCart && !canOpenSessionFromDetail,
            }"
            :disabled="!canAddToCart && !canOpenSessionFromDetail"
            :aria-label="addButtonLabel"
            @click="handlePrimaryAction"
          >
            <Transition name="btn-icon" mode="out-in">
              <Check v-if="isAdded" :key="'check'" :size="20" :stroke-width="2.5" />
              <ShoppingCart v-else :key="'cart'" :size="20" :stroke-width="1.75" />
            </Transition>
            <span class="btn-label">
              <Transition name="btn-text" mode="out-in">
                <span v-if="isAdded" key="added">{{ t('products.addedBang') }}</span>
                <span v-else-if="!canAddToCart && product.has_variants && !matchedVariant" key="select">
                  {{ t('products.selectVariant') }}
                </span>
                <span v-else-if="canOpenSessionFromDetail" key="session">
                  {{ addButtonLabel }}
                </span>
                <span v-else key="price">
                  {{ addButtonLabel }}&nbsp;—&nbsp;<PriceDisplay
                    :amount="lineTotal.toFixed(2)"
                    size="md"
                    class="btn-price"
                  />
                </span>
              </Transition>
            </span>
          </button>
        </div>

      </div>
    </template>
    </PageContainer>

    <ResponsiveOverlay
      :open="variantSheetOpen"
      :title="t('products.variantsTitle')"
      @close="variantSheetOpen = false"
    >
      <div class="variant-sheet-list">
        <button
          v-for="variant in activeVariants"
          :key="variant.id"
          class="variant-sheet-item"
          :class="{ 'variant-sheet-item--active': matchedVariant?.id === variant.id }"
          type="button"
          @click="chooseVariantFromList(variant)"
        >
          <div class="variant-sheet-main">
            <span class="variant-sheet-name">
              {{
                variant.attribute_values.length > 0
                  ? variant.attribute_values.map((entry) => `${entry.attribute_name}: ${entry.value}`).join(' · ')
                  : `SKU ${variant.display_sku || variant.sku || variant.id}`
              }}
            </span>
            <span class="variant-sheet-stock">
              {{ formatStock(variant.stock_quantity) }}
            </span>
          </div>
          <PriceDisplay :amount="variant.effective_price" size="sm" />
        </button>
      </div>
    </ResponsiveOverlay>

    <ResponsiveOverlay
      :open="writeoffSheetOpen"
      :title="t('products.writeoffTitle')"
      @close="closeWriteoffSheet"
    >
      <div class="writeoff-sheet">
        <label class="writeoff-field">
          <span>{{ t('products.lotAndLocation') }}</span>
          <select
            v-model="selectedWriteoffKey"
            class="writeoff-select"
            @change="refreshWriteoffPreview"
          >
            <option
              v-for="option in writeoffOptions"
              :key="option.key"
              :value="option.key"
            >
              {{ option.label }} · {{ t('products.availableQty', { count: option.quantity }) }}
            </option>
          </select>
        </label>

        <label class="writeoff-field">
          <span>{{ t('common.quantity') }}</span>
          <input
            class="writeoff-input"
            type="number"
            min="1"
            :max="selectedWriteoffOption?.quantity || 1"
            :value="writeoffQuantity"
            @input="updateWriteoffQuantity(($event.target as HTMLInputElement).value)"
          >
        </label>

        <label class="writeoff-field">
          <span>{{ t('common.reason') }}</span>
          <input
            v-model="writeoffReason"
            class="writeoff-input"
            type="text"
            :placeholder="t('products.writeoffReasonPlaceholder')"
          >
        </label>

        <label class="writeoff-check">
          <input
            v-model="writeoffNegligence"
            type="checkbox"
            @change="refreshWriteoffPreview"
          >
          <span>{{ t('products.negligenceLossBusiness') }}</span>
        </label>

        <div class="writeoff-effect">
          <div>
            <span>{{ t('products.lossAmount') }}</span>
            <strong>{{ formatPrice(writeoffPreview?.loss_amount || 0) }}</strong>
          </div>
          <div>
            <span>{{ t('common.available') }}</span>
            <strong>{{ selectedWriteoffOption?.quantity || 0 }} {{ t('common.pieces') }}</strong>
          </div>
        </div>

        <p v-if="writeoffError" class="writeoff-error">{{ writeoffError }}</p>

        <button
          class="writeoff-confirm"
          :disabled="writeoffSubmitting || writeoffLoading || !selectedWriteoffOption"
          @click="submitWriteoff"
        >
          <span v-if="writeoffSubmitting">{{ t('products.writeoffSubmitting') }}</span>
          <span v-else>{{ t('products.confirmWriteoff') }}</span>
        </button>
      </div>
    </ResponsiveOverlay>

  </div>
</template>

<style scoped>
/* ===== Page shell ===== */
.detail-page {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-4));
}

.desktop-page-chrome {
  display: none;
}

/* ===== Header ===== */
.detail-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--header-height);
  padding: 0 var(--space-4);
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
}

.back-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  flex-shrink: 0;
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}

.back-btn:hover {
  background: var(--color-bg-secondary);
}

.back-btn:active {
  transform: scale(0.88);
  background: var(--color-bg-sunken);
}

.header-title {
  flex: 1;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-spacer {
  width: 44px;
  flex-shrink: 0;
}

/* ===== Loading skeleton ===== */
.detail-loading {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}

.skeleton-hero {
  width: 100%;
  padding-top: 56.25%; /* 16:9 */
  background: var(--color-bg-secondary);
}

.skeleton-body {
  padding: var(--space-5) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.skeleton-line {
  background: var(--color-bg-sunken);
  border-radius: var(--radius-sm);
}

.skeleton-line--title  { height: 1.5rem;  width: 70%; }
.skeleton-line--meta   { height: 0.875rem; width: 45%; }
.skeleton-line--price  { height: 1.75rem;  width: 40%; }
.skeleton-line--btn    { height: 52px;     width: 100%; border-radius: var(--radius-lg); }

.skeleton-chips-group {
  display: flex;
  gap: var(--space-2);
}

.skeleton-chip {
  height: 36px;
  width: 64px;
  background: var(--color-bg-sunken);
  border-radius: var(--radius-full);
}

/* ===== Error state ===== */
.detail-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.error-icon {
  color: var(--color-text-tertiary);
}

.error-message {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  max-width: 300px;
}

.error-retry-btn {
  height: 44px;
  padding: 0 var(--space-6);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out);
}

.error-retry-btn:hover { background: var(--color-brand-600); }
.error-retry-btn:active { transform: scale(0.97); }

/* ===== Product body ===== */
.detail-body {
  display: flex;
  flex-direction: column;
}

/* ===== Hero image area — 16:9 ===== */
.product-hero {
  position: relative;
  width: 100%;
  padding-top: 56.25%;
  background: var(--color-bg-secondary);
  overflow: hidden;
  flex-shrink: 0;
}

.product-hero-inner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    160deg,
    var(--color-brand-50) 0%,
    var(--color-bg-secondary) 100%
  );
}

.hero-icon {
  color: var(--color-brand-200);
}

.hero-photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ===== Info section ===== */
.product-info-section {
  padding: var(--space-5) var(--space-4) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.product-name {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.product-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.meta-category {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-brand-500);
  background: var(--color-brand-50);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
}

.meta-separator {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.meta-sku {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.product-description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: var(--leading-relaxed);
  margin-top: var(--space-1);
}

/* ===== Variant chips ===== */
.variants-section {
  padding: 0 var(--space-4) var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-4);
}

.attr-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.attr-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.attr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.attr-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  min-width: 44px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  border: 1.5px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring),
    opacity var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

.attr-chip:active:not(:disabled) {
  transform: scale(0.93);
}

.attr-chip--selected {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.attr-chip--selected:active {
  background: var(--color-brand-600);
  border-color: var(--color-brand-600);
}

.attr-chip--disabled {
  opacity: 0.35;
  cursor: not-allowed;
  text-decoration: line-through;
}

.variants-list-btn {
  width: 100%;
  min-height: 42px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

/* ===== Price + stock ===== */
.price-stock-section {
  margin: 0 var(--space-4);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.price-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mode-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.currency-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.currency-toggle {
  display: inline-flex;
  padding: 3px;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
}

.currency-toggle button {
  min-width: 56px;
  height: 30px;
  padding: 0 var(--space-2);
  border-radius: calc(var(--radius-md) - 3px);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.currency-toggle button.active {
  background: var(--color-bg-elevated);
  color: var(--color-brand-700);
  box-shadow: var(--shadow-sm);
}

.price-label,
.stock-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}

.price-row :deep(.price) {
  color: var(--color-brand-500);
}

.mode-badge {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.price-input-wrap {
  display: grid;
  gap: var(--space-2);
}

.currency-trace {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.discount-reason-wrap {
  display: grid;
  gap: var(--space-2);
}

.stock-value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-success);
}

.stock-value--empty {
  color: var(--color-error);
}

.stock-breakdown {
  display: grid;
  gap: var(--space-3);
}

.stock-breakdown__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.stock-state {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.stock-state--warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.stock-state--empty {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.stock-breakdown__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.stock-metric {
  min-width: 0;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  display: grid;
  gap: 2px;
}

.stock-metric span {
  color: var(--color-text-secondary);
  font-size: 11px;
}

.stock-metric strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.stock-transfer-btn,
.stock-writeoff-btn {
  min-height: 38px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.stock-transfer-btn {
  color: var(--color-brand-700);
}

.stock-writeoff-btn {
  color: var(--color-error);
}

.writeoff-sheet {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.writeoff-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.writeoff-select,
.writeoff-input {
  width: 100%;
  min-height: 44px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.writeoff-select {
  padding: 0 var(--space-3);
}

.writeoff-input {
  padding: 0 var(--space-3);
}

.writeoff-check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.writeoff-check input {
  width: 18px;
  height: 18px;
  accent-color: var(--color-brand-600);
}

.writeoff-effect {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.writeoff-effect > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.writeoff-effect span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.writeoff-effect strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-align: right;
}

.writeoff-error {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.writeoff-confirm {
  width: 100%;
  min-height: 48px;
  border-radius: var(--radius-lg);
  background: var(--color-error);
  color: white;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.writeoff-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.supplier-history-section {
  display: grid;
  gap: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
}

.supplier-history-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.supplier-history-head span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.supplier-history-head h3 {
  margin-top: 3px;
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.supplier-history-head svg {
  color: var(--color-brand-600);
}

.supplier-history-list {
  display: grid;
  gap: var(--space-2);
}

.supplier-history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 54px;
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-2);
}

.supplier-history-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.supplier-history-row > div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.supplier-history-row strong,
.supplier-history-row b {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.supplier-history-row small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.supplier-history-side {
  justify-items: end;
  text-align: right;
  flex: 0 0 auto;
}

/* ===== Cart section ===== */
.cart-section {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.qty-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qty-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

/* ===== Add-to-cart button ===== */
.add-to-cart-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  height: 52px;
  padding: 0 var(--space-5);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  box-shadow: var(--shadow-float);
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring),
    box-shadow var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.add-to-cart-btn:hover {
  background: var(--color-brand-600);
}

.add-to-cart-btn:active {
  transform: scale(0.97);
  box-shadow: none;
}

.add-to-cart-btn--added {
  background: var(--color-success);
  box-shadow: 0 6px 20px rgba(45, 159, 111, 0.3);
}

.add-to-cart-btn--disabled {
  background: var(--color-bg-sunken);
  color: var(--color-text-tertiary);
  box-shadow: none;
  cursor: not-allowed;
}

.add-to-cart-btn--disabled:hover {
  background: var(--color-bg-sunken);
}

.btn-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  overflow: hidden;
  white-space: nowrap;
}

.add-to-cart-btn :deep(.btn-price) {
  color: inherit;
  font-size: inherit;
  font-weight: inherit;
}

.variant-sheet-list {
  display: grid;
  gap: var(--space-2);
}

.variant-sheet-item {
  width: 100%;
  min-height: 54px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  padding: var(--space-2) var(--space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.variant-sheet-item--active {
  border-color: var(--color-brand-300);
  background: var(--color-brand-50);
}

.variant-sheet-main {
  min-width: 0;
  display: grid;
  gap: 2px;
  text-align: left;
}

.variant-sheet-name {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: normal;
}

.variant-sheet-stock {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

/* ===== Button icon/text transitions ===== */
.btn-icon-enter-active,
.btn-icon-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
}
.btn-icon-enter-from { opacity: 0; transform: scale(0.5) rotate(-30deg); }
.btn-icon-leave-to   { opacity: 0; transform: scale(0.5) rotate(30deg); }

.btn-text-enter-active,
.btn-text-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out);
}
.btn-text-enter-from,
.btn-text-leave-to { opacity: 0; }

/* ===== Responsive ===== */
@media (min-width: 768px) {
  .detail-page {
    min-height: 100%;
    padding-bottom: var(--space-6);
  }

  .desktop-page-chrome {
    display: block;
  }

  .detail-header {
    display: none;
  }

  .detail-container {
    padding: var(--space-6) clamp(var(--space-5), 3vw, var(--space-8));
  }

  .detail-body {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 400px);
    grid-template-rows: auto auto auto auto auto;
    align-items: start;
    gap: 0 clamp(var(--space-5), 3vw, var(--space-8));
  }

  .product-hero {
    grid-column: 1;
    grid-row: 1 / span 4;
    height: min(420px, 52vw);
    padding-top: 0;
    border-radius: var(--radius-xl);
  }

  .product-info-section {
    grid-column: 2;
    grid-row: 1;
    padding: 0 0 var(--space-4);
  }

  .variants-section {
    grid-column: 2;
    grid-row: 2;
    padding: var(--space-4) 0;
  }

  .price-stock-section {
    grid-column: 2;
    grid-row: 3;
    margin: 0;
  }

  .cart-section {
    grid-column: 2;
    grid-row: 4;
    padding: var(--space-4) 0 0;
  }

  .supplier-history-section {
    grid-column: 1;
    grid-row: 5;
    margin-top: var(--space-5);
  }
}

@media (min-width: 1024px) {
  .detail-body {
    grid-template-columns: minmax(0, 1fr) minmax(380px, 440px);
  }

  .product-hero {
    height: min(520px, 48vw);
  }
}

/* ===== Reduced motion ===== */
@media (prefers-reduced-motion: reduce) {
  .add-to-cart-btn,
  .attr-chip,
  .back-btn,
  .btn-icon-enter-active,
  .btn-icon-leave-active,
  .btn-text-enter-active,
  .btn-text-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
