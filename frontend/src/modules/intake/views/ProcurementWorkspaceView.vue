<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProcurementWorkspaceStore } from '@/modules/intake/stores/procurementWorkspace'
import { storeToRefs } from 'pinia'
import { useToast } from '@/composables/useToast'
import { useProcurementReadiness } from '@/modules/intake/composables/useProcurementReadiness'
import ProcurementHeader from '@/modules/intake/components/workspace/ProcurementHeader.vue'
import ProcurementCardSupplier from '@/modules/intake/components/workspace/ProcurementCardSupplier.vue'
import ProcurementCardItems from '@/modules/intake/components/workspace/ProcurementCardItems.vue'
import ProcurementCardExpenses from '@/modules/intake/components/workspace/ProcurementCardExpenses.vue'
import ProcurementCardFinancing from '@/modules/intake/components/workspace/ProcurementCardFinancing.vue'
import ProcurementCardPayment from '@/modules/intake/components/workspace/ProcurementCardPayment.vue'
import ProcurementCardReceive from '@/modules/intake/components/workspace/ProcurementCardReceive.vue'
import ProcurementCardHistory from '@/modules/intake/components/workspace/ProcurementCardHistory.vue'
import WorkspaceFlowNav from '@/modules/intake/components/workspace/WorkspaceFlowNav.vue'
import WorkspaceSummaryRail from '@/modules/intake/components/workspace/WorkspaceSummaryRail.vue'
import WorkspaceSupplierPickerSheet from '@/modules/intake/components/workspace/WorkspaceSupplierPickerSheet.vue'
import AmendmentSheet from '@/modules/intake/components/workspace/AmendmentSheet.vue'
import ProcurementCancelDialog from '@/modules/intake/components/workspace/ProcurementCancelDialog.vue'
import ReverseReceiveBatchDialog from '@/modules/intake/components/workspace/ReverseReceiveBatchDialog.vue'
import ProcurementVentureSettlementCard from '@/modules/intake/components/workspace/ProcurementVentureSettlementCard.vue'
import VentureCloseCard from '@/modules/intake/components/workspace/VentureCloseCard.vue'
import {
  closeProcurement,
  createProcurementVentureSettlement,
  fetchProcurementClosePreview,
  fetchProcurementVentureSummary,
  type ClosePreview,
  type ProcurementVentureSummary,
} from '@/api/partnerships'

const route = useRoute()
const router = useRouter()
const store = useProcurementWorkspaceStore()
const { procurement, isLoading, error } = storeToRefs(store)
const toast = useToast()

const supplierPickerOpen = ref(false)
const amendSheetOpen = ref(false)
const amendTarget = ref<'items' | 'expenses'>('items')
const cancelDialogOpen = ref(false)
const reverseDialogOpen = ref(false)
const ventureSummary = ref<ProcurementVentureSummary | null>(null)
const savingVentureSettlement = ref(false)
const closePreview = ref<ClosePreview | null>(null)
const closingProcurement = ref(false)

const paymentError = ref<string | null>(null)
const lastPaymentCashAccountId = ref<number | null>(null)
const lastPaymentAction = ref<string | null>(null)
const lastPaymentPayload = ref<Record<string, unknown> | null>(null)

const PAYMENT_ACTIONS = new Set(['PAY_COSTS', 'PAY_SUPPLIER_PAYABLE'])

const { capitalSectionVisible } = useProcurementReadiness(procurement)

const paymentSectionVisible = computed(
  () => procurement.value?.documents.settlement?.type !== 'AT_RECEIPT',
)
const postReceiveView = computed(() => {
  const status = procurement.value?.status
  return status === 'RECEIVED' || status === 'PARTIALLY_RECEIVED' || status === 'CLOSED'
})

// Which flow steps have a rendered section in this scenario. Backend policy
// drives visibility; we only render the rail items the user can actually reach.
const stepVisible = computed<Record<string, boolean>>(() => ({
  purchase_intent: true,
  supplier_settlement: true,
  funding: capitalSectionVisible.value,
  payment_obligation: paymentSectionVisible.value,
  goods_receipt: true,
  history: true,
}))

// Section order is the founder-controlled sequence (NOT the canonical doc
// order): funding → supplier → goods → payment → receipt → history. The rail
// mirrors the on-screen section order so they stay coherent.
const SECTION_ORDER = ['funding', 'supplier_settlement', 'purchase_intent', 'payment_obligation', 'goods_receipt', 'history']

