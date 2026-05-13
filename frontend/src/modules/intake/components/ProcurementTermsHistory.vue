<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarClock, Pencil } from 'lucide-vue-next'
import {
  amendProcurementTerms,
  fetchProcurementTermsAmendments,
  type ProcurementDetail,
  type ProcurementTermsAmendment,
} from '@/api/partnerships'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseButton from '@/components/base/BaseButton.vue'

const props = defineProps<{
  procurementId: number
  terms: ProcurementDetail['terms']
}>()

const emit = defineEmits<{
  changed: []
}>()

const { t } = useI18n()
const amendments = ref<ProcurementTermsAmendment[]>([])
const isLoading = ref(false)
const editOpen = ref(false)
const reason = ref('')
const deadlineDate = ref('')
const notes = ref('')
const isSubmitting = ref(false)

const hasTerms = computed(() => Boolean(props.terms))
const canEditDeadline = computed(() => props.terms?.type === 'DEFERRED')

function fieldLabel(field: string): string {
  const key = `procurements.detail.termsField.${field}`
  const label = t(key)
  return label === key ? field : label
}

function openEdit(): void {
  deadlineDate.value = props.terms?.deadline_date ?? ''
  notes.value = props.terms?.notes ?? ''
  reason.value = ''
  editOpen.value = true
}

async function load(): Promise<void> {
  if (!hasTerms.value) return
  isLoading.value = true
  try {
    amendments.value = await fetchProcurementTermsAmendments(props.procurementId)
  } finally {
    isLoading.value = false
  }
}

async function submit(): Promise<void> {
  if (!props.terms || isSubmitting.value) return
  const newFields: Record<string, unknown> = {
    notes: notes.value.trim(),
  }
  if (canEditDeadline.value) {
    newFields.deadline_date = deadlineDate.value || null
  }
  isSubmitting.value = true
  try {
    await amendProcurementTerms(props.procurementId, {
      new_fields: newFields,
      reason: reason.value.trim(),
    })
    editOpen.value = false
    await load()
    emit('changed')
  } finally {
    isSubmitting.value = false
  }
}

watch(() => props.procurementId, load)
onMounted(load)
</script>

<template>
  <section v-if="terms" class="terms-history">
    <header class="terms-head">
      <div>
        <span>{{ t('procurements.detail.termsEyebrow') }}</span>
        <h2>{{ t('procurements.detail.termsTitle') }}</h2>
      </div>
      <button type="button" @click="openEdit">
        <Pencil :size="14" :stroke-width="2" />
        {{ t('common.edit') }}
      </button>
    </header>

    <div class="terms-summary">
      <div>
        <span>{{ t('common.type') }}</span>
        <strong>{{ t(`procurements.create.terms${terms.type.charAt(0)}${terms.type.slice(1).toLowerCase()}`) }}</strong>
      </div>
      <div>
        <span>{{ t('suppliers.toPay') }}</span>
        <strong class="tabular-nums">{{ terms.remaining_amount }} {{ terms.currency_of_obligation }}</strong>
      </div>
      <div v-if="terms.deadline_date">
        <span>{{ t('suppliers.deadline') }}</span>
        <strong>{{ terms.deadline_date }}</strong>
      </div>
    </div>

    <div class="amendments">
      <div class="amendments-head">
        <span>{{ t('procurements.detail.termsAmendments') }}</span>
        <strong>{{ amendments.length }}</strong>
      </div>
      <p v-if="isLoading" class="muted">{{ t('common.loading') }}</p>
      <p v-else-if="amendments.length === 0" class="muted">{{ t('procurements.detail.termsNoAmendments') }}</p>
      <article v-for="amendment in amendments" :key="amendment.id" class="amendment-row">
        <div class="amendment-date">
          <CalendarClock :size="14" :stroke-width="1.8" />
          <span>{{ amendment.amended_at }}</span>
        </div>
        <strong>{{ amendment.reason || t('procurements.detail.termsAmendmentNoReason') }}</strong>
        <ul>
          <li v-for="(value, field) in amendment.change_payload.after || {}" :key="field">
            {{ fieldLabel(String(field)) }}: {{ value }}
          </li>
        </ul>
      </article>
    </div>

    <AppBottomSheet :open="editOpen" :title="t('procurements.detail.termsEditTitle')" @close="editOpen = false">
      <form class="edit-form" @submit.prevent="submit">
        <label v-if="canEditDeadline" class="field-group">
          <span>{{ t('suppliers.deadline') }}</span>
          <input v-model="deadlineDate" class="input-field" type="date" />
        </label>
        <label class="field-group">
          <span>{{ t('procurements.create.termsNotes') }}</span>
          <textarea v-model="notes" class="textarea-field" rows="2" />
        </label>
        <label class="field-group">
          <span>{{ t('common.reason') }}</span>
          <textarea
            v-model="reason"
            class="textarea-field"
            rows="2"
            :placeholder="t('procurements.detail.termsReasonPlaceholder')"
          />
        </label>
        <BaseButton
          type="submit"
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="isSubmitting"
        >
          {{ t('common.save') }}
        </BaseButton>
      </form>
    </AppBottomSheet>
  </section>
</template>

<style scoped>
.terms-history {
  display: grid;
  gap: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
}

.terms-head,
.amendments-head,
.terms-summary > div,
.amendment-date {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.terms-head h2 {
  margin-top: 2px;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.terms-head span,
.terms-summary span,
.amendments-head,
.field-group span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.terms-head button {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.terms-summary {
  display: grid;
  gap: var(--space-2);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  padding: var(--space-3);
}

.terms-summary strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  text-align: right;
}

.amendments {
  display: grid;
  gap: var(--space-2);
}

.amendment-row {
  display: grid;
  gap: 6px;
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-2);
}

.amendment-date {
  justify-content: flex-start;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.amendment-row strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.amendment-row ul {
  display: grid;
  gap: 3px;
  padding-left: 16px;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.edit-form,
.field-group {
  display: grid;
  gap: var(--space-2);
}

.edit-form {
  gap: var(--space-3);
}

.input-field,
.textarea-field {
  width: 100%;
  min-height: 42px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  padding: 0 var(--space-3);
  color: var(--color-text-primary);
}

.textarea-field {
  min-height: 72px;
  padding-top: var(--space-2);
  resize: vertical;
}
</style>
