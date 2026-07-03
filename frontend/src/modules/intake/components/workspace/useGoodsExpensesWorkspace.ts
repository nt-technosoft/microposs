import { computed, proxyRefs, ref } from 'vue'
import type { Router } from 'vue-router'
import { createProduct, fetchCategories, fetchProductVariants, fetchVariantsPaginated } from '@/api/catalog'
import {
  createProcurementWorkspace,
  fetchProcurementWorkspace,
  runProcurementWorkspaceAction,
  type ProcurementWorkspacePayload,
} from '@/api/partnerships'
import { useToast } from '@/composables/useToast'
import { useFxRate } from '@/composables/useFxRate'
import { PricingMode } from '@/types/enums'
import type { Category, Product, ProductVariant } from '@/types/models'
import type {
  AllocationMethod,
  CurrencyCode,
  DraftExpenseRow,
  DraftLineRow,
  ExpenseType,
} from './types'

interface UseGoodsExpensesWorkspaceOptions {
  router: Router
  getProcurementId: () => number | null
}

export function useGoodsExpensesWorkspace(options: UseGoodsExpensesWorkspaceOptions) {
  const toast = useToast()
  const {
    rate: latestUsdRate,
    error: latestUsdRateError,
    load: loadLatestUsdRateFromApi,
  } = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

  const workspace = ref<ProcurementWorkspacePayload | null>(null)
  const categories = ref<Category[]>([])
  const allVariants = ref<ProductVariant[]>([])
  const draftLines = ref<DraftLineRow[]>([])
  const draftExpenses = ref<DraftExpenseRow[]>([])
  const primaryCurrency = ref<CurrencyCode>('UZS')
  const removedItemIds = ref<number[]>([])
  const removedExpenseIds = ref<number[]>([])
  const isLoading = ref(false)
  const isSavingDraft = ref(false)
  const draftError = ref<string | null>(null)
  const lineErrors = ref<Record<string, string>>({})
  const expenseErrors = ref<Record<string, string>>({})
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
  let controller: AbortController | null = null

  const categoryOptions = computed(() => [
    { value: null, label: 'Все категории' },
    ...categories.value.map((category) => ({ value: category.id, label: category.name })),
  ])

  const quickProductCategoryOptions = computed(() => [
    { value: null, label: 'Без категории' },
    ...categories.value.map((category) => ({ value: category.id, label: category.name })),
  ])

  const expenseTypeOptions = [
    { value: 'CUSTOMS', label: 'Растаможка' },
    { value: 'LOGISTICS', label: 'Логистика' },
    { value: 'FEE', label: 'Комиссия' },
    { value: 'OTHER', label: 'Другое' },
  ]

  const allocationOptions = [
    { value: 'BY_VALUE', label: 'По стоимости' },
    { value: 'BY_QUANTITY', label: 'По количеству' },
  ]

  const filteredVariants = computed(() => {
    const query = variantSearch.value.trim().toLowerCase()
    return allVariants.value.filter((variant) => {
      if (variantSearchCategory.value !== null && variant.category_id !== variantSearchCategory.value) return false
      if (!query) return true
      const searchable = [variant.product_name ?? '', variant.display_sku ?? '', variant.sku ?? ''].join(' ').toLowerCase()
      return searchable.includes(query)
    })
  })

  const editableItemTargets = computed(() => {
    return draftLines.value
      .filter((line) => line.serverId !== null && !line.locked_reason)
      .map((line) => ({
        id: line.serverId as number,
        label: line.variant ? variantDisplay(line.variant) : `Товар #${line.serverId}`,
      }))
  })

  const hasUnsavedLines = computed(() => draftLines.value.some((line) => line.serverId === null))
  const goodsTotalUzs = computed(() => draftLines.value.reduce((sum, line) => {
    const quantity = parsePositiveNumber(line.quantity)
    const price = parsePositiveNumber(line.cost_per_unit)
    return sum + moneyAmountToUzs(quantity * price, line.currency, line.fx_rate)
  }, 0))
  const expensesTotalUzs = computed(() => draftExpenses.value.reduce((sum, expense) => {
    return sum + moneyAmountToUzs(parsePositiveNumber(expense.amount), expense.currency, expense.fx_rate)
  }, 0))
  const procurementTotalUzs = computed(() => goodsTotalUzs.value + expensesTotalUzs.value)
  const goodsTotal = computed(() => amountUzsToPrimary(goodsTotalUzs.value))
  const expensesTotal = computed(() => amountUzsToPrimary(expensesTotalUzs.value))
  const procurementTotal = computed(() => amountUzsToPrimary(procurementTotalUzs.value))

  function buildEmptyLine(): DraftLineRow {
    return {
      id: crypto.randomUUID(),
      serverId: null,
      variant: null,
      quantity: '1',
      cost_per_unit: '',
      currency: primaryCurrency.value,
      fx_rate: defaultFxRateForCurrency(primaryCurrency.value),
      locked_reason: null,
    }
  }

  function buildEmptyExpense(): DraftExpenseRow {
    return {
      id: crypto.randomUUID(),
      serverId: null,
      expense_type: 'CUSTOMS',
      amount: '',
      currency: primaryCurrency.value,
      fx_rate: defaultFxRateForCurrency(primaryCurrency.value),
      allocation_method: 'BY_VALUE',
      notes: '',
      target_item_ids: [],
      locked_reason: null,
    }
  }

  function normalizeCurrency(value: unknown): CurrencyCode {
    return String(value ?? 'UZS').trim().toUpperCase() === 'USD' ? 'USD' : 'UZS'
  }

  function defaultFxRateForCurrency(currency: string): string {
    return normalizeCurrency(currency) === 'UZS' ? '1' : latestUsdRate.value
  }

  function nextCurrency(currency: string): CurrencyCode {
    return normalizeCurrency(currency) === 'UZS' ? 'USD' : 'UZS'
  }

  function showFxField(currency: string): boolean {
    return normalizeCurrency(currency) !== 'UZS'
  }

  function parsePositiveNumber(raw: unknown): number {
    const value = Number.parseFloat(String(raw ?? ''))
    return Number.isFinite(value) && value > 0 ? value : 0
  }

  function moneyAmountToUzs(amount: number, currency: string, fxRate: unknown): number {
    if (!Number.isFinite(amount) || amount <= 0) return 0
    if (normalizeCurrency(currency) === 'UZS') return amount
    return amount * parsePositiveNumber(fxRate)
  }

  function amountUzsToPrimary(amount: number): number {
    if (primaryCurrency.value === 'UZS') return amount
    const rate = parsePositiveNumber(latestUsdRate.value)
    return rate > 0 ? amount / rate : 0
  }

  function formatCurrencyTotalLabel(currency: string): string {
    return normalizeCurrency(currency) === 'USD' ? 'USD -> UZS' : 'UZS'
  }

  function normalizeTextInput(value: unknown): string {
    return String(value ?? '').trim()
  }

  function variantDisplay(variant: ProductVariant): string {
    return variant.product_name ?? variant.display_sku ?? variant.sku ?? `VAR-${variant.id}`
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

  function placeholderVariantFromItem(item: ProcurementWorkspacePayload['documents']['items'][number]): ProductVariant {
    return {
      id: item.product_variant_id,
      created_at: '',
      updated_at: '',
      product_name: item.product_variant_name,
      sku: item.product_variant_name || `VAR-${item.product_variant_id}`,
      display_sku: item.product_variant_name || `VAR-${item.product_variant_id}`,
      price: item.unit_purchase_price,
      effective_price: item.unit_purchase_price,
      is_active: true,
      attribute_values: [],
    }
  }

  function populateDrafts(payload: ProcurementWorkspacePayload): void {
    workspace.value = payload
    primaryCurrency.value = normalizeCurrency(payload.documents.procurement.primary_currency || payload.display.primary_currency)
    draftLines.value = payload.documents.items
      .filter((item) => item.lifecycle_state !== 'CANCELLED')
      .map((item) => ({
        id: `server-${item.id}`,
        serverId: item.id,
        variant: placeholderVariantFromItem(item),
        quantity: item.quantity,
        cost_per_unit: item.unit_purchase_price,
        currency: normalizeCurrency(item.currency),
        fx_rate: item.fx_rate,
        locked_reason: item.locked_reason,
      }))
    draftExpenses.value = payload.documents.expenses
      .filter((expense) => expense.lifecycle_state !== 'CANCELLED')
      .map((expense) => ({
        id: `server-${expense.id}`,
        serverId: expense.id,
        expense_type: expense.expense_type as ExpenseType,
        amount: expense.amount,
        currency: normalizeCurrency(expense.currency),
        fx_rate: expense.fx_rate,
        allocation_method: expense.allocation_method as AllocationMethod,
        notes: '',
        target_item_ids: expense.target_item_ids ?? [],
        locked_reason: expense.locked_reason,
      }))
    removedItemIds.value = []
    removedExpenseIds.value = []
    lineErrors.value = {}
    expenseErrors.value = {}
  }

  async function loadWorkspace(): Promise<void> {
    const procurementId = options.getProcurementId()
    if (!procurementId) return
    controller?.abort()
    controller = new AbortController()
    isLoading.value = true
    try {
      const payload = await fetchProcurementWorkspace(procurementId, controller.signal)
      populateDrafts(payload)
    } catch (error) {
      if ((error as { name?: string }).name !== 'CanceledError') {
        draftError.value = error instanceof Error ? error.message : 'Не удалось загрузить приход'
      }
    } finally {
      isLoading.value = false
    }
  }

  async function loadReferences(): Promise<void> {
    try {
      const [loadedCategories] = await Promise.all([
        fetchCategories(),
        loadLatestUsdRate(),
      ])
      categories.value = loadedCategories
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Не удалось загрузить справочники')
    }
  }

  async function loadLatestUsdRate(): Promise<void> {
    try {
      await loadLatestUsdRateFromApi()
    } catch {
      toast.error(latestUsdRateError.value || 'Курс USD/UZS не найден')
    }
  }

  async function loadAllVariants(): Promise<void> {
    const loaded: ProductVariant[] = []
    let page = 1
    while (true) {
      const response = await fetchVariantsPaginated({ active: true, page, page_size: 100 }, controller?.signal)
      loaded.push(...response.results)
      if (!response.next) break
      page += 1
    }
    allVariants.value = loaded
  }

  function validateLine(line: DraftLineRow): string {
    if (line.locked_reason) return ''
    if (!line.variant) return 'Выберите товар'
    if (parsePositiveNumber(line.quantity) <= 0) return 'Укажите количество'
    if (parsePositiveNumber(line.cost_per_unit) <= 0) return 'Укажите цену закупки'
    if (showFxField(line.currency) && parsePositiveNumber(line.fx_rate) <= 0) return 'Не найден курс валюты'
    return ''
  }

  function validateExpense(expense: DraftExpenseRow): string {
    if (expense.locked_reason) return ''
    if (parsePositiveNumber(expense.amount) <= 0) return 'Укажите сумму расхода'
    if (showFxField(expense.currency) && parsePositiveNumber(expense.fx_rate) <= 0) return 'Не найден курс валюты'
    return ''
  }

  function validateLinesForAppend(): boolean {
    const errors: Record<string, string> = {}
    for (const line of draftLines.value) {
      const error = validateLine(line)
      if (error) errors[line.id] = error
    }
    lineErrors.value = errors
    return Object.keys(errors).length === 0
  }

  function validateExpensesForAppend(): boolean {
    const errors: Record<string, string> = {}
    for (const expense of draftExpenses.value) {
      const error = validateExpense(expense)
      if (error) errors[expense.id] = error
    }
    expenseErrors.value = errors
    return Object.keys(errors).length === 0
  }

  function addEmptyLine(): void {
    if (draftLines.value.length > 0 && !validateLinesForAppend()) {
      toast.error('Сначала заполните текущий товар')
      return
    }
    draftLines.value = [...draftLines.value, buildEmptyLine()]
  }

  function removeLine(rowId: string): void {
    if (draftLines.value.length <= 1) {
      toast.error('В приходе должен быть минимум один товар')
      return
    }
    const row = draftLines.value.find((line) => line.id === rowId)
    if (row?.serverId && !row.locked_reason) {
      removedItemIds.value = [...new Set([...removedItemIds.value, row.serverId])]
    }
    draftLines.value = draftLines.value.filter((line) => line.id !== rowId)
    const { [rowId]: _removed, ...nextErrors } = lineErrors.value
    lineErrors.value = nextErrors
    draftExpenses.value = draftExpenses.value.map((expense) => ({
      ...expense,
      target_item_ids: expense.target_item_ids.filter((id) => id !== row?.serverId),
    }))
  }

  function updateLine(rowId: string, field: keyof Omit<DraftLineRow, 'id' | 'serverId' | 'locked_reason'>, value: string | ProductVariant | null): void {
    draftLines.value = draftLines.value.map((line) => {
      if (line.id !== rowId || line.locked_reason) return line
      return { ...line, [field]: value }
    })
    const line = draftLines.value.find((item) => item.id === rowId)
    if (line && !validateLine(line)) {
      const { [rowId]: _removed, ...nextErrors } = lineErrors.value
      lineErrors.value = nextErrors
    }
  }

  function addExpense(): void {
    if (draftExpenses.value.length > 0 && !validateExpensesForAppend()) {
      toast.error('Сначала заполните текущий расход')
      return
    }
    draftExpenses.value = [...draftExpenses.value, buildEmptyExpense()]
  }

  function removeExpense(rowId: string): void {
    const row = draftExpenses.value.find((expense) => expense.id === rowId)
    if (row?.serverId && !row.locked_reason) {
      removedExpenseIds.value = [...new Set([...removedExpenseIds.value, row.serverId])]
    }
    draftExpenses.value = draftExpenses.value.filter((expense) => expense.id !== rowId)
    const { [rowId]: _removed, ...nextErrors } = expenseErrors.value
    expenseErrors.value = nextErrors
  }

  function updateExpense(rowId: string, field: keyof Omit<DraftExpenseRow, 'id' | 'serverId' | 'locked_reason'>, value: string | number[]): void {
    draftExpenses.value = draftExpenses.value.map((expense) => {
      if (expense.id !== rowId || expense.locked_reason) return expense
      return { ...expense, [field]: value } as DraftExpenseRow
    })
    const expense = draftExpenses.value.find((item) => item.id === rowId)
    if (expense && !validateExpense(expense)) {
      const { [rowId]: _removed, ...nextErrors } = expenseErrors.value
      expenseErrors.value = nextErrors
    }
  }

  function setLineCurrency(rowId: string, currencyValue: string): void {
    const currency = normalizeCurrency(currencyValue)
    draftLines.value = draftLines.value.map((line) => {
      if (line.id !== rowId || line.locked_reason) return line
      return {
        ...line,
        currency,
        fx_rate: currency === line.currency ? line.fx_rate : defaultFxRateForCurrency(currency),
      }
    })
  }

  function toggleLineCurrency(rowId: string): void {
    const line = draftLines.value.find((item) => item.id === rowId)
    if (!line) return
    setLineCurrency(rowId, nextCurrency(line.currency))
  }

  function setExpenseCurrency(rowId: string, currencyValue: string): void {
    const currency = normalizeCurrency(currencyValue)
    draftExpenses.value = draftExpenses.value.map((expense) => {
      if (expense.id !== rowId || expense.locked_reason) return expense
      return {
        ...expense,
        currency,
        fx_rate: currency === expense.currency ? expense.fx_rate : defaultFxRateForCurrency(currency),
      }
    })
  }

  function toggleExpenseCurrency(rowId: string): void {
    const expense = draftExpenses.value.find((item) => item.id === rowId)
    if (!expense) return
    setExpenseCurrency(rowId, nextCurrency(expense.currency))
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

  function selectVariant(variant: ProductVariant): void {
    if (!activeLineId.value) return
    const duplicateExists = draftLines.value.some((line) => {
      if (line.id === activeLineId.value || !line.variant) return false
      return line.variant.id === variant.id
    })
    if (duplicateExists) {
      toast.error('Этот товар уже добавлен в приход')
      return
    }

    updateLine(activeLineId.value, 'variant', variant)
    closeVariantPicker()
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
    quickProductError.value = null
  }

  function closeQuickProductCreator(): void {
    quickProductSheetOpen.value = false
    quickProductTargetLineId.value = null
    resetQuickProductForm()
  }

  async function createQuickProductAction(): Promise<void> {
    const name = normalizeTextInput(quickProductName.value)
    if (!name) {
      quickProductError.value = 'Введите название товара'
      return
    }

    isCreatingQuickProduct.value = true
    quickProductError.value = null
    try {
      const product = await createProduct({
        name,
        category_id: quickProductCategoryId.value,
        pricing_mode: PricingMode.DEFAULT_EDITABLE,
        base_price: normalizeTextInput(quickProductBasePrice.value) || null,
      })
      const variants = product.variants?.length > 0 ? product.variants : await fetchProductVariants(product.id)
      const createdVariant = variants.find((variant) => variant.is_active !== false) ?? variants[0]
      if (!createdVariant) {
        quickProductError.value = 'Товар создан, но вариант не найден'
        return
      }
      const variant = normalizeCreatedVariant(product, createdVariant)
      allVariants.value = [variant, ...allVariants.value.filter((item) => item.id !== variant.id)]
      const targetLineId = quickProductTargetLineId.value ?? draftLines.value.find((line) => !line.variant)?.id ?? null
      if (targetLineId) {
        updateLine(targetLineId, 'variant', variant)
      } else {
        draftLines.value = [...draftLines.value, { ...buildEmptyLine(), variant }]
      }
      toast.success('Товар создан и добавлен')
      closeQuickProductCreator()
    } catch (error) {
      quickProductError.value = error instanceof Error ? error.message : 'Не удалось создать товар'
    } finally {
      isCreatingQuickProduct.value = false
    }
  }

  function toggleExpenseTarget(expenseId: string, itemId: number): void {
    const expense = draftExpenses.value.find((row) => row.id === expenseId)
    if (!expense || expense.locked_reason) return
    const next = new Set(expense.target_item_ids)
    if (next.has(itemId)) next.delete(itemId)
    else next.add(itemId)
    updateExpense(expenseId, 'target_item_ids', Array.from(next))
  }

  function setExpenseAllTargets(expenseId: string): void {
    updateExpense(expenseId, 'target_item_ids', [])
  }

  function validateDraftWorkspace(): string {
    const nextLineErrors: Record<string, string> = {}
    const nextExpenseErrors: Record<string, string> = {}
    const seenVariantIds = new Set<number>()
    for (const line of draftLines.value) {
      if (line.locked_reason) continue
      const error = validateLine(line)
      if (error) {
        nextLineErrors[line.id] = error
        continue
      }
      if (!line.variant) continue
      if (seenVariantIds.has(line.variant.id)) {
        nextLineErrors[line.id] = 'Такой товар уже есть в приходе'
        continue
      }
      seenVariantIds.add(line.variant.id)
    }
    for (const expense of draftExpenses.value) {
      if (expense.locked_reason) continue
      const error = validateExpense(expense)
      if (error) nextExpenseErrors[expense.id] = error
    }
    lineErrors.value = nextLineErrors
    expenseErrors.value = nextExpenseErrors
    return Object.values(nextLineErrors)[0] ?? Object.values(nextExpenseErrors)[0] ?? ''
  }

  async function ensureWorkspace(): Promise<ProcurementWorkspacePayload> {
    if (workspace.value) return workspace.value
    const created = await createProcurementWorkspace({ primary_currency: primaryCurrency.value })
    workspace.value = created
    await options.router.replace({ name: 'procurement-detail', params: { id: created.id } })
    return created
  }

  function setPrimaryCurrency(currency: CurrencyCode): void {
    primaryCurrency.value = currency
    draftLines.value = draftLines.value.map((line) => {
      if (line.locked_reason || line.variant || line.cost_per_unit) return line
      return { ...line, currency, fx_rate: defaultFxRateForCurrency(currency) }
    })
    draftExpenses.value = draftExpenses.value.map((expense) => {
      if (expense.locked_reason || expense.amount) return expense
      return { ...expense, currency, fx_rate: defaultFxRateForCurrency(currency) }
    })
  }

  async function saveGoodsAndExpenses(): Promise<void> {
    draftError.value = null
    const validation = validateDraftWorkspace()
    if (validation) {
      draftError.value = validation
      toast.error(validation)
      return
    }

    isSavingDraft.value = true
    try {
      const target = await ensureWorkspace()
      if (target.documents.procurement.primary_currency !== primaryCurrency.value) {
        await runProcurementWorkspaceAction(target.id, 'UPDATE_SOURCE', {
          primary_currency: primaryCurrency.value,
        })
      }
      const updated = await runProcurementWorkspaceAction(target.id, 'UPDATE_ITEMS', {
        items: draftLines.value
          .filter((line) => !line.locked_reason)
          .map((line) => ({
            id: line.serverId ?? undefined,
            product_variant_id: line.variant!.id,
            quantity: line.quantity,
            unit_purchase_price: line.cost_per_unit,
            currency: normalizeCurrency(line.currency),
            fx_rate: showFxField(line.currency) ? line.fx_rate : '1',
          })),
        expenses: draftExpenses.value
          .filter((expense) => !expense.locked_reason)
          .map((expense) => ({
            id: expense.serverId ?? undefined,
            expense_type: expense.expense_type,
            amount: expense.amount,
            currency: normalizeCurrency(expense.currency),
            fx_rate: showFxField(expense.currency) ? expense.fx_rate : '1',
            allocation_method: expense.allocation_method,
            notes: expense.notes.trim(),
            target_item_ids: expense.target_item_ids,
          })),
        cancel_item_ids: removedItemIds.value,
        cancel_expense_ids: removedExpenseIds.value,
      })
      populateDrafts(updated)
      toast.success('Товары и расходы сохранены')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось сохранить товары и расходы'
      draftError.value = message
      toast.error(message)
    } finally {
      isSavingDraft.value = false
    }
  }

  async function initGoodsExpenses(): Promise<void> {
    if (draftLines.value.length === 0) addEmptyLine()
    await loadReferences()
    await loadWorkspace()
  }

  function abortGoodsExpensesRequests(): void {
    controller?.abort()
  }

  return proxyRefs({
    workspace,
    primaryCurrency,
    draftLines,
    draftExpenses,
    lineErrors,
    expenseErrors,
    isLoading,
    isSavingDraft,
    draftError,
    variantSheetOpen,
    variantSearch,
    variantSearchCategory,
    quickProductSheetOpen,
    quickProductName,
    quickProductCategoryId,
    quickProductBasePrice,
    quickProductError,
    isCreatingQuickProduct,
    categoryOptions,
    quickProductCategoryOptions,
    expenseTypeOptions,
    allocationOptions,
    filteredVariants,
    editableItemTargets,
    hasUnsavedLines,
    goodsTotal,
    expensesTotal,
    procurementTotal,
    variantDisplay,
    showFxField,
    formatCurrencyTotalLabel,
    initGoodsExpenses,
    abortGoodsExpensesRequests,
    setPrimaryCurrency,
    addEmptyLine,
    addExpense,
    openQuickProductCreator,
    closeQuickProductCreator,
    openVariantPicker,
    closeVariantPicker,
    removeLine,
    updateLine,
    toggleLineCurrency,
    removeExpense,
    updateExpense,
    toggleExpenseCurrency,
    toggleExpenseTarget,
    setExpenseAllTargets,
    saveGoodsAndExpenses,
    selectVariant,
    createQuickProductAction,
  })
}