const flowSteps = computed(() =>
  (procurement.value?.flow.steps ?? [])
    .filter((step) => stepVisible.value[step.key] ?? true)
    .slice()
    .sort((a, b) => SECTION_ORDER.indexOf(a.key) - SECTION_ORDER.indexOf(b.key)),
)

const currentStep = computed(() => procurement.value?.flow.current_step ?? null)

function scrollToStep(key: string): void {
  const el = document.getElementById(`step-${key}`)
  if (!el) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

async function ensureWorkspace(): Promise<void> {
  const id = route.params.id ? Number(route.params.id) : null
  if (id) {
    await store.load(id)
    await Promise.all([loadVentureSummary(id), loadClosePreview(id)])
  } else {
    const mode = route.query.mode as string | undefined
    const agreementId = route.query.agreement ? Number(route.query.agreement) : undefined
    const draftId = await store.createDraft({
      funding_source: mode === 'partnership' ? 'PARTNERSHIP' : 'OWN_FUNDS',
      ...(agreementId ? { agreement_id: agreementId } : {}),
    })
    await router.replace({ name: 'procurement-detail', params: { id: draftId } })
  }
}

async function loadVentureSummary(id = procurement.value?.id ?? null): Promise<void> {
  if (!id) {
    ventureSummary.value = null
    return
  }
  try {
    ventureSummary.value = await fetchProcurementVentureSummary(Number(id))
  } catch {
    ventureSummary.value = null
  }
}

async function loadClosePreview(id = procurement.value?.id ?? null): Promise<void> {
  if (!id) {
    closePreview.value = null
    return
  }
  try {
    closePreview.value = await fetchProcurementClosePreview(Number(id))
  } catch {
    closePreview.value = null
  }
}

async function onCloseProcurement(): Promise<void> {
  if (!procurement.value) return
  closingProcurement.value = true
  try {
    await closeProcurement(procurement.value.id)
    toast.success('Приход закрыт')
    await Promise.all([store.load(procurement.value.id), loadClosePreview(procurement.value.id)])
  } catch (err) {
    const data = (err as any)?.response?.data
    const reasons: string[] = data?.blocking_reasons ?? []
    toast.error(reasons[0] ?? data?.detail ?? (err instanceof Error ? err.message : 'Не удалось закрыть приход'))
    await loadClosePreview(procurement.value.id)
  } finally {
    closingProcurement.value = false
  }
}

async function dispatch(action: string, payload: Record<string, unknown> = {}): Promise<void> {
  if (PAYMENT_ACTIONS.has(action)) {
    lastPaymentAction.value = action
    lastPaymentPayload.value = payload
    lastPaymentCashAccountId.value = (payload.cash_account_id as number | null) ?? null
    paymentError.value = null
  }
  try {
    await store.dispatch(action, payload)
    if (PAYMENT_ACTIONS.has(action)) paymentError.value = null
  } catch (err) {
    const detail = (err as any)?.response?.data?.detail
    const msg = detail ?? (err instanceof Error ? err.message : 'Ошибка операции')
    if (PAYMENT_ACTIONS.has(action)) {
      paymentError.value = msg
    } else {
      toast.error(msg)
    }
  }
}

async function retryLastPayment(): Promise<void> {
  if (!lastPaymentAction.value || !lastPaymentPayload.value) return
  await dispatch(lastPaymentAction.value, lastPaymentPayload.value)
}

function handleMenuAction(actionKey: string): void {
  if (actionKey === 'amend_items') { amendTarget.value = 'items'; amendSheetOpen.value = true; return }
  if (actionKey === 'amend_expenses') { amendTarget.value = 'expenses'; amendSheetOpen.value = true; return }
  if (actionKey === 'cancel') { cancelDialogOpen.value = true; return }
  if (actionKey === 'reverse_receive') { reverseDialogOpen.value = true; return }
  toast.info(`Будет реализовано: ${actionKey}`)
}

async function onUpdateSource(payload: { supplier_id?: number | null; funding_source?: string }): Promise<void> {
  await dispatch('UPDATE_SOURCE', payload as Record<string, unknown>)
}

async function onUpdateSettlement(payload: { type: string }): Promise<void> {
  await dispatch('UPDATE_SETTLEMENT', payload as Record<string, unknown>)
}

function onSupplierSelect(supplierId: number): void {
  supplierPickerOpen.value = false
  onUpdateSource({ supplier_id: supplierId })
}

async function onUpdateItems(items: Record<string, unknown>[]): Promise<void> {
  await dispatch('UPDATE_ITEMS', { items })
}

async function onUpdateExpenses(expenses: Record<string, unknown>[]): Promise<void> {
  await dispatch('UPDATE_EXPENSES', { expenses })
}

async function onLinkAgreement(agreementId: number): Promise<void> {
  await dispatch('LINK_INVESTMENT_AGREEMENT', { agreement_id: agreementId })
}

async function onCancelConfirm(reason: string): Promise<void> {
  await dispatch('CANCEL_WORKSPACE', { reason })
}

async function onDeleteExpense(expenseId: number): Promise<void> {
  await dispatch('UPDATE_EXPENSES', { cancel_expense_ids: [expenseId] })
}

async function onDeleteItem(itemId: number): Promise<void> {
  await dispatch('UPDATE_ITEMS', { cancel_item_ids: [itemId] })
}

async function onSplitItem(payload: { item_id: number; quantity: number }): Promise<void> {
  await dispatch('SPLIT_ITEM', payload)
}

async function onVentureSettle(type: 'CONSTRUCTIVE' | 'FINAL'): Promise<void> {
  if (!procurement.value) return
  savingVentureSettlement.value = true
  try {
    await createProcurementVentureSettlement(procurement.value.id, {
      settlement_type: type,
      inventory_value_uzs: '0',
      reserve_uzs: '0',
    })
    toast.success(type === 'FINAL' ? 'Финальная сверка сохранена' : 'Конструктивная сверка сохранена')
    await Promise.all([
      store.load(procurement.value.id),
      loadVentureSummary(procurement.value.id),
      loadClosePreview(procurement.value.id),
    ])
  } catch (err) {
    const detail = (err as any)?.response?.data?.detail
    toast.error(detail ?? (err instanceof Error ? err.message : 'Не удалось сохранить сверку'))
  } finally {
    savingVentureSettlement.value = false
  }
}

onMounted(ensureWorkspace)
watch(() => route.params.id, ensureWorkspace)
onBeforeUnmount(() => store.$reset())
</script>

<template>
  <div class="workspace">
    <ProcurementHeader
      :procurement-id="procurement?.id ?? null"
      :status="procurement?.status ?? null"
      :title="procurement?.display.title ?? 'Новый приход'"
      :subtitle="procurement?.display.subtitle ?? null"
      :procurement="procurement"
      @back="router.back()"
      @menu-action="handleMenuAction"
    />

    <main class="workspace-body">
      <div v-if="isLoading" class="state">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state">Нет данных</div>

      <div v-else class="mx-auto w-full max-w-[1200px] px-4 py-4 pb-10 sm:px-6">
        <!-- Mobile stepper -->
        <div class="sticky top-0 z-10 -mx-4 mb-4 border-b border-neutral-200 bg-background/90 px-4 py-2 backdrop-blur lg:hidden">
          <WorkspaceFlowNav
            variant="stepper"
            :steps="flowSteps"
            :current-step="currentStep"
            @navigate="scrollToStep"
          />
        </div>

        <div class="lg:grid lg:grid-cols-[200px_minmax(0,1fr)_300px] lg:gap-6">
          <!-- Desktop rail -->
          <aside class="hidden lg:block">
            <div class="sticky top-4">
              <WorkspaceFlowNav
                variant="rail"
                :steps="flowSteps"
                :current-step="currentStep"
                @navigate="scrollToStep"
              />
            </div>
          </aside>

          <!-- Sections in the founder-controlled order -->
          <div class="flex min-w-0 flex-col gap-3">
            <template v-if="postReceiveView">
              <section v-if="ventureSummary" class="scroll-mt-16">
                <ProcurementVentureSettlementCard
                  :summary="ventureSummary"
                  :saving="savingVentureSettlement"
                  :readonly="procurement?.status === 'CLOSED'"
                  @settle="onVentureSettle"
                />
              </section>

              <section v-if="closePreview" class="scroll-mt-16">
                <VentureCloseCard
                  entity-label="приход"
                  :preview="closePreview"
                  :busy="closingProcurement"
                  @close="onCloseProcurement"
                />
              </section>

              <details class="rounded-2xl border border-border bg-background p-3">
                <summary class="cursor-pointer text-sm font-medium text-foreground">Исходные детали прихода</summary>
                <div class="mt-3 flex flex-col gap-3">
                  <ProcurementCardItems
                    :procurement="procurement"
                    @update-items="onUpdateItems"
                    @delete-item="onDeleteItem"
                    @split-item="onSplitItem"
                  />
                  <ProcurementCardExpenses
                    :procurement="procurement"
                    @update-expenses="onUpdateExpenses"
                    @delete-expense="onDeleteExpense"
                  />
                </div>
              </details>
            </template>

            <section v-if="capitalSectionVisible" id="step-funding" class="scroll-mt-16">
              <ProcurementCardFinancing
                :procurement="procurement"
                @link-agreement="onLinkAgreement"
                @dispatch="(k, p) => dispatch(k, p)"
              />
            </section>

            <section v-if="!postReceiveView" id="step-supplier_settlement" class="scroll-mt-16">
              <ProcurementCardSupplier
                :procurement="procurement"
                @update-source="onUpdateSource"
                @update-settlement="onUpdateSettlement"
                @open-supplier-picker="supplierPickerOpen = true"
              />
            </section>

            <section v-if="!postReceiveView" id="step-purchase_intent" class="flex scroll-mt-16 flex-col gap-3">
              <ProcurementCardItems
                :procurement="procurement"
                @update-items="onUpdateItems"
                @delete-item="onDeleteItem"
                @split-item="onSplitItem"
              />
              <ProcurementCardExpenses
                :procurement="procurement"
                @update-expenses="onUpdateExpenses"
                @delete-expense="onDeleteExpense"
              />
            </section>

            <section v-if="paymentSectionVisible && !postReceiveView" id="step-payment_obligation" class="scroll-mt-16">
              <ProcurementCardPayment
                :procurement="procurement"
                :payment-error="paymentError"
                :last-payment-cash-account-id="lastPaymentCashAccountId"
                @dispatch="(k, p) => dispatch(k, p)"
                @retry-payment="retryLastPayment"
              />
            </section>

            <section v-if="!postReceiveView" id="step-goods_receipt" class="scroll-mt-16">
              <ProcurementCardReceive
                :procurement="procurement"
                @dispatch="(k, p) => dispatch(k, p)"
              />
            </section>

            <section v-if="ventureSummary && !postReceiveView" class="scroll-mt-16">
              <ProcurementVentureSettlementCard
                :summary="ventureSummary"
                :saving="savingVentureSettlement"
                :readonly="procurement?.status === 'CLOSED'"
                @settle="onVentureSettle"
              />
            </section>

            <section v-if="closePreview && !postReceiveView" class="scroll-mt-16">
              <VentureCloseCard
                entity-label="приход"
                :preview="closePreview"
                :busy="closingProcurement"
                @close="onCloseProcurement"
              />
            </section>

            <section id="step-history" class="scroll-mt-16">
              <ProcurementCardHistory :procurement="procurement" />
            </section>
          </div>

          <!-- Desktop summary -->
          <aside class="hidden lg:block">
            <div class="sticky top-4">
              <WorkspaceSummaryRail :procurement="procurement" @navigate="scrollToStep" />
            </div>
          </aside>
        </div>
      </div>
    </main>

    <WorkspaceSupplierPickerSheet
      v-model:open="supplierPickerOpen"
      :selected-id="procurement?.documents.procurement.supplier_id ?? null"
      @select="onSupplierSelect"
    />

    <AmendmentSheet
      v-if="procurement"
      v-model:open="amendSheetOpen"
      :procurement="procurement"
      :target="amendTarget"
      @dispatch="(k, p) => dispatch(k, p)"
    />

    <ProcurementCancelDialog
      v-if="procurement"
      v-model:open="cancelDialogOpen"
      :procurement="procurement"
      @confirm="onCancelConfirm"
    />

    <ReverseReceiveBatchDialog
      v-if="procurement"
      v-model:open="reverseDialogOpen"
      :procurement="procurement"
      @dispatch="(k, p) => dispatch(k, p)"
    />
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100dvh;
  display: grid;
  grid-template-rows: auto 1fr;
  background: var(--bg);
}

.workspace-body {
  overflow-y: auto;
}

.state {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--neutral-500);
}

.state-error {
  color: var(--destructive);
}
</style>
