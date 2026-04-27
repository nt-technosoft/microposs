<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CheckCircle2, AlertCircle, PlusCircle, ArrowRightLeft, Plus, Trash2, RefreshCcw, ChevronDown, BarChart3 } from 'lucide-vue-next'
import { PricingMode, ProcurementStatus, ProcurementType } from '@/types/enums'
import { formatPrice, formatPriceCompact } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import { fetchLocations } from '@/api/inventory'
import { fetchLatestFxRate } from '@/api/finance'
import { createSupplier, fetchSuppliers } from '@/api/suppliers'
import { createProduct, fetchCategories, fetchProductVariants, fetchVariantsPaginated } from '@/api/catalog'
import {
  addProcurementContribution,
  addProcurementWithdrawal,
  createProcurementBalanceExchange,
  fetchProcurement,
  payProcurementExpenses,
  payProcurementItems,
  receiveProcurement,
  updateProcurement,
  type ProcurementDetail,
} from '@/api/partnerships'
import { useAuthStore } from '@/stores/auth'
import type { Category, Product, ProductVariant, Supplier } from '@/types/models'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'

const FALLBACK_FX_RATE = '12000'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()

const procurement = ref<ProcurementDetail | null>(null)
const locations = ref<Array<{ value: number; label: string }>>([])
const selectedWarehouseId = ref<number | null>(null)
const isLoading = ref(true)
const isConfirming = ref(false)
const errorMessage = ref<string | null>(null)
const latestUsdRate = ref('12000')
const suppliers = ref<Supplier[]>([])
const categories = ref<Category[]>([])
const allVariants = ref<ProductVariant[]>([])
const selectedSupplierId = ref<number | null>(null)
const isSavingDraft = ref(false)
const isPayingItems = ref(false)
const isPayingExpenses = ref(false)
const draftError = ref<string | null>(null)
const contributionSheetOpen = ref(false)
const exchangeSheetOpen = ref(false)
const withdrawalSheetOpen = ref(false)
const contributionPartnerId = ref<number | null>(null)
const contributionAmount = ref('')
const contributionCurrency = ref('USD')
const contributionFxRate = ref('12000')
const contributionNotes = ref('')
const contributionRateManualOpen = ref(false)
const withdrawalAmount = ref('')
const withdrawalCurrency = ref('UZS')
const withdrawalFxRate = ref('1')
const withdrawalReason = ref('')
const withdrawalRateManualOpen = ref(false)
const isSavingContribution = ref(false)
const isSavingWithdrawal = ref(false)
const contributionError = ref<string | null>(null)
const exchangeError = ref<string | null>(null)
const withdrawalError = ref<string | null>(null)
const isSavingExchange = ref(false)
const variantSheetOpen = ref(false)
const activeLineId = ref<string | null>(null)
const variantSearch = ref('')
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

interface DraftLineRow {
  id: string
  serverId: number | null
  variant: ProductVariant | null
  quantity: string
  cost_per_unit: string
  currency: string
  fx_rate: string
}

interface DraftExpenseRow {
  id: string
  serverId: number | null
  expense_type: 'CUSTOMS' | 'LOGISTICS' | 'FEE' | 'OTHER'
  amount: string
  currency: string
  fx_rate: string
  allocation_method: 'BY_VALUE' | 'BY_QUANTITY'
  notes: string
}

const draftLines = ref<DraftLineRow[]>([])
const draftExpenses = ref<DraftExpenseRow[]>([])
const stageState = ref({
  contract: false,
  balance: true,
  operations: true,
  receive: true,
  service: false,
})
const showFullBalanceHistory = ref(false)
const expandedBalanceHistoryId = ref<string | null>(null)
const expandedDraftLineId = ref<string | null>(null)
const expandedDraftExpenseId = ref<string | null>(null)
const expandedCostPreviewKey = ref<string | null>(null)
const exchangeFromCurrency = ref('USD')
const exchangeToCurrency = ref('UZS')
const exchangeFromAmount = ref('')
const exchangeRate = ref(FALLBACK_FX_RATE)
const exchangeNotes = ref('')
const exchangeRateManualOpen = ref(false)

const typeLabel: Record<ProcurementType, string> = {
  [ProcurementType.OWN_FUNDS]: 'Свои деньги',
  [ProcurementType.PARTNERSHIP]: 'Партнёрский',
  [ProcurementType.MUSHARAKA]: 'Мушарака',
  [ProcurementType.DISTRIBUTOR]: 'Дистрибьютор',
}

const expenseTypeLabel: Record<string, string> = {
  CUSTOMS: 'Растаможка',
  LOGISTICS: 'Логистика',
  FEE: 'Комиссия',
  OTHER: 'Другое',
}

const allocationOptions = [
  { value: 'BY_VALUE', label: 'По стоимости' },
  { value: 'BY_QUANTITY', label: 'По количеству' },
]

const categoryOptions = computed(() => categories.value.map((category) => ({ value: category.id, label: category.name })))
const supplierOptions = computed(() => suppliers.value.map((supplier) => ({ value: supplier.id, label: supplier.name })))

const canConfirm = computed(() => procurement.value?.status === ProcurementStatus.OPEN)
const canReceive = computed(() => {
  const status = procurement.value?.receive_plan?.status
  return canConfirm.value && selectedWarehouseId.value !== null && (status === 'READY' || status === 'AUTO_SURPLUS')
})
const canManageBalance = computed(() => Boolean(auth.isOwner) && canConfirm.value)

const hasForeignCurrency = computed(() => {
  if (!procurement.value) return false
  return procurement.value.items.some((line) => String(line.currency || 'UZS').toUpperCase() !== 'UZS')
    || procurement.value.expenses.some((expense) => String(expense.currency || 'UZS').toUpperCase() !== 'UZS')
})

const receiveBalanceEntries = computed(() => {
  const balances = procurement.value?.receive_plan?.balances ?? {}
  return Object.entries(balances)
})
const balanceEntries = computed(() => {
  const balances = procurement.value?.balance?.balances ?? {}
  return Object.entries(balances)
})
const paidItems = computed(() => (procurement.value?.items ?? []).filter((item) => item.status === 'PAID'))
const paidExpenses = computed(() => (procurement.value?.expenses ?? []).filter((expense) => expense.status === 'PAID'))
const contractPartners = computed(() => procurement.value?.contract?.partners ?? [])
const contributionPartnerOptions = computed(() => contractPartners.value.map((partner) => ({
  value: partner.partner,
  label: `${partner.partner_name} · ${partner.role === 'INVESTOR' ? 'инвестор' : 'бизнес'}`,
})))
const balanceParticipantTotals = computed(() => procurement.value?.balance?.participant_totals ?? [])
const balanceHistoryEntries = computed(() => procurement.value?.balance?.history ?? [])
const visibleBalanceHistoryEntries = computed(() => showFullBalanceHistory.value
  ? balanceHistoryEntries.value
  : balanceHistoryEntries.value.slice(0, 6))
const hasCollapsedBalanceHistory = computed(() => balanceHistoryEntries.value.length > 6)
const balanceStatusKind = computed(() => {
  if (procurement.value?.receive_plan.status === 'READY') return 'success'
  return 'blocked'
})
const selectedWithdrawalBalance = computed(() => {
  if (!procurement.value) return 0
  return Number(procurement.value.balance.balances[withdrawalCurrency.value] ?? '0')
})
const selectedExchangeBalance = computed(() => {
  if (!procurement.value) return 0
  return Number(procurement.value.balance.balances[exchangeFromCurrency.value] ?? '0')
})
const exchangeToAmountPreview = computed(() => {
  const amount = parsePositiveNumber(exchangeFromAmount.value)
  const rate = parsePositiveNumber(pairRateFromStandardRate(exchangeFromCurrency.value, exchangeToCurrency.value, exchangeRate.value))
  if (amount <= 0 || rate <= 0) return 0
  return amount * rate
})
const contractSummary = computed(() => {
  if (!procurement.value?.contract) return 'Без партнёрского договора'
  const investor = procurement.value.contract.partners.find((partner) => partner.role === 'INVESTOR')
  return [
    investor?.partner_name ?? 'Инвестор',
    formatPrice(procurement.value.contract.planned_budget, procurement.value.contract.currency),
  ].join(' · ')
})
const balanceSummary = computed(() => {
  if (!balanceEntries.value.length) return 'Баланс пока пуст'
  return balanceEntries.value.map(([currency, amount]) => formatPrice(amount, currency)).join(' · ')
})
const operationsSummary = computed(() => {
  const parts = [
    draftLines.value.length ? `товары к оплате: ${draftLines.value.length}` : '',
    draftExpenses.value.length ? `расходы к оплате: ${draftExpenses.value.length}` : '',
    paidItems.value.length ? `оплачено: ${paidItems.value.length} тов.` : '',
    paidExpenses.value.length ? `оплачено: ${paidExpenses.value.length} расх.` : '',
  ].filter(Boolean)
  return parts.join(' · ') || 'Операций пока нет'
})
const hasDraftChanges = computed(() => draftLines.value.length > 0 || draftExpenses.value.length > 0 || selectedSupplierId.value !== procurement.value?.supplier)

const totalAmount = computed(() => {
  if (!procurement.value) return 0
  return procurement.value.items.reduce((sum, line) => {
    return sum + Number(line.quantity) * Number(line.unit_purchase_price) * Number(line.fx_rate)
  }, 0)
})

const expensesTotal = computed(() => {
  if (!procurement.value) return 0
  return procurement.value.expenses.reduce((sum, expense) => {
    return sum + Number(expense.amount) * Number(expense.fx_rate)
  }, 0)
})

const procurementTotal = computed(() => totalAmount.value + expensesTotal.value)
const costPreviewScenarios = computed(() => {
  if (!procurement.value) return []

  const scenarios = [
    {
      key: 'receive-now',
      label: 'Если оприходовать сейчас',
      basis: procurement.value.cost_preview.receive_basis,
      showStatus: false,
    },
  ]

  if (procurement.value.cost_preview.reallocation_pending && procurement.value.cost_preview.if_all_current_lines_paid.lines.length) {
    scenarios.push({
      key: 'after-payment',
      label: 'Если оплатить всё текущее',
      basis: procurement.value.cost_preview.if_all_current_lines_paid,
      showStatus: true,
    })
  }

  return scenarios.filter((scenario) => scenario.basis.lines.length > 0)
})
const headerSummaryItems = computed(() => [
  {
    label: 'Поставщик',
    value: procurement.value?.supplier_name ?? 'Не выбран',
  },
  {
    label: 'Баланс прихода',
    value: balanceEntries.value.length ? balanceSummary.value : 'Пока пуст',
  },
  {
    label: 'Оприходование',
    value: receiveStatusMeta(procurement.value?.receive_plan.status ?? 'NOT_OPEN').label,
  },
])
const filteredVariants = computed(() => {
  const query = variantSearch.value.trim().toLowerCase()
  return allVariants.value.filter((variant) => {
    if (!query) return true
    const searchable = [variant.product_name ?? '', variant.display_sku ?? '', variant.sku ?? ''].join(' ').toLowerCase()
    return searchable.includes(query)
  })
})

function normalizeCurrency(value: unknown): string {
  const currency = String(value ?? 'UZS').trim().toUpperCase()
  return currency === 'USD' ? 'USD' : 'UZS'
}

function nextCurrency(currency: string): string {
  return normalizeCurrency(currency) === 'UZS' ? 'USD' : 'UZS'
}

function parsePositiveNumber(raw: unknown): number {
  const value = Number.parseFloat(String(raw ?? ''))
  return Number.isFinite(value) && value > 0 ? value : 0
}

function defaultFxRateForCurrency(currency: string): string {
  return normalizeCurrency(currency) === 'UZS' ? '1' : latestUsdRate.value
}

function standardUsdUzsRate(): string {
  return latestUsdRate.value
}

function pairRateFromStandardRate(fromCurrency: string, toCurrency: string, standardRateRaw: string): string {
  const from = normalizeCurrency(fromCurrency)
  const to = normalizeCurrency(toCurrency)
  if (from === to) return '1'
  const standardRate = parsePositiveNumber(standardRateRaw)
  if (from === 'USD' && to === 'UZS') return standardRate > 0 ? standardRate.toFixed(6) : '0'
  if (from === 'UZS' && to === 'USD') {
    return standardRate > 0 ? (1 / standardRate).toFixed(6) : '0'
  }
  return '1'
}

function showFxField(currency: string): boolean {
  return normalizeCurrency(currency) !== 'UZS'
}

function toggleStage(stage: keyof typeof stageState.value): void {
  stageState.value[stage] = !stageState.value[stage]
}

