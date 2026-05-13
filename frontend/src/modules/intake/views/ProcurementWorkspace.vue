<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  PackagePlus,
  Plus,
  RefreshCcw,
  WalletCards,
} from 'lucide-vue-next'
import { fetchVariantsPaginated } from '@/api/catalog'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import { fetchLocations } from '@/api/inventory'
import { fetchPartners, type Partner } from '@/api/core'
import {
  createProcurementWorkspace,
  fetchInvestmentAgreements,
  fetchProcurementWorkspace,
  runProcurementWorkspaceAction,
  type InvestmentAgreementListItem,
  type ProcurementWorkspacePayload,
  type WorkspaceActionKey,
  type WorkspaceFundingSource,
  type WorkspaceSettlementType,
} from '@/api/partnerships'
import { fetchSuppliers } from '@/api/suppliers'
import type { Location, ProductVariant, Supplier } from '@/types/models'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

type SelectValue = number | ''

const route = useRoute()
const router = useRouter()
const toast = useToast()

const workspace = ref<ProcurementWorkspacePayload | null>(null)
const suppliers = ref<Supplier[]>([])
const variants = ref<ProductVariant[]>([])
const locations = ref<Location[]>([])
const cashAccounts = ref<CashAccountRecord[]>([])
const agreements = ref<InvestmentAgreementListItem[]>([])
const partners = ref<Partner[]>([])
const isLoading = ref(false)
const isMutating = ref(false)
const error = ref<string | null>(null)
let controller: AbortController | null = null

const createForm = ref({
  funding_source: 'OWN_FUNDS' as WorkspaceFundingSource,
  supplier_id: '' as SelectValue,
  investment_agreement_id: '' as SelectValue,
  notes: '',
})

const sourceForm = ref({
  funding_source: 'OWN_FUNDS' as WorkspaceFundingSource,
  supplier_id: '' as SelectValue,
  investment_agreement_id: '' as SelectValue,
  notes: '',
})

const itemForm = ref({
  product_variant_id: '' as SelectValue,
  quantity: '1',
  unit_purchase_price: '',
  currency: 'UZS',
  fx_rate: '1',
})

const expenseForm = ref({
  expense_type: 'LOGISTICS',
  amount: '',
  currency: 'UZS',
  fx_rate: '1',
  allocation_method: 'BY_VALUE',
  notes: '',
})

const settlementForm = ref({
  type: 'PREPAID' as WorkspaceSettlementType,
  currency_of_obligation: 'UZS',
  fx_rate_at_obligation: '1',
  total_amount_due: '',
  deadline_date: '',
  notes: '',
})

const scheduleForm = ref({
  installments_count: '3',
  first_due_date: '',
  interval: 'MONTHLY',
})

const receiveForm = ref({
  warehouse_id: '' as SelectValue,
})

const costPaymentForm = ref({
  cash_account_id: '' as SelectValue,
  amount: '',
  currency: 'UZS',
})

const payablePaymentForm = ref({
  payable_id: '' as SelectValue,
  cash_account_id: '' as SelectValue,
  amount: '',
  currency: 'UZS',
})

const capitalForm = ref({
  partner_id: '' as SelectValue,
  cash_account_id: '' as SelectValue,
  amount: '',
  currency: 'UZS',
  fx_rate: '1',
  notes: '',
})

const allocationForm = ref({
  partner_id: '' as SelectValue,
  amount: '',
  currency: 'UZS',
  fx_rate: '1',
})

const agreementForm = ref({
  planned_budget: '',
  currency: 'UZS',
  mudaraba_ratio: '0',
  notes: '',
  first_partner_id: '' as SelectValue,
  first_partner_role: 'INVESTOR',
  first_partner_capital: '',
  first_partner_profit: '0.5',
  second_partner_id: '' as SelectValue,
  second_partner_role: 'OPERATOR',
  second_partner_capital: '',
  second_partner_profit: '0.5',
})

const workspaceId = computed(() => Number(route.params.id || 0))
const isCreateMode = computed(() => !workspaceId.value)
const documents = computed(() => workspace.value?.documents ?? null)
const policy = computed(() => workspace.value?.policy ?? null)
const summaries = computed(() => workspace.value?.summaries ?? null)
const allowedActions = computed(() => new Set(policy.value?.allowed_actions ?? []))
const visibleSections = computed(() => new Set(workspace.value?.sections.filter((section) => section.visible).map((section) => section.key) ?? []))
const primaryCurrency = computed(() => workspace.value?.display.primary_currency ?? 'UZS')
const selectedCostAccount = computed(() => cashAccounts.value.find((account) => account.id === costPaymentForm.value.cash_account_id))
const selectedPayableAccount = computed(() => cashAccounts.value.find((account) => account.id === payablePaymentForm.value.cash_account_id))
const selectedCapitalAccount = computed(() => cashAccounts.value.find((account) => account.id === capitalForm.value.cash_account_id))

