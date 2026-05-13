import { computed, onBeforeUnmount, ref, type Ref } from 'vue'
import { createSupplier } from '@/api/suppliers'
import { createProduct, fetchProductVariants, fetchVariantsPaginated } from '@/api/catalog'
import { PricingMode } from '@/types/enums'
import type { Product, ProductVariant, Supplier } from '@/types/models'
import type { ProcurementDetail } from '@/api/partnerships'
import type { ExpenseRow, LineRow } from '@/modules/intake/types'

interface ToastLike {
  success: (message: string) => void
  error: (message: string) => void
}

interface UseIntakeQuickActionsOptions {
  allVariants: Ref<ProductVariant[]>
  lines: Ref<LineRow[]>
  suppliers: Ref<Supplier[]>
  selectedSupplierId: Ref<number | null>
  updateLine: (rowId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null) => void
  buildEmptyLine: () => LineRow
  t: (key: string, params?: Record<string, unknown>) => string
  toast: ToastLike
}

export function useIntakeQuickActions({
  allVariants,
  lines,
  suppliers,
  selectedSupplierId,
  updateLine,
  buildEmptyLine,
  t,
  toast,
}: UseIntakeQuickActionsOptions) {
  const variantSheetOpen = ref(false)
  const activeLineId = ref<string | null>(null)
  const variantSearch = ref('')
  const variantSearchCategory = ref<number | null>(null)

  const quickProductSheetOpen = ref(false)
  const quickProductTargetLineId = ref<string | null>(null)
  const quickProductName = ref('')
  const quickProductCategoryId = ref<number | null>(null)
  const quickProductBasePrice = ref('')
  const quickProductError = ref<string | null>(null)
  const isCreatingQuickProduct = ref(false)

  const quickSupplierSheetOpen = ref(false)
  const quickSupplierName = ref('')
  const quickSupplierPhone = ref('')
  const quickSupplierEmail = ref('')
  const quickSupplierError = ref<string | null>(null)
  const isCreatingQuickSupplier = ref(false)
  let variantsAbortController: AbortController | null = null

  async function loadAllVariants(): Promise<void> {
    variantsAbortController?.abort()
    const controller = new AbortController()
    variantsAbortController = controller
    const loaded: ProductVariant[] = []
    let page = 1
    try {
      while (true) {
        const response = await fetchVariantsPaginated({
          active: true,
          page,
          page_size: 100,
          ...(selectedSupplierId.value ? { supplier_id: selectedSupplierId.value, order: 'preferred' as const } : {}),
        }, controller.signal)
        loaded.push(...response.results)
        if (!response.next) break
        page += 1
      }
      if (variantsAbortController === controller) {
        allVariants.value = loaded
      }
    } catch (error: unknown) {
      const requestError = error as { code?: string; name?: string }
      if (requestError.code === 'ERR_CANCELED' || requestError.name === 'CanceledError') return
      throw error
    } finally {
      if (variantsAbortController === controller) {
        variantsAbortController = null
      }
    }
  }

  async function openVariantPicker(lineId: string): Promise<void> {
    activeLineId.value = lineId
    variantSheetOpen.value = true
    if (allVariants.value.length === 0) {
      await loadAllVariants()
    }
  }

  function closeVariantPicker(): void {
    variantSheetOpen.value = false
    activeLineId.value = null
  }

  function resetQuickProductForm(): void {
    quickProductName.value = ''
    quickProductCategoryId.value = null
    quickProductBasePrice.value = ''
    quickProductError.value = null
  }

  function openQuickProductCreator(lineId: string | null = null): void {
    quickProductTargetLineId.value = lineId
    quickProductSheetOpen.value = true
    variantSheetOpen.value = false
    quickProductError.value = ''
  }

  function closeQuickProductCreator(): void {
    quickProductSheetOpen.value = false
    quickProductTargetLineId.value = null
    resetQuickProductForm()
  }

  function resetQuickSupplierForm(): void {
    quickSupplierName.value = ''
    quickSupplierPhone.value = ''
    quickSupplierEmail.value = ''
    quickSupplierError.value = null
  }

  function openQuickSupplierCreator(): void {
    resetQuickSupplierForm()
    quickSupplierSheetOpen.value = true
  }

  function closeQuickSupplierCreator(): void {
    quickSupplierSheetOpen.value = false
  }

  function getProductCategoryId(product: Product): number | null {
    if (typeof product.category === 'number') return product.category
    return product.category?.id ?? null
  }

  function normalizeCreatedVariant(product: Product, variant: ProductVariant): ProductVariant {
    return {
      ...variant,
      product_name: variant.product_name ?? product.name,
      category_id: variant.category_id ?? getProductCategoryId(product),
      category_name: variant.category_name ?? product.category_name ?? product.category?.name ?? null,
    }
  }

  function placeholderVariantFromProcurementItem(item: ProcurementDetail['items'][number]): ProductVariant {
    return {
      id: item.product_variant,
      created_at: '',
      updated_at: '',
      product_name: item.product_variant_name,
      sku: item.product_variant_name || `VAR-${item.product_variant}`,
      display_sku: item.product_variant_name || `VAR-${item.product_variant}`,
      price: item.unit_purchase_price,
      effective_price: item.unit_purchase_price,
      is_active: true,
      attribute_values: [],
    }
  }

  function defaultLineCost(variant: ProductVariant, product?: Product): string {
    return String(variant.price ?? variant.effective_price ?? product?.base_price ?? '')
  }

  function normalizeTextInput(value: unknown): string {
    return String(value ?? '').trim()
  }

  async function createQuickProduct(): Promise<void> {
    const name = normalizeTextInput(quickProductName.value)
    if (!name) {
      quickProductError.value = t('products.nameRequired')
      return
    }

    const basePrice = normalizeTextInput(quickProductBasePrice.value)
    isCreatingQuickProduct.value = true
    quickProductError.value = null
    try {
      const product = await createProduct({
        name,
        category_id: quickProductCategoryId.value,
        pricing_mode: PricingMode.DEFAULT_EDITABLE,
        base_price: basePrice || null,
      })

      const variants = product.variants?.length > 0
        ? product.variants
        : await fetchProductVariants(product.id)
      const createdVariant = variants.find((variant) => variant.is_active !== false) ?? variants[0]
      if (!createdVariant) {
        quickProductError.value = t('procurements.create.productCreatedNoVariant')
        return
      }

      const variant = normalizeCreatedVariant(product, createdVariant)
      allVariants.value = [
        variant,
        ...allVariants.value.filter((item) => item.id !== variant.id),
      ]

      const targetLineId = quickProductTargetLineId.value
        ?? lines.value.find((line) => !line.variant)?.id
        ?? null
      const cost = defaultLineCost(variant, product)
      if (targetLineId) {
        updateLine(targetLineId, 'variant', variant)
        const targetLine = lines.value.find((line) => line.id === targetLineId)
        if (targetLine && !targetLine.cost_per_unit && cost) {
          updateLine(targetLineId, 'cost_per_unit', cost)
        }
      } else {
        lines.value = [
          ...lines.value,
          {
            ...buildEmptyLine(),
            variant,
            cost_per_unit: cost,
          },
        ]
      }

      toast.success(t('procurements.create.productCreatedAdded'))
      closeQuickProductCreator()
    } catch (error: unknown) {
      const apiError = error as { response?: { data?: { detail?: string; name?: string[] } } }
      quickProductError.value = apiError.response?.data?.detail
        ?? apiError.response?.data?.name?.[0]
        ?? t('products.createFailed')
    } finally {
      isCreatingQuickProduct.value = false
    }
  }

  async function createQuickSupplier(): Promise<void> {
    const name = normalizeTextInput(quickSupplierName.value)
    if (!name) {
      quickSupplierError.value = t('procurements.create.supplierNameRequired')
      return
    }

    isCreatingQuickSupplier.value = true
    quickSupplierError.value = null
    try {
      const supplier = await createSupplier({
        name,
        phone: normalizeTextInput(quickSupplierPhone.value) || undefined,
        email: normalizeTextInput(quickSupplierEmail.value) || undefined,
      })
      suppliers.value = [supplier, ...suppliers.value.filter((item) => item.id !== supplier.id)]
      selectedSupplierId.value = supplier.id
      toast.success(t('procurements.create.supplierCreated'))
      closeQuickSupplierCreator()
    } catch (error: unknown) {
      const apiError = error as { response?: { data?: { detail?: string; name?: string[] } } }
      quickSupplierError.value = apiError.response?.data?.detail
        ?? apiError.response?.data?.name?.[0]
        ?? t('procurements.create.supplierCreateFailed')
    } finally {
      isCreatingQuickSupplier.value = false
    }
  }

  const filteredVariants = computed(() => {
    const query = variantSearch.value.trim().toLowerCase()
    return allVariants.value.filter((variant) => {
      if (variantSearchCategory.value !== null && variant.category_id !== variantSearchCategory.value) {
        return false
      }
      if (!query) return true
      const searchable = [variant.product_name ?? '', variant.display_sku ?? '', variant.sku ?? ''].join(' ').toLowerCase()
      return searchable.includes(query)
    })
  })

  function selectVariant(variant: ProductVariant): void {
    if (!activeLineId.value) return

    const duplicateExists = lines.value.some((line) => {
      if (line.id === activeLineId.value || !line.variant) {
        return false
      }
      return line.variant.id === variant.id
    })

    if (duplicateExists) {
      toast.error(t('procurements.create.duplicateVariant'))
      return
    }

    updateLine(activeLineId.value, 'variant', variant)
    if (!lines.value.find((line) => line.id === activeLineId.value)?.cost_per_unit && variant.price) {
      updateLine(activeLineId.value, 'cost_per_unit', variant.price)
    }
    closeVariantPicker()
  }

  function variantDisplay(variant: ProductVariant): string {
    return variant.product_name ?? variant.display_sku ?? variant.sku ?? `VAR-${variant.id}`
  }

  onBeforeUnmount(() => {
    variantsAbortController?.abort()
  })

  return {
    loadAllVariants,
    variantSheetOpen,
    activeLineId,
    variantSearch,
    variantSearchCategory,
    quickProductSheetOpen,
    quickProductTargetLineId,
    quickProductName,
    quickProductCategoryId,
    quickProductBasePrice,
    quickProductError,
    isCreatingQuickProduct,
    quickSupplierSheetOpen,
    quickSupplierName,
    quickSupplierPhone,
    quickSupplierEmail,
    quickSupplierError,
    isCreatingQuickSupplier,
    openVariantPicker,
    closeVariantPicker,
    openQuickProductCreator,
    closeQuickProductCreator,
    openQuickSupplierCreator,
    closeQuickSupplierCreator,
    placeholderVariantFromProcurementItem,
    createQuickProduct,
    createQuickSupplier,
    filteredVariants,
    selectVariant,
    variantDisplay,
  }
}
