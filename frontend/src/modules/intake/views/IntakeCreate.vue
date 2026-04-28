<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Wallet, Handshake, Users, AlertCircle, Plus, Trash2, UserPlus, ChevronDown, RefreshCcw } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useIdempotency } from '@/composables/useIdempotency'
import { formatPrice } from '@/utils/currency'
import { PricingMode, ProcurementType } from '@/types/enums'
import type { Category, Product, ProductVariant, Supplier } from '@/types/models'
import { createSupplier, fetchSuppliers } from '@/api/suppliers'
import { createProduct, fetchCategories, fetchProductVariants, fetchVariantsPaginated } from '@/api/catalog'
import {
  createProcurement,
  fetchInvestmentAgreement,
  fetchProcurement,
  updateProcurement,
  type InvestmentAgreementDetail,
  type ProcurementDetail,
} from '@/api/partnerships'
import { fetchPartners, type Partner } from '@/api/core'
import { fetchLatestFxRate } from '@/api/finance'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { generateRequestId } = useIdempotency()

interface TypeCard {
  type: ProcurementType
  label: string
  description: string
  icon: typeof Wallet
  disabled?: boolean
}

const TYPE_CARDS: TypeCard[] = [
  {
    type: ProcurementType.OWN_FUNDS,
    label: 'Свои деньги',
    description: 'Рабочий путь без партнёрского контракта',
    icon: Wallet,
  },
  {
    type: ProcurementType.PARTNERSHIP,
    label: 'Партнёрский',
    description: 'Капитал и прибыль по договорённости партнёров',
    icon: Handshake,
  },
  {
    type: ProcurementType.MUSHARAKA,
    label: 'Мушарака',
    description: 'Прибыль следует долям капитала',
    icon: Users,
  },
]

const EXPENSE_TYPE_OPTIONS = [
  { value: 'CUSTOMS', label: 'Растаможка' },
  { value: 'LOGISTICS', label: 'Логистика' },
  { value: 'FEE', label: 'Комиссия' },
  { value: 'OTHER', label: 'Другое' },
]

const ALLOCATION_OPTIONS = [
  { value: 'BY_VALUE', label: 'По стоимости' },
  { value: 'BY_QUANTITY', label: 'По количеству' },
]

const FALLBACK_FOREIGN_FX_RATE = '12100'

const selectedType = ref<ProcurementType>(ProcurementType.OWN_FUNDS)
const selectedSupplierId = ref<number | null>(null)
const notes = ref('')
const suppliers = ref<Supplier[]>([])
const categories = ref<Category[]>([])
const allVariants = ref<ProductVariant[]>([])
const partners = ref<Partner[]>([])
const isLoadingRefs = ref(false)
const isSaving = ref(false)
const formError = ref<string | null>(null)
const isLoadingDraft = ref(false)
const linkedAgreement = ref<InvestmentAgreementDetail | null>(null)
const editingAgreementId = ref<number | null>(null)
const simulatedInvestorCapitalPercentDraft = ref('')
const isRecalculationOpen = ref(false)
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
const latestUsdRate = ref(FALLBACK_FOREIGN_FX_RATE)
const contractCurrency = ref('USD')
const plannedBudget = ref('')

