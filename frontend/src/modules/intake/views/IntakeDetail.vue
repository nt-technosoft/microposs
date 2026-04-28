<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CheckCircle2, AlertCircle, PlusCircle, ArrowRightLeft, Plus, Trash2, RefreshCcw, ChevronDown, BarChart3, Wallet } from 'lucide-vue-next'
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
  createAgreementAllocations,
  createProcurementBalanceExchange,
  fetchAgreementAllocationPreview,
  fetchProcurement,
  fetchProcurementReceivePlan,
  payProcurementExpenses,
  payProcurementItems,
  receiveProcurement,
  splitProcurementItem,
  updateProcurementExpenseTargets,
  updateProcurement,
  type AgreementAllocationPreview,
  type ProcurementDetail,
  type ReceiveBatchCapitalPreview,
} from '@/api/partnerships'
import { useAuthStore } from '@/stores/auth'
import type { Category, Product, ProductVariant, Supplier } from '@/types/models'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'

const FALLBACK_FX_RATE = '12100'
const RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE = 'Сервер не вернул доли партии. Повторите расчёт.'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const auth = useAuthStore()

const procurement = ref<ProcurementDetail | null>(null)
const locations = ref<Array<{ value: number; label: string; kind?: 'shop' | 'storage'; location_type?: 'warehouse' | 'store' }>>([])
const selectedWarehouseId = ref<number | null>(null)
const isLoading = ref(true)
const isConfirming = ref(false)
const errorMessage = ref<string | null>(null)
const latestUsdRate = ref('12100')
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
const contributionFxRate = ref('12100')
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
const allocationSheetOpen = ref(false)
const allocationPreview = ref<AgreementAllocationPreview | null>(null)
const allocationError = ref<string | null>(null)
const isLoadingAllocation = ref(false)
const isAllocatingFromAgreement = ref(false)

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
  target_item_ids: number[]
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
const expandedExpenseTargetsId = ref<string | null>(null)
const expandedPaidExpenseId = ref<number | null>(null)
const paidExpenseTargetDrafts = ref<Record<number, number[]>>({})
const savingExpenseTargetsId = ref<number | null>(null)
const expandedCostPreviewKey = ref<string | null>(null)
const expandedReceiveBatchId = ref<number | null>(null)
const receiveConfirmSheetOpen = ref(false)
const isLoadingReceivePlan = ref(false)
const receivePlanPreview = ref<ReceiveBatchCapitalPreview | null>(null)
const receivePlanPreviewKey = ref('')
const receivePlanPreviewError = ref('')
const receiveCapitalEditing = ref(false)
const receiveCapitalDrafts = ref<Record<number, string>>({})
const receiveCapitalDraftIssue = ref('')
const receiveCapitalConfirmedKey = ref('')
const selectedReceiveItemIds = ref<number[]>([])
const splitItemSheetOpen = ref(false)
const splitItemQuantity = ref('')
const splitItemError = ref('')
const isSplittingItem = ref(false)
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

const canWorkOnProcurement = computed(() => (
  procurement.value?.status === ProcurementStatus.OPEN
  || procurement.value?.status === ProcurementStatus.PARTIALLY_RECEIVED
))
const canConfirm = computed(() => canWorkOnProcurement.value)
const canReceive = computed(() => {
  const status = procurement.value?.receive_plan?.status
  return canConfirm.value && selectedWarehouseId.value !== null && (status === 'READY' || status === 'AUTO_SURPLUS' || status === 'AGREEMENT_SURPLUS')
})
const canManageBalance = computed(() => Boolean(auth.isOwner) && canConfirm.value)
const isLinkedProcurement = computed(() => Boolean(procurement.value?.agreement))
const canAllocateFromAgreement = computed(() => Boolean(auth.isOwner && canConfirm.value && procurement.value?.agreement))

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
const receivedItems = computed(() => (procurement.value?.items ?? []).filter((item) => item.status === 'RECEIVED'))
const pendingDraftItems = computed(() => (procurement.value?.items ?? []).filter((item) => item.status === 'DRAFT'))
const receiveBatches = computed(() => procurement.value?.receive_batches ?? procurement.value?.receive_plan?.receive_batches ?? [])
const receivableLines = computed(() => procurement.value?.cost_preview.receive_basis.lines ?? [])
const selectedReceiveIdSet = computed(() => new Set(selectedReceiveItemIds.value))
const selectedReceiveLines = computed(() => receivableLines.value.filter((line) => selectedReceiveIdSet.value.has(line.item_id)))
const allReceivableSelected = computed(() => receivableLines.value.length > 0 && selectedReceiveLines.value.length === receivableLines.value.length)
const receiveCapitalSelectionKey = computed(() => selectedReceiveLines.value.map((line) => line.item_id).sort((a, b) => a - b).join(','))
const isPartnershipReceive = computed(() => {
  const type = procurement.value?.procurement_type
  return type === ProcurementType.PARTNERSHIP || type === ProcurementType.MUSHARAKA
})
const requiresReceiveCapitalAllocation = computed(() => isPartnershipReceive.value && selectedReceiveLines.value.length > 0)
const receivePartialMode = computed(() => selectedReceiveLines.value.length > 0 && selectedReceiveLines.value.length < receivableLines.value.length)
const receiveWillFinish = computed(() => {
  if (!procurement.value || selectedReceiveLines.value.length === 0) return false
  const receivePlan = procurement.value.receive_plan
  return allReceivableSelected.value
    && receivePlan.draft_items_count === 0
    && receivePlan.draft_expenses_count === 0
    && receivePlan.pending_paid_items_count === selectedReceiveLines.value.length
})
const receiveUnsafeExpenseScope = computed(() => {
  if (!selectedReceiveLines.value.length) return false
  const selected = selectedReceiveIdSet.value
  const delayed = new Set<number>([
    ...receivableLines.value.filter((line) => !selected.has(line.item_id)).map((line) => line.item_id),
    ...pendingDraftItems.value.map((item) => item.id),
  ])
  const hasDelayedLines = delayed.size > 0
  const paidExpenseConflict = paidExpenses.value.some((expense) => {
    const targets = paidExpenseTargetIds(expense)
    if (!targets.length) return hasDelayedLines
    return targets.some((id) => selected.has(id)) && targets.some((id) => delayed.has(id))
  })
  const draftExpenseConflict = draftExpenses.value.some((expense) => {
    const targets = expense.target_item_ids ?? []
    if (!targets.length) return true
    return targets.some((id) => selected.has(id))
  })
  return paidExpenseConflict || draftExpenseConflict
})
const canOpenReceiveConfirm = computed(() => canReceive.value && selectedReceiveLines.value.length > 0 && !receiveUnsafeExpenseScope.value)
const receiveSelectionTotal = computed(() => selectedReceiveLines.value.reduce((sum, line) => {
  return sum + Number(line.quantity) * Number(line.landed_cost_per_unit_uzs)
}, 0))
const activeReceiveCapitalPreview = computed(() => {
  if (receivePlanPreview.value && receivePlanPreviewKey.value === receiveCapitalSelectionKey.value) {
    return receivePlanPreview.value
  }
  if (allReceivableSelected.value) {
    return procurement.value?.receive_plan?.batch_capital_preview ?? null
  }
  return null
})
const receiveCapitalRows = computed(() => activeReceiveCapitalPreview.value?.partners ?? [])
const receiveCapitalRequired = computed(() => Number(activeReceiveCapitalPreview.value?.required_amount ?? 0))
const receiveCapitalCurrency = computed(() => activeReceiveCapitalPreview.value?.currency ?? procurement.value?.contract?.currency ?? 'UZS')
const receiveCapitalMudarabaRatio = computed(() => Number(procurement.value?.contract?.mudaraba_ratio ?? 0))
const receiveCapitalDraftAmounts = computed<Record<number, number>>(() => Object.fromEntries(
  receiveCapitalRows.value.map((row) => {
    const parsed = parseLooseNumber(receiveCapitalDrafts.value[row.partner_id] ?? row.amount)
    return [row.partner_id, Number.isFinite(parsed) && parsed > 0 ? roundMoney(parsed) : 0]
  }),
))
const receiveCapitalDraftTotal = computed(() => receiveCapitalRows.value.reduce((sum, row) => {
  return sum + (receiveCapitalDraftAmounts.value[row.partner_id] ?? 0)
}, 0))
const receiveCapitalIsBalanced = computed(() => {
  if (!receiveCapitalRows.value.length) return true
  return Math.abs(receiveCapitalDraftTotal.value - receiveCapitalRequired.value) <= 0.01
})
const receiveCapitalDisplayRows = computed(() => {
  const required = receiveCapitalRequired.value
  const mudarabaRatio = receiveCapitalMudarabaRatio.value
  const rows = receiveCapitalRows.value.map((row) => {
    const amount = receiveCapitalDraftAmounts.value[row.partner_id] ?? parsePositiveNumber(row.amount)
    const capitalShare = required > 0 ? roundShare(amount / required) : 0
    return {
      ...row,
      amount,
      capitalShare,
      profitShare: 0,
    }
  })
  const investorCapitalTotal = rows
    .filter((row) => row.role === 'INVESTOR')
    .reduce((sum, row) => sum + row.capitalShare, 0)

  let distributedProfitShare = 0
  let operatorIndex = -1
  rows.forEach((row, index) => {
    let profitShare = 0
    if (row.role === 'INVESTOR') {
      profitShare = roundShare(row.capitalShare * mudarabaRatio)
    } else if (row.role === 'OPERATOR') {
      operatorIndex = index
      profitShare = roundShare(row.capitalShare + ((1 - mudarabaRatio) * investorCapitalTotal))
    }
    row.profitShare = profitShare
    distributedProfitShare += profitShare
  })
  if (operatorIndex >= 0) {
    const residue = roundShare(1 - distributedProfitShare)
    rows[operatorIndex].profitShare = roundShare(rows[operatorIndex].profitShare + residue)
  }
  return rows
})
const receiveCapitalValidationMessage = computed(() => {
  if (!requiresReceiveCapitalAllocation.value || !activeReceiveCapitalPreview.value || activeReceiveCapitalPreview.value.status !== 'READY') {
    return ''
  }
  if (receiveCapitalDraftIssue.value) return receiveCapitalDraftIssue.value
  for (const row of receiveCapitalRows.value) {
    const raw = receiveCapitalDrafts.value[row.partner_id] ?? row.amount
    const parsed = parseLooseNumber(raw)
    if (!Number.isFinite(parsed) || parsed < 0) {
      return 'Укажи корректные суммы долей партии.'
    }
    const available = parsePositiveNumber(row.available_amount)
    if (parsed - available > 0.01) {
      return `${displayPartnerName(row.partner_name, row.role)} может покрыть только ${formatCompactAmount(available, receiveCapitalCurrency.value)}.`
    }
  }
  if (!receiveCapitalIsBalanced.value) {
    return `Сумма долей должна равняться ${formatCompactAmount(receiveCapitalRequired.value, receiveCapitalCurrency.value)}.`
  }
  return ''
})
const canFinalizeReceiveCapitalEditing = computed(() => (
  Boolean(activeReceiveCapitalPreview.value && activeReceiveCapitalPreview.value.status === 'READY')
  && !receiveCapitalValidationMessage.value
))
const isReceiveCapitalConfirmed = computed(() => (
  receiveCapitalConfirmedKey.value === receiveCapitalSelectionKey.value
  && Boolean(activeReceiveCapitalPreview.value && activeReceiveCapitalPreview.value.status === 'READY')
  && !receiveCapitalEditing.value
))
const receiveCapitalApprovalNote = computed(() => {
  if (!requiresReceiveCapitalAllocation.value || !activeReceiveCapitalPreview.value || activeReceiveCapitalPreview.value.status !== 'READY') {
    return ''
  }
  if (receiveCapitalEditing.value) {
    return 'Проверь суммы, затем нажми «Готово». После этого отдельно подтверди доли партии.'
  }
  if (isReceiveCapitalConfirmed.value) {
    return 'Доли партии подтверждены. Теперь можно оприходовать эту поставку.'
  }
  return 'Сначала подтверди доли партии. Без этого оприходование останется заблокированным.'
})
const canSubmitReceiveConfirm = computed(() => {
  const preview = activeReceiveCapitalPreview.value
  return canOpenReceiveConfirm.value
    && !isLoadingReceivePlan.value
    && (
      requiresReceiveCapitalAllocation.value
        ? Boolean(preview && preview.status === 'READY' && !receiveCapitalEditing.value && !receiveCapitalValidationMessage.value && isReceiveCapitalConfirmed.value)
        : (!preview || (preview.status === 'READY' && receiveCapitalIsBalanced.value))
    )
})
const receiveSelectionLabel = computed(() => {
  if (!receivableLines.value.length) return 'Нет оплаченных строк'
  if (allReceivableSelected.value) return `Все готовые строки: ${receivableLines.value.length}`
  return `Выбрано: ${selectedReceiveLines.value.length} из ${receivableLines.value.length}`
})
const receiveProgressLabel = computed(() => {
  const plan = procurement.value?.receive_plan
  if (!plan) return ''
  const total = plan.received_items_count + plan.pending_paid_items_count + plan.draft_items_count
  if (!total) return 'Нет позиций'
  const left = plan.pending_paid_items_count + plan.draft_items_count
  return `${plan.received_items_count}/${total} позиций · осталось ${left}`
})
const receiveActionLabel = computed(() => {
  if (isConfirming.value) return 'Оприходование…'
  if (!canReceive.value) return 'Сначала свести баланс'
  if (!selectedReceiveLines.value.length) return 'Выберите позиции'
  if (receiveWillFinish.value) return 'Завершить приход'
  return 'Оприходовать выбранные'
})
const splitCandidateLine = computed(() => selectedReceiveLines.value.length === 1 ? selectedReceiveLines.value[0] : null)
const splitQuantityNumeric = computed(() => parsePositiveNumber(splitItemQuantity.value))
const splitRemainingQuantity = computed(() => {
  const line = splitCandidateLine.value
  if (!line) return 0
  const currentQuantity = Number(line.quantity)
  const next = splitQuantityNumeric.value
  if (next <= 0 || next >= currentQuantity) return currentQuantity
  return currentQuantity - next
})
const canSplitSelectedReceiveLine = computed(() => {
  const line = splitCandidateLine.value
  if (!line) return false
  return Number(line.quantity) > 1
})
const contractPartners = computed(() => procurement.value?.contract?.partners ?? [])
const contributionPartnerOptions = computed(() => contractPartners.value.map((partner) => ({
  value: partner.partner,
  label: `${partner.partner_name} · ${partner.role === 'INVESTOR' ? 'инвестор' : 'бизнес'}`,
})))
const balanceParticipantTotals = computed(() => procurement.value?.balance?.participant_totals ?? [])
const balanceHistoryEntries = computed(() => {
  const entries = procurement.value?.balance?.history ?? []
  return [...entries].sort((left, right) => {
    const leftTime = new Date(left.date).getTime()
    const rightTime = new Date(right.date).getTime()
    return leftTime - rightTime
  })
})
const visibleBalanceHistoryEntries = computed(() => showFullBalanceHistory.value
  ? balanceHistoryEntries.value
  : balanceHistoryEntries.value.slice(0, 6))
