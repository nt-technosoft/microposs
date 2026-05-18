<script setup lang="ts">
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import InvestmentAgreementDetailSheet from './InvestmentAgreementDetailSheet.vue'
import InvestmentAgreementQuickForm from './InvestmentAgreementQuickForm.vue'
import { formatPrice } from '@/utils/currency'
import type { InvestmentAgreementDetail, InvestmentAgreementListItem } from '@/api/partnerships'
import { computed, ref } from 'vue'

const props = defineProps<{
  agreements: InvestmentAgreementListItem[]
  selectedAgreementId: number | null
  linkedAgreementId: number | null
  isLoading: boolean
  isCreating: boolean
  error: string | null
  currentProcurementId: number | null
}>()

const emit = defineEmits<{
  updateSelectedAgreement: [agreementId: number | null]
  start: []
  createdAgreement: [agreement: InvestmentAgreementDetail]
}>()

const createOpen = ref(false)
const detailOpen = ref(false)
const selectedAgreement = computed(() => props.agreements.find((agreement) => agreement.id === props.selectedAgreementId) ?? null)
const linkedAgreement = computed(() => props.agreements.find((agreement) => agreement.id === props.linkedAgreementId) ?? null)

function balanceLabel(agreement: InvestmentAgreementListItem): string {
  const amount = Number(agreement.balances?.[agreement.currency] ?? 0)
  return formatPrice(Number.isFinite(amount) ? amount : 0, agreement.currency)
}

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function investorLabel(agreement: InvestmentAgreementListItem): string {
  return agreement.investor_names?.length ? agreement.investor_names.join(', ') : 'Инвестор не указан'
}

function agreementFactLine(agreement: InvestmentAgreementListItem): string {
  return [
    dateLabel(agreement.opened_at),
    `Бюджет ${formatPrice(Number(agreement.planned_budget || 0), agreement.currency)}`,
    `Доступно ${balanceLabel(agreement)}`,
    `${agreement.procurements_count} прих.`,
  ].join(' · ')
}

function onCreated(agreement: InvestmentAgreementDetail): void {
  createOpen.value = false
  emit('createdAgreement', agreement)
}
</script>

<template>
  <div class="investment-start">
    <template v-if="linkedAgreementId">
      <button class="agreement-card linked-card" type="button" @click="detailOpen = true">
        <span class="agreement-line">
          <strong>#{{ linkedAgreementId }} · {{ linkedAgreement ? investorLabel(linkedAgreement) : 'Инвестдоговор' }}</strong>
          <small>{{ linkedAgreement ? agreementFactLine(linkedAgreement) : 'Открыть детали договора' }}</small>
        </span>
      </button>
    </template>

    <template v-else>
      <div class="compact-copy">
        <strong>Выберите договор для партнёрского прихода</strong>
        <span>Один инвестдоговор может финансировать несколько приходов. Если договора ещё нет, создайте его здесь же.</span>
      </div>

      <div v-if="isLoading" class="empty-box">Загрузка договоров…</div>
      <div v-else-if="agreements.length === 0" class="empty-box">
        <strong>Инвестдоговоров пока нет</strong>
        <span>Создайте первый договор и вернитесь к товарам в этом же workspace.</span>
      </div>
      <div v-else class="agreement-list">
        <button
          v-for="agreement in agreements"
          :key="agreement.id"
          class="agreement-card"
          :class="{ active: selectedAgreementId === agreement.id }"
          type="button"
          :disabled="isCreating"
          @click="emit('updateSelectedAgreement', agreement.id)"
        >
          <span class="agreement-line">
            <strong>#{{ agreement.id }} · {{ investorLabel(agreement) }}</strong>
            <small>{{ agreementFactLine(agreement) }}</small>
          </span>
        </button>
      </div>

      <div class="agreement-actions">
        <button class="primary-action" type="button" :disabled="!selectedAgreementId || isCreating" @click="emit('start')">
          {{ isCreating ? 'Создание…' : selectedAgreement ? `Начать с договором #${selectedAgreement.id}` : 'Начать партнёрский приход' }}
        </button>
        <button class="secondary-action" type="button" :disabled="isCreating" @click="createOpen = true">
          Создать новый договор
        </button>
      </div>
    </template>

    <p v-if="error" class="error-note">{{ error }}</p>

    <AppBottomSheet :open="createOpen" title="Новый инвестдоговор" @close="createOpen = false">
      <InvestmentAgreementQuickForm @created="onCreated" />
    </AppBottomSheet>
    <InvestmentAgreementDetailSheet
      :open="detailOpen"
      :agreement-id="linkedAgreementId"
      :current-procurement-id="currentProcurementId"
      @close="detailOpen = false"
    />
  </div>
</template>

<style scoped>
.investment-start,
.agreement-list {
  display: grid;
  gap: 12px;
}

.compact-copy {
  display: grid;
  gap: 4px;
}

.compact-copy strong,
.empty-box strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.compact-copy span,
.empty-box span,
.error-note {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.empty-box {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.agreement-card {
  display: grid;
  gap: 4px;
  padding: 12px 13px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  text-align: left;
}

.linked-card {
  background: var(--color-brand-50);
}

.agreement-card.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.agreement-line {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.agreement-line strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  line-height: 1.25;
}

.agreement-line small {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agreement-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
}

.primary-action,
.secondary-action {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.primary-action {
  border: 0;
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.secondary-action {
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
}

.primary-action:disabled,
.secondary-action:disabled {
  opacity: 0.58;
}

.error-note {
  color: var(--color-danger);
}
</style>