const canAddItem = computed(() => Boolean(itemForm.value.product_variant_id && itemForm.value.quantity && itemForm.value.unit_purchase_price))
const canSaveSettlement = computed(() => Boolean(settlementForm.value.type && settlementForm.value.total_amount_due))
const canReceive = computed(() => Boolean(receiveForm.value.warehouse_id && hasAction('RECEIVE_BATCH')))
const canPayCosts = computed(() => Boolean(costPaymentForm.value.cash_account_id && hasAction('PAY_COSTS')))
const canPayPayable = computed(() => Boolean(payablePaymentForm.value.payable_id && payablePaymentForm.value.cash_account_id && payablePaymentForm.value.amount && hasAction('PAY_SUPPLIER_PAYABLE')))
const canRecordContribution = computed(() => Boolean(capitalForm.value.partner_id && capitalForm.value.cash_account_id && capitalForm.value.amount && hasAction('RECORD_CAPITAL_CONTRIBUTION')))
const canAllocateCapital = computed(() => Boolean(allocationForm.value.partner_id && allocationForm.value.amount && hasAction('ALLOCATE_CAPITAL')))
const canCreateAgreement = computed(() => Boolean(
  sourceForm.value.funding_source === 'PARTNERSHIP'
  && agreementForm.value.planned_budget
  && agreementForm.value.first_partner_id
  && agreementForm.value.first_partner_capital,
))
const shouldShowPayments = computed(() => Boolean(
  hasAction('PAY_COSTS')
  || hasAction('PAY_SUPPLIER_PAYABLE')
  || documents.value?.payables.length
  || documents.value?.payments.length,
))

function hasAction(action: WorkspaceActionKey): boolean {
  return allowedActions.value.has(action)
}

function optionNumber(value: SelectValue): number | null {
  return value === '' ? null : Number(value)
}

function money(value: string | number | null | undefined, currency = 'UZS'): string {
  return formatPrice(value ?? '0', currency)
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' })
}

function variantLabel(variant: ProductVariant): string {
  const sku = variant.display_sku || variant.sku
  return [variant.product_name, sku].filter(Boolean).join(' · ')
}

function extractError(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { data?: { detail?: unknown; message?: unknown } } }).response
    const detail = response?.data?.detail ?? response?.data?.message
    if (typeof detail === 'string') return detail
  }
  return err instanceof Error ? err.message : 'Операция не выполнена'
}

function syncForms(payload: ProcurementWorkspacePayload): void {
  const source = payload.documents.source
  sourceForm.value = {
    funding_source: (source.funding_source || 'OWN_FUNDS') as WorkspaceFundingSource,
    supplier_id: source.supplier_id ?? '',
    investment_agreement_id: source.investment_agreement_id ?? '',
    notes: payload.documents.procurement.notes ?? '',
  }
  if (payload.documents.settlement) {
    const settlement = payload.documents.settlement
    settlementForm.value = {
      type: settlement.type as WorkspaceSettlementType,
      currency_of_obligation: settlement.currency_of_obligation,
      fx_rate_at_obligation: settlement.fx_rate_at_obligation,
      total_amount_due: settlement.total_amount_due,
      deadline_date: settlement.deadline_date ?? '',
      notes: settlement.notes ?? '',
    }
  } else if (payload.summaries.items_total_uzs !== '0.00') {
    settlementForm.value.total_amount_due = payload.summaries.items_total_uzs
  }
  if (payload.documents.payables.length > 0) {
    const payable = payload.documents.payables[0]
    payablePaymentForm.value.payable_id = payable.id
    payablePaymentForm.value.amount = payable.remaining_amount
    payablePaymentForm.value.currency = payable.currency
  }
  if (payload.documents.investment?.partners.length) {
    const partner = payload.documents.investment.partners[0]
    capitalForm.value.partner_id = partner.partner_id
    capitalForm.value.currency = payload.documents.investment.currency
    allocationForm.value.partner_id = partner.partner_id
    allocationForm.value.currency = payload.documents.investment.currency
  }
}

async function loadOptions(signal?: AbortSignal): Promise<void> {
  const [supplierPage, variantPage, warehouses, accounts, agreementRows, partnerRows] = await Promise.all([
    fetchSuppliers({ active: true }, signal),
    fetchVariantsPaginated({ active: true, page_size: 100 }, signal),
    fetchLocations(),
    fetchCashAccounts(signal),
    fetchInvestmentAgreements(),
    fetchPartners({ is_active: true }, signal),
  ])
  suppliers.value = supplierPage.results
  variants.value = variantPage.results
  locations.value = warehouses
  cashAccounts.value = accounts
  agreements.value = agreementRows
  partners.value = partnerRows
}

async function loadWorkspace(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  isLoading.value = true
  error.value = null
  try {
    await loadOptions(controller.signal)
    if (!isCreateMode.value) {
      const payload = await fetchProcurementWorkspace(workspaceId.value, controller.signal)
      workspace.value = payload
      syncForms(payload)
    } else {
      workspace.value = null
    }
  } catch (err) {
    if (controller.signal.aborted) return
    error.value = extractError(err)
    toast.error(error.value)
  } finally {
    if (!controller.signal.aborted) {
      isLoading.value = false
    }
  }
}

async function createWorkspace(): Promise<void> {
  isMutating.value = true
  try {
    const payload = await createProcurementWorkspace({
      funding_source: createForm.value.funding_source,
      supplier_id: optionNumber(createForm.value.supplier_id),
      investment_agreement_id: optionNumber(createForm.value.investment_agreement_id),
      notes: createForm.value.notes,
      client_request_id: crypto.randomUUID(),
    })
    toast.success('Черновик прихода открыт')
    await router.replace({ name: 'procurement-detail', params: { id: payload.id } })
  } catch (err) {
    toast.error(extractError(err))
  } finally {
    isMutating.value = false
  }
}

