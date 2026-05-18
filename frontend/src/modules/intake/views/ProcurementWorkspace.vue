<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown } from 'lucide-vue-next'
import {
  createProcurementWorkspace,
  fetchInvestmentAgreements,
  type InvestmentAgreementDetail,
  type InvestmentAgreementListItem,
} from '@/api/partnerships'
import WorkspaceGoodsExpensesBlock from '@/modules/intake/components/workspace/WorkspaceGoodsExpensesBlock.vue'
import WorkspaceInvestmentStartBlock from '@/modules/intake/components/workspace/WorkspaceInvestmentStartBlock.vue'
import WorkspaceQuickProductSheet from '@/modules/intake/components/workspace/WorkspaceQuickProductSheet.vue'
import WorkspaceVariantPickerSheet from '@/modules/intake/components/workspace/WorkspaceVariantPickerSheet.vue'
import { useGoodsExpensesWorkspace } from '@/modules/intake/components/workspace/useGoodsExpensesWorkspace'

const route = useRoute()
const router = useRouter()

const procurementId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const goods = useGoodsExpensesWorkspace({
  router,
  getProcurementId: () => procurementId.value,
})

type WorkspaceMode = 'regular' | 'partnership'
type WorkspaceBlockKey = 'investment' | 'goods' | 'supplier' | 'finance' | 'receipt' | 'history'

const routeMode = computed<WorkspaceMode>(() => (
  route.query.mode === 'partnership' || route.query.agreement_id ? 'partnership' : 'regular'
))
const workspaceMode = computed<WorkspaceMode>(() => {
  if (goods.workspace?.policy.funding_source === 'PARTNERSHIP') return 'partnership'
  return routeMode.value
})
const investmentAgreements = ref<InvestmentAgreementListItem[]>([])
const selectedAgreementId = ref<number | null>(Number(route.query.agreement_id) || null)
const isLoadingAgreements = ref(false)
const isStartingPartnership = ref(false)
const investmentError = ref<string | null>(null)
const openBlocks = ref<Record<WorkspaceBlockKey, boolean>>({
  investment: true,
  goods: true,
  supplier: false,
  finance: false,
  receipt: false,
  history: false,
})

const isNewWorkspace = computed(() => procurementId.value === null && goods.workspace === null)
const pageTitle = computed(() => (
  isNewWorkspace.value
    ? (workspaceMode.value === 'partnership' ? 'Новый партнёрский приход' : 'Новый приход')
    : `Приход #${goods.workspace?.id ?? procurementId.value}`
))

const linkedAgreementId = computed(() => (
  goods.workspace?.documents.source.investment_agreement_id
  ?? goods.workspace?.documents.investment?.agreement_id
  ?? null
))

const workspaceBlocks = computed<Array<{ key: WorkspaceBlockKey; title: string }>>(() => {
  const base: Array<{ key: WorkspaceBlockKey; title: string }> = [
    { key: 'goods', title: 'Товары и расходы' },
    { key: 'supplier', title: 'Условия закупки' },
    { key: 'finance', title: 'Финансы' },
    { key: 'receipt', title: 'Приёмка' },
    { key: 'history', title: 'История' },
  ]
  if (workspaceMode.value !== 'partnership') return base
  return [{ key: 'investment', title: 'Инвестдоговор' }, ...base]
})

function isBlockOpen(key: WorkspaceBlockKey): boolean {
  return Boolean(openBlocks.value[key])
}

function toggleWorkspaceBlock(key: WorkspaceBlockKey): void {
  openBlocks.value = { ...openBlocks.value, [key]: !openBlocks.value[key] }
}

async function loadInvestmentAgreements(): Promise<void> {
  if (workspaceMode.value !== 'partnership') return
  isLoadingAgreements.value = true
  investmentError.value = null
  try {
    investmentAgreements.value = await fetchInvestmentAgreements()
    if (!selectedAgreementId.value && !linkedAgreementId.value && investmentAgreements.value.length > 0) {
      selectedAgreementId.value = investmentAgreements.value[0].id
    }
  } catch (error) {
    investmentError.value = error instanceof Error ? error.message : 'Не удалось загрузить инвестдоговоры'
  } finally {
    isLoadingAgreements.value = false
  }
}

