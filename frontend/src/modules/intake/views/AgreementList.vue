<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FileText, RefreshCcw } from 'lucide-vue-next'
import { fetchInvestmentAgreements, type InvestmentAgreementListItem } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import ProcurementSectionShell from '@/modules/intake/components/ProcurementSectionShell.vue'

const router = useRouter()
const toast = useToast()

const agreements = ref<InvestmentAgreementListItem[]>([])
const loading = ref(false)
const error = ref('')

const totals = computed(() => agreements.value.reduce((acc, item) => {
  acc.budget += Number.parseFloat(item.planned_budget || '0') || 0
  acc.open += item.status === 'OPEN' || item.status === 'ACTIVE' ? 1 : 0
  return acc
}, { budget: 0, open: 0 }))

function balanceLabel(item: InvestmentAgreementListItem): string {
  const parts = Object.entries(item.balances || {})
    .filter(([, amount]) => Math.abs(Number.parseFloat(amount || '0')) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
}

function statusLabel(status: string): string {
  if (status === 'ACTIVE') return 'Активен'
  if (status === 'OPEN') return 'Открыт'
  if (status === 'CLOSED') return 'Закрыт'
  if (status === 'CANCELLED') return 'Отменён'
  return status
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    agreements.value = await fetchInvestmentAgreements()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить инвестдоговоры'
    toast.error(error.value)
  } finally {
    loading.value = false
  }
}

function goToCreate(): void {
  router.push({ name: 'agreement-create' })
}

onMounted(load)
</script>

<template>
  <ProcurementSectionShell
    active-mode="agreements"
    title="Договоры"
    primary-label="Новый"
    primary-aria-label="Новый инвестдоговор"
    @primary="goToCreate"
  >
    <template #header-actions>
      <button class="icon-btn" type="button" aria-label="Обновить договоры" @click="load">
        <RefreshCcw :size="17" />
      </button>
    </template>

    <template #summary>
      <div class="summary-grid">
        <div class="summary-tile">
          <span class="summary-label">Активные</span>
          <strong class="summary-value">{{ totals.open }}</strong>
        </div>
        <div class="summary-tile">
          <span class="summary-label">Плановый бюджет</span>
          <strong class="summary-value">{{ formatPrice(totals.budget, 'USD') }}</strong>
        </div>
      </div>
    </template>

    <div class="content">
      <div v-if="loading" class="state">Загрузка...</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>
      <div v-else-if="agreements.length === 0" class="empty">
        <FileText :size="34" />
        <strong>Инвестдоговоров пока нет</strong>
        <span>Создайте договор, внесите деньги и откройте первый связанный приход.</span>
      </div>

      <button
        v-for="agreement in agreements"
        v-else
        :key="agreement.id"
        class="agreement-row"
        type="button"
        @click="router.push({ name: 'agreement-detail', params: { id: agreement.id } })"
      >
        <div class="row-main">
          <strong>Инвестдоговор #{{ agreement.id }}</strong>
          <span>{{ agreement.supplier_name || 'Без поставщика' }} · {{ agreement.procurements_count }} приходов</span>
        </div>
        <div class="row-side">
          <strong>{{ balanceLabel(agreement) }}</strong>
          <span>{{ statusLabel(agreement.status) }}</span>
        </div>
      </button>
    </div>
  </ProcurementSectionShell>
</template>

<style scoped>
.icon-btn {
  width: 38px;
  height: 38px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

.summary-tile {
  display: grid;
  gap: 4px;
  padding: var(--space-3) var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.summary-value {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.content {
  display: grid;
  gap: var(--space-3);
}

.agreement-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: center;
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  text-align: left;
  transition: box-shadow var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.agreement-row:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-sm);
}

.agreement-row:active {
  transform: scale(0.985);
}

.row-main,
.row-side {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.row-main strong,
.row-side strong {
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.row-main span,
.row-side span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.row-side {
  text-align: right;
}

.state,
.empty {
  display: grid;
  place-items: center;
  gap: var(--space-2);
  min-height: 180px;
  color: var(--color-text-secondary);
  text-align: center;
}

.state-error {
  color: var(--color-danger);
}

.empty strong {
  color: var(--color-text-primary);
}

.empty span {
  max-width: 280px;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}
</style>
