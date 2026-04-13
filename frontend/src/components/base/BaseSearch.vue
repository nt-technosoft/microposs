<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { Search, X } from 'lucide-vue-next'

interface Props {
  modelValue: string
  placeholder?: string
  debounce?: number
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: 'Поиск...',
  debounce: 300,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'search': [value: string]
}>()

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput(event: Event) {
  const target = event.target as HTMLInputElement
  const value = target.value

  emit('update:modelValue', value)

  if (debounceTimer !== null) {
    clearTimeout(debounceTimer)
  }

  debounceTimer = setTimeout(() => {
    emit('search', value)
    debounceTimer = null
  }, props.debounce)
}

function clearInput() {
  emit('update:modelValue', '')
  emit('search', '')

  if (debounceTimer !== null) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
}

onBeforeUnmount(() => {
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer)
  }
})
</script>

<template>
  <div class="search-wrap">
    <Search
      class="search-icon"
      :size="18"
      :stroke-width="1.75"
      aria-hidden="true"
    />

    <input
      class="search-input"
      type="search"
      :value="modelValue"
      :placeholder="placeholder"
      aria-label="Поиск"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      spellcheck="false"
      @input="onInput"
    />

    <button
      v-if="modelValue"
      class="search-clear"
      type="button"
      aria-label="Очистить поиск"
      @click="clearInput"
    >
      <X :size="16" :stroke-width="2" />
    </button>
  </div>
</template>

<style scoped>
.search-wrap {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.search-icon {
  position: absolute;
  left: var(--space-4);
  color: var(--color-text-tertiary);
  pointer-events: none;
  flex-shrink: 0;
}

.search-input {
  width: 100%;
  height: 44px;
  padding: 0 var(--space-10) 0 calc(var(--space-4) + 18px + var(--space-2));
  background: var(--color-bg-secondary);
  border: 1.5px solid transparent;
  border-radius: var(--radius-full);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out);
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}

.search-input::placeholder {
  color: var(--color-text-tertiary);
}

.search-input:focus {
  background: var(--color-bg-elevated);
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 3px var(--color-brand-100);
}

/* Remove browser default search cancel button */
.search-input::-webkit-search-cancel-button,
.search-input::-webkit-search-decoration {
  -webkit-appearance: none;
  appearance: none;
}

.search-clear {
  position: absolute;
  right: var(--space-3);
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  color: var(--color-text-tertiary);
  background: var(--color-bg-sunken);
  transition:
    color var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}

.search-clear:hover {
  color: var(--color-text-primary);
  background: var(--color-border-default);
}

.search-clear:active {
  transform: scale(0.88);
}
</style>
