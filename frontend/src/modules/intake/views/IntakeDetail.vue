<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CheckCircle2, AlertCircle } from 'lucide-vue-next'
import { ReceiptStatus, ReceiptType } from '@/types/enums'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import api from '@/api/client'

interface ReceiptParticipant {
  id: number
  participant_type: 'business' | 'investor'
  entity_id: number
  capital_amount: string
  profit_ratio: string
}

interface ReceiptLine {
  id: number
  product_variant_name: string
  quantity: number
  cost_per_unit: string
  total_cost: string
}

interface ReceiptDetail {
  id: number
  receipt_type: ReceiptType
  status: ReceiptStatus
  date: string
  destination_name: string
  lines: ReceiptLine[]
  participants: ReceiptParticipant[]
  notes: string
}

const route = useRoute()
const router = useRouter()
const toast = useToast()

const receipt = ref<ReceiptDetail | null>(null)
const isLoading = ref(true)
const isConfirming = ref(false)
const errorMessage = ref<string | null>(null)

const typeLabel: Record<ReceiptType, string> = {
  [ReceiptType.BUSINESS_OWNED]: 'Свои деньги',
  [ReceiptType.MUDARABA]: 'Мудараба',
  [ReceiptType.MUSHARAKA]: 'Мушарака',
  [ReceiptType.SUPPLIER_PURCHASE]: 'Поставщик',
  [ReceiptType.CONSIGNMENT]: 'Консигнация',
}

const canConfirm = computed(() => receipt.value?.status === ReceiptStatus.DRAFT)

const totalAmount = computed(() => {
  if (!receipt.value) return 0
  return receipt.value.lines.reduce((sum, line) => sum + parseFloat(line.total_cost || '0'), 0)
})

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadReceipt(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    errorMessage.value = 'Некорректный ID прихода'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = null

  try {
    const { data } = await api.get<ReceiptDetail>(`/api/v1/inventory/receipts/${id}/`)
    receipt.value = data
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить приход'
  } finally {
    isLoading.value = false
  }
}

async function confirmReceipt(): Promise<void> {
  if (!receipt.value || !canConfirm.value) return

  isConfirming.value = true
  try {
    await api.post(`/api/v1/inventory/receipts/${receipt.value.id}/confirm/`)
    toast.success('Приход подтверждён')
    await loadReceipt()
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось подтвердить приход'
    toast.error(message)
  } finally {
    isConfirming.value = false
  }
}

onMounted(loadReceipt)
</script>

<template>
  <div class="detail-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Приход #{{ route.params.id }}</h1>
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
      <button class="retry-btn" type="button" @click="loadReceipt">Повторить</button>
    </div>

    <template v-else-if="receipt">
      <main class="content">
        <section class="card">
          <div class="row row-between">
            <div class="chips">
              <span class="chip chip-type">{{ typeLabel[receipt.receipt_type] }}</span>
              <span class="chip" :class="receipt.status === 'confirmed' ? 'chip-success' : 'chip-draft'">
                {{ receipt.status === 'confirmed' ? 'Подтверждён' : 'Черновик' }}
              </span>
            </div>
            <span class="date">{{ formatDateTime(receipt.date) }}</span>
          </div>

          <div class="meta">
            <span>Склад: <strong>{{ receipt.destination_name }}</strong></span>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">Участники</h2>
          <div v-if="receipt.participants.length === 0" class="muted">
            Для этого типа прихода участники не требуются.
          </div>
          <div v-else class="participants">
            <div v-for="p in receipt.participants" :key="p.id" class="participant-row">
              <span class="participant-name">
                {{ p.participant_type === 'business' ? 'Бизнес' : `Инвестор #${p.entity_id}` }}
              </span>
              <span class="participant-share">
                {{ (Number(p.profit_ratio) * 100).toFixed(0) }}% прибыли
              </span>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">Товары</h2>
          <div class="lines">
            <div v-for="line in receipt.lines" :key="line.id" class="line-row">
              <div class="line-main">
                <span class="line-name">{{ line.product_variant_name }}</span>
                <span class="line-qty">× {{ line.quantity }}</span>
              </div>
              <span class="line-total tabular-nums">{{ formatPrice(line.total_cost) }}</span>
            </div>
          </div>
          <div class="divider" />
          <div class="row row-between total-row">
            <span>Итого</span>
            <strong class="tabular-nums">{{ formatPrice(totalAmount) }}</strong>
          </div>
        </section>

        <section v-if="receipt.notes" class="card">
          <h2 class="section-title">Заметки</h2>
          <p class="notes">{{ receipt.notes }}</p>
        </section>
      </main>

      <footer class="footer">
        <button
          v-if="canConfirm"
          class="confirm-btn"
          type="button"
          :disabled="isConfirming"
          @click="confirmReceipt"
        >
          <span v-if="isConfirming" class="spinner" />
          <CheckCircle2 v-else :size="18" :stroke-width="2" />
          <span>{{ isConfirming ? 'Подтверждение…' : 'Подтвердить приход' }}</span>
        </button>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.detail-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.page-title {
  flex: 1;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.back-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
}

.header-spacer {
  width: 40px;
  height: 40px;
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--space-24) + env(safe-area-inset-bottom, 0px));
}

.card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
}

.row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.row-between {
  justify-content: space-between;
}

.chips {
  display: flex;
  gap: var(--space-2);
}

.chip {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  padding: 0 var(--space-2);
  min-height: 22px;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.chip-type {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.chip-success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.chip-draft {
  background: var(--color-bg-sunken);
  color: var(--color-text-secondary);
}

.date {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.meta {
  margin-top: var(--space-3);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.participants,
.lines {
  display: grid;
  gap: var(--space-2);
}

.participant-row,
.line-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.participant-name,
.line-name {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.participant-share,
.line-qty {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.line-main {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.line-total {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.divider {
  height: 1px;
  background: var(--color-border-subtle);
  margin: var(--space-3) 0;
}

.total-row {
  color: var(--color-text-primary);
}

.notes {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  white-space: pre-wrap;
}

.footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: var(--space-3) var(--space-4);
  padding-bottom: calc(var(--space-3) + env(safe-area-inset-bottom, 0px));
  background: linear-gradient(to top, var(--color-bg-primary), rgba(0, 0, 0, 0));
}

.confirm-btn {
  width: 100%;
  min-height: 48px;
  border-radius: var(--radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-weight: var(--font-semibold);
}

.confirm-btn:disabled {
  opacity: 0.6;
}

.loading-wrap,
.error-wrap {
  padding: var(--space-4);
}

.error-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  align-items: flex-start;
  color: var(--color-error);
}

.retry-btn {
  min-height: 40px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
}

.skeleton {
  border-radius: var(--radius-md);
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 0%,
    var(--color-bg-elevated) 50%,
    var(--color-bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.1s linear infinite;
}

.skeleton-title {
  height: 20px;
  width: 45%;
  margin-bottom: var(--space-3);
}

.skeleton-card {
  height: 120px;
  margin-bottom: var(--space-3);
}

.spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: spin 0.7s linear infinite;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