const editingProcurementId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) ? raw : null
})
const isEditMode = computed(() => editingProcurementId.value !== null)
const linkedAgreementId = computed(() => {
  const raw = Number(route.query.agreement_id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})
const isLinkedAgreementMode = computed(() => linkedAgreementId.value !== null && !isEditMode.value)

interface LineRow {
  id: string
  variant: ProductVariant | null
  quantity: string
  cost_per_unit: string
  currency: string
  fx_rate: string
}

const lines = ref<LineRow[]>([])
const variantSheetOpen = ref(false)
const activeLineId = ref<string | null>(null)
const variantSearch = ref('')
const variantSearchCategory = ref<number | null>(null)

interface ExpenseRow {
  id: string
  expense_type: 'CUSTOMS' | 'LOGISTICS' | 'FEE' | 'OTHER'
  amount: string
  currency: string
  fx_rate: string
  allocation_method: 'BY_VALUE' | 'BY_QUANTITY'
  notes: string
}

interface ContractRow {
  id: string
  partner_id: number | null
  role: 'INVESTOR' | 'OPERATOR'
  capital_percent: string
  profit_percent: string
}

function buildEmptyLine(): LineRow {
  return {
    id: crypto.randomUUID(),
    variant: null,
    quantity: '1',
    cost_per_unit: '',
    currency: 'UZS',
    fx_rate: '1',
  }
}

function buildEmptyExpense(): ExpenseRow {
  return {
    id: crypto.randomUUID(),
    expense_type: 'CUSTOMS',
    amount: '',
    currency: 'UZS',
    fx_rate: '1',
    allocation_method: 'BY_VALUE',
    notes: '',
  }
}

const expenses = ref<ExpenseRow[]>([])
const contractRows = ref<ContractRow[]>([
  { id: crypto.randomUUID(), partner_id: null, role: 'INVESTOR', capital_percent: '50', profit_percent: '50' },
  { id: crypto.randomUUID(), partner_id: null, role: 'OPERATOR', capital_percent: '50', profit_percent: '50' },
])

function addEmptyLine(): void {
  lines.value = [...lines.value, buildEmptyLine()]
}

function removeLine(rowId: string): void {
  lines.value = lines.value.filter((line) => line.id !== rowId)
}

function addExpense(): void {
  expenses.value = [...expenses.value, buildEmptyExpense()]
}

function removeExpense(rowId: string): void {
  expenses.value = expenses.value.filter((expense) => expense.id !== rowId)
}

function updateLine(rowId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null): void {
  lines.value = lines.value.map((line) => line.id === rowId ? { ...line, [field]: value } : line)
}

function updateExpense(rowId: string, field: keyof Omit<ExpenseRow, 'id'>, value: string): void {
  expenses.value = expenses.value.map((expense) => expense.id === rowId ? { ...expense, [field]: value } as ExpenseRow : expense)
}

function updateContractRow(rowId: string, field: keyof Omit<ContractRow, 'id'>, value: string | number | null): void {
  contractRows.value = contractRows.value.map((row) => row.id === rowId ? { ...row, [field]: value } as ContractRow : row)
}

type ContractEditableField = 'partner_id' | 'capital_percent' | 'profit_percent'

function updateContractRole(role: ContractRow['role'], field: ContractEditableField, value: string | number | null): void {
  const row = contractRows.value.find((item) => item.role === role)
  if (!row) return
  updateContractRow(row.id, field, value)
}

function normalizeCurrency(value: unknown): string {
  const currency = String(value ?? 'UZS').trim().toUpperCase()
  if (currency === 'USD') return 'USD'
  return 'UZS'
}

function defaultFxRateForCurrency(currency: string): string {
  return normalizeCurrency(currency) === 'UZS' ? '1' : latestUsdRate.value
}

function nextCurrency(currency: string): string {
  return normalizeCurrency(currency) === 'UZS' ? 'USD' : 'UZS'
}

function parsePositiveNumber(raw: unknown): number {
  const value = Number.parseFloat(String(raw ?? ''))
  if (!Number.isFinite(value) || value <= 0) return 0
  return value
}

function getFxRateValue(currency: string, raw: unknown): number {
  if (normalizeCurrency(currency) === 'UZS') return 1
  return parsePositiveNumber(raw)
}

function moneyAmountToUzs(amount: number, currency: string, fxRate: unknown): number {
  const normalizedCurrency = normalizeCurrency(currency)
  if (!Number.isFinite(amount) || amount <= 0) return 0
  if (normalizedCurrency === 'UZS') return amount
  return amount * getFxRateValue(normalizedCurrency, fxRate)
}

function setLineCurrency(rowId: string, currencyValue: string | number | boolean | null): void {
  const currency = normalizeCurrency(currencyValue)
  lines.value = lines.value.map((line) => line.id === rowId
    ? {
        ...line,
        currency,
        fx_rate: currency === line.currency
          ? line.fx_rate
          : currency === 'UZS'
            ? '1'
            : defaultFxRateForCurrency(currency),
      }
    : line)
}

function toggleLineCurrency(rowId: string): void {
  const line = lines.value.find((item) => item.id === rowId)
  if (!line) return
  setLineCurrency(rowId, nextCurrency(line.currency))
}

function setExpenseCurrency(rowId: string, currencyValue: string | number | boolean | null): void {
  const currency = normalizeCurrency(currencyValue)
  expenses.value = expenses.value.map((expense) => expense.id === rowId
    ? {
        ...expense,
        currency,
        fx_rate: currency === expense.currency
          ? expense.fx_rate
          : currency === 'UZS'
            ? '1'
            : defaultFxRateForCurrency(currency),
      }
    : expense)
}

async function loadLatestUsdRate(): Promise<void> {
  try {
    const rate = await fetchLatestFxRate({
      base_currency: 'USD',
      quote_currency: 'UZS',
    })
    if (parsePositiveNumber(rate.rate) > 0) {
      latestUsdRate.value = String(rate.rate)
    }
  } catch {
    latestUsdRate.value = FALLBACK_FOREIGN_FX_RATE
  }
}

function toggleExpenseCurrency(rowId: string): void {
  const expense = expenses.value.find((item) => item.id === rowId)
  if (!expense) return
  setExpenseCurrency(rowId, nextCurrency(expense.currency))
}

function showFxField(currency: string): boolean {
  return normalizeCurrency(currency) !== 'UZS'
}

function formatCurrencyTotalLabel(currency: string): string {
  return normalizeCurrency(currency) === 'USD' ? 'USD -> UZS' : 'UZS'
}

function formatEditablePercent(value: number): string {
  return Number(value.toFixed(4)).toString()
}

function updatePairPercent(role: ContractRow['role'], field: 'capital_percent' | 'profit_percent', rawValue: string): void {
  const peerRole: ContractRow['role'] = role === 'INVESTOR' ? 'OPERATOR' : 'INVESTOR'
  const trimmedValue = rawValue.trim()

  if (trimmedValue === '') {
    contractRows.value = contractRows.value.map((row) => {
      if (row.role === role) return { ...row, [field]: '' }
      if (row.role === peerRole) return { ...row, [field]: '100' }
      return row
    })
    return
  }

  const parsedValue = Number.parseFloat(trimmedValue)
  if (!Number.isFinite(parsedValue)) return

  const currentValue = formatEditablePercent(clampPercent(parsedValue))
  const peerValue = formatEditablePercent(100 - Number.parseFloat(currentValue))

  contractRows.value = contractRows.value.map((row) => {
    if (row.role === role) return { ...row, [field]: currentValue }
    if (row.role === peerRole) return { ...row, [field]: peerValue }
    return row
  })
}

function openInvestorInvitePage(): void {
  router.push({ name: 'owner-investors' })
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
    quickProductError.value = 'Введите название товара'
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
      quickProductError.value = 'Товар создан, но вариант не найден'
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

    toast.success('Товар создан и добавлен в приход')
    closeQuickProductCreator()
  } catch (error: unknown) {
    const apiError = error as { response?: { data?: { detail?: string; name?: string[] } } }
    quickProductError.value = apiError.response?.data?.detail
      ?? apiError.response?.data?.name?.[0]
      ?? 'Не удалось создать товар'
  } finally {
    isCreatingQuickProduct.value = false
  }
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
    const apiError = error as { response?: { data?: { detail?: string; name?: string[] } } }
    quickSupplierError.value = apiError.response?.data?.detail
      ?? apiError.response?.data?.name?.[0]
      ?? 'Не удалось создать поставщика'
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
    toast.error('Этот товар уже добавлен в закупку')
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

const supplierOptions = computed(() => suppliers.value.map((supplier) => ({ value: supplier.id, label: supplier.name })))
const categoryOptions = computed(() => categories.value.map((category) => ({ value: category.id, label: category.name })))
const investorOptions = computed(() => partners.value.filter((partner) => partner.role === 'INVESTOR').map((partner) => ({ value: partner.id, label: partner.display_name })))
const hasLinkedInvestors = computed(() => investorOptions.value.length > 0)

const grandTotal = computed(() => lines.value.reduce((sum, line) => {
  const lineAmount = (parseFloat(line.quantity) || 0) * (parseFloat(line.cost_per_unit) || 0)
  return sum + moneyAmountToUzs(lineAmount, line.currency, line.fx_rate)
}, 0))
const expenseTotal = computed(() => expenses.value.reduce((sum, expense) => {
  return sum + moneyAmountToUzs(parseFloat(expense.amount) || 0, expense.currency, expense.fx_rate)
}, 0))
const procurementTotal = computed(() => grandTotal.value + expenseTotal.value)
const procurementTotalInContractCurrency = computed(() => {
  const totalUzs = procurementTotal.value
  if (normalizeCurrency(contractCurrency.value) === 'UZS') return totalUzs
  const fx = parsePositiveNumber(latestUsdRate.value)
  if (fx <= 0) return 0
  return totalUzs / fx
})
const plannedBudgetAmount = computed(() => parsePositiveNumber(plannedBudget.value))
const hasForeignCurrency = computed(() => {
  return lines.value.some((line) => normalizeCurrency(line.currency) !== 'UZS')
    || expenses.value.some((expense) => normalizeCurrency(expense.currency) !== 'UZS')
})
const isPartnershipType = computed(() => selectedType.value !== ProcurementType.OWN_FUNDS)
const investorContractRow = computed(() => contractRows.value.find((row) => row.role === 'INVESTOR') ?? null)
const operatorContractRow = computed(() => contractRows.value.find((row) => row.role === 'OPERATOR') ?? null)

const capitalPercentTotal = computed(() => contractRows.value.reduce((sum, row) => sum + (parseFloat(row.capital_percent) || 0), 0))
const profitTotal = computed(() => contractRows.value.reduce((sum, row) => sum + (parseFloat(row.profit_percent) || 0), 0))

const investorCapitalPercent = computed(() => {
  return contractRows.value
    .filter((row) => row.role === 'INVESTOR')
    .reduce((sum, row) => sum + (parseFloat(row.capital_percent) || 0), 0)
})

const investorProfitShare = computed(() => {
  return contractRows.value
    .filter((row) => row.role === 'INVESTOR')
    .reduce((sum, row) => sum + (parseFloat(row.profit_percent) || 0), 0) / 100
})

const investorCapitalShare = computed(() => investorCapitalPercent.value / 100)
const investorProfitPercent = computed(() => investorProfitShare.value * 100)
const operatorCapitalPercent = computed(() => Math.max(0, 100 - investorCapitalPercent.value))
const operatorProfitPercent = computed(() => Math.max(0, 100 - investorProfitPercent.value))

const mudarabaRatio = computed(() => {
  if (!isPartnershipType.value) return 0
  if (selectedType.value === ProcurementType.MUSHARAKA) return 1
  if (investorCapitalShare.value <= 0) return Number.NaN
  return investorProfitShare.value / investorCapitalShare.value
})

const expectedProfitByRole = computed(() => {
  if (capitalPercentTotal.value <= 0 || Number.isNaN(mudarabaRatio.value)) return { investor: 0, operator: 0 }
  const investor = investorCapitalShare.value * mudarabaRatio.value
  return {
    investor,
    operator: 1 - investor,
  }
})

const simulatedInvestorCapitalPercent = computed(() => {
  if (simulatedInvestorCapitalPercentDraft.value !== '') {
    return clampPercent(simulatedInvestorCapitalPercentDraft.value)
  }
  return investorCapitalPercent.value
})

const simulatedInvestorProfitPercent = computed(() => {
  if (!Number.isFinite(mudarabaRatio.value)) return 0
  return Math.min(100, Math.max(0, simulatedInvestorCapitalPercent.value * mudarabaRatio.value))
})

const simulatedOperatorProfitPercent = computed(() => Math.max(0, 100 - simulatedInvestorProfitPercent.value))
const simulationCapitalDelta = computed(() => simulatedInvestorCapitalPercent.value - investorCapitalPercent.value)
const simulationProfitDelta = computed(() => simulatedInvestorProfitPercent.value - investorProfitPercent.value)
const hasSimulationDelta = computed(() => Math.abs(simulationCapitalDelta.value) > 0.05)
const simulationRangeStyle = computed(() => ({
  '--split': `${simulatedInvestorCapitalPercent.value}%`,
}))

function clampPercent(raw: string | number): number {
  const value = Number.parseFloat(String(raw))
  if (!Number.isFinite(value)) return 0
  return Math.min(100, Math.max(0, value))
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return '—'
  return `${value.toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  })}%`
}

function formatSignedPercent(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '-' : ''
  return `${sign}${Math.abs(value).toLocaleString('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  })}%`
}

function setSimulationCapitalPercent(raw: string | number): void {
  simulatedInvestorCapitalPercentDraft.value = clampPercent(raw).toFixed(2)
}

function resetSimulation(): void {
  simulatedInvestorCapitalPercentDraft.value = ''
}

function buildDefaultContractRows(): ContractRow[] {
  const investor = partners.value.find((partner) => partner.role === 'INVESTOR')
  const operator = partners.value.find((partner) => partner.role === 'OPERATOR')
  const currentInvestor = investorContractRow.value
  const currentOperator = operatorContractRow.value
  return [
    {
      id: crypto.randomUUID(),
      partner_id: currentInvestor?.partner_id ?? investor?.id ?? null,
      role: 'INVESTOR',
      capital_percent: currentInvestor?.capital_percent ?? '50',
      profit_percent: currentInvestor?.profit_percent ?? '50',
    },
    {
      id: crypto.randomUUID(),
      partner_id: currentOperator?.partner_id ?? operator?.id ?? null,
      role: 'OPERATOR',
      capital_percent: currentOperator?.capital_percent ?? '50',
      profit_percent: currentOperator?.profit_percent ?? '50',
    },
  ]
}

function applyDefaultContract(): void {
  contractRows.value = buildDefaultContractRows()
}

function resetDraftForm(): void {
  selectedType.value = ProcurementType.OWN_FUNDS
  editingAgreementId.value = null
  selectedSupplierId.value = null
  notes.value = ''
  lines.value = []
  expenses.value = []
  contractCurrency.value = 'USD'
  plannedBudget.value = ''
  contractRows.value = buildDefaultContractRows()
}

function applyLinkedAgreementDefaults(): void {
  const agreement = linkedAgreement.value
  if (!agreement) return
  selectedType.value = ProcurementType.PARTNERSHIP
  selectedSupplierId.value = agreement.supplier
  contractCurrency.value = normalizeCurrency(agreement.currency)
  plannedBudget.value = String(agreement.planned_budget)
  contractRows.value = agreement.partners.map((partner) => ({
    id: crypto.randomUUID(),
    partner_id: partner.partner,
    role: partner.role as ContractRow['role'],
    capital_percent: Number(agreement.planned_budget) > 0
      ? formatEditablePercent((Number(partner.planned_capital_share) / Number(agreement.planned_budget)) * 100)
      : '0',
    profit_percent: formatEditablePercent(Number(partner.profit_share) * 100),
  }))
}

function populateFormFromProcurement(procurement: ProcurementDetail): void {
  selectedType.value = procurement.procurement_type as ProcurementType
  editingAgreementId.value = procurement.agreement
  selectedSupplierId.value = procurement.supplier
  notes.value = procurement.notes ?? ''
  lines.value = procurement.items.map((item) => {
    const variant = allVariants.value.find((entry) => entry.id === item.product_variant)
    return {
      id: crypto.randomUUID(),
      variant: variant ?? placeholderVariantFromProcurementItem(item),
      quantity: String(item.quantity),
      cost_per_unit: String(item.unit_purchase_price),
      currency: normalizeCurrency(item.currency),
      fx_rate: String(item.fx_rate),
    }
  })
  expenses.value = procurement.expenses.map((expense) => ({
    id: crypto.randomUUID(),
    expense_type: expense.expense_type as ExpenseRow['expense_type'],
    amount: String(expense.amount),
    currency: normalizeCurrency(expense.currency),
    fx_rate: String(expense.fx_rate),
    allocation_method: expense.allocation_method as ExpenseRow['allocation_method'],
    notes: expense.notes ?? '',
  }))

  if (procurement.contract) {
    contractCurrency.value = normalizeCurrency(procurement.contract.currency)
    plannedBudget.value = String(procurement.contract.planned_budget)
    const budget = Number(procurement.contract.planned_budget) || 0
    contractRows.value = procurement.contract.partners.map((partner) => ({
      id: crypto.randomUUID(),
      partner_id: partner.partner,
      role: partner.role as ContractRow['role'],
      capital_percent: budget > 0
        ? formatEditablePercent((Number(partner.planned_capital_share) / budget) * 100)
        : '0',
      profit_percent: formatEditablePercent(Number(partner.profit_share) * 100),
    }))
  } else {
    contractCurrency.value = 'USD'
    plannedBudget.value = ''
    contractRows.value = buildDefaultContractRows()
  }
}

async function loadExistingDraft(): Promise<void> {
  if (editingProcurementId.value === null) return
  isLoadingDraft.value = true
  try {
    const procurement = await fetchProcurement(editingProcurementId.value)
    if (procurement.status !== 'OPEN') {
      throw new Error('Редактировать можно только открытый приход')
    }
    populateFormFromProcurement(procurement)
  } finally {
    isLoadingDraft.value = false
  }
}

function validate() {
  const seenVariantIds = new Set<number>()
  for (const line of lines.value) {
    if (!line.variant) return 'Выберите товар в каждой строке'
    if (seenVariantIds.has(line.variant.id)) return 'Один и тот же товар нельзя добавлять в закупку дважды'
    seenVariantIds.add(line.variant.id)
    if (!line.quantity || parseFloat(line.quantity) <= 0) return 'Укажите количество'
    if (!line.cost_per_unit || parseFloat(line.cost_per_unit) <= 0) return 'Укажите цену закупки'
    if (showFxField(line.currency) && getFxRateValue(line.currency, line.fx_rate) <= 0) return 'Укажите курс для валютной строки товара'
  }
  for (const expense of expenses.value) {
    if (!expense.amount || parseFloat(expense.amount) <= 0) return 'Укажите сумму расхода'
    if (showFxField(expense.currency) && getFxRateValue(expense.currency, expense.fx_rate) <= 0) return 'Укажите курс для валютного расхода'
  }
  if (isPartnershipType.value) {
    if (contractRows.value.some((row) => !row.partner_id)) return 'Выберите всех партнёров'
    if (new Set(contractRows.value.map((row) => row.partner_id)).size !== contractRows.value.length) return 'Партнёры в договоре не должны повторяться'
    if (!contractRows.value.some((row) => row.role === 'OPERATOR')) return 'Не найден бизнес-участник договора'
    if (!contractRows.value.some((row) => row.role === 'INVESTOR')) return 'В договоре нужен инвестор'
    if (plannedBudgetAmount.value <= 0) return 'Укажите плановый бюджет договора'
    if (capitalPercentTotal.value <= 0) return 'Укажите капитал партнёров'
    if (Math.abs(capitalPercentTotal.value - 100) > 0.0001) return 'Доли капитала должны дать 100%'
    if (Math.abs(profitTotal.value - 100) > 0.01) return 'Доли прибыли должны дать 100%'
    if (!Number.isFinite(mudarabaRatio.value) || mudarabaRatio.value < 0 || mudarabaRatio.value > 1) return 'Формула прибыли не сходится с капиталом'
    const investorProfitPercent = investorProfitShare.value * 100
    if (Math.abs(investorProfitPercent - expectedProfitByRole.value.investor * 100) > 0.05) return 'Доля инвестора не соответствует формуле договора'
  }
  return ''
}

async function saveDraft(): Promise<void> {
  const validation = validate()
  formError.value = validation || null
  if (validation) return

  isSaving.value = true
  try {
    const contract = isPartnershipType.value
      ? {
          mudaraba_ratio: mudarabaRatio.value.toFixed(6),
          planned_budget: plannedBudgetAmount.value.toFixed(2),
          currency: normalizeCurrency(contractCurrency.value),
          partners: contractRows.value.map((row) => ({
            partner_id: row.partner_id as number,
            role: row.role,
            planned_capital_share: (plannedBudgetAmount.value * ((Number.parseFloat(row.capital_percent) || 0) / 100)).toFixed(2),
            profit_share: ((Number.parseFloat(row.profit_percent) || 0) / 100).toFixed(6),
          })),
        }
      : undefined

    const payload = {
      client_request_id: isEditMode.value ? undefined : generateRequestId(),
      procurement_type: selectedType.value,
      supplier_id: selectedSupplierId.value,
      agreement_id: isLinkedAgreementMode.value ? linkedAgreementId.value : editingAgreementId.value,
      notes: notes.value.trim(),
      items: lines.value.map((line) => ({
        product_variant_id: line.variant!.id,
        quantity: parseFloat(line.quantity),
        unit_purchase_price: parseFloat(line.cost_per_unit),
        currency: normalizeCurrency(line.currency),
        fx_rate: String(getFxRateValue(line.currency, line.fx_rate) || defaultFxRateForCurrency(line.currency)),
      })),
      expenses: expenses.value.map((expense) => ({
        expense_type: expense.expense_type,
        amount: Number.parseFloat(expense.amount),
        currency: normalizeCurrency(expense.currency),
        fx_rate: String(getFxRateValue(expense.currency, expense.fx_rate) || defaultFxRateForCurrency(expense.currency)),
        allocation_method: expense.allocation_method,
        notes: expense.notes.trim(),
      })),
      contract,
    }

    const procurement = isEditMode.value && editingProcurementId.value !== null
      ? await updateProcurement(editingProcurementId.value, payload)
      : await createProcurement(payload)

    toast.success(isEditMode.value ? 'Приход обновлён' : 'Приход открыт')
    await router.push({ name: 'procurement-detail', params: { id: procurement.id } })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : (isEditMode.value ? 'Не удалось обновить приход' : 'Не удалось открыть приход')
    formError.value = msg
    toast.error(msg)
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  isLoadingRefs.value = true
  try {
    const [supplierResponse, categoryResponse, partnerResponse] = await Promise.all([
      fetchSuppliers(),
      fetchCategories(),
      fetchPartners({ is_active: true }),
      loadLatestUsdRate(),
    ])
    suppliers.value = supplierResponse.results
    categories.value = categoryResponse
    partners.value = partnerResponse
    resetDraftForm()
    if (isLinkedAgreementMode.value && linkedAgreementId.value) {
      linkedAgreement.value = await fetchInvestmentAgreement(linkedAgreementId.value)
      applyLinkedAgreementDefaults()
    }
    await loadExistingDraft()
  } catch {
    toast.error('Ошибка загрузки справочных данных')
  } finally {
    isLoadingRefs.value = false
  }
})
</script>

<template>
  <div class="create-page">
    <header class="page-header">
      <button class="btn-back" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="20" :stroke-width="1.75" />
      </button>
      <h1 class="page-title">{{ isEditMode ? 'Редактирование прихода' : 'Новый приход' }}</h1>
      <div class="header-spacer" />
    </header>

    <div class="form-body">
      <section v-if="linkedAgreement" class="linked-agreement-strip">
        <div>
          <span>Источник капитала</span>
          <strong>Инвестдоговор #{{ linkedAgreement.id }}</strong>
        </div>
        <button type="button" @click="router.push({ name: 'agreement-detail', params: { id: linkedAgreement.id } })">
          Открыть
        </button>
      </section>

      <section class="form-section">
        <h2 class="section-title">Тип закупки</h2>
        <div class="type-grid">
          <button
            v-for="card in TYPE_CARDS"
            :key="card.type"
            class="type-card"
            :class="{ selected: selectedType === card.type }"
            :disabled="isLinkedAgreementMode"
            @click="selectedType = card.type; applyDefaultContract()"
          >
            <div class="type-card-icon">
              <component :is="card.icon" :size="22" :stroke-width="1.75" />
            </div>
            <span class="type-card-label">{{ card.label }}</span>
            <span class="type-card-desc">{{ card.description }}</span>
          </button>
        </div>
      </section>

      <section v-if="isPartnershipType" class="form-section">
        <div class="section-header">
          <h2 class="section-title">Договор</h2>
          <button class="btn-add-investor" type="button" @click="openInvestorInvitePage">
            <UserPlus :size="16" :stroke-width="2" />
            Добавить инвестора
          </button>
        </div>

        <div v-if="!hasLinkedInvestors" class="investor-empty">
          <div class="investor-empty-copy">
            <strong>Связанных инвесторов пока нет</strong>
            <span>Создайте ссылку приглашения. После принятия инвестор появится в списке и сможет видеть свои отчёты.</span>
          </div>
          <button class="investor-empty-action" type="button" @click="openInvestorInvitePage">
            <UserPlus :size="16" :stroke-width="2" />
            Создать приглашение
          </button>
        </div>

        <div class="agreement-layout">
          <div class="agreement-panel">
            <div class="field-group">
              <label class="field-label">Инвестор</label>
              <BaseSelect
                :model-value="investorContractRow?.partner_id ?? null"
                :options="investorOptions"
                title="Выбор инвестора"
                placeholder="Выберите инвестора"
                @update:model-value="(value) => updateContractRole('INVESTOR', 'partner_id', value as number | null)"
              />
            </div>

            <div class="field-group">
              <label class="field-label">Плановый бюджет договора</label>
              <div class="money-field">
                <input
                  v-model="plannedBudget"
                  type="number"
                  class="input-field money-input"
                  min="0"
                  step="0.01"
                  :placeholder="normalizeCurrency(contractCurrency) === 'USD' ? '15000' : '180000000'"
                />
                <button type="button" class="currency-toggle" @click="contractCurrency = nextCurrency(contractCurrency)">
                  <span class="currency-toggle-code">{{ contractCurrency }}</span>
                  <RefreshCcw :size="14" :stroke-width="2" />
                </button>
              </div>
            </div>

            <div v-if="isEditMode && procurementTotalInContractCurrency > 0" class="agreement-budget-card">
              <span>Текущая сумма добавленных позиций</span>
              <strong class="tabular-nums">{{ formatPrice(procurementTotalInContractCurrency, normalizeCurrency(contractCurrency)) }}</strong>
            </div>

            <div class="formula-note">
              <span>Валюта договора задаёт расчётную валюту долей. План фиксирует капитал и прибыль. Если фактический вклад отличается, прибыль пересчитывается по коэффициенту Mudaraba.</span>
            </div>

            <div class="agreement-input-table">
              <div class="agreement-input-head">
                <span />
                <span>Инвестор</span>
                <span>Бизнес</span>
              </div>

              <div class="agreement-input-row">
                <strong>Капитал %</strong>
                <div class="field-group">
                  <input
                    type="number"
                    class="input-field"
                    :value="investorContractRow?.capital_percent ?? ''"
                    min="0"
                    max="100"
                    step="0.0001"
                    @input="(e) => updatePairPercent('INVESTOR', 'capital_percent', (e.target as HTMLInputElement).value)"
                  />
                </div>
                <div class="field-group">
                  <input
                    type="number"
                    class="input-field"
                    :value="operatorContractRow?.capital_percent ?? ''"
                    min="0"
                    max="100"
                    step="0.0001"
                    @input="(e) => updatePairPercent('OPERATOR', 'capital_percent', (e.target as HTMLInputElement).value)"
                  />
                </div>
              </div>

              <div class="agreement-input-row">
                <strong>Прибыль %</strong>
                <div class="field-group">
                  <input
                    type="number"
                    class="input-field"
                    :value="investorContractRow?.profit_percent ?? ''"
                    min="0"
                    max="100"
                    step="0.0001"
                    @input="(e) => updatePairPercent('INVESTOR', 'profit_percent', (e.target as HTMLInputElement).value)"
                  />
                </div>
                <div class="field-group">
                  <input
                    type="number"
                    class="input-field"
                    :value="operatorContractRow?.profit_percent ?? ''"
                    min="0"
                    max="100"
                    step="0.0001"
                    @input="(e) => updatePairPercent('OPERATOR', 'profit_percent', (e.target as HTMLInputElement).value)"
                  />
                </div>
              </div>
            </div>

            <div class="formula-strip">
              <span>Коэффициент Mudaraba</span>
              <strong class="tabular-nums">{{ Number.isFinite(mudarabaRatio) ? mudarabaRatio.toFixed(6) : '—' }}</strong>
            </div>

            <div class="recalculation-panel" :class="{ open: isRecalculationOpen }">
              <button
                class="recalculation-toggle"
                type="button"
                :aria-expanded="isRecalculationOpen"
                @click="isRecalculationOpen = !isRecalculationOpen"
              >
                <span class="recalculation-toggle-copy">
                  <span class="panel-kicker">Перерасчёт</span>
                  <strong>Факт может отличаться от плана</strong>
                  <span>Перед закрытием сделки доли можно выровнять или оставить фактический вклад и пересчитать прибыль.</span>
                </span>
                <span class="recalculation-toggle-action">
                  {{ isRecalculationOpen ? 'Скрыть' : 'Правила' }}
                  <ChevronDown class="recalculation-chevron" :size="18" :stroke-width="2" />
                </span>
              </button>

              <div v-if="isRecalculationOpen" class="recalculation-details">
                <div class="rule-list">
                  <div>
                    <strong>1. План фиксируется в договоре</strong>
                    <span>Капитал и прибыль задают коэффициент Mudaraba: прибыль инвестора / доля капитала инвестора.</span>
                  </div>
                  <div>
                    <strong>2. Факт проверяется при закрытии</strong>
                    <span>Если внесённые доли капитала отличаются от плана, система показывает отклонение перед закрытием сделки.</span>
                  </div>
                  <div>
                    <strong>3. Есть два варианта</strong>
                    <span>Партнёры могут выровнять капитал до плана или оставить фактические доли и пересчитать прибыль по прежнему коэффициенту.</span>
                  </div>
                </div>

                <div class="split-control">
                  <div class="split-header">
                    <span>Фактическая доля капитала инвестора</span>
                    <strong class="tabular-nums">{{ formatPercent(simulatedInvestorCapitalPercent) }}</strong>
                  </div>
                  <input
                    class="range-input split-range"
                    type="range"
                    min="0"
                    max="100"
                    step="0.1"
                    :value="simulatedInvestorCapitalPercent"
                    :style="simulationRangeStyle"
                    @input="(e) => setSimulationCapitalPercent((e.target as HTMLInputElement).value)"
                  />
                  <div class="range-labels">
                    <span>Бизнес {{ formatPercent(100 - simulatedInvestorCapitalPercent) }}</span>
                    <span>Инвестор {{ formatPercent(simulatedInvestorCapitalPercent) }}</span>
                  </div>
                </div>

                <div class="simulation-result">
                  <div>
                    <span>Прибыль инвестора</span>
                    <strong class="tabular-nums">{{ formatPercent(simulatedInvestorProfitPercent) }}</strong>
                  </div>
                  <div>
                    <span>Прибыль бизнеса</span>
                    <strong class="tabular-nums">{{ formatPercent(simulatedOperatorProfitPercent) }}</strong>
                  </div>
                </div>

                <div class="recalculation-note" :class="{ active: hasSimulationDelta }">
                  <span v-if="hasSimulationDelta">
                    Отклонение капитала инвестора {{ formatSignedPercent(simulationCapitalDelta) }} изменит его прибыль на {{ formatSignedPercent(simulationProfitDelta) }}.
                  </span>
                  <span v-else>
                    Сейчас симуляция совпадает с планом договора.
                  </span>
                  <button type="button" @click="resetSimulation">Сбросить</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="isEditMode" class="form-section">
        <div class="section-header">
          <h2 class="section-title">Поставщик</h2>
          <button class="btn-add-small" type="button" @click="openQuickSupplierCreator">
            <Plus :size="14" :stroke-width="2.5" />
            Добавить поставщика
          </button>
        </div>
        <div class="field-group">
          <label class="field-label">Поставщик можно выбрать позже</label>
          <BaseSelect v-model="selectedSupplierId" :options="supplierOptions" title="Выбор поставщика" placeholder="Без поставщика" :disabled="isLoadingRefs" />
        </div>
        <p class="empty-inline">
          Склад оприходования выбирается позже, когда приход будет готов к этапу receive.
        </p>
      </section>

      <section v-if="isEditMode" class="form-section">
        <div class="section-header">
          <h2 class="section-title">Товары</h2>
          <div class="section-actions">
            <button class="btn-add-small" type="button" @click="openQuickProductCreator()">
              <Plus :size="14" :stroke-width="2.5" />
              Создать товар
            </button>
            <button class="btn-add-small" type="button" @click="addEmptyLine">
              <Plus :size="14" :stroke-width="2.5" />
              Добавить строку
            </button>
          </div>
        </div>

        <div v-if="lines.length === 0" class="empty-inline">
          Товары можно добавить после открытия прихода.
        </div>

        <div v-else class="line-list">
          <div v-for="line in lines" :key="line.id" class="line-row">
            <div class="line-row-top">
              <button class="picker-btn line-product-btn" type="button" @click="openVariantPicker(line.id)">
                {{ line.variant ? variantDisplay(line.variant) : 'Выбрать товар' }}
              </button>
              <button class="btn-delete line-delete" type="button" aria-label="Удалить строку" @click="removeLine(line.id)">
                <Trash2 :size="16" :stroke-width="2" />
              </button>
            </div>

            <div class="line-row-main">
              <div class="field-group">
                <label class="micro-label">Кол-во</label>
                <input
                  type="number"
                  class="input-field line-input"
                  :value="line.quantity"
                  min="0"
                  placeholder="1"
                  aria-label="Количество"
                  @input="(e) => updateLine(line.id, 'quantity', (e.target as HTMLInputElement).value)"
                />
              </div>

              <div class="field-group line-price-cell">
                <label class="micro-label">Цена закупки</label>
                <div class="money-field">
                  <input
                    type="number"
                    class="input-field line-input money-input"
                    :value="line.cost_per_unit"
                    min="0"
                    step="0.000001"
                    placeholder="Цена"
                    aria-label="Цена закупки"
                    @input="(e) => updateLine(line.id, 'cost_per_unit', (e.target as HTMLInputElement).value)"
                  />
                  <button
                    type="button"
                    class="currency-toggle"
                    :aria-label="`Сменить валюту строки. Сейчас ${normalizeCurrency(line.currency)}`"
                    @click="toggleLineCurrency(line.id)"
                  >
                    <span class="currency-toggle-code">{{ normalizeCurrency(line.currency) }}</span>
                    <RefreshCcw :size="14" :stroke-width="2" />
                  </button>
                </div>
              </div>
            </div>

            <div v-if="showFxField(line.currency)" class="line-row-extra">
              <div class="field-group">
                <label class="micro-label">Курс {{ formatCurrencyTotalLabel(line.currency) }}</label>
                <input
                  type="number"
                  class="input-field line-input"
                  :value="line.fx_rate"
                  min="0"
                  step="0.0001"
                  placeholder="12100"
                  aria-label="Курс валюты"
                  @input="(e) => updateLine(line.id, 'fx_rate', (e.target as HTMLInputElement).value)"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="isEditMode" class="form-section">
        <div class="section-header">
          <h2 class="section-title">Расходы прихода</h2>
          <button class="btn-add-small" type="button" @click="addExpense">
            <Plus :size="14" :stroke-width="2.5" />
            Добавить
          </button>
        </div>

        <div v-if="expenses.length === 0" class="empty-inline">
          Дополнительных расходов нет.
        </div>

        <div v-for="expense in expenses" :key="expense.id" class="participant-card">
          <div class="participant-header">
            <span class="participant-num">Расход</span>
            <button class="btn-delete" type="button" aria-label="Удалить расход" @click="removeExpense(expense.id)">
              <Trash2 :size="16" :stroke-width="2" />
            </button>
          </div>
          <div class="field-row">
            <div class="field-group flex-1">
              <label class="field-label">Тип</label>
              <BaseSelect
                :model-value="expense.expense_type"
                :options="EXPENSE_TYPE_OPTIONS"
                title="Тип расхода"
                @update:model-value="(value) => updateExpense(expense.id, 'expense_type', String(value))"
              />
            </div>
            <div class="field-group flex-1">
              <label class="field-label">Разносить</label>
              <BaseSelect
                :model-value="expense.allocation_method"
                :options="ALLOCATION_OPTIONS"
                title="Метод распределения"
                @update:model-value="(value) => updateExpense(expense.id, 'allocation_method', String(value))"
              />
            </div>
          </div>
          <div class="field-group">
            <label class="field-label">Сумма</label>
            <div class="money-field">
              <input
                type="number"
                class="input-field money-input"
                :value="expense.amount"
                min="0"
                placeholder="0"
                @input="(e) => updateExpense(expense.id, 'amount', (e.target as HTMLInputElement).value)"
              />
              <button
                type="button"
                class="currency-toggle"
                :aria-label="`Сменить валюту расхода. Сейчас ${normalizeCurrency(expense.currency)}`"
                @click="toggleExpenseCurrency(expense.id)"
              >
                <span class="currency-toggle-code">{{ normalizeCurrency(expense.currency) }}</span>
                <RefreshCcw :size="14" :stroke-width="2" />
              </button>
            </div>
          </div>
          <div v-if="showFxField(expense.currency)" class="field-group">
            <label class="field-label">Курс {{ formatCurrencyTotalLabel(expense.currency) }}</label>
            <input
              type="number"
              class="input-field"
              :value="expense.fx_rate"
              min="0"
              step="0.0001"
              placeholder="12100"
              @input="(e) => updateExpense(expense.id, 'fx_rate', (e.target as HTMLInputElement).value)"
            />
          </div>
          <div class="field-group">
            <label class="field-label">Комментарий</label>
            <input class="input-field" :value="expense.notes" @input="(e) => updateExpense(expense.id, 'notes', (e.target as HTMLInputElement).value)" />
          </div>
        </div>
      </section>

      <section v-if="isEditMode" class="form-section">
        <h2 class="section-title">Итого</h2>
        <div v-if="hasForeignCurrency" class="summary-hint">
          Итог считается в эквиваленте UZS по курсам, указанным в строках товаров и расходов.
        </div>
        <div class="summary-card">
          <span>Товары</span>
          <strong class="tabular-nums">{{ formatPrice(grandTotal) }}</strong>
        </div>
        <div class="summary-card summary-card-muted">
          <span>Расходы</span>
          <strong class="tabular-nums">{{ formatPrice(expenseTotal) }}</strong>
        </div>
        <div class="summary-card">
          <span>К оплате</span>
          <strong class="tabular-nums">{{ formatPrice(procurementTotal) }}</strong>
        </div>
      </section>

      <section class="form-section">
        <h2 class="section-title">Заметки</h2>
        <textarea v-model="notes" class="textarea-field" rows="4" placeholder="Комментарий к закупке" />
      </section>

      <section v-if="!isEditMode" class="form-section">
        <div class="agreement-panel">
          <div class="agreement-panel-header">
            <strong>Что будет дальше</strong>
            <span class="type-card-desc">После открытия прихода ты попадёшь в рабочее пространство прихода: баланс, товары, расходы, оплата и receive.</span>
          </div>
        </div>
      </section>

      <div v-if="formError" class="error-box">
        <AlertCircle :size="18" :stroke-width="1.75" />
        <span>{{ formError }}</span>
      </div>
    </div>

    <footer class="footer-actions">
      <button class="btn-primary" :disabled="isSaving || isLoadingDraft" @click="saveDraft">
        {{ isSaving ? (isEditMode ? 'Сохранение…' : 'Открытие…') : (isEditMode ? 'Сохранить изменения' : 'Открыть приход') }}
      </button>
    </footer>

    <AppBottomSheet :open="variantSheetOpen" title="Выбор товара" @close="closeVariantPicker">
      <div class="sheet-body">
        <div class="sheet-actions">
          <input v-model="variantSearch" class="input-field" type="text" placeholder="Поиск товара" />
          <button class="btn-add-small" type="button" @click="openQuickProductCreator(activeLineId)">
            <Plus :size="14" :stroke-width="2.5" />
            Новый
          </button>
        </div>
        <BaseSelect v-model="variantSearchCategory" :options="[{ value: null, label: 'Все категории' }, ...categoryOptions]" title="Категория" placeholder="Фильтр по категории" />
        <div class="variant-list">
          <button v-for="variant in filteredVariants" :key="variant.id" class="variant-row" @click="selectVariant(variant)">
            <span>{{ variantDisplay(variant) }}</span>
            <span class="tabular-nums">{{ variant.price ?? variant.effective_price ?? '0' }}</span>
          </button>
        </div>
      </div>
    </AppBottomSheet>

    <AppBottomSheet :open="quickProductSheetOpen" title="Быстрое создание товара" @close="closeQuickProductCreator">
      <form class="quick-product-form" @submit.prevent="createQuickProduct">
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
            title="Категория товара"
            placeholder="Без категории"
          />
        </div>

        <div class="field-group">
          <label class="field-label">Базовая цена</label>
          <input v-model="quickProductBasePrice" class="input-field" type="number" min="0" placeholder="0" />
        </div>

        <button class="btn-primary" type="submit" :disabled="isCreatingQuickProduct">
          {{ isCreatingQuickProduct ? 'Создание…' : 'Создать и добавить' }}
        </button>
      </form>
    </AppBottomSheet>

    <AppBottomSheet :open="quickSupplierSheetOpen" title="Быстрое создание поставщика" @close="closeQuickSupplierCreator">
      <form class="quick-product-form" @submit.prevent="createQuickSupplier">
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

        <button class="btn-primary" type="submit" :disabled="isCreatingQuickSupplier">
          {{ isCreatingQuickSupplier ? 'Создание…' : 'Создать и выбрать' }}
        </button>
      </form>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.create-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header { position: sticky; top: 0; z-index: var(--z-sticky); display: flex; align-items: center; gap: var(--space-3); height: var(--header-height); padding: 0 var(--space-4); background: var(--color-bg-primary); border-bottom: 1px solid var(--color-border-subtle); }
.btn-back,.header-spacer { width: 40px; height: 40px; display:inline-flex; align-items:center; justify-content:center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.page-title { flex:1; font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.form-body { display:grid; gap: var(--space-4); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-12)); }
.linked-agreement-strip { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-brand-50); }
.linked-agreement-strip div { min-width:0; display:grid; gap: 2px; }
.linked-agreement-strip span { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-medium); }
.linked-agreement-strip strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.linked-agreement-strip button { flex:0 0 auto; min-height:34px; padding:0 var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.form-section { display:grid; gap: var(--space-3); }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.type-grid { display:grid; gap: var(--space-3); }
.type-card { display:grid; gap: var(--space-2); text-align:left; padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.type-card.selected { border-color: var(--color-brand-500); box-shadow: 0 0 0 2px rgba(27,138,111,0.12); }
.type-card.disabled, .type-card:disabled { opacity: 0.55; }
.type-card-label { font-weight: var(--font-semibold); }
.type-card-desc { color: var(--color-text-secondary); font-size: var(--text-sm); }
.contract-metrics { display:grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: var(--space-2); }
.contract-metrics > div { display:grid; gap: 2px; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); border:1px solid var(--color-border-subtle); }
.contract-metrics span, .empty-inline { color: var(--color-text-secondary); font-size: var(--text-sm); }
.field-group { display:grid; gap: var(--space-2); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.micro-label { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.field-row { display:flex; gap: var(--space-3); }
.flex-1 { flex:1; }
.input-field,.textarea-field,.picker-btn { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.picker-btn { color: var(--color-text-secondary); }
.section-header, .participant-header, .summary-card, .variant-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.section-header { flex-wrap: wrap; }
.section-actions { display:flex; align-items:center; justify-content:flex-end; gap: var(--space-2); flex-wrap:wrap; margin-left:auto; }
.participant-card { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.participant-num { font-weight: var(--font-semibold); }
.btn-add-small {
  min-height: 36px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap: var(--space-1);
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  border:1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-brand-600);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
}
.btn-delete { display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-500); }
.btn-add-investor { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); color: var(--color-brand-600); background: var(--color-bg-elevated); font-weight: var(--font-medium); white-space: nowrap; }
.investor-empty { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px dashed var(--color-border-default); background: var(--color-bg-elevated); }
.investor-empty-copy { display:grid; gap: var(--space-1); }
.investor-empty-copy strong { color: var(--color-text-primary); font-weight: var(--font-semibold); }
.investor-empty-copy span { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.investor-empty-action { min-height: 44px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); padding: 0 var(--space-4); border-radius: var(--radius-md); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
.agreement-layout { display:grid; gap: var(--space-3); }
.agreement-panel { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.agreement-panel-header { display:grid; gap: 2px; }
.agreement-panel-header strong { color: var(--color-text-primary); font-size: var(--text-lg); font-weight: var(--font-semibold); }
.panel-kicker { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0; }
.agreement-meta-row { display:grid; grid-template-columns: minmax(0, 1fr) minmax(160px, 0.8fr); gap: var(--space-3); align-items:end; }
.agreement-budget-card { display:grid; gap: 4px; min-height: 48px; padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.agreement-budget-card span { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.agreement-budget-card strong { color: var(--color-text-primary); font-size: var(--text-base); }
.formula-note { display:flex; align-items:flex-start; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-brand-50); color: var(--color-brand-700); font-size: var(--text-sm); line-height: 1.45; }
.agreement-input-table { display:grid; gap: var(--space-2); }
.agreement-input-head,
.agreement-input-row { display:grid; grid-template-columns: minmax(82px, 0.72fr) repeat(2, minmax(0, 1fr)); gap: var(--space-2); align-items:start; }
.agreement-input-head { padding: 0 var(--space-3); color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.agreement-input-row { padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); }
.agreement-input-row > strong { align-self:center; color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.agreement-input-row .field-group span { color: var(--color-text-tertiary); font-size: var(--text-xs); }
.split-control { display:grid; gap: var(--space-2); }
.split-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); color: var(--color-text-secondary); font-size: var(--text-sm); }
.split-header strong { color: var(--color-text-primary); font-size: var(--text-base); }
.range-input { width:100%; accent-color: var(--color-brand-500); }
.range-input:disabled { opacity: 0.45; }
.split-range { -webkit-appearance:none; appearance:none; height: 8px; border-radius: var(--radius-full); background: linear-gradient(to right, var(--color-accent-400) 0 var(--split), var(--color-brand-500) var(--split) 100%); outline:none; }
.split-range::-webkit-slider-thumb { -webkit-appearance:none; appearance:none; width: 22px; height: 22px; border-radius: var(--radius-full); border:2px solid var(--color-brand-600); background: var(--color-bg-elevated); box-shadow: 0 2px 8px rgba(17, 24, 39, 0.16); cursor:pointer; }
.split-range::-moz-range-thumb { width: 20px; height: 20px; border-radius: var(--radius-full); border:2px solid var(--color-brand-600); background: var(--color-bg-elevated); box-shadow: 0 2px 8px rgba(17, 24, 39, 0.16); cursor:pointer; }
.range-labels { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); color: var(--color-text-tertiary); font-size: var(--text-xs); }
.formula-strip { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); color: var(--color-text-secondary); }
.formula-strip strong { color: var(--color-text-primary); }
.recalculation-panel { display:grid; gap: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); overflow:hidden; }
.recalculation-panel.open { padding-bottom: var(--space-3); }
.recalculation-toggle { width:100%; display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); text-align:left; background: var(--color-bg-primary); }
.recalculation-toggle-copy { min-width:0; display:grid; gap: 2px; }
.recalculation-toggle-copy strong { color: var(--color-text-primary); font-size: var(--text-base); font-weight: var(--font-semibold); }
.recalculation-toggle-copy span:last-child { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.recalculation-toggle-action { flex:0 0 auto; display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.recalculation-chevron { transition: transform var(--duration-fast) var(--ease-out); }
.recalculation-panel.open .recalculation-chevron { transform: rotate(180deg); }
.recalculation-details { display:grid; gap: var(--space-3); padding: 0 var(--space-3); }
.rule-list { display:grid; gap: var(--space-2); }
.rule-list > div { display:grid; gap: 2px; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); border:1px solid var(--color-border-subtle); }
.rule-list strong { color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.rule-list span { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.simulation-result { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); }
.simulation-result > div { display:grid; gap: var(--space-1); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.simulation-result span { color: var(--color-text-secondary); font-size: var(--text-xs); }
.simulation-result strong { color: var(--color-text-primary); font-size: var(--text-lg); }
.recalculation-note { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.recalculation-note.active { background: var(--color-accent-50); color: var(--color-accent-700); }
.recalculation-note button { flex:0 0 auto; color: var(--color-brand-600); font-weight: var(--font-semibold); white-space: nowrap; }
.line-list { display:grid; gap: var(--space-1); border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-elevated); overflow:hidden; }
.line-row { display:grid; gap: var(--space-2); padding: var(--space-3); border-bottom:1px solid var(--color-border-subtle); }
.line-row:last-child { border-bottom:none; }
.line-row-top { display:grid; grid-template-columns: minmax(0, 1fr) 36px; gap: var(--space-2); align-items:start; }
.line-row-main { display:grid; grid-template-columns: minmax(92px, 0.65fr) minmax(0, 1.35fr); gap: var(--space-2); align-items:start; }
.line-row-extra { display:grid; gap: var(--space-2); }
.line-price-cell { min-width: 0; }
.line-product-btn { min-height:40px; padding: var(--space-2) var(--space-3); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.line-input { min-height:40px; padding: var(--space-2) var(--space-3); }
.money-field { position: relative; }
.money-input { padding-right: 88px; }
.currency-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  height: 30px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap: 6px;
  padding: 0 10px;
  border:1px solid var(--color-border-default);
  border-radius: calc(var(--radius-md) - 2px);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  z-index: 1;
}
.currency-toggle-code {
  font-size: var(--text-sm);
  line-height: 1;
}
.currency-toggle:hover {
  border-color: var(--color-brand-500);
  color: var(--color-brand-700);
}
.line-delete { width:36px; height:36px; justify-content:center; border-radius: var(--radius-md); color: var(--color-text-tertiary); }
.line-delete:hover { color: var(--color-error); background: var(--color-error-bg); }
.summary-hint { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.summary-card { padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-brand-50); color: var(--color-brand-700); }
.summary-card-muted { background: var(--color-bg-elevated); color: var(--color-text-primary); border:1px solid var(--color-border-subtle); }
.warning-box, .error-box { display:flex; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-lg); }
.warning-box { background: var(--color-accent-50); color: var(--color-accent-600); }
.error-box { background: var(--color-error-bg); color: var(--color-danger); }
.footer-actions { position: sticky; bottom: 0; padding: var(--space-4); background: linear-gradient(to top, var(--color-bg-primary), transparent); }
.btn-primary { width:100%; height: 48px; border:none; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
.sheet-body { display:grid; gap: var(--space-3); }
.sheet-actions { display:grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-2); align-items:center; }
.quick-product-form { display:grid; gap: var(--space-3); }
.variant-list { display:grid; gap: var(--space-2); max-height: 40vh; overflow:auto; }
.variant-row { padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }

@media (max-width: 520px) {
  .agreement-input-head,
  .agreement-input-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agreement-input-head span:first-child,
  .agreement-input-row > strong { grid-column: 1 / -1; }
  .agreement-meta-row { grid-template-columns: 1fr; }
  .section-header { align-items:flex-start; }
  .section-actions { width:100%; margin-left:0; justify-content:flex-start; }
  .line-row-main { grid-template-columns: minmax(88px, 0.62fr) minmax(0, 1.38fr); }
  .money-input { padding-right: 82px; }
  .currency-toggle { right: 5px; padding: 0 8px; }
  .field-row { flex-direction: column; }
  .sheet-actions { grid-template-columns: 1fr; }
  .recalculation-toggle { align-items:flex-start; flex-direction:column; }
  .recalculation-note { align-items:flex-start; flex-direction:column; }
}
</style>
