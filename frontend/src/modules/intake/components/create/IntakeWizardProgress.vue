<script setup lang="ts">
import { Check } from 'lucide-vue-next'

interface StepItem {
  id: number
  title: string
  hint: string
}

const props = defineProps<{
  steps: StepItem[]
  currentStep: number
  maxReachableStep: number
}>()

const emit = defineEmits<{
  select: [step: number]
}>()

function canOpen(step: number): boolean {
  return step <= props.maxReachableStep
}
</script>

<template>
  <section class="wizard-progress">
    <div class="wizard-head">
      <strong>{{ steps[currentStep - 1]?.title }}</strong>
      <span>{{ steps[currentStep - 1]?.hint }}</span>
    </div>

    <div class="wizard-steps" role="tablist" aria-label="Intake steps">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        class="wizard-step"
        :class="{
          'wizard-step--active': step.id === currentStep,
          'wizard-step--done': step.id < currentStep,
        }"
        :disabled="!canOpen(step.id)"
        @click="emit('select', step.id)"
      >
        <span class="wizard-step-index">
          <Check v-if="step.id < currentStep" :size="14" :stroke-width="2.5" />
          <template v-else>{{ step.id }}</template>
        </span>
        <span class="wizard-step-copy">
          <strong>{{ step.title }}</strong>
          <span>{{ step.hint }}</span>
        </span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.wizard-progress {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-brand-50) 65%, transparent), transparent 72%),
    var(--color-bg-elevated);
}

.wizard-head {
  display: grid;
  gap: 2px;
}

.wizard-head strong {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.wizard-head span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.wizard-steps {
  display: grid;
  gap: var(--space-2);
}

.wizard-step {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
  text-align: left;
}

.wizard-step:disabled {
  opacity: 0.55;
}

.wizard-step--active {
  border-color: var(--color-brand-500);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-brand-500) 12%, transparent);
}

.wizard-step--done {
  background: color-mix(in srgb, var(--color-brand-50) 45%, var(--color-bg-primary));
}

.wizard-step-index {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.wizard-step--active .wizard-step-index,
.wizard-step--done .wizard-step-index {
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.wizard-step-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.wizard-step-copy strong {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.wizard-step-copy span {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.35;
}

@media (min-width: 768px) {
  .wizard-steps {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .wizard-step {
    grid-template-columns: 24px minmax(0, 1fr);
    align-items: flex-start;
  }
}
</style>