async function ensureWorkspace(): Promise<ProcurementWorkspacePayload | null> {
  if (workspace.value) return workspace.value
  const payload = await createProcurementWorkspace({
    funding_source: 'OWN_FUNDS',
    notes: 'Draft opened from procurement workspace',
    client_request_id: crypto.randomUUID(),
  })
  workspace.value = payload
  syncForms(payload)
  await router.replace({ name: 'procurement-detail', params: { id: payload.id } })
  return payload
}

async function mutate<TPayload extends Record<string, unknown>>(
  action: WorkspaceActionKey,
  payload: TPayload,
  successMessage: string,
): Promise<void> {
  const activeWorkspace = await ensureWorkspace()
  if (!activeWorkspace) return
  isMutating.value = true
  try {
    const next = await runProcurementWorkspaceAction(activeWorkspace.id, action, payload)
    workspace.value = next
    syncForms(next)
    toast.success(successMessage)
  } catch (err) {
    toast.error(extractError(err))
  } finally {
    isMutating.value = false
  }
}

function saveSource(): Promise<void> {
  return mutate('UPDATE_SOURCE', {
    funding_source: sourceForm.value.funding_source,
    supplier_id: optionNumber(sourceForm.value.supplier_id),
    investment_agreement_id: optionNumber(sourceForm.value.investment_agreement_id),
    notes: sourceForm.value.notes,
  }, 'Источник обновлён')
}

async function addItem(): Promise<void> {
  if (!canAddItem.value) return
  await mutate('UPDATE_ITEMS', {
    items: [{
      product_variant_id: optionNumber(itemForm.value.product_variant_id),
      quantity: itemForm.value.quantity,
      unit_purchase_price: itemForm.value.unit_purchase_price,
      currency: itemForm.value.currency,
      fx_rate: itemForm.value.fx_rate,
    }],
  }, 'Товар добавлен')
  itemForm.value.product_variant_id = ''
  itemForm.value.quantity = '1'
  itemForm.value.unit_purchase_price = ''
}

async function addExpense(): Promise<void> {
  if (!expenseForm.value.amount) return
  await mutate('UPDATE_EXPENSES', {
    expenses: [{
      expense_type: expenseForm.value.expense_type,
      amount: expenseForm.value.amount,
      currency: expenseForm.value.currency,
      fx_rate: expenseForm.value.fx_rate,
      allocation_method: expenseForm.value.allocation_method,
      notes: expenseForm.value.notes,
    }],
  }, 'Расход добавлен')
  expenseForm.value.amount = ''
  expenseForm.value.notes = ''
}

function saveSettlement(): Promise<void> {
  return mutate('UPDATE_SETTLEMENT', {
    settlement: {
      type: settlementForm.value.type,
      currency_of_obligation: settlementForm.value.currency_of_obligation,
      fx_rate_at_obligation: settlementForm.value.fx_rate_at_obligation,
      total_amount_due: settlementForm.value.total_amount_due,
      deadline_date: settlementForm.value.deadline_date || null,
      notes: settlementForm.value.notes,
    },
  }, 'Условия расчёта сохранены')
}

function generateSchedule(): Promise<void> {
  return mutate('GENERATE_INSTALLMENT_SCHEDULE', {
    installments_count: Number(scheduleForm.value.installments_count),
    first_due_date: scheduleForm.value.first_due_date || null,
    interval: scheduleForm.value.interval,
  }, 'График рассрочки построен')
}

function payCosts(): Promise<void> {
  const account = selectedCostAccount.value
  return mutate('PAY_COSTS', {
    cash_account_id: optionNumber(costPaymentForm.value.cash_account_id),
    ...(costPaymentForm.value.amount ? { amount: costPaymentForm.value.amount } : {}),
    currency: costPaymentForm.value.currency || account?.currency || 'UZS',
  }, 'Оплата расходов прихода зафиксирована')
}

function payPayable(): Promise<void> {
  const account = selectedPayableAccount.value
  return mutate('PAY_SUPPLIER_PAYABLE', {
    payable_id: optionNumber(payablePaymentForm.value.payable_id),
    cash_account_id: optionNumber(payablePaymentForm.value.cash_account_id),
    amount: payablePaymentForm.value.amount,
    currency: payablePaymentForm.value.currency || account?.currency || 'UZS',
  }, 'Оплата поставщику зафиксирована')
}

function recordContribution(): Promise<void> {
  const account = selectedCapitalAccount.value
  return mutate('RECORD_CAPITAL_CONTRIBUTION', {
    partner_id: optionNumber(capitalForm.value.partner_id),
    cash_account_id: optionNumber(capitalForm.value.cash_account_id),
    amount: capitalForm.value.amount,
    currency: capitalForm.value.currency || account?.currency || 'UZS',
    fx_rate: capitalForm.value.fx_rate,
    notes: capitalForm.value.notes,
  }, 'Взнос инвестора зафиксирован')
}

function createAgreement(): Promise<void> {
  const partnerRows = [
    {
      partner_id: optionNumber(agreementForm.value.first_partner_id),
      role: agreementForm.value.first_partner_role,
      planned_capital_share: agreementForm.value.first_partner_capital,
      profit_share: agreementForm.value.first_partner_profit,
    },
  ]
  if (agreementForm.value.second_partner_id && agreementForm.value.second_partner_capital) {
    partnerRows.push({
      partner_id: optionNumber(agreementForm.value.second_partner_id),
      role: agreementForm.value.second_partner_role,
      planned_capital_share: agreementForm.value.second_partner_capital,
      profit_share: agreementForm.value.second_partner_profit,
    })
  }
  return mutate('CREATE_INVESTMENT_AGREEMENT', {
    supplier_id: optionNumber(sourceForm.value.supplier_id),
    mudaraba_ratio: agreementForm.value.mudaraba_ratio,
    planned_budget: agreementForm.value.planned_budget,
    currency: agreementForm.value.currency,
    notes: agreementForm.value.notes,
    partners: partnerRows,
  }, 'Инвест-договор создан и привязан')
}

