<script setup lang="ts">
import { ref } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'

const props = defineProps<{
  open: boolean
  totalAmount: string
  currency: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const count = ref('3')
const interval = ref<'MONTHLY' | 'WEEKLY'>('MONTHLY')
const firstDate = ref('')

const canSave = () => parseInt(count.value) > 0 && firstDate.value.length > 0

function onSave(): void {
  if (!canSave()) return
  emit('dispatch', 'GENERATE_INSTALLMENT_SCHEDULE', {
    installments_count: parseInt(count.value),
    first_due_date: firstDate.value,
    interval: interval.value,
  })
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="График рассрочки" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="info-row">
        <span class="info-label">Итого к рассрочке</span>
        <span class="info-value">{{ parseFloat(totalAmount).toLocaleString('ru-RU') }} {{ currency }}</span>
      </div>

      <div class="section-label">Количество платежей</div>
      <input class="input-field" type="number" min="1" max="60" v-model="count" />

      <div class="section-label">Периодичность</div>
      <div class="chips-row">
        <button class="chip" :class="{ active: interval === 'MONTHLY' }" type="button" @click="interval = 'MONTHLY'">Ежемесячно</button>
        <button class="chip" :class="{ active: interval === 'WEEKLY' }" type="button" @click="interval = 'WEEKLY'">Еженедельно</button>
      </div>

      <div class="section-label">Дата первого платежа</div>
      <input class="input-field" type="date" v-model="firstDate" />

      <div v-if="parseInt(count) > 0 && parseFloat(totalAmount) > 0" class="preview-text">
        {{ parseInt(count) }} × {{ Math.round(parseFloat(totalAmount) / parseInt(count)).toLocaleString('ru-RU') }} {{ currency }}
      </div>

      <button class="primary-btn" type="button" :disabled="!canSave()" @click="onSave">
        Сгенерировать график
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.info-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.info-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.info-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.input-field { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.chips-row { display: flex; gap: var(--space-2); }
.chip { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-full); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); cursor: pointer; }
.chip.active { border-color: var(--color-brand-600); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.preview-text { padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
