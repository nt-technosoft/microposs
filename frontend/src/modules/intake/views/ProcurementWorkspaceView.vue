<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
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
import WorkspaceSupplierPickerSheet from '@/modules/intake/components/workspace/WorkspaceSupplierPickerSheet.vue'
import AmendmentSheet from '@/modules/intake/components/workspace/AmendmentSheet.vue'
import ProcurementCancelDialog from '@/modules/intake/components/workspace/ProcurementCancelDialog.vue'
import ReverseReceiveBatchDialog from '@/modules/intake/components/workspace/ReverseReceiveBatchDialog.vue'

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

const paymentError = ref<string | null>(null)
const lastPaymentCashAccountId = ref<number | null>(null)
const lastPaymentAction = ref<string | null>(null)
const lastPaymentPayload = ref<Record<string, unknown> | null>(null)

const PAYMENT_ACTIONS = new Set(['PAY_COSTS', 'PAY_SUPPLIER_PAYABLE'])

const { capitalSectionVisible } = useProcurementReadiness(procurement)

async function ensureWorkspace(): Promise<void> {
  const id = route.params.id ? Number(route.params.id) : null
  if (id) {
    await store.load(id)
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
  if (actionKey === 'amend') { amendTarget.value = 'items'; amendSheetOpen.value = true; return }
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
      @back="router.back()"
      @menu-action="handleMenuAction"
    />

    <main class="workspace-body">
      <div v-if="isLoading" class="state state-loading">Загрузка…</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="!procurement" class="state state-empty">Нет данных</div>
      <div v-else class="cards-container">
        <ProcurementCardFinancing
          v-if="capitalSectionVisible"
          :procurement="procurement"
          @link-agreement="onLinkAgreement"
        />
        <ProcurementCardSupplier
          :procurement="procurement"
          @update-source="onUpdateSource"
          @update-settlement="onUpdateSettlement"
          @open-supplier-picker="supplierPickerOpen = true"
        />
        <ProcurementCardItems
          :procurement="procurement"
          @update-items="onUpdateItems"
          @delete-item="onDeleteItem"
        />
        <ProcurementCardExpenses
          :procurement="procurement"
          @update-expenses="onUpdateExpenses"
          @delete-expense="onDeleteExpense"
        />
        <ProcurementCardPayment
          v-if="procurement.documents.settlement?.type !== 'AT_RECEIPT'"
          :procurement="procurement"
          :payment-error="paymentError"
          :last-payment-cash-account-id="lastPaymentCashAccountId"
          @dispatch="(k, p) => dispatch(k, p)"
          @retry-payment="retryLastPayment"
        />
        <ProcurementCardReceive
          :procurement="procurement"
          @dispatch="(k, p) => dispatch(k, p)"
        />
        <ProcurementCardHistory :procurement="procurement" />
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
  background: var(--color-bg-secondary);
}

.workspace-body {
  overflow-y: auto;
  padding: var(--space-4);
  padding-bottom: var(--space-8);
}

.cards-container {
  display: grid;
  gap: var(--space-3);
  max-width: 640px;
  margin: 0 auto;
}

.state {
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--color-text-secondary);
}

.state-error { color: var(--color-error); }
</style>
