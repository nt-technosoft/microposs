<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-vue-next'

interface Props {
  message: string
  type?: 'success' | 'error' | 'warning' | 'info'
  duration?: number
}

const props = withDefaults(defineProps<Props>(), {
  type: 'success',
  duration: 3000,
})

const emit = defineEmits<{
  dismiss: []
}>()

const visible = ref(true)

const iconMap = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
} as const

onMounted(() => {
  const timeout = props.type === 'error' ? 5000 : props.duration
  setTimeout(() => {
    visible.value = false
    setTimeout(() => emit('dismiss'), 200)
  }, timeout)
})
</script>

<template>
  <Transition name="toast">
    <div v-if="visible" class="toast" :class="`toast--${type}`" role="alert">
      <component :is="iconMap[type]" :size="18" :stroke-width="1.75" class="toast-icon" />
      <span class="toast-message">{{ message }}</span>
    </div>
  </Transition>
</template>

<style scoped>
.toast {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  box-shadow: var(--shadow-lg);
  max-width: 360px;
  pointer-events: auto;
}

.toast--success {
  background: var(--color-text-primary);
  color: var(--color-text-inverse);
}

.toast--error {
  background: var(--color-error);
  color: white;
}

.toast--warning {
  background: var(--color-warning);
  color: var(--color-text-primary);
}

.toast--info {
  background: var(--color-info);
  color: white;
}

.toast-icon {
  flex-shrink: 0;
}

.toast-enter-active {
  animation: slide-down var(--duration-fast) var(--ease-out);
}

.toast-leave-active {
  animation: fade-out var(--duration-fast) var(--ease-in);
}
</style>
