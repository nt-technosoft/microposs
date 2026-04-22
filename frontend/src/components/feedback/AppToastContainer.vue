<script setup lang="ts">
import { useToastState } from '@/composables/useToast'
import AppToast from './AppToast.vue'

const { toasts, removeToast } = useToastState()
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite" aria-atomic="false">
      <TransitionGroup name="toast-list" tag="div" class="toast-list">
        <AppToast
          v-for="toast in toasts"
          :key="toast.id"
          :message="toast.message"
          :type="toast.type"
          :duration="toast.duration"
          @dismiss="removeToast(toast.id)"
        />
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: var(--space-4);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-toast);
  width: 100%;
  max-width: 400px;
  padding: 0 var(--space-4);
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.toast-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
}

/* TransitionGroup animations */
.toast-list-enter-active {
  animation: toast-enter var(--duration-fast) var(--ease-out);
}

.toast-list-leave-active {
  animation: toast-enter var(--duration-fast) var(--ease-in) reverse;
  position: absolute;
}

.toast-list-move {
  transition: transform var(--duration-normal) var(--ease-out);
}

@keyframes toast-enter {
  from {
    opacity: 0;
    transform: translateY(-12px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
</style>