const hasCollapsedBalanceHistory = computed(() => balanceHistoryEntries.value.length > 6)
const balanceStatusKind = computed(() => {
  if (procurement.value?.receive_plan.status === 'READY') return 'success'
  return 'blocked'
})
const expenseTargetOptions = computed(() => {
  const paid = paidItems.value.map((line) => ({
    id: line.id,
    label: line.product_variant_name,
    meta: `${formatPlainAmount(line.quantity)} шт. · оплачено`,
  }))
  const draft = draftLines.value
    .filter((line) => line.serverId !== null && line.variant)
    .map((line) => ({
      id: line.serverId as number,
      label: variantDisplay(line.variant as ProductVariant),
      meta: `${formatPlainAmount(line.quantity)} шт. · черновик`,
    }))
  return [...paid, ...draft]
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
  const value = Number.parseFloat(String(raw ?? '').replace(/\s+/g, '').replace(',', '.'))
  return Number.isFinite(value) && value > 0 ? value : 0
}

function parseLooseNumber(raw: unknown): number {
  const normalized = String(raw ?? '').replace(/\s+/g, '').replace(',', '.').trim()
  if (!normalized) return 0
  const value = Number.parseFloat(normalized)
  return Number.isFinite(value) ? value : Number.NaN
}

function roundMoney(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.round((value + Number.EPSILON) * 100) / 100
}

function roundShare(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.round((value + Number.EPSILON) * 1_000_000) / 1_000_000
}

function formatDraftMoney(value: number): string {
  return trimTrailingZeros(roundMoney(value).toFixed(2))
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
  const isOpen = detail.status === ProcurementStatus.OPEN || detail.status === ProcurementStatus.PARTIALLY_RECEIVED
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
    target_item_ids: [],
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
  if (expandedExpenseTargetsId.value === rowId) {
    expandedExpenseTargetsId.value = null
  }
}

function updateDraftExpense(rowId: string, field: keyof Omit<DraftExpenseRow, 'id'>, value: string | number | null): void {
  draftExpenses.value = draftExpenses.value.map((expense) => expense.id === rowId ? { ...expense, [field]: value } as DraftExpenseRow : expense)
}

function setExpenseTargetsAll(rowId: string): void {
  draftExpenses.value = draftExpenses.value.map((expense) => expense.id === rowId
    ? { ...expense, target_item_ids: [] }
    : expense)
  if (expandedExpenseTargetsId.value === rowId) {
    expandedExpenseTargetsId.value = null
  }
}

function toggleExpenseTarget(rowId: string, itemId: number): void {
  draftExpenses.value = draftExpenses.value.map((expense) => {
    if (expense.id !== rowId) return expense
    const selected = new Set(expense.target_item_ids)
    if (selected.has(itemId)) {
      selected.delete(itemId)
    } else {
      selected.add(itemId)
    }
    return { ...expense, target_item_ids: Array.from(selected) }
  })
}

function isExpenseTargetsExpanded(rowId: string): boolean {
  return expandedExpenseTargetsId.value === rowId
}

function openExpenseTargets(rowId: string): void {
  const expense = draftExpenses.value.find((row) => row.id === rowId)
  if (!expense) return
  if (expense.target_item_ids.length === 0) {
    const allItemIds = expenseTargetOptions.value.map((item) => item.id)
    draftExpenses.value = draftExpenses.value.map((row) => row.id === rowId
      ? { ...row, target_item_ids: allItemIds }
      : row)
  }
  expandedExpenseTargetsId.value = rowId
}

function closeExpenseTargets(rowId: string): void {
  const totalItems = expenseTargetOptions.value.length
  if (totalItems > 0) {
    draftExpenses.value = draftExpenses.value.map((expense) => {
      if (expense.id !== rowId) return expense
      if (expense.target_item_ids.length === totalItems) {
        // Keep compact semantic: empty selection means "all positions".
        return { ...expense, target_item_ids: [] }
      }
      return expense
    })
  }
  if (expandedExpenseTargetsId.value === rowId) {
    expandedExpenseTargetsId.value = null
  }
}

function paidExpenseTargetIds(expense: ProcurementDetail['expenses'][number]): number[] {
  return paidExpenseTargetDrafts.value[expense.id] ?? expense.target_item_ids ?? []
}

function isPaidExpenseTargetsExpanded(expenseId: number): boolean {
  return expandedPaidExpenseId.value === expenseId
}

function setPaidExpenseTargetsAll(expenseId: number): void {
  paidExpenseTargetDrafts.value = {
    ...paidExpenseTargetDrafts.value,
    [expenseId]: [],
  }
  if (expandedPaidExpenseId.value === expenseId) {
    expandedPaidExpenseId.value = null
  }
}

function openPaidExpenseTargets(expenseId: number): void {
  const expense = paidExpenses.value.find((item) => item.id === expenseId)
  if (!expense) return
  const currentTargets = paidExpenseTargetIds(expense)
  if (currentTargets.length === 0) {
    paidExpenseTargetDrafts.value = {
      ...paidExpenseTargetDrafts.value,
      [expenseId]: expenseTargetOptions.value.map((item) => item.id),
    }
  }
  expandedPaidExpenseId.value = expenseId
}

function closePaidExpenseTargets(expenseId: number): void {
  const totalItems = expenseTargetOptions.value.length
  const expense = paidExpenses.value.find((item) => item.id === expenseId)
  if (expense && totalItems > 0 && paidExpenseTargetIds(expense).length === totalItems) {
    paidExpenseTargetDrafts.value = {
      ...paidExpenseTargetDrafts.value,
      [expenseId]: [],
    }
  }
  if (expandedPaidExpenseId.value === expenseId) {
    expandedPaidExpenseId.value = null
  }
}

function togglePaidExpenseTargets(expenseId: number): void {
  if (isPaidExpenseTargetsExpanded(expenseId)) {
    closePaidExpenseTargets(expenseId)
    return
  }
  openPaidExpenseTargets(expenseId)
}

function togglePaidExpenseTarget(expenseId: number, itemId: number): void {
  const expense = paidExpenses.value.find((item) => item.id === expenseId)
  if (!expense) return
  const selected = new Set(paidExpenseTargetIds(expense))
  if (selected.has(itemId)) {
    selected.delete(itemId)
  } else {
    selected.add(itemId)
  }
  paidExpenseTargetDrafts.value = {
    ...paidExpenseTargetDrafts.value,
    [expenseId]: Array.from(selected),
  }
}

function paidExpenseTargetsSummaryLabel(expense: ProcurementDetail['expenses'][number]): string {
  const targetIds = paidExpenseTargetIds(expense)
  if (targetIds.length === 0) return 'Выбрать конкретные товары'
  return `Выбрано позиций: ${targetIds.length}`
}

function toggleExpenseTargets(rowId: string): void {
  if (isExpenseTargetsExpanded(rowId)) {
    closeExpenseTargets(rowId)
    return
  }
  openExpenseTargets(rowId)
}

function expenseTargetsSummaryLabel(expense: DraftExpenseRow): string {
  if (expense.target_item_ids.length === 0) return 'Выбрать конкретные товары'
  return `Выбрано позиций: ${expense.target_item_ids.length}`
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
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
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
    PARTIALLY_RECEIVED: 'Частично оприходовано',
    RECEIVED: 'Приход завершён',
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
    AGREEMENT_SURPLUS: 'Остаток вернётся в договор',
    COSTS_UNPAID: 'Нужно сверить движения по балансу',
    DRAFT_PENDING: 'Есть позиции к оплате',
    RECALCULATE_OR_CONTRIBUTE: 'Нужна доплата или перерасчёт',
    CONTRIBUTION_REQUIRED: 'Нужна доплата',
    NO_ITEMS: 'Добавьте товары',
    NOT_OPEN: 'Закупка уже закрыта',
    COMPLETE: 'Приход завершён',
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
      hint: 'Баланс сведен. Выбери строки, которые фактически пришли на склад.',
    },
    AUTO_SURPLUS: {
      label: 'Нужно вернуть остаток',
      tone: 'warning',
      hint: 'После возврата излишка партнёрам оприходование станет доступно.',
    },
    AGREEMENT_SURPLUS: {
      label: 'Остаток в договор',
      tone: 'warning',
      hint: 'При оприходовании лишний баланс вернётся в общий инвестдоговор.',
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
    COMPLETE: {
      label: 'Приход завершён',
      tone: 'success',
      hint: 'Все строки этого прихода уже зафиксированы на складе.',
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
  const targets = paidExpenseTargetIds(expense)
  const scope = targets.length === 0 ? 'все позиции' : `${targets.length} поз.`
  return `${allocationMethodLabel(expense.allocation_method)} · ${scope}`
}

function focusExpenseTargetFix(): void {
  focusStage('operations')
  const selected = selectedReceiveIdSet.value
  const delayed = new Set<number>([
    ...receivableLines.value.filter((line) => !selected.has(line.item_id)).map((line) => line.item_id),
    ...pendingDraftItems.value.map((item) => item.id),
  ])
  const hasDelayedLines = delayed.size > 0
  const paidConflict = paidExpenses.value.find((expense) => {
    const targets = paidExpenseTargetIds(expense)
    if (!targets.length) return hasDelayedLines
    return targets.some((id) => selected.has(id)) && targets.some((id) => delayed.has(id))
  })
  if (paidConflict) {
    expandedPaidExpenseId.value = paidConflict.id
    return
  }
  const draftConflict = draftExpenses.value.find((expense) => {
    const targets = expense.target_item_ids ?? []
    if (!targets.length) return true
    return targets.some((id) => selected.has(id))
  })
  if (draftConflict) {
    expandedDraftExpenseId.value = draftConflict.id
    openExpenseTargets(draftConflict.id)
  }
}

function selectItemForReceive(itemId: number): void {
  selectedReceiveItemIds.value = [itemId]
  focusStage('receive')
  void nextTick(() => refreshReceiveCapitalPreview())
}

async function splitRoadItem(itemId: number): Promise<void> {
  selectedReceiveItemIds.value = [itemId]
  focusStage('receive')
  await nextTick()
  void refreshReceiveCapitalPreview()
  openSplitItemSheet()
}

function toggleCostPreviewScenario(key: string): void {
  expandedCostPreviewKey.value = expandedCostPreviewKey.value === key ? null : key
}

function toggleReceiveBatch(batchId: number): void {
  expandedReceiveBatchId.value = expandedReceiveBatchId.value === batchId ? null : batchId
}

function syncReceiveSelection(): void {
  selectedReceiveItemIds.value = receivableLines.value.length
    ? [receivableLines.value[0].item_id]
    : []
  void nextTick(() => refreshReceiveCapitalPreview())
}

function toggleReceiveLine(itemId: number): void {
  const selected = new Set(selectedReceiveItemIds.value)
  if (selected.has(itemId)) {
    selected.delete(itemId)
  } else {
    selected.add(itemId)
  }
  selectedReceiveItemIds.value = Array.from(selected)
  void nextTick(() => refreshReceiveCapitalPreview())
}

function toggleAllReceiveLines(): void {
  selectedReceiveItemIds.value = allReceivableSelected.value
    ? []
    : receivableLines.value.map((line) => line.item_id)
  void nextTick(() => refreshReceiveCapitalPreview())
}

let receivePlanRequestId = 0

watch(
  [
    () => procurement.value?.id,
    () => procurement.value?.status,
    () => procurement.value?.procurement_type,
    receiveCapitalSelectionKey,
  ],
  () => {
    void refreshReceiveCapitalPreview()
  },
  { immediate: true },
)

function apiErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as {
      response?: {
        data?: {
          detail?: unknown
          [key: string]: unknown
        } | string
      }
    }).response
    const payload = response?.data
    if (typeof payload === 'string' && payload.trim().length) return payload
    if (payload && typeof payload === 'object') {
      if (typeof payload.detail === 'string' && payload.detail.trim().length) return payload.detail
      for (const value of Object.values(payload)) {
        if (typeof value === 'string' && value.trim().length) return value
        if (Array.isArray(value) && value.length && typeof value[0] === 'string') return value[0]
      }
    }
  }
  if (error instanceof Error && error.message.trim().length) return error.message
  return fallback
}

