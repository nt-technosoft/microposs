<script setup lang="ts">
import { ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
})

const emit = defineEmits<{
  close: []
}>()

const sheetRef = ref<HTMLElement | null>(null)

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})

function onBackdropClick() {
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="sheet-overlay" @click.self="onBackdropClick">
        <div ref="sheetRef" class="sheet" role="dialog" aria-modal="true">
          <div class="sheet-handle" aria-hidden="true" />

          <div v-if="title" class="sheet-header">
            <h3 class="sheet-title">{{ title }}</h3>
            <button
              class="sheet-close"
              aria-label="Закрыть"
              @click="emit('close')"
            >
              <X :size="20" :stroke-width="1.75" />
            </button>
          </div>

          <div class="sheet-body">
            <slot />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: var(--z-modal);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet {
  width: 100%;
  max-width: 540px;
  max-height: 85vh;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  border-radius: var(--radius-full);
  background: var(--color-text-tertiary);
  margin: var(--space-3) auto var(--space-2);
  opacity: 0.5;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-5) var(--space-3);
}

.sheet-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.sheet-close {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out);
}

.sheet-close:hover {
  background: var(--color-bg-secondary);
}

.sheet-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-5) var(--space-6);
  padding-bottom: calc(var(--space-6) + env(safe-area-inset-bottom, 0px));
}

/* Transitions */
.sheet-enter-active .sheet {
  animation: slide-up var(--duration-normal) var(--ease-out);
}
.sheet-leave-active .sheet {
  animation: slide-up var(--duration-fast) var(--ease-in) reverse;
}

.sheet-enter-active {
  animation: fade-in var(--duration-fast) var(--ease-out);
}
.sheet-leave-active {
  animation: fade-out var(--duration-fast) var(--ease-in);
}
</style>
