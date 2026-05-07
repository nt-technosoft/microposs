<script setup lang="ts">
import { useI18n } from 'vue-i18n'

interface Props {
  show: boolean
  message?: string
}

withDefaults(defineProps<Props>(), {
  message: '',
})

const { t } = useI18n()
</script>

<template>
  <Teleport to="body">
    <Transition name="overlay">
      <div
        v-if="show"
        class="overlay"
        role="status"
        aria-live="polite"
        :aria-label="message || t('common.loading')"
      >
        <div class="overlay-content">
          <div class="spinner" aria-hidden="true">
            <div class="spinner-ring" />
          </div>
          <p class="overlay-message">{{ message || t('common.loading') }}</p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-overlay);
  background: rgba(250, 250, 248, 0.85);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
}

/* Spinner */
.spinner {
  width: 48px;
  height: 48px;
  position: relative;
}

.spinner-ring {
  width: 100%;
  height: 100%;
  border-radius: var(--radius-full);
  border: 3px solid var(--color-brand-100);
  border-top-color: var(--color-brand-500);
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.overlay-message {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

/* Transitions */
.overlay-enter-active {
  animation: fade-overlay var(--duration-normal) var(--ease-out);
}

.overlay-leave-active {
  animation: fade-overlay var(--duration-fast) var(--ease-in) reverse;
}

@keyframes fade-overlay {
  from { opacity: 0; }
  to   { opacity: 1; }
}
</style>
