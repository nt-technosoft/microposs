<script setup lang="ts">
import { watch, onBeforeUnmount, ref, nextTick } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title: string
  size?: 'sm' | 'md' | 'full'
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
})

const emit = defineEmits<{
  close: []
}>()

const modalRef = ref<HTMLElement | null>(null)
const firstFocusable = ref<HTMLElement | null>(null)
const lastFocusable = ref<HTMLElement | null>(null)

const focusableSelectors = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  if (!firstFocusable.value || !lastFocusable.value) return

  if (event.shiftKey) {
    if (document.activeElement === firstFocusable.value) {
      event.preventDefault()
      lastFocusable.value.focus()
    }
  } else {
    if (document.activeElement === lastFocusable.value) {
      event.preventDefault()
      firstFocusable.value.focus()
    }
  }
}

function onKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close')
  }
  trapFocus(event)
}

async function setupFocusTrap() {
  await nextTick()
  if (!modalRef.value) return

  const focusable = Array.from(
    modalRef.value.querySelectorAll<HTMLElement>(focusableSelectors)
  )
  firstFocusable.value = focusable[0] ?? null
  lastFocusable.value = focusable[focusable.length - 1] ?? null
  firstFocusable.value?.focus()
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', onKeyDown)
    setupFocusTrap()
  } else {
    document.body.style.overflow = ''
    document.removeEventListener('keydown', onKeyDown)
  }
})

onBeforeUnmount(() => {
  document.body.style.overflow = ''
  document.removeEventListener('keydown', onKeyDown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="modal-overlay"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @click.self="emit('close')"
      >
        <div
          ref="modalRef"
          class="modal"
          :class="`modal--${size}`"
        >
          <div class="modal-header">
            <h2 class="modal-title">{{ title }}</h2>
            <button
              class="modal-close"
              aria-label="Закрыть"
              @click="emit('close')"
            >
              <X :size="20" :stroke-width="1.75" />
            </button>
          </div>

          <div class="modal-body">
            <slot />
          </div>

          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(26, 23, 20, 0.5);
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: var(--space-4);
}

@media (min-width: 640px) {
  .modal-overlay {
    align-items: center;
  }
}

.modal {
  width: 100%;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl) var(--radius-xl) var(--radius-xl) var(--radius-xl);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  max-height: 90dvh;
  overflow: hidden;
}

/* On mobile, modal slides up from bottom with rounded top corners only */
@media (max-width: 639px) {
  .modal {
    border-radius: var(--radius-xl) var(--radius-xl) var(--radius-md) var(--radius-md);
    max-height: 92dvh;
  }

  .modal-overlay {
    padding: 0;
    align-items: flex-end;
  }
}

.modal--sm { max-width: 400px; }
.modal--md { max-width: 560px; }
.modal--full {
  max-width: 100%;
  height: 100dvh;
  max-height: 100dvh;
  border-radius: 0;
  margin: 0;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-5) var(--space-5) var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.modal-close {
  width: 40px;
  height: 40px;
  min-width: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.modal-close:hover {
  background: var(--color-bg-secondary);
}

.modal-close:active {
  transform: scale(0.92);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5);
  padding-bottom: calc(var(--space-5) + env(safe-area-inset-bottom, 0px));
}

.modal-footer {
  padding: var(--space-4) var(--space-5);
  padding-bottom: calc(var(--space-4) + env(safe-area-inset-bottom, 0px));
  border-top: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

/* Transitions */
.modal-enter-active {
  animation: fade-in var(--duration-fast) var(--ease-out);
}
.modal-leave-active {
  animation: fade-in var(--duration-fast) var(--ease-in) reverse;
}

.modal-enter-active .modal {
  animation: slide-up var(--duration-normal) var(--ease-out);
}
.modal-leave-active .modal {
  animation: slide-up var(--duration-fast) var(--ease-in) reverse;
}

@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes slide-up {
  from { transform: translateY(40px); opacity: 0; }
  to   { transform: translateY(0); opacity: 1; }
}
</style>