function setReceiveCapitalDraft(partnerId: number, value: string): void {
  receiveCapitalConfirmedKey.value = ''
  const preview = activeReceiveCapitalPreview.value
  const rows = receiveCapitalRows.value
  const targetRow = rows.find((row) => row.partner_id === partnerId)

  if (!preview || preview.status !== 'READY' || !targetRow) {
    receiveCapitalDrafts.value = {
      ...receiveCapitalDrafts.value,
      [partnerId]: value,
    }
    receiveCapitalDraftIssue.value = ''
    return
  }

  const parsed = parseLooseNumber(value)
  if (!Number.isFinite(parsed) || parsed < 0) {
    receiveCapitalDrafts.value = {
      ...receiveCapitalDrafts.value,
      [partnerId]: value,
    }
    receiveCapitalDraftIssue.value = 'Укажи корректную сумму доли.'
    return
  }

  const required = roundMoney(receiveCapitalRequired.value)
  const targetAmount = roundMoney(parsed)
  const nextDrafts: Record<number, string> = {
    ...receiveCapitalDrafts.value,
    [partnerId]: value,
  }

  const otherRows = rows.filter((row) => row.partner_id !== partnerId)
  const remainderNeeded = roundMoney(required - targetAmount)

  if (!otherRows.length) {
    receiveCapitalDrafts.value = {
      [partnerId]: formatDraftMoney(targetAmount),
    }
    receiveCapitalDraftIssue.value = remainderNeeded === 0
      ? ''
      : `Сумма партии должна равняться ${formatCompactAmount(required, receiveCapitalCurrency.value)}.`
    return
  }

  if (remainderNeeded <= 0) {
    for (const row of otherRows) {
      nextDrafts[row.partner_id] = '0'
    }
    receiveCapitalDrafts.value = nextDrafts
    receiveCapitalDraftIssue.value = remainderNeeded < 0
      ? `Сумма партии превышена на ${formatCompactAmount(Math.abs(remainderNeeded), receiveCapitalCurrency.value)}.`
      : ''
    return
  }

  const distributionPool = otherRows.map((row) => ({
    partnerId: row.partner_id,
    available: roundMoney(parsePositiveNumber(row.available_amount)),
    basis: roundMoney(parseLooseNumber(receiveCapitalDrafts.value[row.partner_id] ?? row.amount) || parsePositiveNumber(row.amount) || 0),
  }))
  const totalOtherAvailable = distributionPool.reduce((sum, row) => sum + row.available, 0)

  if (remainderNeeded - totalOtherAvailable > 0.01) {
    for (const row of distributionPool) {
      nextDrafts[row.partnerId] = formatDraftMoney(row.available)
    }
    receiveCapitalDrafts.value = nextDrafts
    receiveCapitalDraftIssue.value = `Остальным участникам не хватает ${formatCompactAmount(remainderNeeded - totalOtherAvailable, receiveCapitalCurrency.value)} для этой партии.`
    return
  }

  const allocations = new Map<number, number>()
  distributionPool.forEach((row) => allocations.set(row.partnerId, 0))
  let remaining = remainderNeeded
  let activePool = distributionPool

  while (remaining > 0.009 && activePool.length > 0) {
    const totalBasis = activePool.reduce((sum, row) => sum + (row.basis > 0 ? row.basis : 1), 0)
    let distributedThisRound = 0

    activePool.forEach((row, index) => {
      const capacity = roundMoney(row.available - (allocations.get(row.partnerId) ?? 0))
      if (capacity <= 0) return
      const share = totalBasis > 0 ? ((row.basis > 0 ? row.basis : 1) / totalBasis) : (1 / activePool.length)
      const suggested = index === activePool.length - 1
        ? roundMoney(remaining - distributedThisRound)
        : roundMoney(remaining * share)
      const allocation = Math.min(capacity, Math.max(0, suggested))
      allocations.set(row.partnerId, roundMoney((allocations.get(row.partnerId) ?? 0) + allocation))
      distributedThisRound = roundMoney(distributedThisRound + allocation)
    })

    if (distributedThisRound <= 0) {
      const fallbackRow = activePool.find((row) => roundMoney(row.available - (allocations.get(row.partnerId) ?? 0)) > 0)
      if (!fallbackRow) break
      const fallbackCapacity = roundMoney(fallbackRow.available - (allocations.get(fallbackRow.partnerId) ?? 0))
      const fallbackAllocation = Math.min(fallbackCapacity, remaining)
      allocations.set(fallbackRow.partnerId, roundMoney((allocations.get(fallbackRow.partnerId) ?? 0) + fallbackAllocation))
      distributedThisRound = fallbackAllocation
    }

    remaining = roundMoney(remaining - distributedThisRound)
    activePool = distributionPool.filter((row) => roundMoney(row.available - (allocations.get(row.partnerId) ?? 0)) > 0)
  }

  for (const row of distributionPool) {
    nextDrafts[row.partnerId] = formatDraftMoney(allocations.get(row.partnerId) ?? 0)
  }

  receiveCapitalDrafts.value = nextDrafts
  receiveCapitalDraftIssue.value = remaining > 0.01
    ? `Не удалось распределить ещё ${formatCompactAmount(remaining, receiveCapitalCurrency.value)}.`
    : ''
}

function syncReceiveCapitalDrafts(preview: ReceiveBatchCapitalPreview | null): void {
  receiveCapitalDrafts.value = Object.fromEntries(
    (preview?.partners ?? []).map((row) => [row.partner_id, row.amount]),
  )
  receiveCapitalEditing.value = false
  receiveCapitalDraftIssue.value = ''
  receiveCapitalConfirmedKey.value = ''
}

function toggleReceiveCapitalEditing(): void {
  if (!activeReceiveCapitalPreview.value || activeReceiveCapitalPreview.value.status !== 'READY') return
  if (receiveCapitalEditing.value) {
    if (!canFinalizeReceiveCapitalEditing.value) return
    receiveCapitalEditing.value = false
    return
  }
  receiveCapitalConfirmedKey.value = ''
  receiveCapitalDraftIssue.value = ''
  receiveCapitalEditing.value = true
}

function confirmReceiveCapitalAllocation(): void {
  if (receiveCapitalEditing.value || !activeReceiveCapitalPreview.value || activeReceiveCapitalPreview.value.status !== 'READY') return
  if (receiveCapitalValidationMessage.value) return
  receiveCapitalConfirmedKey.value = receiveCapitalSelectionKey.value
}

function receiveCapitalPayload() {
  if (!receiveCapitalRows.value.length) return undefined
  return receiveCapitalRows.value.map((row) => ({
    partner_id: row.partner_id,
    amount: receiveCapitalDrafts.value[row.partner_id] ?? row.amount,
  }))
}