function focusStage(stage: keyof typeof stageState.value): void {
  stageState.value[stage] = true
  window.requestAnimationFrame(() => {
    document.getElementById(`stage-${stage}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function openProcurementAudit(): void {
  router.push({ name: 'reports-procurement-profitability', params: { id: route.params.id } })
}

function syncStageState(detail: ProcurementDetail, force = false): void {
  if (!force && procurement.value?.status === detail.status) return
  const isOpen = detail.status === ProcurementStatus.OPEN
  stageState.value = {
    contract: false,
    balance: true,
    operations: isOpen,
    receive: isOpen,
    service: false,
  }
}

function buildEmptyDraftLine(): DraftLineRow {
  return {
    id: crypto.randomUUID(),
    serverId: null,
    variant: null,
    quantity: '1',
    cost_per_unit: '',
    currency: 'UZS',
    fx_rate: '1',
  }
}

function buildEmptyDraftExpense(): DraftExpenseRow {
  return {
    id: crypto.randomUUID(),
    serverId: null,
    expense_type: 'CUSTOMS',
    amount: '',
    currency: 'UZS',
    fx_rate: '1',
    allocation_method: 'BY_VALUE',
    notes: '',
  }
}

function addDraftLine(): void {
  const nextLine = buildEmptyDraftLine()
  draftLines.value = [...draftLines.value, nextLine]
  expandedDraftLineId.value = nextLine.id
}

function removeDraftLine(rowId: string): void {
  draftLines.value = draftLines.value.filter((line) => line.id !== rowId)
  if (expandedDraftLineId.value === rowId) {
    expandedDraftLineId.value = draftLines.value[0]?.id ?? null
  }
}

function updateDraftLine(rowId: string, field: keyof Omit<DraftLineRow, 'id'>, value: string | ProductVariant | null | number): void {
  draftLines.value = draftLines.value.map((line) => line.id === rowId ? { ...line, [field]: value } : line)
}

function addDraftExpense(): void {
  const nextExpense = buildEmptyDraftExpense()
  draftExpenses.value = [...draftExpenses.value, nextExpense]
  expandedDraftExpenseId.value = nextExpense.id
}

function removeDraftExpense(rowId: string): void {
  draftExpenses.value = draftExpenses.value.filter((expense) => expense.id !== rowId)
  if (expandedDraftExpenseId.value === rowId) {
    expandedDraftExpenseId.value = draftExpenses.value[0]?.id ?? null
  }
}

function updateDraftExpense(rowId: string, field: keyof Omit<DraftExpenseRow, 'id'>, value: string | number | null): void {
  draftExpenses.value = draftExpenses.value.map((expense) => expense.id === rowId ? { ...expense, [field]: value } as DraftExpenseRow : expense)
}

function setDraftLineCurrency(rowId: string, currencyValue: string): void {
  const currency = normalizeCurrency(currencyValue)
  draftLines.value = draftLines.value.map((line) => line.id === rowId
    ? {
        ...line,
        currency,
        fx_rate: currency === line.currency ? line.fx_rate : defaultFxRateForCurrency(currency),
      }
    : line)
}

function toggleDraftLineCurrency(rowId: string): void {
  const line = draftLines.value.find((item) => item.id === rowId)
  if (!line) return
  setDraftLineCurrency(rowId, nextCurrency(line.currency))
}

function setDraftExpenseCurrency(rowId: string, currencyValue: string): void {
  const currency = normalizeCurrency(currencyValue)
  draftExpenses.value = draftExpenses.value.map((expense) => expense.id === rowId
    ? {
        ...expense,
        currency,
        fx_rate: currency === expense.currency ? expense.fx_rate : defaultFxRateForCurrency(currency),
      }
    : expense)
}

function toggleDraftExpenseCurrency(rowId: string): void {
  const expense = draftExpenses.value.find((item) => item.id === rowId)
  if (!expense) return
  setDraftExpenseCurrency(rowId, nextCurrency(expense.currency))
}

function variantDisplay(variant: ProductVariant): string {
  return variant.product_name ?? variant.display_sku ?? variant.sku ?? `VAR-${variant.id}`
}

async function loadAllVariants(): Promise<void> {
  const loaded: ProductVariant[] = []
  let page = 1
  while (true) {
    const response = await fetchVariantsPaginated({ active: true, page, page_size: 100 })
    loaded.push(...response.results)
    if (!response.next) break
    page += 1
  }
  allVariants.value = loaded
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
    toast.error('Этот товар уже добавлен в черновик')
    return
  }
  updateDraftLine(activeLineId.value, 'variant', variant)
  const target = draftLines.value.find((line) => line.id === activeLineId.value)
  if (target && !target.cost_per_unit && variant.price) {
    updateDraftLine(activeLineId.value, 'cost_per_unit', variant.price)
  }
  closeVariantPicker()
}

function normalizeTextInput(value: unknown): string {
  return String(value ?? '').trim()
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

async function createQuickProduct(): Promise<void> {
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
      updateDraftLine(targetLineId, 'variant', variant)
      const targetLine = draftLines.value.find((line) => line.id === targetLineId)
      if (targetLine && !targetLine.cost_per_unit && variant.price) {
        updateDraftLine(targetLineId, 'cost_per_unit', variant.price)
      }
    } else {
      draftLines.value = [...draftLines.value, { ...buildEmptyDraftLine(), variant, cost_per_unit: String(variant.price ?? '') }]
    }
    toast.success('Товар создан')
    closeQuickProductCreator()
  } catch (error: unknown) {
    quickProductError.value = error instanceof Error ? error.message : 'Не удалось создать товар'
  } finally {
    isCreatingQuickProduct.value = false
  }
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

async function createQuickSupplier(): Promise<void> {
  const name = normalizeTextInput(quickSupplierName.value)
  if (!name) {
    quickSupplierError.value = 'Введите название поставщика'
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
    toast.success('Поставщик создан')
    closeQuickSupplierCreator()
  } catch (error: unknown) {
    quickSupplierError.value = error instanceof Error ? error.message : 'Не удалось создать поставщика'
  } finally {
    isCreatingQuickSupplier.value = false
  }
}

function toggleContributionCurrency(): void {
  contributionCurrency.value = normalizeCurrency(contributionCurrency.value) === 'UZS' ? 'USD' : 'UZS'
  contributionFxRate.value = defaultFxRateForCurrency(contributionCurrency.value)
  contributionRateManualOpen.value = false
}

function syncExchangeRate(): void {
  exchangeRate.value = standardUsdUzsRate()
}

function swapExchangeCurrencies(): void {
  const nextFrom = exchangeToCurrency.value
  exchangeToCurrency.value = exchangeFromCurrency.value
  exchangeFromCurrency.value = nextFrom
  syncExchangeRate()
  exchangeRateManualOpen.value = false
}

function toggleWithdrawalCurrency(): void {
  withdrawalCurrency.value = normalizeCurrency(withdrawalCurrency.value) === 'UZS' ? 'USD' : 'UZS'
  withdrawalFxRate.value = defaultFxRateForCurrency(withdrawalCurrency.value)
  withdrawalRateManualOpen.value = false
}

function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatCompactAmount(value: string | number, currency?: string | null): string {
  if (currency) return formatPrice(value, currency)
  return formatPrice(value)
}

function formatPlainAmount(value: string | number): string {
  const num = typeof value === 'string' ? Number.parseFloat(value) : value
  if (!Number.isFinite(num)) return '—'
  return num.toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })
}

function trimTrailingZeros(value: string | number): string {
  const raw = String(value ?? '').trim()
  if (!raw) return '0'
  if (!raw.includes('.')) return raw
  return raw.replace(/\.?0+$/, '')
}

function formatUsdUzsRate(rate: string | number, fromCurrency: string, toCurrency: string): string {
  const parsed = typeof rate === 'string' ? Number.parseFloat(rate) : rate
  if (!Number.isFinite(parsed) || parsed <= 0) return '—'
  const from = normalizeCurrency(fromCurrency)
  const to = normalizeCurrency(toCurrency)
  if (from === 'USD' && to === 'UZS') return trimTrailingZeros(parsed.toFixed(6))
  if (from === 'UZS' && to === 'USD') return trimTrailingZeros((1 / parsed).toFixed(6))
  return trimTrailingZeros(parsed.toFixed(6))
}

function procurementStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    OPEN: 'В процессе',
    RECEIVED: 'Оприходован',
    CLOSED: 'Закрыт',
    CANCELLED: 'Отменён',
  }
  return labels[status] ?? status
}

function receivePlanLabel(status: string): string {
  const labels: Record<string, string> = {
    BLOCKED: 'В процессе',
    READY: 'Готово к оприходованию',
    AUTO_SURPLUS: 'Есть остаток к возврату',
    COSTS_UNPAID: 'Нужно сверить движения по балансу',
    DRAFT_PENDING: 'Есть позиции к оплате',
    RECALCULATE_OR_CONTRIBUTE: 'Нужна доплата или перерасчёт',
    CONTRIBUTION_REQUIRED: 'Нужна доплата',
    NO_ITEMS: 'Добавьте товары',
    NOT_OPEN: 'Закупка уже закрыта',
  }
  return labels[status] ?? status
}

function receiveStatusMeta(status: string): { label: string; tone: 'success' | 'warning' | 'neutral'; hint: string } {
  const map: Record<string, { label: string; tone: 'success' | 'warning' | 'neutral'; hint: string }> = {
    BLOCKED: {
      label: 'В процессе',
      tone: 'warning',
      hint: 'Приход пока в работе. Добавь и оплати позиции, затем сведи баланс по валютам.',
    },
    READY: {
      label: 'Можно оприходовать',
      tone: 'success',
      hint: 'Баланс сведен, можно завершить приход на выбранный склад.',
    },
    AUTO_SURPLUS: {
      label: 'Нужно вернуть остаток',
      tone: 'warning',
      hint: 'После возврата излишка партнёрам оприходование станет доступно.',
    },
    COSTS_UNPAID: {
      label: 'Нужно сверить баланс',
      tone: 'warning',
      hint: 'Есть оплаченные позиции, для которых не хватает движения по балансу прихода.',
    },
    DRAFT_PENDING: {
      label: 'Есть позиции к оплате',
      tone: 'warning',
      hint: 'Сначала оплати товары и расходы, которые ещё находятся в рабочем списке.',
    },
    RECALCULATE_OR_CONTRIBUTE: {
      label: 'Нужна доплата',
      tone: 'warning',
      hint: 'Баланс прихода не сходится. Добавь деньги или пересчитай движения.',
    },
    CONTRIBUTION_REQUIRED: {
      label: 'Нужна доплата',
      tone: 'warning',
      hint: 'По одной из валют не хватает денег для завершения прихода.',
    },
    NO_ITEMS: {
      label: 'Нет товаров',
      tone: 'neutral',
      hint: 'Сначала добавь товары в приход.',
    },
    NOT_OPEN: {
      label: 'Приход закрыт',
      tone: 'neutral',
      hint: 'Этот приход уже не находится на этапе оприходования.',
    },
  }
  return map[status] ?? {
    label: receivePlanLabel(status),
    tone: 'neutral',
    hint: 'Проверь текущее состояние прихода.',
  }
}

function roleLabel(role: string): string {
  return role === 'INVESTOR' ? 'Инвестор' : 'Бизнес'
}

function displayPartnerName(partnerName: string, role?: string | null): string {
  return role === 'OPERATOR' ? 'Бизнес' : partnerName
}

function formatSharePercent(value: string | number): string {
  const numeric = typeof value === 'string' ? Number.parseFloat(value) : value
  if (!Number.isFinite(numeric)) return '0.00%'
  return `${(numeric * 100).toFixed(2)}%`
}

function toggleBalanceHistoryEntry(entryId: string): void {
  expandedBalanceHistoryId.value = expandedBalanceHistoryId.value === entryId ? null : entryId
}

function toggleDraftLineExpanded(lineId: string): void {
  expandedDraftLineId.value = expandedDraftLineId.value === lineId ? null : lineId
}

function toggleDraftExpenseExpanded(expenseId: string): void {
  expandedDraftExpenseId.value = expandedDraftExpenseId.value === expenseId ? null : expenseId
}

function balanceHistoryAmountClass(kind: string): string {
  if (kind === 'CONTRIBUTION') return 'history-amount--in'
  if (kind === 'WITHDRAWAL') return 'history-amount--out'
  return 'history-amount--exchange'
}

function balanceHistoryKindLabel(kind: string): string {
  if (kind === 'CONTRIBUTION') return 'Приход'
  if (kind === 'WITHDRAWAL') return 'Расход'
  return 'Обмен'
}

function balanceHistoryRowClass(kind: string): string {
  if (kind === 'CONTRIBUTION') return 'money-flow-row--in'
  if (kind === 'WITHDRAWAL') return 'money-flow-row--out'
  return 'money-flow-row--exchange'
}

function balanceHistorySignedAmount(
  kind: 'CONTRIBUTION' | 'WITHDRAWAL' | 'EXCHANGE',
  amount: string | number,
  currency: string,
): string {
  const value = formatCompactAmount(amount, currency)
  if (kind === 'CONTRIBUTION') return `+${value}`
  if (kind === 'WITHDRAWAL') return `-${value}`
  return value
}

function allocationMethodLabel(value: string): string {
  return value === 'BY_QUANTITY' ? 'по количеству' : 'по стоимости'
}

function draftLineSummary(line: DraftLineRow): string {
  const quantity = parsePositiveNumber(line.quantity)
  const price = parsePositiveNumber(line.cost_per_unit)
  if (quantity > 0 && price > 0) {
    return `${formatPlainAmount(quantity)} шт. · ${formatCompactAmount(price, line.currency)} / шт.`
  }
  if (quantity > 0) {
    return `${formatPlainAmount(quantity)} шт.`
  }
  return 'Укажи количество и цену'
}

function draftLineTotal(line: DraftLineRow): string {
  const quantity = parsePositiveNumber(line.quantity)
  const price = parsePositiveNumber(line.cost_per_unit)
  if (quantity <= 0 || price <= 0) return '—'
  return formatCompactAmount(quantity * price, line.currency)
}

function draftExpenseSummary(expense: DraftExpenseRow): string {
  return [
    allocationMethodLabel(expense.allocation_method),
    expense.notes.trim() || null,
  ].filter(Boolean).join(' · ') || 'Укажи сумму и комментарий при необходимости'
}

function draftExpenseAmount(expense: DraftExpenseRow): string {
  const amount = parsePositiveNumber(expense.amount)
  if (amount <= 0) return '—'
  return formatCompactAmount(amount, expense.currency)
}

function paidItemSummary(line: ProcurementDetail['items'][number]): string {
  return `${formatPlainAmount(line.quantity)} шт. · ${formatCompactAmount(line.unit_purchase_price, line.currency)} / шт.`
}

function paidExpenseSummary(expense: ProcurementDetail['expenses'][number]): string {
  return allocationMethodLabel(expense.allocation_method)
}

function toggleCostPreviewScenario(key: string): void {
  expandedCostPreviewKey.value = expandedCostPreviewKey.value === key ? null : key
}

function costPreviewScenarioSummary(itemsCount: number, expensesCount: number): string {
  return `${itemsCount} тов. · ${expensesCount} расх.`
}

function costPreviewScenarioExpenses(totalExpenses: string | number): string {
  return formatPriceCompact(totalExpenses, 'UZS')
}

function costPreviewLineSummary(
  line: ProcurementDetail['cost_preview']['receive_basis']['lines'][number],
  showStatus: boolean,
): string {
  const parts = [`${formatPlainAmount(line.quantity)} шт.`]
  if (showStatus) {
    parts.push(line.status === 'PAID' ? 'оплачено' : 'черновик')
  }
  return parts.join(' · ')
}

function ledgerPartnerRole(partnerId: number): string | null {
  const match = contractPartners.value.find((partner) => partner.partner === partnerId)
  return match?.role ?? null
}

function preferredExchangeSourceCurrency(targetCurrency: string): string | null {
  if (!procurement.value) return null
  const normalizedTarget = normalizeCurrency(targetCurrency)
  const entries = Object.entries(procurement.value.balance.balances)
    .map(([currency, amount]) => ({ currency: normalizeCurrency(currency), amount: Number(amount) }))
    .filter((item) => item.currency !== normalizedTarget && item.amount > 0)
  return entries[0]?.currency ?? null
}

function openExchangeSheet(targetCurrency?: string, targetAmount?: number): void {
  exchangeError.value = null
  exchangeNotes.value = ''
  exchangeRateManualOpen.value = false
  const normalizedTarget = normalizeCurrency(
    targetCurrency
      ?? procurement.value?.contract?.currency
      ?? 'UZS',
  )
  const source = preferredExchangeSourceCurrency(normalizedTarget)
    ?? (normalizedTarget === 'USD' ? 'UZS' : 'USD')
  exchangeFromCurrency.value = source
  exchangeToCurrency.value = normalizedTarget
  exchangeRate.value = standardUsdUzsRate()
  const pairRate = parsePositiveNumber(pairRateFromStandardRate(source, normalizedTarget, exchangeRate.value))
  if (targetAmount && pairRate > 0) {
    exchangeFromAmount.value = (targetAmount / pairRate).toFixed(2)
  } else {
    exchangeFromAmount.value = ''
  }
  exchangeSheetOpen.value = true
}

function closeExchangeSheet(): void {
  exchangeSheetOpen.value = false
}

function resetContributionForm(): void {
  contributionError.value = null
  contributionAmount.value = ''
  contributionNotes.value = ''
  contributionRateManualOpen.value = false
  contributionPartnerId.value = contractPartners.value.length === 1
    ? contractPartners.value[0]?.partner ?? null
    : null
  contributionCurrency.value = normalizeCurrency(procurement.value?.contract?.currency ?? 'USD')
  contributionFxRate.value = defaultFxRateForCurrency(contributionCurrency.value)
}

function resetWithdrawalForm(currency?: string): void {
  withdrawalError.value = null
  withdrawalAmount.value = ''
  withdrawalReason.value = ''
  withdrawalRateManualOpen.value = false
  const preferred = currency
    ?? Object.keys(procurement.value?.receive_plan?.missing_spend ?? {})[0]
    ?? Object.keys(procurement.value?.balance?.balances ?? {})[0]
    ?? procurement.value?.contract?.currency
    ?? 'UZS'
  withdrawalCurrency.value = normalizeCurrency(preferred)
  withdrawalFxRate.value = defaultFxRateForCurrency(withdrawalCurrency.value)
}

function openContributionSheet(preferredCurrency?: string): void {
  resetContributionForm()
  if (preferredCurrency) {
    contributionCurrency.value = normalizeCurrency(preferredCurrency)
    contributionFxRate.value = defaultFxRateForCurrency(contributionCurrency.value)
  }
  contributionSheetOpen.value = true
}

function openWithdrawalSheet(currency?: string): void {
  resetWithdrawalForm(currency)
  withdrawalSheetOpen.value = true
}

function closeContributionSheet(): void {
  contributionSheetOpen.value = false
}

function closeWithdrawalSheet(): void {
  withdrawalSheetOpen.value = false
}

async function loadLatestRate(): Promise<void> {
  try {
    const latest = await fetchLatestFxRate({
      base_currency: 'USD',
      quote_currency: 'UZS',
    })
    latestUsdRate.value = String(latest.rate)
  } catch {
    latestUsdRate.value = '12000'
  }
}

function populateDraftWorkspace(detail: ProcurementDetail): void {
  selectedSupplierId.value = detail.supplier
  draftLines.value = detail.items
    .filter((item) => item.status === 'DRAFT')
    .map((item) => {
      const variant = allVariants.value.find((entry) => entry.id === item.product_variant) ?? {
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
      return {
        id: crypto.randomUUID(),
        serverId: item.id,
        variant,
        quantity: item.quantity,
        cost_per_unit: item.unit_purchase_price,
        currency: normalizeCurrency(item.currency),
        fx_rate: String(item.fx_rate),
      }
    })
  draftExpenses.value = detail.expenses
    .filter((expense) => expense.status === 'DRAFT')
    .map((expense) => ({
      id: crypto.randomUUID(),
      serverId: expense.id,
      expense_type: expense.expense_type as DraftExpenseRow['expense_type'],
      amount: expense.amount,
      currency: normalizeCurrency(expense.currency),
      fx_rate: String(expense.fx_rate),
      allocation_method: expense.allocation_method as DraftExpenseRow['allocation_method'],
      notes: expense.notes ?? '',
    }))
  expandedDraftLineId.value = draftLines.value[0]?.id ?? null
  expandedDraftExpenseId.value = draftExpenses.value[0]?.id ?? null
}

function buildContractPayload(detail: ProcurementDetail) {
  if (!detail.contract) return undefined
  return {
    mudaraba_ratio: detail.contract.mudaraba_ratio,
    planned_budget: detail.contract.planned_budget,
    currency: detail.contract.currency,
    partners: detail.contract.partners.map((partner) => ({
      partner_id: partner.partner,
      role: partner.role,
      planned_capital_share: partner.planned_capital_share,
      profit_share: partner.profit_share,
    })),
  }
}

function validateDraftWorkspace(): string {
  const seenVariantIds = new Set<number>()
  for (const line of draftLines.value) {
    if (!line.variant) return 'Выберите товар в каждой строке'
    if (seenVariantIds.has(line.variant.id)) return 'Один и тот же товар нельзя добавлять дважды'
    seenVariantIds.add(line.variant.id)
    if (parsePositiveNumber(line.quantity) <= 0) return 'Укажите количество'
    if (parsePositiveNumber(line.cost_per_unit) <= 0) return 'Укажите цену закупки'
    if (showFxField(line.currency) && parsePositiveNumber(line.fx_rate) <= 0) return 'Укажите курс для валютной строки товара'
  }
  for (const expense of draftExpenses.value) {
    if (parsePositiveNumber(expense.amount) <= 0) return 'Укажите сумму расхода'
    if (showFxField(expense.currency) && parsePositiveNumber(expense.fx_rate) <= 0) return 'Укажите курс для валютного расхода'
  }
  return ''
}

async function saveDraftWorkspace(): Promise<boolean> {
  if (!procurement.value) return false
  draftError.value = null
  const validation = validateDraftWorkspace()
  if (validation) {
    draftError.value = validation
    toast.error(validation)
    return false
  }

  isSavingDraft.value = true
  try {
    const updated = await updateProcurement(procurement.value.id, {
      procurement_type: procurement.value.procurement_type,
      supplier_id: selectedSupplierId.value,
      notes: procurement.value.notes,
      contract: buildContractPayload(procurement.value),
      items: draftLines.value.map((line) => ({
        product_variant_id: line.variant!.id,
        quantity: parseFloat(line.quantity),
        unit_purchase_price: parseFloat(line.cost_per_unit),
        currency: normalizeCurrency(line.currency),
        fx_rate: showFxField(line.currency) ? line.fx_rate : '1',
      })),
      expenses: draftExpenses.value.map((expense) => ({
        expense_type: expense.expense_type,
        amount: parseFloat(expense.amount),
        currency: normalizeCurrency(expense.currency),
        fx_rate: showFxField(expense.currency) ? expense.fx_rate : '1',
        allocation_method: expense.allocation_method,
        notes: expense.notes.trim(),
      })),
    })
    procurement.value = updated
    populateDraftWorkspace(updated)
    toast.success('Черновики прихода сохранены')
    return true
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось сохранить черновики'
    draftError.value = message
    toast.error(message)
    return false
  } finally {
    isSavingDraft.value = false
  }
}

function sumDraftItemRequirements(): Record<string, number> {
  return draftLines.value.reduce<Record<string, number>>((acc, line) => {
    const currency = normalizeCurrency(line.currency)
    const amount = parsePositiveNumber(line.quantity) * parsePositiveNumber(line.cost_per_unit)
    acc[currency] = (acc[currency] ?? 0) + amount
    return acc
  }, {})
}

function sumDraftExpenseRequirements(): Record<string, number> {
  return draftExpenses.value.reduce<Record<string, number>>((acc, expense) => {
    const currency = normalizeCurrency(expense.currency)
    const amount = parsePositiveNumber(expense.amount)
    acc[currency] = (acc[currency] ?? 0) + amount
    return acc
  }, {})
}

function detectShortfall(requiredByCurrency: Record<string, number>): { currency: string; missing: number } | null {
  if (!procurement.value) return null
  for (const [currency, required] of Object.entries(requiredByCurrency)) {
    const available = Number(procurement.value.balance.balances[currency] ?? '0')
    if (required - available > 0.0001) {
      return {
        currency,
        missing: Number((required - available).toFixed(2)),
      }
    }
  }
  return null
}

function handleShortfall(shortfall: { currency: string; missing: number }, contextLabel: string): void {
  const sourceCurrency = preferredExchangeSourceCurrency(shortfall.currency)
  if (sourceCurrency) {
    toast.error(`Для ${contextLabel} не хватает ${shortfall.currency}. Открыл обмен валют внутри прихода.`)
    openExchangeSheet(shortfall.currency, shortfall.missing)
    focusStage('balance')
    return
  }
  toast.error(`Для ${contextLabel} не хватает ${shortfall.currency}. Открыл пополнение баланса.`)
  openContributionSheet(shortfall.currency)
  focusStage('balance')
}

async function payDraftItemBatch(): Promise<void> {
  if (!procurement.value) return
  if (draftLines.value.length === 0) {
    toast.error('Нет неоплаченных товаров')
    return
  }
  const saved = await saveDraftWorkspace()
  if (!saved) return
  const shortfall = detectShortfall(sumDraftItemRequirements())
  if (shortfall) {
    handleShortfall(shortfall, 'оплаты товаров')
    return
  }
  isPayingItems.value = true
  try {
    await payProcurementItems(procurement.value.id)
    toast.success('Товары оплачены из баланса прихода')
    await loadProcurement()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : 'Не удалось оплатить товары')
  } finally {
    isPayingItems.value = false
  }
}

async function payDraftExpenseBatch(expenseIds?: number[]): Promise<void> {
  if (!procurement.value) return
  if (draftExpenses.value.length === 0) {
    toast.error('Нет неоплаченных расходов')
    return
  }
  const saved = await saveDraftWorkspace()
  if (!saved) return
  const shortfall = detectShortfall(sumDraftExpenseRequirements())
  if (shortfall) {
    handleShortfall(shortfall, 'оплаты расходов')
    return
  }
  isPayingExpenses.value = true
  try {
    await payProcurementExpenses(procurement.value.id, expenseIds && expenseIds.length > 0 ? { expense_ids: expenseIds } : undefined)
    toast.success('Расходы оплачены из баланса прихода')
    await loadProcurement()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : 'Не удалось оплатить расходы')
  } finally {
    isPayingExpenses.value = false
  }
}

async function submitExchange(): Promise<void> {
  if (!procurement.value) return
  exchangeError.value = null
  const fromAmount = parsePositiveNumber(exchangeFromAmount.value)
  const standardRate = parsePositiveNumber(exchangeRate.value)
  const fromCurrency = normalizeCurrency(exchangeFromCurrency.value)
  const toCurrency = normalizeCurrency(exchangeToCurrency.value)
  const pairRate = parsePositiveNumber(pairRateFromStandardRate(fromCurrency, toCurrency, exchangeRate.value))

  if (fromCurrency === toCurrency) {
    exchangeError.value = 'Валюты обмена должны отличаться'
    return
  }
  if (fromAmount <= 0) {
    exchangeError.value = 'Укажите сумму списания'
    return
  }
  if (standardRate <= 0 || pairRate <= 0) {
    exchangeError.value = 'Укажите корректный курс'
    return
  }

  isSavingExchange.value = true
  try {
    await createProcurementBalanceExchange(procurement.value.id, {
      from_currency: fromCurrency,
      from_amount: fromAmount.toFixed(2),
      to_currency: toCurrency,
      rate: pairRate.toFixed(6),
      notes: exchangeNotes.value.trim(),
    })
    toast.success('Обмен валют проведён внутри прихода')
    closeExchangeSheet()
    await loadProcurement()
  } catch (error: unknown) {
    exchangeError.value = error instanceof Error ? error.message : 'Не удалось провести обмен'
    toast.error(exchangeError.value)
  } finally {
    isSavingExchange.value = false
  }
}

async function loadProcurement(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    errorMessage.value = 'Некорректный ID закупки'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = null
  try {
    const detail = await fetchProcurement(id)
    syncStageState(detail, procurement.value === null)
    procurement.value = detail
    populateDraftWorkspace(detail)
    showFullBalanceHistory.value = false
    expandedBalanceHistoryId.value = null
    expandedCostPreviewKey.value = null
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить закупку'
  } finally {
    isLoading.value = false
  }
}

async function loadLocations() {
  const items = await fetchLocations()
  locations.value = items.filter((location) => location.is_active !== false).map((location) => ({ value: location.id, label: location.name }))
  if (selectedWarehouseId.value === null && locations.value.length > 0) {
    selectedWarehouseId.value = locations.value[0].value
  }
}

async function confirmReceipt(): Promise<void> {
  if (!procurement.value || !canReceive.value || selectedWarehouseId.value === null) return

  isConfirming.value = true
  try {
    const updated = await receiveProcurement(procurement.value.id, selectedWarehouseId.value)
    procurement.value = updated
    toast.success('Закупка оприходована')
    await loadProcurement()
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось оприходовать закупку'
    toast.error(message)
  } finally {
    isConfirming.value = false
  }
}

async function submitContribution(): Promise<void> {
  if (!procurement.value) return
  contributionError.value = null
  if (!contributionPartnerId.value) {
    contributionError.value = 'Выберите участника'
    return
  }
  if (parsePositiveNumber(contributionAmount.value) <= 0) {
    contributionError.value = 'Укажите сумму пополнения'
    return
  }
  if (showFxField(contributionCurrency.value) && parsePositiveNumber(contributionFxRate.value) <= 0) {
    contributionError.value = 'Укажите курс для валютного пополнения'
    return
  }

  isSavingContribution.value = true
  try {
    await addProcurementContribution(procurement.value.id, {
      partner_id: contributionPartnerId.value,
      amount: contributionAmount.value,
      currency: normalizeCurrency(contributionCurrency.value),
      fx_rate: showFxField(contributionCurrency.value) ? contributionFxRate.value : '1',
      notes: contributionNotes.value.trim(),
    })
    toast.success('Баланс прихода пополнен')
    closeContributionSheet()
    await loadProcurement()
  } catch (error: unknown) {
    contributionError.value = error instanceof Error ? error.message : 'Не удалось пополнить баланс'
    toast.error(contributionError.value)
  } finally {
    isSavingContribution.value = false
  }
}

async function submitWithdrawal(): Promise<void> {
  if (!procurement.value) return
  withdrawalError.value = null
  if (parsePositiveNumber(withdrawalAmount.value) <= 0) {
    withdrawalError.value = 'Укажите сумму списания'
    return
  }
  if (showFxField(withdrawalCurrency.value) && parsePositiveNumber(withdrawalFxRate.value) <= 0) {
    withdrawalError.value = 'Укажите курс для валютного списания'
    return
  }

  isSavingWithdrawal.value = true
  try {
    await addProcurementWithdrawal(procurement.value.id, {
      amount: withdrawalAmount.value,
      currency: normalizeCurrency(withdrawalCurrency.value),
      fx_rate: showFxField(withdrawalCurrency.value) ? withdrawalFxRate.value : '1',
      reason: withdrawalReason.value.trim(),
    })
    toast.success('Списание из баланса сохранено')
    closeWithdrawalSheet()
    await loadProcurement()
  } catch (error: unknown) {
    withdrawalError.value = error instanceof Error ? error.message : 'Не удалось списать из баланса'
    toast.error(withdrawalError.value)
  } finally {
    isSavingWithdrawal.value = false
  }
}

onMounted(async () => {
  await auth.ensureUserLoaded()
  const [supplierResponse, categoryResponse] = await Promise.all([
    fetchSuppliers(),
    fetchCategories(),
  ])
  suppliers.value = supplierResponse.results
  categories.value = categoryResponse
  await Promise.all([loadProcurement(), loadLocations(), loadLatestRate()])
})
</script>

<template>
  <div class="detail-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Закупка #{{ route.params.id }}</h1>
      <div class="header-spacer" />
    </header>

    <div v-if="isLoading" class="loading-wrap" aria-busy="true">
      <div class="skeleton skeleton-title" />
      <div class="skeleton skeleton-card" />
      <div class="skeleton skeleton-card" />
      <div class="skeleton skeleton-card" />
    </div>

    <div v-else-if="errorMessage" class="error-wrap" role="alert">
      <AlertCircle :size="24" :stroke-width="1.75" />
      <p>{{ errorMessage }}</p>
      <button class="retry-btn" type="button" @click="loadProcurement">Повторить</button>
    </div>

    <template v-else-if="procurement">
      <main class="content">
        <section class="card">
          <div class="row row-between">
            <div class="chips">
              <span class="chip chip-type">{{ typeLabel[procurement.procurement_type as ProcurementType] }}</span>
              <span class="chip" :class="procurement.status === 'RECEIVED' ? 'chip-success' : 'chip-draft'">
                {{ procurementStatusLabel(procurement.status) }}
              </span>
            </div>
            <span class="date">{{ formatDateTime(procurement.opened_at) }}</span>
          </div>
          <div class="stage-pills">
            <button class="stage-pill stage-pill--done" type="button" @click="focusStage('contract')">1. Договор</button>
            <button class="stage-pill stage-pill--active" type="button" @click="focusStage('balance')">2. Баланс</button>
            <button class="stage-pill stage-pill--active" type="button" @click="focusStage('operations')">3. Товары и расходы</button>
            <button class="stage-pill" :class="canReceive ? 'stage-pill--done' : ''" type="button" @click="focusStage('receive')">4. Оприходование</button>
          </div>

          <button v-if="auth.isOwner" class="audit-entry" type="button" @click="openProcurementAudit">
            <span class="audit-entry-icon"><BarChart3 :size="16" :stroke-width="1.75" /></span>
            <span class="audit-entry-copy">
              <strong>Аудит закупки</strong>
              <span>Прибыль, остаток, прогноз и распределение долей</span>
            </span>
          </button>

          <div class="summary-grid">
            <div v-for="item in headerSummaryItems" :key="item.label" class="summary-item">
              <span class="summary-label">{{ item.label }}</span>
              <strong class="summary-value">{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section id="stage-contract" class="card stage-card">
          <button class="stage-card-head" type="button" @click="toggleStage('contract')">
            <div>
              <h2 class="section-title">Договор</h2>
              <p class="stage-summary">{{ contractSummary }}</p>
            </div>
            <ChevronDown class="stage-chevron" :class="{ 'stage-chevron--open': stageState.contract }" :size="18" :stroke-width="2" />
          </button>
          <div v-if="stageState.contract" class="stage-body">
            <div v-if="!procurement.contract || procurement.contract.partners.length === 0" class="muted">
              Для этого типа закупки партнёры не заданы.
            </div>
            <div v-else class="participants">
              <p class="muted">Валюта договора: <strong>{{ procurement.contract.currency }}</strong></p>
              <div v-for="partner in procurement.contract.partners" :key="partner.id" class="participant-row">
                <span class="participant-name">{{ displayPartnerName(partner.partner_name, partner.role) }}</span>
                <span class="participant-share">{{ roleLabel(partner.role) }} · капитал {{ Number(partner.planned_capital_share).toFixed(2) }} {{ procurement.contract.currency }} · прибыль {{ (Number(partner.profit_share) * 100).toFixed(2) }}%</span>
              </div>
            </div>
          </div>
        </section>

        <section id="stage-balance" class="card balance-card stage-card">
          <button class="stage-card-head" type="button" @click="toggleStage('balance')">
            <div>
              <h2 class="section-title">Баланс прихода</h2>
              <p class="stage-summary">{{ balanceSummary }}</p>
            </div>
            <ChevronDown class="stage-chevron" :class="{ 'stage-chevron--open': stageState.balance }" :size="18" :stroke-width="2" />
          </button>

          <div v-if="stageState.balance" class="stage-body">
            <div class="balance-overview">
              <div class="row row-between balance-overview-head">
                <span class="status-pill" :class="balanceStatusKind === 'success' ? 'status-pill--success' : 'status-pill--blocked'">
                  {{ receiveStatusMeta(procurement.receive_plan.status).label }}
                </span>
                <span class="subtle-meta">{{ balanceHistoryEntries.length }} движ.</span>
              </div>

              <div v-if="balanceEntries.length" class="balance-chip-list">
                <span v-for="[currency, amount] in balanceEntries" :key="currency" class="balance-chip">
                  {{ formatPrice(amount, currency) }}
                </span>
              </div>
              <p v-else class="muted">Баланс пока пуст.</p>

              <p class="balance-caption">
                {{ procurement.receive_plan.status === 'NOT_OPEN'
                  ? 'Приход завершён. Ниже показана итоговая картина по балансу и движениям.'
                  : receiveStatusMeta(procurement.receive_plan.status).hint }}
              </p>
            </div>

            <div v-if="balanceParticipantTotals.length" class="balance-block">
              <div class="section-inline-head">
                <strong class="subsection-title">Участники</strong>
                <span class="subtle-meta">{{ balanceParticipantTotals.length }}</span>
              </div>
              <div class="mini-table">
                <div class="mini-table-head">
                  <span>Участник</span>
                  <span>Внёс</span>
                  <span>Нетто</span>
                  <span>Доля</span>
                </div>
                <div class="mini-table-body">
                  <div v-for="item in balanceParticipantTotals" :key="item.partner_id" class="mini-table-row">
                    <div class="mini-table-cell mini-table-cell--main">
                      <strong class="participant-name">{{ displayPartnerName(item.partner_name, item.role) }}</strong>
                      <span class="line-qty">{{ roleLabel(item.role) }}</span>
                    </div>
                    <div class="mini-table-cell">
                      <strong class="tabular-nums">{{ formatCompactAmount(item.contributed_amount, item.contract_currency) }}</strong>
                    </div>
                    <div class="mini-table-cell">
                      <strong class="tabular-nums">{{ formatCompactAmount(item.net_capital, item.contract_currency) }}</strong>
                    </div>
                    <div class="mini-table-cell">
                      <strong class="tabular-nums">{{ formatSharePercent(item.actual_capital_share) }}</strong>
                      <span class="line-qty">профит {{ formatSharePercent(item.planned_profit_share) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="balanceHistoryEntries.length" class="balance-block">
              <div class="section-inline-head">
                <strong class="subsection-title">Движение денег</strong>
                <span class="subtle-meta">{{ balanceHistoryEntries.length }} операций</span>
              </div>
              <div class="money-flow-table">
                <div class="money-flow-head">
                  <span>Тип</span>
                  <span>Операция</span>
                  <span>Сумма</span>
                </div>
                <div class="money-flow-body">
                  <article
                    v-for="entry in visibleBalanceHistoryEntries"
                    :key="entry.id"
                    class="money-flow-row"
                    :class="[
                      balanceHistoryRowClass(entry.kind),
                      { 'money-flow-row--open': expandedBalanceHistoryId === entry.id },
                    ]"
                  >
                    <button class="money-flow-summary" type="button" @click="toggleBalanceHistoryEntry(entry.id)">
                      <span class="money-flow-kind">
                        {{ balanceHistoryKindLabel(entry.kind) }}
                      </span>
                      <div class="money-flow-main">
                        <strong class="participant-name">{{ entry.title }}</strong>
                        <span class="line-qty">
                          {{ formatDateTime(entry.date) }}
                          <template v-if="entry.partner_name"> · {{ displayPartnerName(entry.partner_name, entry.partner_role) }}</template>
                        </span>
                      </div>
                      <strong class="tabular-nums history-amount money-flow-amount" :class="balanceHistoryAmountClass(entry.kind)">
                        {{ balanceHistorySignedAmount(entry.kind, entry.amount, entry.currency) }}
                      </strong>
                      <ChevronDown class="stage-chevron money-flow-chevron" :class="{ 'stage-chevron--open': expandedBalanceHistoryId === entry.id }" :size="16" :stroke-width="2" />
                    </button>
                    <div v-if="expandedBalanceHistoryId === entry.id" class="money-flow-detail">
                      <span v-if="entry.kind === 'EXCHANGE'" class="line-qty">
                        {{ formatCompactAmount(entry.amount, entry.currency) }} -> {{ formatCompactAmount(entry.secondary_amount || '0', entry.secondary_currency) }}
                        · курс {{ formatUsdUzsRate(entry.fx_rate, entry.currency, entry.secondary_currency || entry.currency) }}
                      </span>
                      <span v-else-if="entry.note" class="line-qty">{{ entry.note }}</span>
                      <span v-else class="line-qty">Без дополнительного комментария</span>
                    </div>
                  </article>
                </div>
              </div>
              <button v-if="hasCollapsedBalanceHistory" class="inline-link" type="button" @click="showFullBalanceHistory = !showFullBalanceHistory">
                {{ showFullBalanceHistory ? 'Свернуть историю' : `Показать все ${balanceHistoryEntries.length} операций` }}
              </button>
            </div>

            <div v-if="Object.keys(procurement.receive_plan.missing_spend).length" class="balance-block warning-block">
              <div class="section-inline-head">
                <strong class="subsection-title">Служебная несостыковка</strong>
                <button class="inline-link" type="button" @click="toggleStage('service')">
                  {{ stageState.service ? 'Скрыть' : 'Исправить' }}
                </button>
              </div>
              <div class="compact-inline-list">
                <div v-for="(amount, currency) in procurement.receive_plan.missing_spend" :key="currency" class="compact-inline-item">
                  <span class="participant-name">{{ currency }}</span>
                  <span class="participant-share">не закрыто {{ amount }}</span>
                </div>
              </div>
            </div>

            <div v-if="procurement.receive_plan.suggested_withdrawals.length" class="balance-block">
              <div class="section-inline-head">
                <strong class="subsection-title">Излишек к возврату</strong>
                <span class="subtle-meta">{{ procurement.receive_plan.suggested_withdrawals.length }}</span>
              </div>
              <div class="compact-inline-list">
                <div v-for="item in procurement.receive_plan.suggested_withdrawals" :key="item.partner_id" class="compact-inline-item">
                  <span class="participant-name">{{ item.partner_name }}</span>
                  <span class="participant-share">вернуть {{ item.amount }} {{ item.currency }}</span>
                </div>
              </div>
            </div>

            <div v-if="canManageBalance" class="balance-actions">
              <button class="action-btn" type="button" @click="openContributionSheet()">
                <PlusCircle :size="16" :stroke-width="2" />
                Пополнить
              </button>
              <button class="action-btn action-btn--secondary" type="button" @click="openExchangeSheet()">
                <ArrowRightLeft :size="16" :stroke-width="2" />
                Обменять
              </button>
            </div>

            <div v-if="stageState.service && Object.keys(procurement.receive_plan.missing_spend).length" class="service-actions-card">
              <div class="section-inline-head">
                <strong class="subsection-title">Сервисные действия</strong>
                <span class="subtle-meta">для старых данных</span>
              </div>
              <div class="compact-inline-list">
                <div v-for="(amount, currency) in procurement.receive_plan.missing_spend" :key="`service-${currency}`" class="compact-inline-item">
                  <span class="participant-name">{{ currency }}</span>
                  <button class="inline-link" type="button" @click="openWithdrawalSheet(currency)">
                    Списать {{ amount }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="stage-operations" class="card stage-card">
          <button class="stage-card-head" type="button" @click="toggleStage('operations')">
            <div>
              <h2 class="section-title">Товары и расходы</h2>
              <p class="stage-summary">{{ operationsSummary }}</p>
            </div>
            <ChevronDown class="stage-chevron" :class="{ 'stage-chevron--open': stageState.operations }" :size="18" :stroke-width="2" />
          </button>
          <div v-if="stageState.operations" class="stage-body">
          <p class="muted">Оплаченные позиции остаются ниже как история. Новые позиции можно добавлять и оплачивать по мере работы с приходом.</p>

          <div class="workspace-grid">
            <div class="field-group">
              <label class="field-label">Поставщик</label>
              <div class="inline-field-actions">
                <BaseSelect
                  v-model="selectedSupplierId"
                  :options="supplierOptions"
                  title="Выбор поставщика"
                  placeholder="Без поставщика"
                />
                <button class="action-chip" type="button" @click="openQuickSupplierCreator">
                  <Plus :size="14" :stroke-width="2" />
                  Поставщик
                </button>
              </div>
            </div>

            <div class="workspace-block">
              <div class="workspace-head">
                <div>
                  <h3 class="subsection-title">Товары</h3>
                  <p class="muted">Добавляй позиции, а затем оплачивай их из баланса прихода.</p>
                </div>
              </div>

              <div v-if="paidItems.length" class="paid-block">
                <div class="section-inline-head">
                  <span class="group-label">Оплаченные товары</span>
                  <span class="subtle-meta">{{ paidItems.length }}</span>
                </div>
                <div class="record-table">
                  <div class="record-table-head">
                    <span>Позиция</span>
                    <span>Статус</span>
                    <span>Сумма</span>
                  </div>
                  <div v-for="line in paidItems" :key="line.id" class="record-row record-row--settled">
                    <div class="record-main">
                      <strong class="participant-name">{{ line.product_variant_name }}</strong>
                      <span class="line-qty">{{ paidItemSummary(line) }}</span>
                    </div>
                    <span class="record-status record-status--settled">Оплачено</span>
                    <strong class="tabular-nums record-amount">{{ formatPrice(Number(line.quantity) * Number(line.unit_purchase_price), line.currency) }}</strong>
                  </div>
                </div>
              </div>

              <div v-if="paidItems.length && draftLines.length" class="workspace-separator" />

              <div v-if="draftLines.length" class="draft-block">
                <div class="section-inline-head">
                  <span class="group-label">К оплате</span>
                  <span class="subtle-meta">{{ draftLines.length }}</span>
                </div>
                <div class="record-table">
                  <div class="record-table-head">
                    <span>Позиция</span>
                    <span>Статус</span>
                    <span>Сумма</span>
                  </div>
                  <article
                    v-for="line in draftLines"
                    :key="line.id"
                    class="record-entry"
                    :class="{ 'record-entry--open': expandedDraftLineId === line.id }"
                  >
                    <div class="record-row">
                      <button class="record-row-toggle" type="button" @click="toggleDraftLineExpanded(line.id)">
                        <div class="record-main">
                          <strong class="participant-name">{{ line.variant ? variantDisplay(line.variant) : 'Новый товар' }}</strong>
                          <span class="line-qty">{{ draftLineSummary(line) }}</span>
                        </div>
                        <span class="record-status record-status--draft">Черновик</span>
                        <strong class="tabular-nums record-amount">{{ draftLineTotal(line) }}</strong>
                        <ChevronDown class="stage-chevron record-chevron" :class="{ 'stage-chevron--open': expandedDraftLineId === line.id }" :size="16" :stroke-width="2" />
                      </button>
                      <button class="icon-btn-inline record-row-remove" type="button" aria-label="Удалить строку" @click.stop="removeDraftLine(line.id)">
                        <Trash2 :size="16" :stroke-width="2" />
                      </button>
                    </div>
                    <div v-if="expandedDraftLineId === line.id" class="record-panel">
                      <button class="picker-btn draft-product-btn" :class="{ 'picker-btn--placeholder': !line.variant }" type="button" @click="openVariantPicker(line.id)">
                        {{ line.variant ? variantDisplay(line.variant) : 'Выбрать товар' }}
                      </button>
                      <div class="draft-line-grid">
                        <div class="field-group">
                          <label class="field-label">Кол-во</label>
                          <input
                            :value="line.quantity"
                            class="input-field compact-input"
                            type="number"
                            min="0"
                            placeholder="1"
                            @input="(e) => updateDraftLine(line.id, 'quantity', (e.target as HTMLInputElement).value)"
                          />
                        </div>
                        <div class="field-group">
                          <label class="field-label">Цена</label>
                          <div class="money-field">
                            <input
                              :value="line.cost_per_unit"
                              class="input-field compact-input money-input"
                              type="number"
                              min="0"
                              placeholder="0"
                              @input="(e) => updateDraftLine(line.id, 'cost_per_unit', (e.target as HTMLInputElement).value)"
                            />
                            <button type="button" class="currency-toggle" title="Сменить валюту" @click="toggleDraftLineCurrency(line.id)">
                              <span class="currency-toggle-code">{{ line.currency }}</span>
                              <span class="currency-toggle-hint" aria-hidden="true">
                                <RefreshCcw :size="12" :stroke-width="2" />
                              </span>
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </article>
                </div>
              </div>
              <p v-else-if="paidItems.length === 0" class="muted">Товаров пока нет.</p>

              <div class="workspace-separator" />
              <div class="action-row action-row--double action-row--compact-double">
                <button class="action-chip" type="button" @click="addDraftLine">
                  <Plus :size="14" :stroke-width="2" />
                  Добавить товар
                </button>
                <button class="action-chip" type="button" @click="openQuickProductCreator()">
                  <Plus :size="14" :stroke-width="2" />
                  Создать товар
                </button>
              </div>

              <div v-if="draftLines.length || selectedSupplierId !== procurement.supplier" class="workspace-separator" />

              <div v-if="draftLines.length || selectedSupplierId !== procurement.supplier" class="action-row action-row--double action-row--compact-double">
                <button
                  class="action-btn action-btn--secondary"
                  :class="{ 'action-btn--full': !draftLines.length }"
                  type="button"
                  :disabled="isSavingDraft"
                  @click="saveDraftWorkspace"
                >
                  {{ isSavingDraft ? 'Сохранение…' : 'Сохранить товары' }}
                </button>
                <button v-if="draftLines.length" class="action-btn" type="button" :disabled="isPayingItems || draftLines.length === 0" @click="payDraftItemBatch">
                  {{ isPayingItems ? 'Оплата…' : 'Оплатить товары' }}
                </button>
              </div>
            </div>

            <div class="workspace-block">
              <div class="workspace-head">
                <div>
                  <h3 class="subsection-title">Расходы</h3>
                  <p class="muted">Расход относится ко всему приходу и попадёт в себестоимость при оприходовании.</p>
                </div>
              </div>
              <button class="action-chip action-chip--full" type="button" @click="addDraftExpense">
                  <Plus :size="14" :stroke-width="2" />
                  Добавить расход
              </button>

              <div v-if="paidExpenses.length" class="paid-block">
                <div class="section-inline-head">
                  <span class="group-label">Оплаченные расходы</span>
                  <span class="subtle-meta">{{ paidExpenses.length }}</span>
                </div>
                <div class="record-table">
                  <div class="record-table-head">
                    <span>Расход</span>
                    <span>Статус</span>
                    <span>Сумма</span>
                  </div>
                  <div v-for="expense in paidExpenses" :key="expense.id" class="record-row record-row--settled">
                    <div class="record-main">
                      <strong class="participant-name">{{ expenseTypeLabel[expense.expense_type] ?? expense.expense_type }}</strong>
                      <span class="line-qty">{{ paidExpenseSummary(expense) }}</span>
                    </div>
                    <span class="record-status record-status--settled">Оплачено</span>
                    <strong class="tabular-nums record-amount">{{ formatPrice(Number(expense.amount), expense.currency) }}</strong>
                  </div>
                </div>
              </div>

              <div v-if="paidExpenses.length && draftExpenses.length" class="workspace-separator" />

              <div v-if="draftExpenses.length" class="draft-block">
                <div class="section-inline-head">
                  <span class="group-label">К оплате</span>
                  <span class="subtle-meta">{{ draftExpenses.length }}</span>
                </div>
                <div class="record-table">
                  <div class="record-table-head">
                    <span>Расход</span>
                    <span>Статус</span>
                    <span>Сумма</span>
                  </div>
                  <article
                    v-for="expense in draftExpenses"
                    :key="expense.id"
                    class="record-entry"
                    :class="{ 'record-entry--open': expandedDraftExpenseId === expense.id }"
                  >
                    <div class="record-row">
                      <button class="record-row-toggle" type="button" @click="toggleDraftExpenseExpanded(expense.id)">
                        <div class="record-main">
                          <strong class="participant-name">{{ expenseTypeLabel[expense.expense_type] }}</strong>
                          <span class="line-qty">{{ draftExpenseSummary(expense) }}</span>
                        </div>
                        <span class="record-status record-status--draft">Черновик</span>
                        <strong class="tabular-nums record-amount">{{ draftExpenseAmount(expense) }}</strong>
                        <ChevronDown class="stage-chevron record-chevron" :class="{ 'stage-chevron--open': expandedDraftExpenseId === expense.id }" :size="16" :stroke-width="2" />
                      </button>
                      <button class="icon-btn-inline record-row-remove" type="button" aria-label="Удалить расход" @click.stop="removeDraftExpense(expense.id)">
                        <Trash2 :size="16" :stroke-width="2" />
                      </button>
                    </div>
                    <div v-if="expandedDraftExpenseId === expense.id" class="record-panel">
                      <div class="field-group">
                        <label class="field-label">Тип</label>
                        <BaseSelect
                          :model-value="expense.expense_type"
                          :options="[
                            { value: 'CUSTOMS', label: 'Растаможка' },
                            { value: 'LOGISTICS', label: 'Логистика' },
                            { value: 'FEE', label: 'Комиссия' },
                            { value: 'OTHER', label: 'Другое' },
                          ]"
                          title="Тип расхода"
                          @update:model-value="(value) => updateDraftExpense(expense.id, 'expense_type', String(value))"
                        />
                      </div>
                      <div class="expense-grid-split">
                        <div class="field-group">
                          <label class="field-label">Разносить</label>
                          <BaseSelect
                            :model-value="expense.allocation_method"
                            :options="allocationOptions"
                            title="Метод распределения"
                            @update:model-value="(value) => updateDraftExpense(expense.id, 'allocation_method', String(value))"
                          />
                        </div>
                        <div class="field-group">
                          <label class="field-label">Сумма</label>
                          <div class="money-field">
                            <input
                              :value="expense.amount"
                              class="input-field compact-input money-input"
                              type="number"
                              min="0"
                              placeholder="0"
                              @input="(e) => updateDraftExpense(expense.id, 'amount', (e.target as HTMLInputElement).value)"
                            />
                            <button type="button" class="currency-toggle" title="Сменить валюту" @click="toggleDraftExpenseCurrency(expense.id)">
                              <span class="currency-toggle-code">{{ expense.currency }}</span>
                              <span class="currency-toggle-hint" aria-hidden="true">
                                <RefreshCcw :size="12" :stroke-width="2" />
                              </span>
                            </button>
                          </div>
                        </div>
                      </div>
                      <div class="field-group">
                        <label class="field-label">Комментарий</label>
                        <input
                          :value="expense.notes"
                          class="input-field compact-input"
                          type="text"
                          placeholder="Например, первая часть растаможки"
                          @input="(e) => updateDraftExpense(expense.id, 'notes', (e.target as HTMLInputElement).value)"
                        />
                      </div>
                    </div>
                  </article>
                </div>
              </div>
              <p v-else-if="paidExpenses.length === 0" class="muted">Расходов пока нет.</p>

              <div v-if="draftExpenses.length" class="inline-actions">
                <button
                  class="action-btn action-btn--secondary"
                  :class="{ 'action-btn--full': !draftExpenses.length }"
                  type="button"
                  :disabled="isSavingDraft"
                  @click="saveDraftWorkspace"
                >
                  {{ isSavingDraft ? 'Сохранение…' : 'Сохранить расходы' }}
                </button>
                <button class="action-btn" type="button" :disabled="isPayingExpenses || draftExpenses.length === 0" @click="payDraftExpenseBatch()">
                  {{ isPayingExpenses ? 'Оплата…' : 'Оплатить расходы' }}
                </button>
              </div>
            </div>
          </div>

          <div v-if="draftError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ draftError }}</span>
          </div>

          <div class="divider" />
          <div class="summary-metric-card">
            <span class="summary-label">Сумма добавленных позиций</span>
            <strong class="summary-metric-value tabular-nums">{{ formatPrice(procurementTotal) }}</strong>
            <span class="helper-text">UZS-эквивалент всех сохранённых товаров и расходов этого прихода.</span>
          </div>

          <div v-if="procurement.status === ProcurementStatus.OPEN && costPreviewScenarios.length" class="cost-preview-card">
            <div class="cost-preview-head">
              <strong class="subsection-title">Предварительная себестоимость</strong>
              <p class="muted">{{ procurement.cost_preview.message }}</p>
            </div>

            <div class="cost-preview-list">
              <article
                v-for="scenario in costPreviewScenarios"
                :key="scenario.key"
                class="cost-preview-scenario"
                :class="{ 'cost-preview-scenario--open': expandedCostPreviewKey === scenario.key }"
              >
                <button class="cost-preview-summary" type="button" @click="toggleCostPreviewScenario(scenario.key)">
                  <div class="cost-preview-main">
                    <strong class="participant-name">{{ scenario.label }}</strong>
                    <span class="line-qty">{{ costPreviewScenarioSummary(scenario.basis.items_count, scenario.basis.expenses_count) }}</span>
                  </div>
                  <div class="cost-preview-meta">
                    <span class="cost-preview-chip">Расходы {{ costPreviewScenarioExpenses(scenario.basis.total_expenses_uzs) }}</span>
                  </div>
                  <ChevronDown class="stage-chevron cost-preview-chevron" :class="{ 'stage-chevron--open': expandedCostPreviewKey === scenario.key }" :size="16" :stroke-width="2" />
                </button>

                <div v-if="expandedCostPreviewKey === scenario.key" class="cost-preview-detail">
                  <div class="cost-preview-table">
                    <div class="cost-preview-table-head">
                      <span>Товар</span>
                      <span>Себес./шт</span>
                      <span>Расходы</span>
                    </div>
                    <div
                      v-for="line in scenario.basis.lines"
                      :key="`${scenario.key}-${line.item_id}-${line.status}`"
                      class="cost-preview-line"
                    >
                      <div class="cost-preview-line-main">
                        <strong class="participant-name">{{ line.product_variant_name }}</strong>
                        <span class="line-qty">{{ costPreviewLineSummary(line, scenario.showStatus) }}</span>
                      </div>
                      <div class="cost-preview-line-metric">
                        <strong class="tabular-nums">{{ formatPrice(line.landed_cost_per_unit_uzs) }}</strong>
                      </div>
                      <div class="cost-preview-line-metric">
                        <strong class="tabular-nums">{{ formatPrice(line.allocated_expense_uzs) }}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>
          </div>
        </section>

        <section id="stage-receive" class="card stage-card">
          <button class="stage-card-head" type="button" @click="toggleStage('receive')">
            <div>
              <h2 class="section-title">Оприходование</h2>
            </div>
            <ChevronDown class="stage-chevron" :class="{ 'stage-chevron--open': stageState.receive }" :size="18" :stroke-width="2" />
          </button>
          <div v-if="stageState.receive" class="stage-body">
          <div class="receive-status-line">
            <span
              class="status-pill"
              :class="procurement.status === 'RECEIVED' ? 'status-pill--success' : 'status-pill--blocked'"
            >
              {{ procurementStatusLabel(procurement.status) }}
            </span>
          </div>
          <p class="muted">{{ receiveStatusMeta(procurement.receive_plan.status).hint }}</p>

          <div v-if="receiveBalanceEntries.length" class="receive-balance-inline">
            <span class="summary-label">Остаток баланса</span>
            <div class="receive-balance-inline-values">
              <div v-for="[currency, amount] in receiveBalanceEntries" :key="currency" class="receive-balance-inline-item">
                <span class="receive-currency">{{ currency }}</span>
                <strong class="tabular-nums">{{ formatCompactAmount(amount, currency) }}</strong>
              </div>
            </div>
          </div>

          <div v-if="Object.keys(procurement.receive_plan.missing_spend).length" class="receive-note-line">
            <span class="summary-label">Нужно списать</span>
            <span class="receive-note-value">
              <template v-for="(amount, currency, idx) in procurement.receive_plan.missing_spend" :key="currency">
                <span>{{ currency }} {{ formatCompactAmount(amount, currency) }}</span><span v-if="idx < Object.keys(procurement.receive_plan.missing_spend).length - 1"> · </span>
              </template>
            </span>
          </div>

          <div v-if="procurement.receive_plan.suggested_withdrawals.length" class="receive-note-line">
            <span class="summary-label">К возврату</span>
            <span class="receive-note-value">
              <template v-for="(item, idx) in procurement.receive_plan.suggested_withdrawals" :key="item.partner_id">
                <span>{{ displayPartnerName(item.partner_name, ledgerPartnerRole(item.partner_id)) }} {{ formatCompactAmount(item.amount, item.currency) }}</span><span v-if="idx < procurement.receive_plan.suggested_withdrawals.length - 1"> · </span>
              </template>
            </span>
          </div>

          <p class="muted">
            Баланс прихода хранится отдельно по валютам. Автоматической конвертации между UZS и USD нет.
          </p>
          <div v-if="canConfirm" class="receive-inline-card">
            <p v-if="!canReceive" class="muted">
              Оприходование станет доступно, когда баланс прихода будет сведен по всем валютам.
            </p>
            <BaseSelect
              v-model="selectedWarehouseId"
              :options="locations"
              title="Склад оприходования"
              placeholder="Выберите склад"
            />
            <button
              class="confirm-btn"
              type="button"
              :disabled="isConfirming || !canReceive"
              @click="confirmReceipt"
            >
              <span v-if="isConfirming" class="spinner" />
              <CheckCircle2 v-else :size="18" :stroke-width="2" />
              <span>{{ isConfirming ? 'Оприходование…' : 'Оприходовать закупку' }}</span>
            </button>
          </div>
          </div>
        </section>

        <section v-if="procurement.notes" class="card">
          <h2 class="section-title">Заметки</h2>
          <p class="notes">{{ procurement.notes }}</p>
        </section>
      </main>

      <AppBottomSheet :open="variantSheetOpen" title="Выбор товара" @close="closeVariantPicker">
        <div class="sheet-form">
          <input v-model="variantSearch" class="input-field" type="text" placeholder="Поиск товара" />
          <button class="action-chip" type="button" @click="openQuickProductCreator(activeLineId)">
            <Plus :size="14" :stroke-width="2" />
            Создать товар
          </button>
          <div class="compact-list">
            <button v-for="variant in filteredVariants" :key="variant.id" class="variant-row-btn" type="button" @click="selectVariant(variant)">
              <span>{{ variantDisplay(variant) }}</span>
              <span class="tabular-nums">{{ variant.price ?? variant.effective_price ?? '0' }}</span>
            </button>
          </div>
        </div>
      </AppBottomSheet>

      <AppBottomSheet :open="quickProductSheetOpen" title="Быстрое создание товара" @close="closeQuickProductCreator">
        <form class="sheet-form" @submit.prevent="createQuickProduct">
          <div v-if="quickProductError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ quickProductError }}</span>
          </div>
          <div class="field-group">
            <label class="field-label">Название *</label>
            <input v-model="quickProductName" class="input-field" type="text" placeholder="Например, iPhone 15 Pro" />
          </div>
          <div class="field-group">
            <label class="field-label">Категория</label>
            <BaseSelect
              v-model="quickProductCategoryId"
              :options="[{ value: null, label: 'Без категории' }, ...categoryOptions]"
              title="Категория"
              placeholder="Без категории"
            />
          </div>
          <div class="field-group">
            <label class="field-label">Базовая цена</label>
            <input v-model="quickProductBasePrice" class="input-field" type="number" min="0" placeholder="0" />
          </div>
          <button class="sheet-submit-btn" type="submit" :disabled="isCreatingQuickProduct">
            {{ isCreatingQuickProduct ? 'Создание…' : 'Создать и добавить' }}
          </button>
        </form>
      </AppBottomSheet>

      <AppBottomSheet :open="quickSupplierSheetOpen" title="Быстрое создание поставщика" @close="closeQuickSupplierCreator">
        <form class="sheet-form" @submit.prevent="createQuickSupplier">
          <div v-if="quickSupplierError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ quickSupplierError }}</span>
          </div>
          <div class="field-group">
            <label class="field-label">Название *</label>
            <input v-model="quickSupplierName" class="input-field" type="text" placeholder="Например, Shenzhen Trade Co." />
          </div>
          <div class="field-group">
            <label class="field-label">Телефон</label>
            <input v-model="quickSupplierPhone" class="input-field" type="text" placeholder="+998 90 000 00 00" />
          </div>
          <div class="field-group">
            <label class="field-label">Email</label>
            <input v-model="quickSupplierEmail" class="input-field" type="email" placeholder="supplier@mail.com" />
          </div>
          <button class="sheet-submit-btn" type="submit" :disabled="isCreatingQuickSupplier">
            {{ isCreatingQuickSupplier ? 'Создание…' : 'Создать и выбрать' }}
          </button>
        </form>
      </AppBottomSheet>

      <AppBottomSheet :open="exchangeSheetOpen" title="Обмен валют внутри прихода" @close="closeExchangeSheet">
        <form class="sheet-form" @submit.prevent="submitExchange">
          <div class="field-row field-row--exchange">
            <div class="field-group field-group--exchange">
              <label class="field-label exchange-field-label">
                Списать из валюты <strong class="exchange-label-currency">{{ exchangeFromCurrency }}</strong>
              </label>
              <input v-model="exchangeFromAmount" class="input-field exchange-input" type="number" min="0" placeholder="0" />
              <span class="helper-text exchange-helper-line">
                <span>Доступно:</span>
                <strong class="tabular-nums">{{ formatPlainAmount(selectedExchangeBalance) }}</strong>
              </span>
            </div>

            <div class="exchange-swap-slot">
              <button class="swap-action" type="button" @click="swapExchangeCurrencies">
                <ArrowRightLeft :size="16" :stroke-width="2" />
              </button>
            </div>

            <div class="field-group field-group--exchange">
              <label class="field-label exchange-field-label">
                Зачислить в валюту <strong class="exchange-label-currency">{{ exchangeToCurrency }}</strong>
              </label>
              <input :value="trimTrailingZeros(exchangeToAmountPreview.toFixed(2))" class="input-field exchange-input exchange-input--readonly" type="text" readonly />
            </div>
          </div>

          <div class="field-group">
            <div class="rate-helper-card">
              <div class="rate-helper-main">
                <span class="field-label rate-helper-label">Курс USD -> UZS</span>
                <strong class="tabular-nums rate-helper-value">{{ trimTrailingZeros(exchangeRate) }}</strong>
              </div>
              <button class="text-action" type="button" @click="exchangeRateManualOpen = !exchangeRateManualOpen">
                {{ exchangeRateManualOpen ? 'Скрыть' : 'Изменить курс' }}
              </button>
            </div>
            <input
              v-if="exchangeRateManualOpen"
              v-model="exchangeRate"
              class="input-field"
              type="number"
              min="0"
              step="0.000001"
              placeholder="0"
            />
          </div>

          <div class="field-group">
            <label class="field-label">Комментарий</label>
            <input v-model="exchangeNotes" class="input-field" type="text" placeholder="Например, обмен для растаможки" />
          </div>

          <div v-if="exchangeError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ exchangeError }}</span>
          </div>

          <button class="sheet-submit-btn" type="submit" :disabled="isSavingExchange">
            {{ isSavingExchange ? 'Провожу обмен…' : 'Провести обмен' }}
          </button>
        </form>
      </AppBottomSheet>

      <AppBottomSheet :open="contributionSheetOpen" title="Пополнить баланс прихода" @close="closeContributionSheet">
        <form class="sheet-form" @submit.prevent="submitContribution">
          <div class="field-group">
            <label class="field-label">Кто пополняет</label>
            <BaseSelect
              v-model="contributionPartnerId"
              :options="contributionPartnerOptions"
              title="Выбор участника"
              placeholder="Выберите участника"
            />
          </div>

          <div class="field-group">
            <label class="field-label">Сумма</label>
            <div class="money-field">
              <input v-model="contributionAmount" class="input-field money-input" type="number" min="0" placeholder="0" />
              <button type="button" class="currency-toggle" title="Сменить валюту" @click="toggleContributionCurrency">
                <span class="currency-toggle-code">{{ contributionCurrency }}</span>
                <span class="currency-toggle-hint" aria-hidden="true">
                  <RefreshCcw :size="12" :stroke-width="2" />
                </span>
              </button>
            </div>
          </div>

          <div v-if="showFxField(contributionCurrency)" class="field-group">
            <div class="rate-helper-card">
              <div>
                <label class="field-label">Курс USD -> UZS</label>
                <strong class="tabular-nums">{{ trimTrailingZeros(contributionFxRate) }}</strong>
              </div>
              <button class="text-action" type="button" @click="contributionRateManualOpen = !contributionRateManualOpen">
                {{ contributionRateManualOpen ? 'Скрыть' : 'Изменить курс' }}
              </button>
            </div>
            <input
              v-if="contributionRateManualOpen"
              v-model="contributionFxRate"
              class="input-field"
              type="number"
              min="0"
              step="0.000001"
              placeholder="0"
            />
          </div>

          <div class="field-group">
            <label class="field-label">Комментарий</label>
            <input v-model="contributionNotes" class="input-field" type="text" placeholder="Например, доплата перед receive" />
          </div>

          <div v-if="contributionError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ contributionError }}</span>
          </div>

          <button class="sheet-submit-btn" type="submit" :disabled="isSavingContribution">
            {{ isSavingContribution ? 'Сохраняю…' : 'Сохранить пополнение' }}
          </button>
        </form>
      </AppBottomSheet>

      <AppBottomSheet :open="withdrawalSheetOpen" title="Списать из баланса прихода" @close="closeWithdrawalSheet">
        <form class="sheet-form" @submit.prevent="submitWithdrawal">
          <div class="field-group">
            <label class="field-label">Сумма</label>
            <div class="money-field">
              <input v-model="withdrawalAmount" class="input-field money-input" type="number" min="0" placeholder="0" />
              <button type="button" class="currency-toggle" title="Сменить валюту" @click="toggleWithdrawalCurrency">
                <span class="currency-toggle-code">{{ withdrawalCurrency }}</span>
                <span class="currency-toggle-hint" aria-hidden="true">
                  <RefreshCcw :size="12" :stroke-width="2" />
                </span>
              </button>
            </div>
            <span class="helper-text">Доступно: {{ formatPrice(selectedWithdrawalBalance, withdrawalCurrency) }}</span>
          </div>

          <div v-if="showFxField(withdrawalCurrency)" class="field-group">
            <div class="rate-helper-card">
              <div>
                <label class="field-label">Курс USD -> UZS</label>
                <strong class="tabular-nums">{{ trimTrailingZeros(withdrawalFxRate) }}</strong>
              </div>
              <button class="text-action" type="button" @click="withdrawalRateManualOpen = !withdrawalRateManualOpen">
                {{ withdrawalRateManualOpen ? 'Скрыть' : 'Изменить курс' }}
              </button>
            </div>
            <input
              v-if="withdrawalRateManualOpen"
              v-model="withdrawalFxRate"
              class="input-field"
              type="number"
              min="0"
              step="0.000001"
              placeholder="0"
            />
          </div>

          <div class="field-group">
            <label class="field-label">Назначение</label>
            <input v-model="withdrawalReason" class="input-field" type="text" placeholder="Например, оплата растаможки" />
          </div>

          <div v-if="withdrawalError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ withdrawalError }}</span>
          </div>

          <button class="sheet-submit-btn" type="submit" :disabled="isSavingWithdrawal">
            {{ isSavingWithdrawal ? 'Сохраняю…' : 'Сохранить списание' }}
          </button>
        </form>
      </AppBottomSheet>
    </template>
  </div>
</template>

<style scoped>
.detail-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header { position: sticky; top: 0; z-index: var(--z-sticky); display: flex; align-items: center; gap: var(--space-3); height: var(--header-height); padding: 0 var(--space-4); border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.page-title { flex: 1; font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.back-btn, .header-spacer { width: 40px; height: 40px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-3); padding: var(--space-3); padding-bottom: calc(var(--bottom-nav-height) + var(--space-10)); }
.card, .footer-card { background: var(--color-bg-elevated); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); padding: var(--space-3); }
.balance-card { gap: var(--space-3); }
.row { display:flex; align-items:center; gap: var(--space-2); }
.row-between { justify-content:space-between; }
.chips { display:flex; gap: var(--space-2); }
.stage-pills { display:flex; flex-wrap:wrap; gap: var(--space-2); margin-top: var(--space-3); }
.stage-pill { display:inline-flex; align-items:center; min-height:28px; padding: 0 var(--space-3); border-radius: var(--radius-full); background: var(--color-bg-primary); color: var(--color-text-secondary); border:1px solid var(--color-border-default); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.stage-pill--done { background: var(--color-success-bg); color: var(--color-success); border-color: transparent; }
.stage-pill--active { background: var(--color-brand-50); color: var(--color-brand-700); border-color: transparent; }
.audit-entry { width:100%; display:flex; align-items:center; gap:var(--space-3); min-height:48px; margin-top:var(--space-3); padding:var(--space-2) var(--space-3); border:1px solid var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-bg-primary); color:var(--color-text-primary); text-align:left; }
.audit-entry-icon { width:34px; height:34px; display:inline-flex; align-items:center; justify-content:center; flex-shrink:0; border-radius:var(--radius-md); background:var(--color-brand-50); color:var(--color-brand-600); }
.audit-entry-copy { min-width:0; display:grid; gap:2px; }
.audit-entry-copy strong { font-size:var(--text-sm); font-weight:var(--font-semibold); }
.audit-entry-copy span { font-size:var(--text-xs); color:var(--color-text-secondary); line-height:var(--leading-normal); }
.stage-card { display:grid; gap: var(--space-2); }
.stage-card-head { display:flex; align-items:flex-start; justify-content:space-between; gap: var(--space-3); text-align:left; }
.stage-summary { color: var(--color-text-secondary); font-size: var(--text-sm); }
.stage-body { display:grid; gap: var(--space-2); }
.stage-chevron { color: var(--color-text-secondary); transition: transform .2s ease; }
.stage-chevron--open { transform: rotate(180deg); }
.chip { display:inline-flex; align-items:center; border-radius: var(--radius-full); padding: 0 var(--space-2); min-height:22px; font-size: var(--text-xs); font-weight: var(--font-semibold); }
.chip-type { background: var(--color-brand-50); color: var(--color-brand-700); }
.chip-success { background: var(--color-success-bg); color: var(--color-success); }
.chip-draft { background: var(--color-bg-sunken); color: var(--color-text-secondary); }
.date, .meta, .muted, .participant-share { color: var(--color-text-secondary); font-size: var(--text-sm); }
.meta { margin-top: var(--space-3); }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); margin-bottom: 0; }
.summary-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); margin-top: var(--space-3); }
.summary-item:last-child { grid-column: 1 / -1; }
.summary-item { display:grid; gap: 2px; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); }
.summary-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.summary-value { color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.participants, .lines { display:grid; gap: var(--space-2); }
.participant-row, .line-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.participant-name, .line-name { font-weight: var(--font-medium); color: var(--color-text-primary); }
.balance-card-head { align-items: flex-start; }
.status-pill { display:inline-flex; align-items:center; min-height:28px; padding: 0 var(--space-3); border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: var(--font-semibold); white-space: nowrap; }
.status-pill--success { background: var(--color-success-bg); color: var(--color-success); }
.status-pill--blocked { background: var(--color-warning-bg, var(--color-brand-50)); color: var(--color-warning, var(--color-brand-700)); }
.balance-overview { display:grid; gap: var(--space-2); padding-bottom: var(--space-2); border-bottom: 1px solid var(--color-border-subtle); }
.balance-overview-head { align-items: center; }
.balance-caption { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: var(--leading-normal); }
.subtle-meta { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.balance-chip-list { display:flex; flex-wrap:wrap; gap: 6px; }
.balance-chip { display:inline-flex; align-items:center; min-height:28px; padding: 0 10px; border-radius: var(--radius-full); border:1px solid var(--color-border-default); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-medium); }
.balance-block { display:grid; gap: var(--space-2); }
.section-inline-head { display:flex; align-items:center; justify-content:space-between; gap: var(--space-2); }
.mini-table,
.money-flow-table,
.record-table { display:grid; gap: 0; border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); overflow:hidden; }
.mini-table-head,
.money-flow-head,
.record-table-head { display:grid; align-items:center; gap: var(--space-2); padding: 10px var(--space-3); background: var(--color-bg-sunken); color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.mini-table-head,
.mini-table-row { grid-template-columns: minmax(0, 1.1fr) repeat(3, minmax(0, 0.8fr)); }
.record-table-head { grid-template-columns: minmax(0, 1fr) auto auto; }
.record-table-head span:nth-child(2),
.record-table-head span:nth-child(3) { justify-self: end; }
.mini-table-row { display:grid; align-items:center; gap: var(--space-2); padding: var(--space-3); border-top: 1px solid var(--color-border-subtle); }
.mini-table-cell { min-width: 0; display:grid; gap: 2px; }
.mini-table-cell--main { align-content: start; }
.money-flow-head { grid-template-columns: 86px minmax(0, 1fr) auto; }
.money-flow-row { border-top: 1px solid var(--color-border-subtle); }
.money-flow-row--in { box-shadow: inset 3px 0 0 var(--color-success); }
.money-flow-row--out { box-shadow: inset 3px 0 0 var(--color-error); }
.money-flow-row--exchange { box-shadow: inset 3px 0 0 var(--color-brand-500); }
.money-flow-summary { width:100%; display:grid; grid-template-columns: 86px minmax(0, 1fr) auto 16px; align-items:center; gap: var(--space-3); padding: var(--space-3); text-align:left; }
.money-flow-kind { display:inline-flex; align-items:center; justify-content:center; min-height:26px; padding: 0 var(--space-2); border-radius: var(--radius-full); border:1px solid transparent; font-size: var(--text-xs); font-weight: var(--font-semibold); }
.money-flow-row--in .money-flow-kind { background: var(--color-success-bg); color: var(--color-success); }
.money-flow-row--out .money-flow-kind { background: var(--color-error-bg); color: var(--color-error); }
.money-flow-row--exchange .money-flow-kind { background: var(--color-brand-50); color: var(--color-brand-700); }
.money-flow-main { min-width: 0; display:grid; gap: 4px; }
.money-flow-amount { white-space: nowrap; }
.money-flow-detail { display:grid; gap: 4px; padding: 0 var(--space-3) var(--space-3) calc(var(--space-3) + 98px); }
.money-flow-chevron { justify-self: end; }
.compact-inline-list { display:grid; gap: 6px; }
.compact-inline-item { display:flex; align-items:flex-start; justify-content:space-between; gap: var(--space-3); }
.warning-block { padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-warning-bg, var(--color-brand-50)); }
.service-actions-card { display:grid; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-md); border:1px dashed var(--color-border-default); background: var(--color-bg-primary); }
.subsection-title { color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.inline-actions { margin-top: var(--space-3); display:flex; flex-wrap:wrap; gap: var(--space-2); }
.inline-actions--compact { margin-top: 0; align-items:center; }
.text-action { display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-medium); }
.inline-field-actions { display:grid; gap: var(--space-2); }
.action-row { display:grid; gap: var(--space-2); margin-top: var(--space-2); }
.action-row--double { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.action-row--compact-double { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.balance-actions { display:flex; flex-wrap:wrap; gap: var(--space-2); }
.action-btn { min-height: 40px; width:100%; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); padding: 0 var(--space-3); border-radius: var(--radius-md); background: var(--color-brand-500); color: var(--color-text-inverse); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.action-btn--secondary { background: var(--color-bg-primary); color: var(--color-brand-700); border:1px solid var(--color-border-default); }
.action-btn--full { grid-column: 1 / -1; }
.action-chip { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-1); padding: 0 var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-brand-700); border:1px solid var(--color-border-default); font-size: var(--text-sm); font-weight: var(--font-medium); }
.action-chip--full { width: 100%; margin-top: var(--space-2); }
.inline-link { color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.line-main { display:flex; flex-direction:column; gap: 2px; }
.line-qty { font-size: var(--text-sm); color: var(--color-text-secondary); }
.divider { height: 1px; background: var(--color-border-subtle); margin: var(--space-3) 0; }
.workspace-head { display:grid; gap: var(--space-2); }
.workspace-separator { height: 1px; background: var(--color-border-subtle); margin: var(--space-1) 0; }
.group-label { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); text-transform: uppercase; letter-spacing: .02em; }
.draft-block, .paid-block { display:grid; gap: var(--space-2); }
.total-row { font-size: var(--text-base); }
.notes { color: var(--color-text-secondary); line-height: var(--leading-normal); }
.workspace-grid { display:grid; gap: var(--space-4); }
.workspace-block { display:grid; gap: var(--space-3); padding-top: var(--space-2); }
.picker-btn { width:100%; min-height:40px; display:flex; align-items:center; justify-content:flex-start; padding: var(--space-2) var(--space-3); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); }
.picker-btn--placeholder { color: var(--color-text-secondary); }
.draft-product-btn { min-height:40px; }
.icon-btn-inline { width: 36px; height: 36px; display:inline-flex; align-items:center; justify-content:center; border-radius: var(--radius-md); color: var(--color-brand-600); }
.record-entry { border-top: 1px solid var(--color-border-subtle); }
.record-row { display:grid; grid-template-columns: minmax(0, 1fr) 36px; gap: var(--space-1); align-items:start; }
.record-row--settled { grid-template-columns: minmax(0, 1fr) auto auto; gap: var(--space-3); align-items:center; padding: var(--space-3); border-top: 1px solid var(--color-border-subtle); }
.record-row-toggle { width:100%; display:grid; grid-template-columns: minmax(0, 1fr) auto auto 16px; align-items:center; gap: var(--space-3); padding: var(--space-3); text-align:left; }
.record-main { min-width: 0; display:grid; gap: 4px; }
.record-status { display:inline-flex; align-items:center; justify-content:center; min-height: 24px; padding: 0 var(--space-2); border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: var(--font-semibold); white-space: nowrap; }
.record-status--settled { background: var(--color-success-bg); color: var(--color-success); }
.record-status--draft { background: var(--color-bg-elevated); color: var(--color-text-secondary); border:1px solid var(--color-border-default); }
.record-amount { white-space: nowrap; justify-self: end; }
.record-chevron { justify-self: end; }
.record-row-remove { margin-top: var(--space-3); margin-right: var(--space-2); }
.record-panel { display:grid; gap: var(--space-3); padding: 0 var(--space-3) var(--space-3); border-top: 1px dashed var(--color-border-subtle); background: var(--color-bg-elevated); }
.draft-line-grid { display:grid; grid-template-columns: minmax(84px, 0.7fr) minmax(0, 1.3fr); gap: var(--space-2); }
.compact-input { min-height: 40px; }
.paid-block { display:grid; gap: var(--space-2); padding-top: var(--space-2); }
.compact-list { display:grid; gap: var(--space-2); }
.compact-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.compact-row--stacked { align-items:flex-start; flex-direction:column; }
.history-amount--in { color: var(--color-success); }
.history-amount--out { color: var(--color-error); }
.history-amount--exchange { color: var(--color-brand-700); }
.cost-preview-card { display:grid; gap: var(--space-3); padding-top: var(--space-2); }
.cost-preview-head { display:grid; gap: 4px; }
.cost-preview-list { display:grid; gap: var(--space-2); }
.cost-preview-scenario { border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); overflow:hidden; }
.cost-preview-summary { width:100%; display:grid; grid-template-columns: minmax(0, 1fr) auto 16px; align-items:center; gap: var(--space-3); padding: var(--space-3); text-align:left; }
.cost-preview-main { min-width: 0; display:grid; gap: 4px; }
.cost-preview-meta { display:flex; justify-content:flex-end; }
.cost-preview-chip { display:inline-flex; align-items:center; min-height:26px; padding: 0 var(--space-2); border-radius: var(--radius-full); background: var(--color-bg-elevated); color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); white-space: nowrap; }
.cost-preview-chevron { justify-self: end; }
.cost-preview-detail { padding: 0 var(--space-3) var(--space-3); border-top: 1px dashed var(--color-border-subtle); background: var(--color-bg-elevated); }
.cost-preview-table { display:grid; gap: 0; border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); overflow:hidden; }
.cost-preview-table-head,
.cost-preview-line { display:grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr) minmax(0, 0.8fr); gap: var(--space-2); align-items:center; }
.cost-preview-table-head { padding: 10px var(--space-3); background: var(--color-bg-sunken); color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.cost-preview-line { padding: var(--space-3); border-top: 1px solid var(--color-border-subtle); }
.cost-preview-line-main,
.cost-preview-line-metric { min-width: 0; display:grid; gap: 4px; }
.cost-preview-line-metric { justify-items: end; text-align: right; }
.summary-metric-card { display:grid; gap: 4px; padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.summary-metric-value { color: var(--color-text-primary); font-size: var(--text-lg); font-weight: var(--font-semibold); }
.receive-status-line { display:flex; align-items:center; justify-content:space-between; gap: var(--space-2); }
.receive-balance-inline { display:grid; gap: var(--space-2); }
.receive-balance-inline-values { display:flex; flex-wrap:wrap; gap: 0; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); overflow: hidden; }
.receive-balance-inline-item { flex: 1 1 160px; min-height: 44px; display:flex; align-items:center; justify-content:space-between; gap: var(--space-2); padding: 0 var(--space-3); border-right: 1px solid var(--color-border-subtle); }
.receive-balance-inline-item:last-child { border-right: 0; }
.receive-currency { color: var(--color-text-secondary); font-size: var(--text-sm); font-weight: var(--font-medium); }
.receive-note-line { display:grid; gap: 2px; }
.receive-note-value { color: var(--color-text-primary); font-size: var(--text-sm); }
.expense-grid-split { display:grid; grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); gap: var(--space-2); }
.variant-row-btn { width:100%; display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); text-align:left; }
.field-group { display:grid; gap: var(--space-2); }
.field-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px minmax(0, 1fr);
  gap: var(--space-2);
  align-items: start;
}
.field-row .field-group { min-width: 0; }
.field-row--exchange { grid-template-columns: minmax(0, 1fr) 44px minmax(0, 1fr); gap: 6px; }
.field-group--exchange { min-width: 0; gap: 6px; }
.exchange-field-label { display:flex; align-items:center; gap: 4px; min-height: 20px; }
.exchange-label-currency { color: var(--color-text-primary); font-weight: var(--font-semibold); }
.exchange-input {
  min-height: 44px;
  padding: 0 12px;
  font-size: var(--text-base);
  font-variant-numeric: tabular-nums;
}
.exchange-input--readonly { background: var(--color-bg-primary); }
.exchange-helper-line { display:flex; align-items:center; gap: 4px; white-space: nowrap; }
.exchange-swap-slot { display:flex; justify-content:center; padding-top: 28px; }
.field-label, .helper-text { color: var(--color-text-secondary); font-size: var(--text-sm); }
.rate-helper-card { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.rate-helper-main { display:grid; gap: 4px; min-width: 0; }
.rate-helper-label { line-height: 1.2; }
.rate-helper-value { color: var(--color-text-primary); font-size: var(--text-lg); line-height: 1.1; letter-spacing: 0; }
.input-field { width: 100%; min-height: 48px; padding: 0 var(--space-4); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); }
.money-field { position: relative; }
.money-field--readonly .input-field { background: var(--color-bg-sunken); }
.money-input { padding-right: 98px; }
.currency-toggle { position: absolute; top: 50%; right: 6px; transform: translateY(-50%); height: 34px; display:inline-flex; align-items:center; justify-content:center; gap: 6px; padding: 0 8px 0 10px; border-radius: calc(var(--radius-md) - 2px); border:1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-text-primary); font-weight: var(--font-semibold); }
.currency-toggle-code { font-size: var(--text-sm); line-height: 1; }
.currency-toggle-hint { width: 18px; height: 18px; display:inline-flex; align-items:center; justify-content:center; border-radius: 999px; background: var(--color-brand-50); color: var(--color-brand-700); border: 1px solid var(--color-brand-100); flex: 0 0 auto; }
.swap-action { width: 44px; height: 44px; display:inline-flex; align-items:center; justify-content:center; border-radius: var(--radius-md); border:1px solid var(--color-border-default); background: var(--color-bg-primary); color: var(--color-brand-700); }
.sheet-form { display:grid; gap: var(--space-3); padding-bottom: var(--space-4); }
.sheet-submit-btn { width:100%; height: 48px; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
.loading-wrap, .error-wrap, .state-box { display:grid; gap: var(--space-3); place-items:center; text-align:center; padding: var(--space-12) var(--space-6); }
.skeleton { border-radius: var(--radius-md); background: linear-gradient(90deg, var(--color-bg-secondary) 25%, var(--color-bg-sunken) 50%, var(--color-bg-secondary) 75%); background-size: 200% 100%; animation: shimmer 1.5s linear infinite; }
.skeleton-title { width: 50%; height: 20px; }
.skeleton-card { width: 100%; height: 96px; }
.retry-btn, .confirm-btn { height: 44px; padding: 0 var(--space-4); border-radius: var(--radius-md); background: var(--color-brand-500); color: var(--color-text-inverse); display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); }
.receive-inline-card { display:grid; gap: var(--space-3); padding-top: var(--space-2); }
.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.35); border-top-color: #fff; border-radius: 9999px; animation: spin .8s linear infinite; }
@media (max-width: 520px) {
  .summary-grid { grid-template-columns: 1fr; }
  .summary-item:last-child { grid-column: auto; }
  .balance-card-head,
  .participant-row,
  .line-row { align-items: flex-start; flex-direction: column; }
  .section-inline-head,
  .compact-inline-item,
  .balance-overview-head { align-items:flex-start; flex-direction: column; }
  .record-table-head,
  .money-flow-head,
  .cost-preview-table-head { display:none; }
  .money-flow-summary,
  .record-row-toggle {
    grid-template-columns: minmax(0, 1fr) auto 16px;
    align-items: start;
  }
  .money-flow-kind,
  .record-status {
    grid-column: 1;
    grid-row: 2;
    justify-self: start;
  }
  .money-flow-amount,
  .record-amount {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: center;
  }
  .money-flow-chevron,
  .record-chevron {
    grid-column: 3;
    grid-row: 1 / span 2;
    align-self: center;
  }
  .money-flow-detail { padding-left: var(--space-3); }
  .cost-preview-summary {
    grid-template-columns: minmax(0, 1fr) 16px;
    align-items: start;
  }
  .cost-preview-meta {
    grid-column: 1;
    justify-content: flex-start;
  }
  .cost-preview-chevron {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: center;
  }
  .cost-preview-line {
    grid-template-columns: 1fr;
    align-items: start;
  }
  .cost-preview-line-metric { justify-items: start; text-align: left; }
  .compact-row { align-items: flex-start; }
  .balance-actions { display:grid; grid-template-columns: 1fr; }
  .action-row--double,
  .expense-grid-split { grid-template-columns: 1fr; }
  .action-row--compact-double { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .field-row--exchange {
    grid-template-columns: minmax(0, 1fr) 42px minmax(0, 1fr);
    gap: 4px;
    align-items: start;
  }
  .receive-status-line { align-items:flex-start; flex-direction:column; }
  .receive-balance-inline-item { flex-basis: 100%; border-right: 0; border-top: 1px solid var(--color-border-subtle); }
  .receive-balance-inline-item:first-child { border-top: 0; }
  .exchange-field-label { font-size: var(--text-xs); }
  .exchange-input {
    min-height: 42px;
    padding: 0 10px;
    font-size: var(--text-sm);
  }
  .exchange-helper-line {
    gap: 3px;
    font-size: var(--text-xs);
  }
  .rate-helper-card {
    align-items: flex-start;
  }
  .rate-helper-value {
    font-size: var(--text-base);
  }
  .exchange-swap-slot { padding-top: 24px; }
  .swap-action {
    width: 42px;
    height: 42px;
  }
}
@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