function allocateCapital(): Promise<void> {
  return mutate('ALLOCATE_CAPITAL', {
    allocations: [{
      partner_id: optionNumber(allocationForm.value.partner_id),
      amount: allocationForm.value.amount,
      currency: allocationForm.value.currency,
      fx_rate: allocationForm.value.fx_rate,
    }],
  }, 'Капитал выделен на приход')
}

function receiveBatch(): Promise<void> {
  return mutate('RECEIVE_BATCH', {
    warehouse_id: optionNumber(receiveForm.value.warehouse_id),
  }, 'Партия оприходована')
}

watch(selectedCostAccount, (account) => {
  if (account) costPaymentForm.value.currency = account.currency
})

watch(selectedPayableAccount, (account) => {
  if (account) payablePaymentForm.value.currency = account.currency
})

watch(selectedCapitalAccount, (account) => {
  if (account) capitalForm.value.currency = account.currency
})

watch(() => route.params.id, () => {
  loadWorkspace()
})

onMounted(loadWorkspace)

onBeforeUnmount(() => {
  controller?.abort()
})
</script>

<template>
  <main class="workspace-page">
    <section class="workspace-top">
      <button class="ghost-button" type="button" @click="router.push({ name: 'procurement-list' })">
        <ArrowLeft :size="17" />
        Приходы
      </button>
      <button class="ghost-button" type="button" :disabled="isLoading" @click="loadWorkspace">
        <RefreshCcw :size="16" />
        Обновить
      </button>
    </section>

    <section v-if="isCreateMode" class="create-shell">
      <div class="poster">
        <span class="eyebrow">Новый приход</span>
        <h1>Сначала что завозим. Деньги и условия — следующим шагом.</h1>
        <p>Приход начинается с товаров и расходов. После первой строки система откроет workspace и поведёт дальше: поставщик, условия, источник денег, оплата и приёмка.</p>
      </div>

      <form class="create-form" @submit.prevent="addItem">
        <label>
          Товар
          <select v-model="itemForm.product_variant_id">
            <option value="">Выберите вариант</option>
            <option v-for="variant in variants" :key="variant.id" :value="variant.id">
              {{ variantLabel(variant) }}
            </option>
          </select>
        </label>
        <div class="form-grid compact">
          <label>
            Количество
            <input v-model="itemForm.quantity" inputmode="decimal" />
          </label>
          <label>
            Цена
            <input v-model="itemForm.unit_purchase_price" inputmode="decimal" />
          </label>
          <label>
            Валюта
            <select v-model="itemForm.currency">
              <option value="UZS">UZS</option>
              <option value="USD">USD</option>
            </select>
          </label>
        </div>
        <button class="primary-button" type="submit" :disabled="isMutating || !canAddItem">
          <PackagePlus :size="18" />
          Открыть workspace и добавить товар
        </button>
        <button class="ghost-button strong" type="button" :disabled="isMutating" @click="createWorkspace">
          Открыть пустой workspace
        </button>
      </form>
    </section>

    <section v-else-if="isLoading" class="state-panel">
      Загружаем workspace прихода…
    </section>

    <section v-else-if="error" class="state-panel state-panel--error">
      {{ error }}
    </section>

    <template v-else-if="workspace && documents">
      <section class="workspace-hero">
        <div>
          <span class="eyebrow">{{ documents.source.funding_source === 'PARTNERSHIP' ? 'Партнёрский приход' : 'Собственные деньги' }}</span>
          <h1>{{ workspace.display.title }}</h1>
          <p>{{ workspace.display.subtitle || 'Поставщик пока не выбран' }}</p>
        </div>
        <div class="hero-facts">
          <div>
            <span>Статус</span>
            <strong>{{ workspace.status }}</strong>
          </div>
          <div>
            <span>Товары</span>
            <strong>{{ money(summaries?.items_total_uzs, 'UZS') }}</strong>
          </div>
          <div>
            <span>Расходы</span>
            <strong>{{ money(summaries?.expenses_total_uzs, 'UZS') }}</strong>
          </div>
        </div>
      </section>

      <section v-if="policy?.blocked_reasons.length" class="policy-strip">
        <CircleAlert :size="18" />
        <div>
          <strong>Что блокирует следующий шаг</strong>
          <p>{{ policy.blocked_reasons[0].message }}</p>
        </div>
      </section>

      <section class="workspace-grid">
        <article v-if="visibleSections.has('source')" class="panel panel--wide flow-source">
          <header>
            <span class="panel-number">03</span>
            <div>
              <h2>Источник денег</h2>
              <p>Здесь выбирается только чьими деньгами финансируем приход. Поставщик и его условия живут отдельно.</p>
            </div>
          </header>
          <div class="form-grid">
            <label>
              Финансирование
              <select v-model="sourceForm.funding_source">
                <option value="OWN_FUNDS">Собственные деньги</option>
                <option value="PARTNERSHIP">Партнёрское финансирование</option>
              </select>
            </label>
            <label v-if="sourceForm.funding_source === 'PARTNERSHIP'">
              Инвест-договор
              <select v-model="sourceForm.investment_agreement_id">
                <option value="">Не привязан</option>
                <option v-for="agreement in agreements" :key="agreement.id" :value="agreement.id">
                  #{{ agreement.id }} · {{ agreement.currency }}
                </option>
              </select>
            </label>
            <label>
              Заметка
              <textarea v-model="sourceForm.notes" rows="2" />
            </label>
          </div>
          <button class="secondary-button" type="button" :disabled="isMutating || !hasAction('UPDATE_SOURCE')" @click="saveSource">
            Сохранить источник
          </button>
        </article>

        <article v-if="visibleSections.has('items')" class="panel panel--wide flow-items">
          <header>
            <span class="panel-number">01</span>
            <div>
              <h2>Товары и расходы</h2>
              <p>Черновые строки можно менять до появления финансовых или складских фактов.</p>
            </div>
          </header>

          <div class="line-list">
            <div v-for="item in documents.items" :key="item.id" class="line-row">
              <div>
                <strong>{{ item.product_variant_name }}</strong>
                <span>{{ item.quantity }} шт · {{ money(item.unit_purchase_price, item.currency) }} · {{ item.lifecycle_state }}</span>
              </div>
              <span>{{ item.payment_state }}</span>
            </div>
            <div v-if="documents.items.length === 0" class="empty-line">Товары ещё не добавлены.</div>
          </div>

          <div class="form-grid">
            <label class="span-2">
              Товар
              <select v-model="itemForm.product_variant_id">
                <option value="">Выберите вариант</option>
                <option v-for="variant in variants" :key="variant.id" :value="variant.id">
                  {{ variantLabel(variant) }}
                </option>
              </select>
            </label>
            <label>
              Количество
              <input v-model="itemForm.quantity" inputmode="decimal" />
            </label>
            <label>
              Цена
              <input v-model="itemForm.unit_purchase_price" inputmode="decimal" />
            </label>
            <label>
              Валюта
              <select v-model="itemForm.currency">
                <option value="UZS">UZS</option>
                <option value="USD">USD</option>
              </select>
            </label>
            <label>
              Курс
              <input v-model="itemForm.fx_rate" inputmode="decimal" />
            </label>
          </div>
          <button class="secondary-button" type="button" :disabled="isMutating || !canAddItem || !hasAction('UPDATE_ITEMS')" @click="addItem">
            <Plus :size="16" />
            Добавить товар
          </button>

          <div class="divider" />

          <div class="line-list">
            <div v-for="expense in documents.expenses" :key="expense.id" class="line-row">
              <div>
                <strong>{{ expense.expense_type }}</strong>
                <span>{{ money(expense.amount, expense.currency) }} · {{ expense.allocation_method }} · {{ expense.lifecycle_state }}</span>
              </div>
              <span>{{ expense.payment_state }}</span>
            </div>
          </div>
          <div class="form-grid">
            <label>
              Тип расхода
              <select v-model="expenseForm.expense_type">
                <option value="LOGISTICS">Логистика</option>
                <option value="CUSTOMS">Таможня</option>
                <option value="FEE">Комиссия</option>
                <option value="OTHER">Другое</option>
              </select>
            </label>
            <label>
              Сумма
              <input v-model="expenseForm.amount" inputmode="decimal" />
            </label>
            <label>
              Валюта
              <select v-model="expenseForm.currency">
                <option value="UZS">UZS</option>
                <option value="USD">USD</option>
              </select>
            </label>
            <label>
              Курс
              <input v-model="expenseForm.fx_rate" inputmode="decimal" />
            </label>
            <label>
              Распределение
              <select v-model="expenseForm.allocation_method">
                <option value="BY_VALUE">По стоимости</option>
                <option value="BY_QUANTITY">По количеству</option>
              </select>
            </label>
            <label>
              Заметка
              <input v-model="expenseForm.notes" />
            </label>
          </div>
          <button class="secondary-button" type="button" :disabled="isMutating || !expenseForm.amount || !hasAction('UPDATE_EXPENSES')" @click="addExpense">
            <Plus :size="16" />
            Добавить расход
          </button>
        </article>

        <article v-if="visibleSections.has('settlement')" class="panel flow-settlement">
          <header>
            <span class="panel-number">02</span>
            <div>
              <h2>Поставщик и условия</h2>
              <p>Тип оплаты определяет, создаём оплату сейчас или кредиторку после приёмки.</p>
            </div>
          </header>
          <div class="form-stack">
            <label>
              Поставщик
              <select v-model="sourceForm.supplier_id">
                <option value="">Без поставщика</option>
                <option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">
                  {{ supplier.name }}
                </option>
              </select>
            </label>
            <label>
              Тип расчёта
              <select v-model="settlementForm.type">
                <option v-for="type in policy?.allowed_settlements ?? []" :key="type" :value="type">
                  {{ type }}
                </option>
              </select>
            </label>
            <label>
              Сумма обязательства
              <input v-model="settlementForm.total_amount_due" inputmode="decimal" />
            </label>
            <label>
              Валюта
              <select v-model="settlementForm.currency_of_obligation">
                <option value="UZS">UZS</option>
                <option value="USD">USD</option>
              </select>
            </label>
            <label>
              Курс
              <input v-model="settlementForm.fx_rate_at_obligation" inputmode="decimal" />
            </label>
            <label>
              Дедлайн
              <input v-model="settlementForm.deadline_date" type="date" />
            </label>
          </div>
          <button class="ghost-button strong" type="button" :disabled="isMutating || !hasAction('UPDATE_SOURCE')" @click="saveSource">
            Сохранить поставщика
          </button>
          <button class="secondary-button" type="button" :disabled="isMutating || !canSaveSettlement || !hasAction('UPDATE_SETTLEMENT')" @click="saveSettlement">
            Сохранить условия
          </button>

          <div v-if="documents.settlement?.type === 'INSTALLMENT'" class="schedule-box">
            <strong>График рассрочки</strong>
            <div v-for="row in documents.settlement.schedule" :key="row.id" class="mini-row">
              <span>{{ row.sequence_number }} · {{ dateLabel(row.due_date) }}</span>
              <b>{{ money(row.amount, row.currency) }}</b>
            </div>
            <div class="form-grid compact">
              <label>
                Кол-во
                <input v-model="scheduleForm.installments_count" inputmode="numeric" />
              </label>
              <label>
                Первая дата
                <input v-model="scheduleForm.first_due_date" type="date" />
              </label>
              <label>
                Интервал
                <select v-model="scheduleForm.interval">
                  <option value="MONTHLY">Месяц</option>
                  <option value="WEEKLY">Неделя</option>
                </select>
              </label>
            </div>
            <button class="ghost-button strong" type="button" :disabled="isMutating || !hasAction('GENERATE_INSTALLMENT_SCHEDULE')" @click="generateSchedule">
              Построить график
            </button>
          </div>
        </article>

        <article v-if="visibleSections.has('capital')" class="panel flow-capital">
          <header>
            <span class="panel-number">04</span>
            <div>
              <h2>Капитал партнёров</h2>
              <p>Деньги инвестора фиксируются как отдельный финансовый факт.</p>
            </div>
          </header>
          <template v-if="documents.investment">
            <div class="line-list">
              <div v-for="partner in documents.investment.partners" :key="partner.partner_id" class="line-row">
                <div>
                  <strong>{{ partner.partner_name }}</strong>
                  <span>Капитал {{ partner.planned_capital_share }} · прибыль {{ partner.profit_share }}</span>
                </div>
              </div>
            </div>
            <div class="form-stack">
              <label>
                Партнёр
                <select v-model="capitalForm.partner_id">
                  <option value="">Выберите партнёра</option>
                  <option v-for="partner in documents.investment.partners" :key="partner.partner_id" :value="partner.partner_id">
                    {{ partner.partner_name }}
                  </option>
                </select>
              </label>
              <label>
                Денежный счёт
                <select v-model="capitalForm.cash_account_id">
                  <option value="">Выберите счёт</option>
                  <option v-for="account in cashAccounts" :key="account.id" :value="account.id">
                    {{ account.name }} · {{ account.currency }} · {{ money(account.balance, account.currency) }}
                  </option>
                </select>
              </label>
              <label>
                Сумма взноса
                <input v-model="capitalForm.amount" inputmode="decimal" />
              </label>
              <label>
                Валюта
                <select v-model="capitalForm.currency">
                  <option value="UZS">UZS</option>
                  <option value="USD">USD</option>
                </select>
              </label>
            </div>
            <button class="secondary-button" type="button" :disabled="isMutating || !canRecordContribution" @click="recordContribution">
              <WalletCards :size="16" />
              Зафиксировать взнос
            </button>

            <div class="divider" />

            <div class="form-grid compact">
              <label>
                Партнёр
                <select v-model="allocationForm.partner_id">
                  <option value="">Выберите партнёра</option>
                  <option v-for="partner in documents.investment.partners" :key="partner.partner_id" :value="partner.partner_id">
                    {{ partner.partner_name }}
                  </option>
                </select>
              </label>
              <label>
                Сумма в приход
                <input v-model="allocationForm.amount" inputmode="decimal" />
              </label>
            </div>
            <button class="ghost-button strong" type="button" :disabled="isMutating || !canAllocateCapital" @click="allocateCapital">
              Выделить капитал на приход
            </button>
          </template>
          <div v-else class="agreement-builder">
            <div class="empty-line">Для партнёрского прихода нужно привязать или создать инвест-договор.</div>
            <div class="form-grid compact">
              <label>
                Бюджет
                <input v-model="agreementForm.planned_budget" inputmode="decimal" />
              </label>
              <label>
                Валюта
                <select v-model="agreementForm.currency">
                  <option value="UZS">UZS</option>
                  <option value="USD">USD</option>
                </select>
              </label>
              <label>
                Mudaraba ratio
                <input v-model="agreementForm.mudaraba_ratio" inputmode="decimal" />
              </label>
            </div>
            <div class="form-grid compact">
              <label>
                Партнёр 1
                <select v-model="agreementForm.first_partner_id">
                  <option value="">Выберите партнёра</option>
                  <option v-for="partner in partners" :key="partner.id" :value="partner.id">
                    {{ partner.display_name }} · {{ partner.role }}
                  </option>
                </select>
              </label>
              <label>
                Роль
                <select v-model="agreementForm.first_partner_role">
                  <option value="INVESTOR">Инвестор</option>
                  <option value="OPERATOR">Оператор</option>
                </select>
              </label>
              <label>
                Капитал
                <input v-model="agreementForm.first_partner_capital" inputmode="decimal" />
              </label>
            </div>
            <div class="form-grid compact">
              <label>
                Партнёр 2
                <select v-model="agreementForm.second_partner_id">
                  <option value="">Не добавлять</option>
                  <option v-for="partner in partners" :key="partner.id" :value="partner.id">
                    {{ partner.display_name }} · {{ partner.role }}
                  </option>
                </select>
              </label>
              <label>
                Роль
                <select v-model="agreementForm.second_partner_role">
                  <option value="INVESTOR">Инвестор</option>
                  <option value="OPERATOR">Оператор</option>
                </select>
              </label>
              <label>
                Капитал
                <input v-model="agreementForm.second_partner_capital" inputmode="decimal" />
              </label>
            </div>
            <button class="secondary-button" type="button" :disabled="isMutating || !canCreateAgreement || !hasAction('CREATE_INVESTMENT_AGREEMENT')" @click="createAgreement">
              Создать и привязать договор
            </button>
          </div>
        </article>

        <article v-if="visibleSections.has('receive')" class="panel flow-receive">
          <header>
            <span class="panel-number">05</span>
            <div>
              <h2>Приёмка</h2>
              <p>Приёмка создаёт складской факт, lot snapshot и дальше строки становятся неизменяемыми.</p>
            </div>
          </header>
          <div class="form-stack">
            <label>
              Склад
              <select v-model="receiveForm.warehouse_id">
                <option value="">Выберите склад</option>
                <option v-for="location in locations" :key="location.id" :value="location.id">
                  {{ location.name }}
                </option>
              </select>
            </label>
          </div>
          <button class="primary-button" type="button" :disabled="isMutating || !canReceive" @click="receiveBatch">
            <CheckCircle2 :size="18" />
            Оприходовать
          </button>

          <div class="line-list">
            <div v-for="batch in documents.receive_batches" :key="batch.id" class="line-row">
              <div>
                <strong>Партия #{{ batch.id }}</strong>
                <span>{{ batch.warehouse_name }} · {{ dateLabel(batch.received_at) }}</span>
              </div>
              <b>{{ money(batch.inventory_total_uzs, 'UZS') }}</b>
            </div>
          </div>
        </article>

        <article v-if="shouldShowPayments" class="panel flow-payments">
          <header>
            <span class="panel-number">06</span>
            <div>
              <h2>Оплаты</h2>
              <p>Оплата товаров и кредиторки проходит через `Payment`, cash и journal.</p>
            </div>
          </header>
          <div class="form-stack">
            <label>
              Счёт оплаты прихода
              <select v-model="costPaymentForm.cash_account_id">
                <option value="">Выберите счёт</option>
                <option v-for="account in cashAccounts" :key="account.id" :value="account.id">
                  {{ account.name }} · {{ account.currency }} · {{ money(account.balance, account.currency) }}
                </option>
              </select>
            </label>
            <label>
              Сумма
              <input v-model="costPaymentForm.amount" inputmode="decimal" placeholder="Можно оставить пустым для UZS" />
            </label>
          </div>
          <button class="secondary-button" type="button" :disabled="isMutating || !canPayCosts" @click="payCosts">
            Оплатить черновые строки
          </button>

          <div v-if="documents.payables.length" class="divider" />
          <template v-if="documents.payables.length">
            <div class="line-list">
              <div v-for="payable in documents.payables" :key="payable.id" class="line-row">
                <div>
                  <strong>Кредиторка #{{ payable.id }}</strong>
                  <span>{{ payable.supplier_name }} · {{ payable.status }} · до {{ dateLabel(payable.due_date) }}</span>
                </div>
                <b>{{ money(payable.remaining_amount, payable.currency) }}</b>
              </div>
            </div>
            <div class="form-grid compact">
              <label>
                Кредиторка
                <select v-model="payablePaymentForm.payable_id">
                  <option v-for="payable in documents.payables" :key="payable.id" :value="payable.id">
                    #{{ payable.id }} · {{ money(payable.remaining_amount, payable.currency) }}
                  </option>
                </select>
              </label>
              <label>
                Счёт
                <select v-model="payablePaymentForm.cash_account_id">
                  <option value="">Выберите счёт</option>
                  <option v-for="account in cashAccounts" :key="account.id" :value="account.id">
                    {{ account.name }} · {{ account.currency }}
                  </option>
                </select>
              </label>
              <label>
                Сумма
                <input v-model="payablePaymentForm.amount" inputmode="decimal" />
              </label>
            </div>
            <button class="ghost-button strong" type="button" :disabled="isMutating || !canPayPayable" @click="payPayable">
              Оплатить поставщику
            </button>
          </template>
        </article>

        <article v-if="visibleSections.has('history')" class="panel panel--wide flow-history">
          <header>
            <span class="panel-number">07</span>
            <div>
              <h2>История</h2>
              <p>Рабочий журнал доменных фактов по этому приходу.</p>
            </div>
          </header>
          <div class="history-list">
            <div v-for="entry in workspace.history" :key="`${entry.kind}-${entry.document_id}-${entry.date}`">
              <span>{{ dateLabel(entry.date) }}</span>
              <strong>{{ entry.title }}</strong>
              <small>{{ entry.kind }}</small>
            </div>
          </div>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.workspace-page {
  min-height: 100%;
  padding: 24px clamp(16px, 4vw, 44px) 56px;
  background:
    radial-gradient(circle at top left, rgba(30, 99, 85, 0.12), transparent 32rem),
    linear-gradient(180deg, var(--color-bg-primary), var(--color-bg-secondary));
  color: var(--color-text-primary);
}