async function startPartnershipWorkspace(): Promise<void> {
  if (!selectedAgreementId.value) return
  isStartingPartnership.value = true
  investmentError.value = null
  try {
    const created = await createProcurementWorkspace({
      funding_source: 'PARTNERSHIP',
      investment_agreement_id: selectedAgreementId.value,
      primary_currency: goods.primaryCurrency,
    })
    await router.replace({ name: 'procurement-detail', params: { id: created.id } })
    await goods.initGoodsExpenses()
  } catch (error) {
    investmentError.value = error instanceof Error ? error.message : 'Не удалось начать партнёрский приход'
  } finally {
    isStartingPartnership.value = false
  }
}

async function startPartnershipWithAgreement(agreementId: number): Promise<void> {
  selectedAgreementId.value = agreementId
  await startPartnershipWorkspace()
}

async function handleCreatedAgreement(agreement: InvestmentAgreementDetail): Promise<void> {
  investmentAgreements.value = [
    {
      id: agreement.id,
      status: agreement.status,
      opened_at: agreement.opened_at,
      closed_at: agreement.closed_at,
      supplier: agreement.supplier,
      supplier_name: agreement.supplier_name,
      planned_budget: agreement.planned_budget,
      currency: agreement.currency,
      mudaraba_ratio: agreement.mudaraba_ratio,
      balances: agreement.balances,
      partners_count: agreement.partners.length,
      investor_names: agreement.partners.filter((partner) => partner.role === 'INVESTOR').map((partner) => partner.partner_name),
      operator_names: agreement.partners.filter((partner) => partner.role === 'OPERATOR').map((partner) => partner.partner_name),
      procurements_count: agreement.procurements.length,
      notes: agreement.notes,
    },
    ...investmentAgreements.value,
  ]
  await startPartnershipWithAgreement(agreement.id)
}

onMounted(async () => {
  await goods.initGoodsExpenses()
  await loadInvestmentAgreements()
})

onBeforeUnmount(() => {
  goods.abortGoodsExpensesRequests()
})
</script>

