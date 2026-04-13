<script setup lang="ts">
interface Props {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  fullWidth?: boolean
}

withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  fullWidth: false,
})
</script>

<template>
  <button
    class="btn"
    :class="[
      `btn--${variant}`,
      `btn--${size}`,
      { 'btn--full': fullWidth, 'btn--loading': loading },
    ]"
    :disabled="disabled || loading"
  >
    <span v-if="loading" class="btn-spinner" aria-hidden="true" />
    <span class="btn-content" :class="{ invisible: loading }">
      <slot />
    </span>
  </button>
</template>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-weight: var(--font-semibold);
  cursor: pointer;
  position: relative;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}

.btn:active:not(:disabled) {
  transform: scale(0.97);
}

.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Sizes */
.btn--sm {
  height: 36px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}
.btn--md {
  height: 44px;
  padding: 0 var(--space-4);
  font-size: var(--text-base);
}
.btn--lg {
  height: 52px;
  padding: 0 var(--space-5);
  font-size: var(--text-lg);
}

/* Variants */
.btn--primary {
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
}
.btn--primary:hover:not(:disabled) {
  background: var(--color-brand-600);
}

.btn--secondary {
  background: transparent;
  border-color: var(--color-brand-500);
  color: var(--color-brand-500);
}
.btn--secondary:hover:not(:disabled) {
  background: var(--color-brand-50);
}

.btn--ghost {
  background: transparent;
  color: var(--color-brand-500);
}
.btn--ghost:hover:not(:disabled) {
  background: var(--color-brand-50);
}

.btn--danger {
  background: var(--color-error);
  color: var(--color-text-inverse);
}
.btn--danger:hover:not(:disabled) {
  background: #c9302c;
}

/* Full width */
.btn--full {
  width: 100%;
}

/* Loading */
.btn-spinner {
  position: absolute;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.btn-content.invisible {
  visibility: hidden;
}
</style>