.workspace-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 22px;
}

.ghost-button,
.secondary-button,
.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 40px;
  border-radius: 999px;
  font-weight: 700;
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
}

.ghost-button {
  border: 1px solid var(--color-border-subtle);
  background: rgba(255, 255, 255, 0.7);
  color: var(--color-text-primary);
  padding: 0 14px;
}

.ghost-button.strong {
  width: 100%;
  background: var(--color-bg-primary);
}

.secondary-button {
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  padding: 0 16px;
}

.primary-button {
  border: 0;
  background: #183b34;
  color: white;
  padding: 0 18px;
}

.ghost-button:hover,
.secondary-button:hover,
.primary-button:hover {
  transform: translateY(-1px);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  transform: none;
}

.create-shell,
.workspace-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 28px;
  align-items: stretch;
}

.poster,
.workspace-hero {
  border-radius: 32px;
  padding: clamp(24px, 5vw, 48px);
  background:
    linear-gradient(135deg, rgba(24, 59, 52, 0.96), rgba(35, 86, 73, 0.86)),
    repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.08) 0 1px, transparent 1px 12px);
  color: white;
  box-shadow: 0 24px 60px rgba(24, 59, 52, 0.2);
}

.poster h1,
.workspace-hero h1 {
  max-width: 780px;
  margin: 12px 0 14px;
  font-size: clamp(2rem, 5vw, 4.8rem);
  line-height: 0.94;
  letter-spacing: -0.06em;
}