async function refreshReceiveCapitalPreview(showError = false): Promise<void> {
  const currentProcurement = procurement.value
  const key = receiveCapitalSelectionKey.value
  receivePlanRequestId += 1
  const requestId = receivePlanRequestId

  if (!currentProcurement || !requiresReceiveCapitalAllocation.value || !key) {
    receivePlanPreview.value = null
    receivePlanPreviewKey.value = ''
    receivePlanPreviewError.value = ''
    syncReceiveCapitalDrafts(null)
    return
  }

  if (
    receivePlanPreview.value
    && receivePlanPreviewKey.value === key
    && !receivePlanPreviewError.value
  ) {
    return
  }

  receivePlanPreview.value = null
  receivePlanPreviewKey.value = key
  receivePlanPreviewError.value = ''
  syncReceiveCapitalDrafts(null)
  isLoadingReceivePlan.value = true

  try {
    const plan = await fetchProcurementReceivePlan(
      currentProcurement.id,
      selectedReceiveLines.value.map((line) => line.item_id),
    )
    if (requestId !== receivePlanRequestId) return
    const preview = plan.batch_capital_preview ?? null
    if (plan.status === 'READY' && !preview) {
      receivePlanPreview.value = null
      receivePlanPreviewKey.value = key
      receivePlanPreviewError.value = RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE
      syncReceiveCapitalDrafts(null)
      if (showError) toast.error(RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE)
      return
    }
    receivePlanPreview.value = preview
    receivePlanPreviewKey.value = key
    receivePlanPreviewError.value = ''
    syncReceiveCapitalDrafts(preview?.status === 'READY' ? preview : null)
  } catch (error: unknown) {
    if (requestId !== receivePlanRequestId) return
    const message = apiErrorMessage(error, 'Не удалось рассчитать доли партии')
    receivePlanPreview.value = null
    receivePlanPreviewError.value = message
    if (showError) toast.error(message)
  } finally {
    if (requestId === receivePlanRequestId) {
      isLoadingReceivePlan.value = false
    }
  }
}

async function retryReceiveCapitalPreview(): Promise<void> {
  await refreshReceiveCapitalPreview(true)
}

async function openReceiveConfirm(): Promise<void> {
  if (!canOpenReceiveConfirm.value) return
  receiveConfirmSheetOpen.value = true
  if (requiresReceiveCapitalAllocation.value && !activeReceiveCapitalPreview.value) {
    await refreshReceiveCapitalPreview(true)
  }
}

function closeReceiveConfirm(): void {
  if (isConfirming.value) return
  receiveConfirmSheetOpen.value = false
  receiveCapitalEditing.value = false
}

function openSplitItemSheet(): void {
  const line = splitCandidateLine.value
  if (!line || !canSplitSelectedReceiveLine.value) return
  splitItemQuantity.value = ''
  splitItemError.value = ''
  splitItemSheetOpen.value = true
}