<template>
  <main class="workspace-shell">
    <header class="workspace-topbar">
      <button class="topbar-button" type="button" aria-label="Назад к списку" @click="router.push({ name: 'procurement-list' })">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>

      <h1>{{ pageTitle }}</h1>

      <span class="topbar-spacer" aria-hidden="true" />
    </header>

    <section class="workspace-canvas" aria-label="Рабочая область прихода">
      <div class="block-list">
        <article v-for="(block, index) in workspaceBlocks" :key="block.key" class="workspace-block">
          <button class="block-header" type="button" @click="toggleWorkspaceBlock(block.key)">
            <span class="block-index">{{ index + 1 }}</span>
            <span class="block-title">{{ block.title }}</span>
            <ChevronDown class="block-chevron" :class="{ open: isBlockOpen(block.key) }" :size="18" :stroke-width="2" />
          </button>

          <div v-if="isBlockOpen(block.key) && block.key === 'investment'" class="block-body">
            <WorkspaceInvestmentStartBlock
              :agreements="investmentAgreements"
              :selected-agreement-id="selectedAgreementId"
              :linked-agreement-id="linkedAgreementId"
              :is-loading="isLoadingAgreements"
              :is-creating="isStartingPartnership"
              :error="investmentError"
              :current-procurement-id="procurementId"
              @update-selected-agreement="selectedAgreementId = $event"
              @start="startPartnershipWorkspace"
              @created-agreement="handleCreatedAgreement"
            />
          </div>

          <div v-if="isBlockOpen(block.key) && block.key === 'goods'" class="block-body">
            <div v-if="workspaceMode === 'partnership' && !linkedAgreementId" class="blocked-body">
              Сначала выберите или создайте инвестдоговор. После этого товары и расходы будут доступны в этом же workspace.
            </div>
            <WorkspaceGoodsExpensesBlock
              v-else
              :lines="goods.draftLines"
              :expenses="goods.draftExpenses"
              :primary-currency="goods.primaryCurrency"
              :line-errors="goods.lineErrors"
              :expense-errors="goods.expenseErrors"
              :goods-total="goods.goodsTotal"
              :expenses-total="goods.expensesTotal"
              :procurement-total="goods.procurementTotal"
              :is-loading="goods.isLoading"
              :is-saving="goods.isSavingDraft"
              :error="goods.draftError"
              :expense-type-options="goods.expenseTypeOptions"
              :allocation-options="goods.allocationOptions"
              :item-targets="goods.editableItemTargets"
              :has-unsaved-lines="goods.hasUnsavedLines"
              :variant-display="goods.variantDisplay"
              :show-fx-field="goods.showFxField"
              :format-currency-total-label="goods.formatCurrencyTotalLabel"
              @update-primary-currency="goods.setPrimaryCurrency"
              @add-line="goods.addEmptyLine"
              @add-expense="goods.addExpense"
              @open-quick-product="goods.openQuickProductCreator()"
              @open-variant-picker="goods.openVariantPicker"
              @remove-line="goods.removeLine"
              @update-line="goods.updateLine"
              @toggle-line-currency="goods.toggleLineCurrency"
              @remove-expense="goods.removeExpense"
              @update-expense="goods.updateExpense"
              @toggle-expense-currency="goods.toggleExpenseCurrency"
              @toggle-expense-target="goods.toggleExpenseTarget"
              @set-expense-all-targets="goods.setExpenseAllTargets"
              @save="goods.saveGoodsAndExpenses"
            />
          </div>
        </article>
      </div>
    </section>

    <WorkspaceVariantPickerSheet
      :open="goods.variantSheetOpen"
      :search="goods.variantSearch"
      :category="goods.variantSearchCategory"
      :category-options="goods.categoryOptions"
      :variants="goods.filteredVariants"
      :variant-display="goods.variantDisplay"
      @close="goods.closeVariantPicker"
      @update-search="goods.variantSearch = $event"
      @update-category="goods.variantSearchCategory = $event"
      @new-product="goods.openQuickProductCreator()"
      @select="goods.selectVariant"
    />

    <WorkspaceQuickProductSheet
      :open="goods.quickProductSheetOpen"
      :name="goods.quickProductName"
      :category-id="goods.quickProductCategoryId"
      :base-price="goods.quickProductBasePrice"
      :category-options="goods.quickProductCategoryOptions"
      :error="goods.quickProductError"
      :saving="goods.isCreatingQuickProduct"
      @close="goods.closeQuickProductCreator"
      @update-name="goods.quickProductName = $event"
      @update-category-id="goods.quickProductCategoryId = $event"
      @update-base-price="goods.quickProductBasePrice = $event"
      @submit="goods.createQuickProductAction"
    />
  </main>
</template>

<style scoped>
.workspace-shell {
  min-height: 100dvh;
  padding: 0 14px 28px;
  background:
    radial-gradient(circle at top left, rgba(46, 125, 50, 0.08), transparent 34%),
    var(--color-bg-secondary);
}

.workspace-topbar {
  position: sticky;
  top: 0;
  z-index: 5;
  min-height: 64px;
  max-width: 1080px;
  margin: 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 0;
  background: linear-gradient(to bottom, var(--color-bg-secondary) 78%, rgba(245, 243, 237, 0));
}

.topbar-button,
.topbar-spacer {
  width: 42px;
  height: 42px;
}

.topbar-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.workspace-topbar h1 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  line-height: 1.2;
  text-align: center;
}

.workspace-canvas {
  max-width: 1080px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}

.block-list {
  display: grid;
  gap: 10px;
}

.workspace-block {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  overflow: hidden;
}

.block-header {
  width: 100%;
  min-height: 64px;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) 24px;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
}

.block-index {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
}

.block-title {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.block-chevron {
  color: var(--color-text-tertiary);
  transition: transform 160ms ease;
}

.block-chevron.open {
  transform: rotate(180deg);
}

.block-body {
  display: grid;
  gap: 14px;
  padding: 0 14px 16px;
}

.blocked-body {
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

@media (max-width: 640px) {
  .workspace-shell {
    padding-inline: 14px;
  }

  .workspace-block {
    border-radius: var(--radius-lg);
  }
}
</style>
              @update-primary-currency="goods.setPrimaryCurrency"