.poster p,
.workspace-hero p {
  max-width: 620px;
  color: rgba(255, 255, 255, 0.76);
  font-size: 1rem;
  line-height: 1.55;
}

.eyebrow {
  display: inline-flex;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: currentColor;
  opacity: 0.72;
}

.create-form,
.panel,
.state-panel {
  border: 1px solid rgba(24, 59, 52, 0.12);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 44px rgba(17, 24, 39, 0.06);
  backdrop-filter: blur(12px);
}

.create-form {
  display: grid;
  gap: 16px;
  padding: 24px;
}

.workspace-hero {
  grid-template-columns: 1fr auto;
  margin-bottom: 18px;
}

.hero-facts {
  display: grid;
  gap: 12px;
  min-width: 220px;
}

.hero-facts div {
  display: grid;
  gap: 4px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.18);
}

.hero-facts span {
  color: rgba(255, 255, 255, 0.62);
  font-size: 0.78rem;
}

.hero-facts strong {
  font-size: 1rem;
}

.policy-strip {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin: 0 0 18px;
  padding: 14px 16px;
  border: 1px solid rgba(194, 65, 12, 0.18);
  border-radius: 20px;
  background: #fff7ed;
  color: #9a3412;
}

.policy-strip p {
  margin-top: 4px;
  color: #9a3412;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  gap: 18px;
}