function closeSplitItemSheet(): void {
  if (isSplittingItem.value) return
  splitItemSheetOpen.value = false
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

function closeAllocationSheet(): void {
  allocationSheetOpen.value = false
}

async function openAgreementAllocationSheet(): Promise<void> {
  if (!procurement.value?.agreement) return
  allocationError.value = null
  allocationPreview.value = null
  allocationSheetOpen.value = true
  isLoadingAllocation.value = true
  try {
    if (hasDraftChanges.value) {
      const saved = await saveDraftWorkspace()
      if (!saved) return
    }
    allocationPreview.value = await fetchAgreementAllocationPreview(procurement.value.agreement, procurement.value.id)
  } catch (error: unknown) {
    allocationError.value = error instanceof Error ? error.message : 'Не удалось рассчитать распределение'
  } finally {
    isLoadingAllocation.value = false
  }
}

async function applyAgreementAllocation(): Promise<void> {
  if (!procurement.value?.agreement || !allocationPreview.value) return
  const rows = allocationPreview.value.suggestions
    .filter((row) => Number(row.amount) > 0)
    .map((row) => ({
      partner_id: row.partner_id,
      amount: row.amount,
      currency: row.currency,
      fx_rate: row.currency === 'USD' ? latestUsdRate.value : '1',
    }))
  if (!rows.length) {
    allocationError.value = 'Нет доступной суммы для распределения'
    return
  }
  isAllocatingFromAgreement.value = true
  try {
    await createAgreementAllocations(procurement.value.agreement, {
      procurement_id: procurement.value.id,
      allocations: rows,
    })
    toast.success('Капитал перенесён из инвестдоговора')
    closeAllocationSheet()
    await loadProcurement({ silent: true })
  } catch (error: unknown) {
    allocationError.value = error instanceof Error ? error.message : 'Не удалось перенести капитал'
  } finally {
    isAllocatingFromAgreement.value = false
  }
}

async function loadLatestRate(): Promise<void> {
  try {
    const latest = await fetchLatestFxRate({
      base_currency: 'USD',
      quote_currency: 'UZS',
    })
    latestUsdRate.value = String(latest.rate)
  } catch {
    latestUsdRate.value = '12100'
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
      target_item_ids: expense.target_item_ids ?? [],
    }))
  paidExpenseTargetDrafts.value = Object.fromEntries(
    detail.expenses
      .filter((expense) => expense.status === 'PAID')
      .map((expense) => [expense.id, expense.target_item_ids ?? []]),
  )
  expandedDraftLineId.value = draftLines.value[0]?.id ?? null
  expandedDraftExpenseId.value = draftExpenses.value[0]?.id ?? null
  expandedPaidExpenseId.value = null
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
      agreement_id: procurement.value.agreement,
      notes: procurement.value.notes,
      contract: buildContractPayload(procurement.value),
      items: draftLines.value.map((line) => ({
        id: line.serverId ?? undefined,
        product_variant_id: line.variant!.id,
        quantity: parseFloat(line.quantity),
        unit_purchase_price: parseFloat(line.cost_per_unit),
        currency: normalizeCurrency(line.currency),
        fx_rate: showFxField(line.currency) ? line.fx_rate : '1',
      })),
      expenses: draftExpenses.value.map((expense) => ({
        id: expense.serverId ?? undefined,
        expense_type: expense.expense_type,
        amount: parseFloat(expense.amount),
        currency: normalizeCurrency(expense.currency),
        fx_rate: showFxField(expense.currency) ? expense.fx_rate : '1',
        allocation_method: expense.allocation_method,
        notes: expense.notes.trim(),
        target_item_ids: expense.target_item_ids,
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

async function savePaidExpenseTargets(expense: ProcurementDetail['expenses'][number]): Promise<void> {
  if (!procurement.value) return
  savingExpenseTargetsId.value = expense.id
  try {
    await updateProcurementExpenseTargets(procurement.value.id, {
      expense_id: expense.id,
      target_item_ids: paidExpenseTargetIds(expense),
    })
    toast.success('Товары расхода обновлены')
    await loadProcurement({ silent: true })
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : 'Не удалось обновить товары расхода')
  } finally {
    savingExpenseTargetsId.value = null
  }
}

function sumDraftItemRequirements(itemIds?: number[]): Record<string, number> {
  const selectedIds = itemIds?.length ? new Set(itemIds) : null
  return draftLines.value
    .filter((line) => !selectedIds || (line.serverId !== null && selectedIds.has(line.serverId)))
    .reduce<Record<string, number>>((acc, line) => {
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
  if (procurement.value?.agreement) {
    toast.error(`Для ${contextLabel} не хватает ${shortfall.currency}. Открыл распределение из инвестдоговора.`)
    void openAgreementAllocationSheet()
    focusStage('balance')
    return
  }
  toast.error(`Для ${contextLabel} не хватает ${shortfall.currency}. Открыл пополнение баланса.`)
  openContributionSheet(shortfall.currency)
  focusStage('balance')
}

async function payDraftItemBatch(itemIds?: number[]): Promise<void> {
  if (!procurement.value) return
  if (draftLines.value.length === 0) {
    toast.error('Нет неоплаченных товаров')
    return
  }
  const saved = await saveDraftWorkspace()
  if (!saved) return
  const targetItemIds = itemIds?.length ? itemIds : undefined
  const required = sumDraftItemRequirements(targetItemIds)
  if (targetItemIds && Object.keys(required).length === 0) {
    toast.error('Эту строку уже нельзя оплатить')
    return
  }
  const shortfall = detectShortfall(required)
  if (shortfall) {
    handleShortfall(shortfall, 'оплаты товаров')
    return
  }
  isPayingItems.value = true
  try {
    await payProcurementItems(procurement.value.id, targetItemIds ? { item_ids: targetItemIds } : undefined)
    toast.success(targetItemIds ? 'Товар оплачен из баланса прихода' : 'Товары оплачены из баланса прихода')
    await loadProcurement({ silent: true })
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
    await loadProcurement({ silent: true })
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
    await loadProcurement({ silent: true })
  } catch (error: unknown) {
    exchangeError.value = error instanceof Error ? error.message : 'Не удалось провести обмен'
    toast.error(exchangeError.value)
  } finally {
    isSavingExchange.value = false
  }
}

async function loadProcurement(options: { silent?: boolean } = {}): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    errorMessage.value = 'Некорректный ID закупки'
    isLoading.value = false
    return
  }

  const shouldShowLoader = !options.silent && procurement.value === null
  if (shouldShowLoader) {
    isLoading.value = true
  }
  errorMessage.value = null
  try {
    const detail = await fetchProcurement(id)
    syncStageState(detail, procurement.value === null)
    procurement.value = detail
    populateDraftWorkspace(detail)
    if (!options.silent) {
      showFullBalanceHistory.value = false
      expandedBalanceHistoryId.value = null
      expandedCostPreviewKey.value = null
    }
    syncReceiveSelection()
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить закупку'
  } finally {
    if (shouldShowLoader) {
      isLoading.value = false
    }
  }
}

async function loadLocations() {
  const items = await fetchLocations()
  const activeLocations = items.filter((location) => location.is_active !== false)
  locations.value = activeLocations.map((location) => ({
    value: location.id,
    label: location.name,
    kind: location.kind,
    location_type: location.location_type,
  }))
  if (selectedWarehouseId.value === null && locations.value.length > 0) {
    const defaultStorage = locations.value.find((location) => location.kind === 'storage' || location.location_type === 'warehouse')
    selectedWarehouseId.value = (defaultStorage ?? locations.value[0]).value
  }
}

async function confirmReceipt(): Promise<void> {
  if (!procurement.value || !canSubmitReceiveConfirm.value || selectedWarehouseId.value === null) return

  const wasFinalReceive = receiveWillFinish.value
  isConfirming.value = true
  try {
    const updated = await receiveProcurement(
      procurement.value.id,
      selectedWarehouseId.value,
      selectedReceiveLines.value.map((line) => line.item_id),
      receiveCapitalPayload(),
    )
    procurement.value = updated
    receiveConfirmSheetOpen.value = false
    toast.success(wasFinalReceive ? 'Приход завершён' : 'Партия оприходована')
    await loadProcurement({ silent: true })
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось оприходовать закупку'
    toast.error(message)
  } finally {
    isConfirming.value = false
  }
}

async function submitSplitItem(): Promise<void> {
  const line = splitCandidateLine.value
  if (!procurement.value || !line) return
  splitItemError.value = ''
  const quantity = parsePositiveNumber(splitItemQuantity.value)
  const currentQuantity = Number(line.quantity)
  if (quantity <= 0 || quantity >= currentQuantity) {
    splitItemError.value = `Укажи количество больше 0 и меньше ${formatPlainAmount(line.quantity)}`
    return
  }

  isSplittingItem.value = true
  try {
    const updated = await splitProcurementItem(procurement.value.id, {
      item_id: line.item_id,
      quantity: splitItemQuantity.value,
    })
    procurement.value = updated
    splitItemSheetOpen.value = false
    toast.success('Строка разделена')
    await loadProcurement({ silent: true })
  } catch (error: unknown) {
    splitItemError.value = apiErrorMessage(error, 'Не удалось разделить строку')
    toast.error(splitItemError.value)
  } finally {
    isSplittingItem.value = false
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
    await loadProcurement({ silent: true })
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
    await loadProcurement({ silent: true })
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
      <button class="retry-btn" type="button" @click="() => loadProcurement()">Повторить</button>
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

          <button
            v-if="procurement.agreement"
            class="source-strip"
            type="button"
            @click="router.push({ name: 'agreement-detail', params: { id: procurement.agreement } })"
          >
            <span>Источник</span>
            <strong>{{ procurement.agreement_label || `Инвестдоговор #${procurement.agreement}` }}</strong>
          </button>
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
                <span class="subtle-meta">{{ balanceParticipantTotals.length }} участ.</span>
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
                  <span>Операция</span>
                  <span>Тип</span>
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
                      <div class="money-flow-main">
                        <strong class="participant-name">{{ entry.title }}</strong>
                        <span class="line-qty">
                          {{ formatDateTime(entry.date) }}
                          <template v-if="entry.partner_name"> · {{ displayPartnerName(entry.partner_name, entry.partner_role) }}</template>
                        </span>
                      </div>
                      <div class="money-flow-side">
                        <span class="money-flow-kind">
                          {{ balanceHistoryKindLabel(entry.kind) }}
                        </span>
                        <strong class="tabular-nums history-amount money-flow-amount" :class="balanceHistoryAmountClass(entry.kind)">
                          {{ balanceHistorySignedAmount(entry.kind, entry.amount, entry.currency) }}
                        </strong>
                      </div>
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
              <button v-if="canAllocateFromAgreement" class="action-btn" type="button" @click="openAgreementAllocationSheet">
                <Wallet :size="16" :stroke-width="2" />
                Из договора
              </button>
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
                  <span class="subtle-meta">{{ paidItems.length }} поз.</span>
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
                  <span class="subtle-meta">{{ draftLines.length }} поз.</span>
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
                              step="0.000001"
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
                <button v-if="draftLines.length" class="action-btn" type="button" :disabled="isPayingItems || draftLines.length === 0" @click="() => payDraftItemBatch()">
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
                  <span class="subtle-meta">{{ paidExpenses.length }} расх.</span>
                </div>
                <div class="record-table">
                  <div class="record-table-head">
                    <span>Расход</span>
                    <span>Статус</span>
                    <span>Сумма</span>
                  </div>
                  <article
                    v-for="expense in paidExpenses"
                    :key="expense.id"
                    class="record-entry"
                    :class="{ 'record-entry--open': expandedPaidExpenseId === expense.id }"
                  >
                    <button class="record-row-toggle" type="button" @click="expandedPaidExpenseId = expandedPaidExpenseId === expense.id ? null : expense.id">
                      <div class="record-main">
                        <strong class="participant-name">{{ expenseTypeLabel[expense.expense_type] ?? expense.expense_type }}</strong>
                        <span class="line-qty">{{ paidExpenseSummary(expense) }}</span>
                      </div>
                      <span class="record-status record-status--settled">Оплачено</span>
                      <strong class="tabular-nums record-amount">{{ formatPrice(Number(expense.amount), expense.currency) }}</strong>
                      <ChevronDown class="stage-chevron record-chevron" :class="{ 'stage-chevron--open': expandedPaidExpenseId === expense.id }" :size="16" :stroke-width="2" />
                    </button>
                    <div v-if="expandedPaidExpenseId === expense.id" class="record-panel">
                      <div v-if="expenseTargetOptions.length" class="field-group">
                        <label class="field-label">К каким товарам относится расход</label>
                        <div class="target-toggle-row">
                          <button
                            class="target-toggle"
                            :class="{ active: paidExpenseTargetIds(expense).length === 0 }"
                            type="button"
                            @click="setPaidExpenseTargetsAll(expense.id)"
                          >
                            Все позиции
                          </button>
                          <button
                            class="target-toggle target-toggle--hint"
                            :class="{ active: paidExpenseTargetIds(expense).length > 0 }"
                            type="button"
                            @click="togglePaidExpenseTargets(expense.id)"
                          >
                            <span>{{ paidExpenseTargetsSummaryLabel(expense) }}</span>
                            <ChevronDown class="target-trigger-icon" :class="{ 'target-trigger-icon--open': isPaidExpenseTargetsExpanded(expense.id) }" :size="14" :stroke-width="2" />
                          </button>
                        </div>
                        <p v-if="!isPaidExpenseTargetsExpanded(expense.id)" class="target-helper">
                          Для частичного оприходования лучше выбрать конкретные товары.
                        </p>
                        <div v-if="isPaidExpenseTargetsExpanded(expense.id)" class="target-picker-list">
                          <button
                            v-for="item in expenseTargetOptions"
                            :key="item.id"
                            class="target-toggle"
                            :class="{ active: paidExpenseTargetIds(expense).includes(item.id) }"
                            type="button"
                            @click="togglePaidExpenseTarget(expense.id, item.id)"
                          >
                            <span>{{ item.label }}</span>
                            <small>{{ item.meta }}</small>
                          </button>
                          <button class="target-picker-close" type="button" @click="closePaidExpenseTargets(expense.id)">
                            Скрыть список
                          </button>
                        </div>
                      </div>
                      <button
                        class="action-btn action-btn--secondary"
                        type="button"
                        :disabled="savingExpenseTargetsId === expense.id"
                        @click="savePaidExpenseTargets(expense)"
                      >
                        {{ savingExpenseTargetsId === expense.id ? 'Сохраняю…' : 'Сохранить товары расхода' }}
                      </button>
                    </div>
                  </article>
                </div>
              </div>

              <div v-if="paidExpenses.length && draftExpenses.length" class="workspace-separator" />

              <div v-if="draftExpenses.length" class="draft-block">
                <div class="section-inline-head">
                  <span class="group-label">К оплате</span>
                  <span class="subtle-meta">{{ draftExpenses.length }} расх.</span>
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
                      <div v-if="expenseTargetOptions.length" class="field-group">
                        <label class="field-label">К каким товарам относится расход</label>
                        <div class="target-toggle-row">
                          <button
                            class="target-toggle"
                            :class="{ active: expense.target_item_ids.length === 0 }"
                            type="button"
                            @click="setExpenseTargetsAll(expense.id)"
                          >
                            Все позиции
                          </button>
                          <button
                            class="target-toggle target-toggle--hint"
                            :class="{ active: expense.target_item_ids.length > 0 }"
                            type="button"
                            @click="toggleExpenseTargets(expense.id)"
                          >
                            <span>{{ expenseTargetsSummaryLabel(expense) }}</span>
                            <ChevronDown class="target-trigger-icon" :class="{ 'target-trigger-icon--open': isExpenseTargetsExpanded(expense.id) }" :size="14" :stroke-width="2" />
                          </button>
                        </div>
                        <p v-if="!isExpenseTargetsExpanded(expense.id)" class="target-helper">
                          Используйте выборочно, если расход относится не ко всем товарам.
                        </p>
                        <div v-if="isExpenseTargetsExpanded(expense.id)" class="target-picker-list">
                          <button
                            v-for="item in expenseTargetOptions"
                            :key="item.id"
                            class="target-toggle"
                            :class="{ active: expense.target_item_ids.includes(item.id) }"
                            type="button"
                            @click="toggleExpenseTarget(expense.id, item.id)"
                          >
                            <span>{{ item.label }}</span>
                            <small>{{ item.meta }}</small>
                          </button>
                          <button class="target-picker-close" type="button" @click="closeExpenseTargets(expense.id)">
                            Скрыть список
                          </button>
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
          <div class="procurement-flow-strip">
            <div class="procurement-flow-item procurement-flow-item--wide">
              <span>Всего в приходе</span>
              <strong class="tabular-nums">{{ formatPrice(procurementTotal) }}</strong>
            </div>
            <div class="procurement-flow-item">
              <span>Товары</span>
              <strong class="tabular-nums">{{ formatPrice(totalAmount) }}</strong>
            </div>
            <div class="procurement-flow-item">
              <span>Расходы</span>
              <strong class="tabular-nums">{{ formatPrice(expensesTotal) }}</strong>
            </div>
          </div>

          <div v-if="canWorkOnProcurement && costPreviewScenarios.length" class="cost-preview-panel">
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
                  <div class="cost-preview-meta-grid">
                    <span>
                      <small>Расходы</small>
                      <strong class="tabular-nums">{{ costPreviewScenarioExpenses(scenario.basis.total_expenses_uzs) }}</strong>
                    </span>
                  </div>
                  <ChevronDown class="stage-chevron cost-preview-chevron" :class="{ 'stage-chevron--open': expandedCostPreviewKey === scenario.key }" :size="16" :stroke-width="2" />
                </button>

                <div v-if="expandedCostPreviewKey === scenario.key" class="cost-preview-detail">
                  <div class="cost-preview-lines">
                    <div
                      v-for="line in scenario.basis.lines"
                      :key="`${scenario.key}-${line.item_id}-${line.status}`"
                      class="cost-preview-line"
                    >
                      <div class="cost-preview-line-main">
                        <strong class="participant-name">{{ line.product_variant_name }}</strong>
                        <span class="line-qty">{{ costPreviewLineSummary(line, scenario.showStatus) }}</span>
                      </div>
                      <div class="cost-preview-line-metrics">
                        <span>
                          <small>Себес./шт</small>
                          <strong class="tabular-nums">{{ formatPrice(line.landed_cost_per_unit_uzs) }}</strong>
                        </span>
                        <span>
                          <small>Расход</small>
                          <strong class="tabular-nums">{{ formatPrice(line.allocated_expense_uzs) }}</strong>
                        </span>
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
            <div class="receive-headline">
              <div>
                <span class="summary-label">Состояние</span>
                <strong>{{ procurementStatusLabel(procurement.status) }}</strong>
                <small>{{ receiveProgressLabel }}</small>
              </div>
              <span
                class="status-pill"
                :class="procurement.status === 'RECEIVED' ? 'status-pill--success' : 'status-pill--blocked'"
              >
                {{ receiveStatusMeta(procurement.receive_plan.status).label }}
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

            <div v-if="receiveBatches.length" class="receive-process-block">
              <div class="receive-process-head">
                <div>
                  <span>На складе</span>
                  <strong>{{ procurement.receive_plan.received_items_count }} позиций</strong>
                </div>
                <span>{{ receiveBatches.length }} парт.</span>
              </div>
              <div class="receive-batch-list">
                <article
                  v-for="batch in receiveBatches"
                  :key="batch.id"
                  class="receive-batch"
                >
                  <button type="button" class="receive-batch-head" @click="toggleReceiveBatch(batch.id)">
                    <span>Партия #{{ batch.id }} · {{ batch.warehouse_name }}</span>
                    <strong>{{ formatPrice(batch.total_inventory_uzs) }}</strong>
                  </button>
	                  <div v-if="expandedReceiveBatchId === batch.id" class="receive-batch-lines">
	                    <div v-for="line in batch.lines" :key="line.id" class="receive-batch-line">
	                      <span>{{ line.product_variant_name }}</span>
	                      <strong>{{ formatPlainAmount(line.quantity) }} шт. · {{ formatPrice(line.landed_cost_per_unit_uzs) }}</strong>
	                    </div>
	                    <div v-for="row in batch.capital_allocations" :key="`batch-capital-${batch.id}-${row.partner}`" class="receive-batch-line receive-batch-line--capital">
	                      <span>{{ displayPartnerName(row.partner_name, row.role) }}</span>
	                      <strong>{{ formatSharePercent(row.capital_share) }} кап. · {{ formatSharePercent(row.profit_share) }} приб.</strong>
	                    </div>
	                  </div>
	                </article>
              </div>
            </div>

            <div v-if="canConfirm" class="receive-inline-card">
              <div class="receive-scope-panel">
                <div class="receive-scope-head">
                  <div>
                    <strong>Следующее оприходование</strong>
                    <span>{{ receiveSelectionLabel }}</span>
                  </div>
                  <span class="receive-scope-status">
                    <b>{{ paidItems.length }} оплач.</b>
                    <i aria-hidden="true" />
                    <b>{{ pendingDraftItems.length }} черн.</b>
                  </span>
                  <button class="target-picker-close receive-select-all-btn" type="button" :disabled="!receivableLines.length" @click="toggleAllReceiveLines">
                    {{ allReceivableSelected ? 'Снять всё' : 'Выбрать всё' }}
                  </button>
                </div>
                <p class="receive-scope-hint">
                  Выберите строки, которые приехали сейчас. Если приехала только часть позиции, разделите строку.
                </p>

                <div v-if="requiresReceiveCapitalAllocation" class="receive-capital-inline">
                  <div class="receive-capital-inline-head">
                    <span>Доли выбранной партии</span>
                    <strong v-if="activeReceiveCapitalPreview?.status === 'READY'" class="tabular-nums">
                      {{ formatCompactAmount(activeReceiveCapitalPreview.required_amount, activeReceiveCapitalPreview.currency) }}
                    </strong>
                    <strong v-else>{{ isLoadingReceivePlan ? 'Расчёт…' : (receivePlanPreviewError ? 'Ошибка расчёта' : (activeReceiveCapitalPreview ? 'Проверка нужна' : 'Расчёт не получен')) }}</strong>
                  </div>
                  <p v-if="isLoadingReceivePlan" class="receive-capital-inline-note">
                    Считаю, кто какой капитал фиксирует в этой партии.
                  </p>
                  <div v-else-if="receivePlanPreviewError" class="receive-capital-inline-alert">
                    <p class="receive-capital-inline-warning">{{ receivePlanPreviewError }}</p>
                    <button type="button" class="receive-capital-inline-action" @click="retryReceiveCapitalPreview">
                      Повторить расчёт
                    </button>
                  </div>
                  <div v-else-if="activeReceiveCapitalPreview && activeReceiveCapitalPreview.status !== 'READY'" class="receive-capital-inline-alert">
                    <p class="receive-capital-inline-warning">
                      {{ activeReceiveCapitalPreview.message || RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE }}
                    </p>
                    <button type="button" class="receive-capital-inline-action" @click="retryReceiveCapitalPreview">
                      Повторить расчёт
                    </button>
                  </div>
                  <div v-else-if="!activeReceiveCapitalPreview" class="receive-capital-inline-alert">
                    <p class="receive-capital-inline-warning">{{ RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE }}</p>
                    <button type="button" class="receive-capital-inline-action" @click="retryReceiveCapitalPreview">
                      Повторить расчёт
                    </button>
                  </div>
                  <div v-else class="receive-capital-inline-list">
                    <span v-for="row in receiveCapitalDisplayRows" :key="`inline-capital-${row.partner_id}`">
                      <b>{{ displayPartnerName(row.partner_name, row.role) }}</b>
                      <em>{{ formatCompactAmount(row.amount, receiveCapitalCurrency) }} · приб. {{ formatSharePercent(row.profitShare) }}</em>
                    </span>
                  </div>
                </div>

                <div v-if="receivableLines.length" class="receive-line-list">
                  <div
                    v-for="line in receivableLines"
                    :key="line.item_id"
                    class="receive-line-option"
                    :class="{ 'receive-line-option--active': selectedReceiveIdSet.has(line.item_id) }"
                  >
                    <button
                      class="receive-line-select"
                      type="button"
                      @click="toggleReceiveLine(line.item_id)"
                    >
                      <span class="receive-line-check">
                        <CheckCircle2 v-if="selectedReceiveIdSet.has(line.item_id)" :size="16" :stroke-width="2" />
                      </span>
                      <span class="receive-line-main">
                        <strong>{{ line.product_variant_name }}</strong>
                        <small>{{ formatPlainAmount(line.quantity) }} шт. · {{ formatPrice(line.landed_cost_per_unit_uzs) }} / шт.</small>
                      </span>
                    </button>
                    <button
                      v-if="Number(line.quantity) > 1"
                      class="receive-line-split-action"
                      type="button"
                      @click="splitRoadItem(line.item_id)"
                    >
                      Разделить
                    </button>
                  </div>
                </div>
                <p v-else class="muted">Оплаченные строки для следующего оприходования появятся здесь.</p>

                <div v-if="pendingDraftItems.length" class="receive-draft-list">
                  <div v-for="item in pendingDraftItems" :key="`draft-${item.id}`" class="receive-draft-row">
                    <span>{{ item.product_variant_name }}</span>
                    <button type="button" :disabled="isPayingItems" @click="payDraftItemBatch([item.id])">Оплатить</button>
                  </div>
                </div>

                <div v-if="receivePartialMode" class="receive-scope-warning">
                  На склад попадут только выбранные строки. Остальные останутся в пути.
                </div>
                <div v-if="receiveWillFinish" class="receive-scope-success">
                  Это последнее оприходование по приходу. После подтверждения приход будет завершён.
                </div>
                <div v-if="receiveUnsafeExpenseScope" class="receive-scope-warning">
                  <span>Уточни товары у расходов: выбранная партия не должна смешиваться с отложенными позициями или неоплаченными расходами.</span>
                  <button type="button" @click="focusExpenseTargetFix">Настроить расходы</button>
                </div>
              </div>

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
                :disabled="isConfirming || !canOpenReceiveConfirm"
                @click="openReceiveConfirm"
              >
                <span v-if="isConfirming" class="spinner" />
                <CheckCircle2 v-else :size="18" :stroke-width="2" />
                <span>{{ receiveActionLabel }}</span>
              </button>
            </div>
          </div>
        </section>

        <section v-if="procurement.notes" class="card">
          <h2 class="section-title">Заметки</h2>
          <p class="notes">{{ procurement.notes }}</p>
        </section>
      </main>

      <AppBottomSheet :open="receiveConfirmSheetOpen" title="Подтвердить оприходование" @close="closeReceiveConfirm">
        <div class="sheet-form">
          <div class="receive-confirm-summary">
            <span>{{ receiveWillFinish ? 'Завершение прихода' : 'Оприходование партии' }}</span>
            <strong class="tabular-nums">{{ selectedReceiveLines.length }} поз. · {{ formatPrice(receiveSelectionTotal) }}</strong>
            <p>
              {{ receiveWillFinish
                ? 'После подтверждения все оставшиеся строки попадут на склад, а приход станет завершённым.'
                : 'На склад попадут только выбранные строки. Остальные позиции останутся в пути внутри этого прихода.' }}
            </p>
          </div>
	          <div class="receive-confirm-list">
	            <div v-for="line in selectedReceiveLines" :key="`confirm-${line.item_id}`" class="receive-confirm-row">
	              <span>{{ line.product_variant_name }}</span>
	              <strong class="tabular-nums">{{ formatPlainAmount(line.quantity) }} шт.</strong>
	            </div>
	          </div>
	          <div v-if="isLoadingReceivePlan" class="receive-capital-box">
	            <span class="summary-label">Доли партии</span>
	            <strong>Считаю распределение…</strong>
	          </div>
	          <div v-else-if="activeReceiveCapitalPreview" class="receive-capital-box">
	            <div class="receive-capital-head">
	              <div>
	                <span class="summary-label">Доли партии</span>
	                <strong>
                    {{ activeReceiveCapitalPreview.status === 'READY'
                      ? formatCompactAmount(activeReceiveCapitalPreview.required_amount, activeReceiveCapitalPreview.currency)
                      : 'Проверка нужна' }}
                  </strong>
	              </div>
                <div v-if="activeReceiveCapitalPreview.status === 'READY'" class="receive-capital-actions">
                  <button
                    type="button"
                    :disabled="receiveCapitalEditing && !canFinalizeReceiveCapitalEditing"
                    @click="toggleReceiveCapitalEditing"
                  >
                    {{ receiveCapitalEditing ? 'Готово' : 'Изменить' }}
                  </button>
                  <button
                    type="button"
                    class="receive-capital-approve"
                    :class="{ 'receive-capital-approve--done': isReceiveCapitalConfirmed }"
                    :disabled="receiveCapitalEditing || !!receiveCapitalValidationMessage || isReceiveCapitalConfirmed"
                    @click="confirmReceiveCapitalAllocation"
                  >
                    {{ isReceiveCapitalConfirmed ? 'Доли подтверждены' : 'Подтвердить доли' }}
                  </button>
                </div>
	            </div>
	            <template v-if="activeReceiveCapitalPreview.status !== 'READY'">
                <p class="receive-capital-warning">
                  {{ activeReceiveCapitalPreview.message || RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE }}
                </p>
                <button type="button" class="receive-capital-retry" @click="retryReceiveCapitalPreview">
                  Повторить расчёт
                </button>
              </template>
	            <div v-else class="receive-capital-list">
	              <div v-for="row in receiveCapitalDisplayRows" :key="`receive-capital-${row.partner_id}`" class="receive-capital-row">
	                <div>
	                  <span>{{ displayPartnerName(row.partner_name, row.role) }}</span>
	                  <small>{{ roleLabel(row.role) }} · кап. {{ formatSharePercent(row.capitalShare) }} · приб. {{ formatSharePercent(row.profitShare) }}</small>
	                </div>
	                <input
	                  v-if="receiveCapitalEditing"
	                  :value="receiveCapitalDrafts[row.partner_id] ?? row.amount"
	                  class="receive-capital-input"
	                  inputmode="decimal"
	                  type="text"
	                  @input="setReceiveCapitalDraft(row.partner_id, ($event.target as HTMLInputElement).value)"
	                />
	                <strong v-else class="tabular-nums">{{ formatCompactAmount(row.amount, receiveCapitalCurrency) }}</strong>
	              </div>
	            </div>
              <p v-if="receiveCapitalApprovalNote" class="receive-capital-note" :class="{ 'receive-capital-note--done': isReceiveCapitalConfirmed }">
                {{ receiveCapitalApprovalNote }}
              </p>
	            <div v-if="receiveCapitalValidationMessage" class="receive-capital-warning">
	              {{ receiveCapitalValidationMessage }}
	            </div>
	          </div>
            <div v-else-if="requiresReceiveCapitalAllocation" class="receive-capital-box">
              <span class="summary-label">Доли партии</span>
              <strong>Расчёт не получен</strong>
              <p class="receive-capital-warning">
                {{ RECEIVE_CAPITAL_PREVIEW_MISSING_MESSAGE }}
              </p>
              <button type="button" class="receive-capital-retry" @click="retryReceiveCapitalPreview">
                Повторить расчёт
              </button>
            </div>
            <p v-if="requiresReceiveCapitalAllocation && !isReceiveCapitalConfirmed" class="receive-submit-hint">
              Сначала подтверди доли партии. Только после этого станет доступно итоговое оприходование.
            </p>
	          <button
	            class="sheet-submit-btn"
	            type="button"
	            :disabled="isConfirming || !canSubmitReceiveConfirm"
	            @click="confirmReceipt"
	          >
            {{ isConfirming ? 'Оприходование…' : 'Подтвердить' }}
          </button>
        </div>
      </AppBottomSheet>

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

      <AppBottomSheet :open="allocationSheetOpen" title="Распределение капитала" @close="closeAllocationSheet">
        <div class="sheet-form">
          <div v-if="isLoadingAllocation" class="muted">Считаю требуемую сумму и доступные остатки...</div>

          <div v-else-if="allocationPreview" class="allocation-preview">
            <div class="allocation-summary">
              <span>Требуется в приход</span>
              <strong>
                <template v-for="(amount, currency, idx) in allocationPreview.required" :key="currency">
                  {{ formatCompactAmount(amount, currency) }}<template v-if="idx < Object.keys(allocationPreview.required).length - 1"> · </template>
                </template>
              </strong>
            </div>
            <div class="mini-table allocation-table">
              <div class="mini-table-head allocation-table-head">
                <span>Участник</span>
                <span>Доступно</span>
                <span>Перенести</span>
              </div>
              <div v-for="row in allocationPreview.suggestions" :key="`${row.partner_id}-${row.currency}`" class="mini-table-row allocation-table-row">
                <span class="participant-name">{{ displayPartnerName(row.partner_name, row.role) }}</span>
                <span class="participant-share tabular-nums">{{ formatCompactAmount(row.available, row.currency) }}</span>
                <strong class="tabular-nums">{{ formatCompactAmount(row.amount, row.currency) }}</strong>
              </div>
            </div>
          </div>

          <div v-if="allocationError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ allocationError }}</span>
          </div>

          <button
            class="sheet-submit-btn"
            type="button"
            :disabled="isLoadingAllocation || isAllocatingFromAgreement || !allocationPreview"
            @click="applyAgreementAllocation"
          >
            {{ isAllocatingFromAgreement ? 'Переношу…' : 'Перенести в приход' }}
          </button>
        </div>
      </AppBottomSheet>

      <AppBottomSheet :open="splitItemSheetOpen" title="Разделить строку" @close="closeSplitItemSheet">
        <div class="sheet-form">
          <div v-if="splitCandidateLine" class="receive-confirm-summary">
            <span>{{ splitCandidateLine.product_variant_name }}</span>
            <strong>{{ formatPlainAmount(splitCandidateLine.quantity) }} шт.</strong>
            <p>Укажи, сколько приехало сейчас. Остаток останется в пути отдельной строкой.</p>
          </div>
          <div v-if="splitCandidateLine" class="split-flow-preview">
            <div class="split-flow-card">
              <span>Сейчас на склад</span>
              <strong>{{ splitQuantityNumeric > 0 ? formatPlainAmount(splitQuantityNumeric) : '—' }} шт.</strong>
            </div>
            <span class="split-flow-arrow">→</span>
            <div class="split-flow-card split-flow-card--muted">
              <span>Останется в пути</span>
              <strong>{{ formatPlainAmount(splitRemainingQuantity) }} шт.</strong>
            </div>
          </div>
          <label class="field-group">
            <span>Количество, которое принять сейчас</span>
            <input
              v-model="splitItemQuantity"
              class="input-field split-quantity-input"
              inputmode="decimal"
              type="number"
              min="0"
              step="0.001"
              placeholder="Например, 30"
            />
          </label>
          <p v-if="splitItemError" class="form-error">{{ splitItemError }}</p>
          <button
            class="sheet-submit-btn"
            type="button"
            :disabled="isSplittingItem"
            @click="submitSplitItem"
          >
            {{ isSplittingItem ? 'Разделяю…' : 'Разделить' }}
          </button>
        </div>
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
.source-strip { width:100%; display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); margin-top: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-brand-50); color: var(--color-text-primary); text-align:left; }
.source-strip span { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.source-strip strong { font-size: var(--text-sm); }
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
.subtle-meta {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height: 24px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}
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
.money-flow-head { grid-template-columns: minmax(0, 1fr) auto auto; }
.money-flow-row { border-top: 1px solid var(--color-border-subtle); }
.money-flow-row--in { box-shadow: inset 3px 0 0 var(--color-success); }
.money-flow-row--out { box-shadow: inset 3px 0 0 var(--color-error); }
.money-flow-row--exchange { box-shadow: inset 3px 0 0 var(--color-brand-500); }
.money-flow-summary { width:100%; display:grid; grid-template-columns: minmax(0, 1fr) auto 16px; align-items:center; gap: var(--space-3); padding: var(--space-3); text-align:left; }
.money-flow-side { min-width: 86px; display:flex; flex-direction:column; align-items:flex-end; justify-content:center; gap: 5px; }
.money-flow-kind { display:inline-flex; align-items:center; justify-content:center; min-height:26px; padding: 0 var(--space-2); border-radius: var(--radius-full); border:1px solid transparent; font-size: var(--text-xs); font-weight: var(--font-semibold); white-space: nowrap; }
.money-flow-row--in .money-flow-kind { background: var(--color-success-bg); color: var(--color-success); }
.money-flow-row--out .money-flow-kind { background: var(--color-error-bg); color: var(--color-error); }
.money-flow-row--exchange .money-flow-kind { background: var(--color-brand-50); color: var(--color-brand-700); }
.money-flow-main { min-width: 0; display:grid; gap: 4px; }
.money-flow-amount { white-space: nowrap; line-height: 1.15; }
.money-flow-detail { display:grid; gap: 4px; padding: 0 var(--space-3) var(--space-3); }
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
.target-toggle-row { display:grid; gap: 6px; }
.target-picker-list { display:grid; gap: 6px; margin-top: 6px; }
.target-toggle { min-height: 38px; display:flex; align-items:center; justify-content:space-between; gap: var(--space-2); padding: 0 var(--space-3); border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-secondary); font-size: var(--text-sm); text-align:left; }
.target-toggle--hint { background: var(--color-bg-elevated); }
.target-toggle.active { border-color: var(--color-brand-500); background: var(--color-brand-50); color: var(--color-brand-700); font-weight: var(--font-semibold); }
.target-toggle small { color: var(--color-text-tertiary); font-size: var(--text-xs); }
.target-helper { color: var(--color-text-tertiary); font-size: var(--text-xs); line-height: 1.35; margin: 0; }
.target-trigger-icon { color: var(--color-text-tertiary); transition: transform 180ms ease; }
.target-trigger-icon--open { transform: rotate(180deg); }
.target-picker-close { min-height: 34px; justify-self: start; padding: 0 var(--space-2); border-radius: var(--radius-md); color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.receive-select-all-btn {
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
  box-shadow: 0 1px 0 rgba(17, 24, 39, 0.04);
}
.receive-select-all-btn:disabled {
  opacity: .55;
  color: var(--color-text-tertiary);
}
.draft-line-grid { display:grid; grid-template-columns: minmax(84px, 0.7fr) minmax(0, 1.3fr); gap: var(--space-2); }
.compact-input { min-height: 40px; }
.paid-block { display:grid; gap: var(--space-2); padding-top: var(--space-2); }
.compact-list { display:grid; gap: var(--space-2); }
.compact-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.compact-row--stacked { align-items:flex-start; flex-direction:column; }
.history-amount--in { color: var(--color-success); }
.history-amount--out { color: var(--color-error); }
.history-amount--exchange { color: var(--color-brand-700); }
.procurement-flow-strip { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-border-subtle); overflow:hidden; }
.procurement-flow-item { min-width: 0; display:grid; gap: 4px; padding: var(--space-3); background: var(--color-bg-primary); }
.procurement-flow-item--wide { grid-column: 1 / -1; }
.procurement-flow-item span { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.procurement-flow-item strong { color: var(--color-text-primary); font-size: var(--text-base); line-height: 1.2; }
.procurement-flow-item--wide strong { font-size: var(--text-xl); }
.cost-preview-panel { display:grid; gap: var(--space-3); padding-top: var(--space-2); }
.cost-preview-head { display:grid; gap: 4px; }
.cost-preview-list { display:grid; gap: var(--space-2); }
.cost-preview-scenario { border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); overflow:hidden; transition: border-color 180ms ease, background-color 180ms ease; }
.cost-preview-scenario--open { border-color: var(--color-brand-200); background: var(--color-brand-50); }
.cost-preview-summary { width:100%; display:grid; grid-template-columns: minmax(0, 1fr) auto 16px; align-items:center; gap: var(--space-3); padding: var(--space-3); text-align:left; }
.cost-preview-main { min-width: 0; display:grid; gap: 4px; }
.cost-preview-meta-grid { display:flex; justify-content:flex-end; }
.cost-preview-meta-grid span { min-width: 96px; display:grid; gap: 2px; text-align:right; }
.cost-preview-meta-grid small,
.cost-preview-line-metrics small { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-medium); }
.cost-preview-meta-grid strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.cost-preview-chevron { justify-self: end; }
.cost-preview-detail { padding: 0 var(--space-3) var(--space-3); }
.cost-preview-lines { display:grid; gap: 1px; border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-border-subtle); overflow:hidden; }
.cost-preview-line { display:grid; grid-template-columns: minmax(0, 1fr) minmax(132px, .7fr); gap: var(--space-2); align-items:center; padding: var(--space-3); background: var(--color-bg-primary); }
.cost-preview-line-main { min-width: 0; display:grid; gap: 4px; }
.cost-preview-line-metrics { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); text-align:right; }
.cost-preview-line-metrics span { min-width: 0; display:grid; gap: 2px; }
.cost-preview-line-metrics strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.summary-metric-card { display:grid; gap: 4px; padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.summary-metric-value { color: var(--color-text-primary); font-size: var(--text-lg); font-weight: var(--font-semibold); }
.receive-headline { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.receive-headline > div { display:grid; gap: 2px; }
.receive-headline strong { color: var(--color-text-primary); font-size: var(--text-lg); }
.receive-headline small { color: var(--color-text-secondary); font-size: var(--text-xs); }
.receive-balance-inline { display:grid; gap: var(--space-2); }
.receive-balance-inline-values { display:flex; flex-wrap:wrap; gap: 0; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); overflow: hidden; }
.receive-balance-inline-item { flex: 1 1 160px; min-height: 44px; display:flex; align-items:center; justify-content:space-between; gap: var(--space-2); padding: 0 var(--space-3); border-right: 1px solid var(--color-border-subtle); }
.receive-balance-inline-item:last-child { border-right: 0; }
.receive-currency { color: var(--color-text-secondary); font-size: var(--text-sm); font-weight: var(--font-medium); }
.receive-note-line { display:grid; gap: 2px; }
.receive-note-value { color: var(--color-text-primary); font-size: var(--text-sm); }
.receive-process-block { display:grid; gap: var(--space-2); padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); }
.receive-process-head { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.receive-process-head > div { min-width:0; display:grid; gap: 2px; }
.receive-process-head span { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0; }
.receive-process-head strong { color: var(--color-text-primary); font-size: var(--text-base); }
.receive-process-head button { flex:0 0 auto; min-height:32px; padding:0 var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-elevated); color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.receive-batch-list,
.pending-road-list { display:grid; gap: 6px; }
.receive-batch { border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-elevated); overflow:hidden; }
.receive-batch-head { width:100%; display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); min-height:44px; padding:0 var(--space-3); text-align:left; }
.receive-batch-head span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-primary); font-size: var(--text-sm); }
.receive-batch-head strong { flex:0 0 auto; color: var(--color-text-secondary); font-size: var(--text-sm); }
.receive-batch-lines { display:grid; gap:1px; border-top:1px solid var(--color-border-subtle); background: var(--color-border-subtle); }
.receive-batch-line,
.pending-road-row { min-height:42px; display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:center; gap: var(--space-2); padding:0 var(--space-3); background: var(--color-bg-primary); }
.receive-batch-line--capital { background: var(--color-bg-elevated); }
.receive-batch-line span,
.pending-road-main span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-primary); font-size: var(--text-sm); }
.receive-batch-line strong,
.pending-road-main strong { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-semibold); white-space:nowrap; }
.pending-road-main { min-width:0; display:grid; gap:2px; }
.pending-road-actions { display:flex; align-items:center; gap:6px; }
.pending-road-actions button { min-height:30px; padding:0 var(--space-2); border-radius:var(--radius-md); border:1px solid var(--color-border-subtle); background:var(--color-bg-elevated); color:var(--color-brand-700); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.pending-road-row--draft strong { color: var(--color-warning, var(--color-brand-700)); }
.receive-scope-panel { display:grid; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.receive-scope-head { display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:start; gap: var(--space-2); }
.receive-scope-head > div { display:grid; gap: 3px; min-width: 0; }
.receive-scope-head strong { color: var(--color-text-primary); font-size: var(--text-base); }
.receive-scope-head span { color: var(--color-text-secondary); font-size: var(--text-sm); }
.receive-scope-status {
  display:inline-flex;
  align-items:center;
  justify-self:end;
  min-height: 26px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}
.receive-scope-status b { font: inherit; }
.receive-scope-status i {
  width: 1px;
  height: 12px;
  margin: 0 7px;
  background: var(--color-border-default);
}
.receive-scope-metrics { grid-column: 1 / -1; display:flex; flex-wrap:wrap; gap: 6px; }
.receive-scope-metrics span {
  display:inline-flex;
  align-items:center;
  min-height: 24px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}
.receive-scope-hint { margin:0; color: var(--color-text-secondary); font-size: var(--text-sm); line-height:1.35; }
.receive-capital-inline { display:grid; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-brand-200, var(--color-border-subtle)); background: var(--color-brand-50); }
.receive-capital-inline-head { display:flex; align-items:flex-start; justify-content:space-between; gap: var(--space-3); }
.receive-capital-inline-head span { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform:uppercase; letter-spacing:.02em; }
.receive-capital-inline-head strong { flex:0 0 auto; color: var(--color-text-primary); font-size: var(--text-sm); line-height:1.2; white-space:nowrap; }
.receive-capital-inline-note,
.receive-capital-inline-warning { margin:0; color: var(--color-text-secondary); font-size: var(--text-sm); line-height:1.35; }
.receive-capital-inline-warning { color: var(--color-warning); }
.receive-capital-inline-alert { display:grid; gap: var(--space-2); }
.receive-capital-inline-action,
.receive-capital-retry {
  justify-self: start;
  min-height: 32px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}
.receive-capital-inline-list { display:grid; gap: 6px; }
.receive-capital-inline-list span { display:grid; grid-template-columns:minmax(0, 1fr) auto; align-items:center; gap: var(--space-2); }
.receive-capital-inline-list b { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.receive-capital-inline-list em { color: var(--color-text-secondary); font-size: var(--text-xs); font-style:normal; white-space:nowrap; }
.receive-line-list { display:grid; gap: 6px; }
.receive-line-option { width:100%; display:grid; grid-template-columns: minmax(0, 1fr) auto; align-items:stretch; min-height: 52px; border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); overflow:hidden; transition: border-color 160ms ease, background-color 160ms ease; }
.receive-line-option--active { border-color: var(--color-brand-300); background: var(--color-brand-50); }
.receive-line-select { min-width:0; display:grid; grid-template-columns: 24px minmax(0, 1fr); gap: var(--space-2); align-items:center; padding: var(--space-2); background:transparent; text-align:left; }
.receive-line-check { width: 20px; height: 20px; display:inline-flex; align-items:center; justify-content:center; border-radius: var(--radius-full); border:1px solid var(--color-border-default); color: var(--color-brand-700); background: var(--color-bg-primary); }
.receive-line-option--active .receive-line-check { border-color: var(--color-brand-500); background: var(--color-bg-primary); }
.receive-line-main { min-width: 0; display:grid; gap: 2px; }
.receive-line-main strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-primary); font-size: var(--text-sm); }
.receive-line-main small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-secondary); font-size: var(--text-xs); }
.receive-line-split-action { min-width:84px; padding:0 var(--space-2); border-left:1px solid var(--color-border-subtle); background:var(--color-bg-primary); color:var(--color-brand-700); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.receive-split-btn { min-height:38px; border:1px dashed var(--color-brand-300); border-radius: var(--radius-md); background: var(--color-brand-50); color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.receive-draft-list { display:grid; gap: 6px; }
.receive-draft-row { min-height:42px; display:flex; align-items:center; justify-content:space-between; gap:var(--space-2); padding:0 var(--space-3); border:1px dashed var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-bg-primary); }
.receive-draft-row span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--color-text-primary); font-size:var(--text-sm); }
.receive-draft-row button { flex:0 0 auto; min-height:30px; padding:0 var(--space-2); border-radius:var(--radius-md); border:1px solid var(--color-border-subtle); background:var(--color-bg-elevated); color:var(--color-brand-700); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.receive-scope-warning { display:grid; gap:var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); background: var(--color-warning-bg); color: var(--color-warning); font-size: var(--text-sm); line-height: 1.35; }
.receive-scope-warning button { justify-self:start; min-height:32px; padding:0 var(--space-3); border-radius:var(--radius-md); background:var(--color-bg-elevated); color:var(--color-brand-700); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.receive-scope-success { padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); background: var(--color-success-bg); color: var(--color-success); font-size: var(--text-sm); line-height: 1.35; }
.receive-confirm-summary { display:grid; gap: 6px; padding: var(--space-3); border-radius: var(--radius-lg); background: var(--color-bg-elevated); }
.receive-confirm-summary span { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.receive-confirm-summary strong { color: var(--color-text-primary); font-size: var(--text-xl); line-height: 1.15; }
.receive-confirm-summary p { margin:0; color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.4; }
.split-flow-preview { display:grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items:center; gap: var(--space-2); }
.split-flow-card { display:grid; gap: 2px; padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.split-flow-card span { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.split-flow-card strong { color: var(--color-text-primary); font-size: var(--text-sm); line-height: 1.3; }
.split-flow-card--muted { background: var(--color-bg-primary); }
.split-flow-arrow { color: var(--color-text-tertiary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.receive-confirm-list { display:grid; gap: 1px; border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-border-subtle); overflow:hidden; }
.receive-confirm-row { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: 10px var(--space-3); background: var(--color-bg-primary); }
.receive-confirm-row span { min-width: 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color: var(--color-text-primary); font-size: var(--text-sm); }
.receive-confirm-row strong { flex: 0 0 auto; color: var(--color-text-secondary); font-size: var(--text-sm); }
.receive-capital-box { display:grid; gap: var(--space-2); padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); }
.receive-capital-head { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.receive-capital-head > div { min-width:0; display:grid; gap:2px; }
.receive-capital-head strong { color: var(--color-text-primary); font-size: var(--text-lg); line-height:1.15; }
.receive-capital-actions { display:flex; align-items:center; gap: 8px; flex-wrap:wrap; justify-content:flex-end; }
.receive-capital-head button { flex:0 0 auto; min-height:32px; padding:0 var(--space-3); border:1px solid var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-bg-elevated); color:var(--color-brand-700); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.receive-capital-head button:disabled { opacity: .5; color: var(--color-text-tertiary); }
.receive-capital-approve { border-color: var(--color-brand-400, var(--color-brand-500)); background: var(--color-brand-600, var(--color-brand-500)); color: #fff; }
.receive-capital-approve:disabled { opacity: 1; background: var(--color-bg-elevated); color: var(--color-text-tertiary); border-color: var(--color-border-subtle); }
.receive-capital-approve--done,
.receive-capital-approve--done:disabled { background: var(--color-success-bg); color: var(--color-success); border-color: rgba(16, 185, 129, 0.18); }
.receive-capital-list { display:grid; gap:1px; border:1px solid var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-border-subtle); overflow:hidden; }
.receive-capital-row { min-height:48px; display:grid; grid-template-columns:minmax(0, 1fr) minmax(98px, auto); align-items:center; gap:var(--space-2); padding:8px var(--space-3); background:var(--color-bg-primary); }
.receive-capital-row > div { min-width:0; display:grid; gap:2px; }
.receive-capital-row span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--color-text-primary); font-size:var(--text-sm); font-weight:var(--font-semibold); }
.receive-capital-row small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--color-text-secondary); font-size:var(--text-xs); }
.receive-capital-row strong { justify-self:end; color:var(--color-text-primary); font-size:var(--text-sm); white-space:nowrap; }
.receive-capital-input { width:100%; min-height:36px; padding:0 var(--space-2); border:1px solid var(--color-border-default); border-radius:var(--radius-md); background:var(--color-bg-primary); color:var(--color-text-primary); font-size:var(--text-sm); text-align:right; }
.receive-capital-note { margin:0; padding:8px var(--space-3); border-radius:var(--radius-md); background: var(--color-bg-elevated); color: var(--color-text-secondary); font-size:var(--text-sm); line-height:1.35; }
.receive-capital-note--done { background: var(--color-success-bg); color: var(--color-success); }
.receive-capital-warning { margin:0; padding:8px var(--space-3); border-radius:var(--radius-md); background:var(--color-warning-bg); color:var(--color-warning); font-size:var(--text-sm); line-height:1.35; }
.receive-submit-hint { margin:0; color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.35; }
.allocation-preview { display:grid; gap: var(--space-3); }
.allocation-summary { display:grid; gap: 3px; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); }
.allocation-summary span { color: var(--color-text-secondary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.allocation-table-head,
.allocation-table-row { grid-template-columns: minmax(0, 1fr) auto auto; }
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
.split-quantity-input {
  min-height: 46px;
  padding: 0 var(--space-3);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  font-variant-numeric: tabular-nums;
}
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
  .section-inline-head {
    flex-direction: row;
    align-items: center;
  }
  .record-table-head,
  .money-flow-head { display:none; }
  .money-flow-summary {
    grid-template-columns: minmax(0, 1fr) auto 16px;
    column-gap: var(--space-2);
    align-items: center;
  }
  .money-flow-side {
    min-width: 78px;
    gap: 4px;
  }
  .record-row-toggle {
    grid-template-columns: minmax(0, 1fr) auto 16px;
    align-items: start;
  }
  .money-flow-side {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }
  .record-row-toggle .record-status {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }
  .record-row-toggle .record-amount {
    grid-column: 2;
    grid-row: 2;
    align-self: start;
    margin-top: 2px;
  }
  .record-row--settled {
    grid-template-columns: minmax(0, 1fr) auto;
    row-gap: 6px;
    column-gap: var(--space-3);
    align-items: start;
  }
  .record-row--settled .record-main {
    grid-column: 1;
    grid-row: 1 / span 2;
  }
  .record-row--settled .record-status {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }
  .record-row--settled .record-amount {
    grid-column: 2;
    grid-row: 2;
    align-self: start;
    justify-self: end;
    margin-top: 2px;
  }
  .money-flow-chevron,
  .record-chevron {
    grid-column: 3;
    grid-row: 1 / span 2;
    align-self: center;
  }
  .money-flow-detail { padding-left: var(--space-3); }
  .cost-preview-summary {
    grid-template-columns: minmax(0, 1fr) auto 16px;
    align-items: center;
    column-gap: var(--space-2);
  }
  .cost-preview-meta-grid {
    grid-column: 2;
    grid-row: 1;
    align-self: center;
  }
  .cost-preview-meta-grid span {
    min-width: 72px;
    gap: 3px;
  }
  .cost-preview-chevron {
    grid-column: 3;
    grid-row: 1;
    align-self: center;
  }
  .cost-preview-line {
    grid-template-columns: 1fr;
    align-items: start;
  }
  .cost-preview-line-metrics { text-align: left; }
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
  .receive-headline { align-items:flex-start; flex-direction:column; }
  .receive-scope-head { grid-template-columns:minmax(0, 1fr) auto; align-items:start; }
  .receive-scope-status { justify-self:end; }
  .pending-road-row { grid-template-columns:1fr; align-items:start; padding:var(--space-2) var(--space-3); }
  .pending-road-actions { justify-content:flex-start; flex-wrap:wrap; }
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
