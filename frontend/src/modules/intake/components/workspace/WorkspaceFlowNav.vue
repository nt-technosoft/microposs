<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Lock } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

interface FlowStep {
  key: string
  title: string
  status: 'ready' | 'blocked' | 'complete' | 'locked'
  blocked_reason?: string | null
}

const props = defineProps<{
  steps: FlowStep[]
  currentStep: string | null
  variant: 'rail' | 'stepper'
}>()

const emit = defineEmits<{ navigate: [key: string] }>()

function isCurrent(key: string): boolean {
  return props.currentStep === key
}
</script>

<template>
  <!-- Desktop vertical rail -->
  <nav v-if="variant === 'rail'" class="flex flex-col gap-0.5" aria-label="Этапы прихода">
    <button
      v-for="step in steps"
      :key="step.key"
      type="button"
      :title="step.blocked_reason ?? undefined"
      :aria-current="isCurrent(step.key) ? 'step' : undefined"
      :class="cn(
        'flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-left text-sm transition-colors',
        isCurrent(step.key)
          ? 'bg-primary/10 font-medium text-foreground'
          : 'text-neutral-600 hover:bg-neutral-100 hover:text-foreground',
      )"
      @click="emit('navigate', step.key)"
    >
      <CheckCircle2 v-if="step.status === 'complete'" class="size-4 shrink-0 text-positive" />
      <AlertTriangle v-else-if="step.status === 'blocked'" class="size-4 shrink-0 text-warning" />
      <Lock v-else-if="step.status === 'locked'" class="size-4 shrink-0 text-neutral-400" />
      <span v-else class="grid size-4 shrink-0 place-items-center">
        <span :class="cn('size-2 rounded-full', isCurrent(step.key) ? 'bg-primary' : 'bg-neutral-300')" />
      </span>
      <span class="truncate">{{ step.title }}</span>
    </button>
  </nav>

  <!-- Mobile horizontal stepper -->
  <nav v-else class="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none" aria-label="Этапы прихода">
    <button
      v-for="step in steps"
      :key="step.key"
      type="button"
      :title="step.blocked_reason ?? undefined"
      :aria-current="isCurrent(step.key) ? 'step' : undefined"
      :class="cn(
        'flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors',
        isCurrent(step.key)
          ? 'border-primary bg-primary/10 font-medium text-foreground'
          : 'border-neutral-200 text-neutral-600',
      )"
      @click="emit('navigate', step.key)"
    >
      <CheckCircle2 v-if="step.status === 'complete'" class="size-3.5 text-positive" />
      <AlertTriangle v-else-if="step.status === 'blocked'" class="size-3.5 text-warning" />
      <Lock v-else-if="step.status === 'locked'" class="size-3.5 text-neutral-400" />
      <span v-else :class="cn('size-1.5 rounded-full', isCurrent(step.key) ? 'bg-primary' : 'bg-neutral-300')" />
      <span class="whitespace-nowrap">{{ step.title }}</span>
    </button>
  </nav>
</template>