.panel {
  display: grid;
  align-content: start;
  gap: 18px;
  padding: 22px;
}

.panel--wide {
  grid-column: 1 / -1;
}

.flow-items { order: 1; }
.flow-settlement { order: 2; }
.flow-source { order: 3; }
.flow-capital { order: 4; }
.flow-payments { order: 5; }
.flow-receive { order: 6; }
.flow-history { order: 7; }

.panel header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.panel h2 {
  margin: 0 0 4px;
  font-size: 1.15rem;
  letter-spacing: -0.03em;
}

.panel p {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.panel-number {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #e6f0eb;
  color: #183b34;
  font-size: 0.78rem;
  font-weight: 800;
  flex-shrink: 0;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.form-grid.compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.form-stack {
  display: grid;
  gap: 14px;
}

.span-2 {
  grid-column: 1 / -1;
}

label {
  display: grid;
  gap: 7px;
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  font-weight: 700;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid var(--color-border-subtle);
  border-radius: 14px;
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  padding: 11px 12px;
  font: inherit;
  outline: none;
}

textarea {
  resize: vertical;
}

input:focus,
select:focus,
textarea:focus {
  border-color: #235649;
  box-shadow: 0 0 0 3px rgba(35, 86, 73, 0.12);
}

.line-list,
.history-list {
  display: grid;
  gap: 8px;
}

.line-row,
.mini-row,
.history-list div {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.line-row div {
  display: grid;
  gap: 4px;
}

.line-row span,
.history-list span,
.history-list small {
  color: var(--color-text-tertiary);
  font-size: 0.82rem;
}

.empty-line {
  padding: 16px;
  border-radius: 18px;
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.divider {
  height: 1px;
  background: var(--color-border-subtle);
  margin: 2px 0;
}

.schedule-box {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 20px;
  background: var(--color-bg-secondary);
}

.agreement-builder {
  display: grid;
  gap: 14px;
}

.state-panel {
  padding: 32px;
}

.state-panel--error {
  border-color: var(--color-error);
  color: var(--color-error);
}

@media (max-width: 980px) {
  .create-shell,
  .workspace-hero,
  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .hero-facts {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 640px) {
  .workspace-page {
    padding: 16px 12px 40px;
  }

  .poster,
  .workspace-hero,
  .panel,
  .create-form {
    border-radius: 22px;
  }

  .form-grid,
  .form-grid.compact,
  .hero-facts {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ghost-button,
  .secondary-button,
  .primary-button {
    transition: none;
  }
}
</style>
