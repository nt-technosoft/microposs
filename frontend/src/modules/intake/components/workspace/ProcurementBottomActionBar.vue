<script setup lang="ts">
import { computed } from 'vue'

const ACTION_LABELS_RU: Record<string, string> = {
  UPDATE_SOURCE: 'Выбрать поставщика',
  UPDATE_ITEMS: 'Добавить товары',
  UPDATE_EXPENSES: 'Добавить расходы',
  UPDATE_SETTLEMENT: 'Выбрать условия',
  CREATE_INVESTMENT_AGREEMENT: 'Создать договор',
  LINK_INVESTMENT_AGREEMENT: 'Привязать договор',
  RECORD_CAPITAL_CONTRIBUTION: 'Внести капитал',
  ALLOCATE_CAPITAL: 'Распределить капитал',
  PAY_COSTS: 'Оплатить',
  PAY_SUPPLIER_PAYABLE: 'Оплатить поставщика',
  GENERATE_INSTALLMENT_SCHEDULE: 'Сгенерировать график',
  RECEIVE_BATCH: 'Принять товар',
  AMEND_SETTLEMENT: 'Изменить условия',
  AMEND_ITEMS: 'Изменить товары',
  AMEND_EXPENSES: 'Изменить расходы',
  RETURN_CONSIGNMENT: 'Вернуть консигнацию',
  CLOSE_WORKSPACE: 'Закрыть приход',
  CANCEL_WORKSPACE: 'Отменить приход',
}

const props = defineProps<{
  actionKey: string | null
  actionLabel: string | null
  reason: string | null
}>()

const emit = defineEmits<{
  click: [actionKey: string]
}>()

const displayLabel = computed(() => {
  if (!props.actionLabel) return 'Сохранить черновик'
  return ACTION_LABELS_RU[props.actionLabel] ?? props.actionLabel
})

function handleClick(): void {
  if (props.actionKey) {
    emit('click', props.actionKey)
  }
}
</script>

<template>
  <footer class="action-bar">
    <div class="action-bar-inner">
      <button
        class="action-btn"
        type="button"
        :disabled="!actionKey"
        @click="handleClick"
      >
        {{ displayLabel }}
      </button>
      <p v-if="reason" class="action-hint">{{ reason }}</p>
    </div>
  </footer>
</template>

<style scoped>
.action-bar {
  position: sticky;
  bottom: 0;
  background: var(--color-bg-primary);
  border-top: 1px solid var(--color-border-subtle);
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
}

.action-bar-inner {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}

.action-btn {
  width: 100%;
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--color-brand-600);
  color: white;
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
  cursor: pointer;
}

.action-btn:disabled {
  opacity: 0.55;
  cursor: default;
}

.action-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-align: center;
  line-height: 1.4;
}
</style>
