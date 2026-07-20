<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import type { PageChromeStatusTone } from './pageChrome'
import { clearPageChrome, registerPageChrome } from './pageChrome'

const props = withDefaults(defineProps<{
  title: string
  eyebrow?: string
  status?: string
  statusTone?: PageChromeStatusTone
  description?: string
}>(), {
  eyebrow: '',
  status: '',
  statusTone: 'neutral',
  description: '',
})

const owner = Symbol('page-chrome')
const usesAppHeader = useMediaQuery('(min-width: 768px)')
const config = computed(() => ({
  title: props.title,
  eyebrow: props.eyebrow,
  status: props.status,
  statusTone: props.statusTone,
}))

watch(config, (value) => registerPageChrome(owner, value), { immediate: true })
onBeforeUnmount(() => clearPageChrome(owner))
</script>

<template>
  <header class="page-chrome">
    <div class="page-chrome__heading">
      <p v-if="eyebrow" class="page-chrome__eyebrow">{{ eyebrow }}</p>
      <div class="page-chrome__title-row">
        <h1 class="page-chrome__title">{{ title }}</h1>
        <span
          v-if="status"
          class="page-chrome__status"
          :data-tone="statusTone"
        >
          {{ status }}
        </span>
      </div>
      <p v-if="description" class="page-chrome__description">{{ description }}</p>
    </div>

    <Teleport defer to="#app-context-actions" :disabled="!usesAppHeader">
      <div v-if="$slots.primary" class="page-chrome__primary">
        <slot name="primary" />
      </div>
    </Teleport>
  </header>
</template>

<style scoped>
.page-chrome {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4);
}

.page-chrome__heading {
  min-width: 0;
}

.page-chrome__eyebrow {
  margin-bottom: var(--space-1);
  color: var(--color-brand-600);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-chrome__title-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: var(--space-2);
}

.page-chrome__title {
  color: var(--color-text-primary);
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  line-height: var(--leading-tight);
}

.page-chrome__description {
  max-width: 70ch;
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
}

.page-chrome__status {
  flex: none;
  border-radius: var(--radius-full);
  background: var(--neutral-100);
  padding: 0.2rem 0.55rem;
  color: var(--neutral-600);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.page-chrome__status[data-tone="positive"] {
  background: color-mix(in oklch, var(--positive) 12%, transparent);
  color: color-mix(in oklch, var(--positive) 78%, var(--neutral-900));
}

.page-chrome__status[data-tone="warning"] {
  background: color-mix(in oklch, var(--warning) 14%, transparent);
  color: color-mix(in oklch, var(--warning) 72%, var(--neutral-900));
}

.page-chrome__status[data-tone="negative"] {
  background: color-mix(in oklch, var(--negative) 12%, transparent);
  color: color-mix(in oklch, var(--negative) 80%, var(--neutral-900));
}

.page-chrome__primary {
  flex: none;
}

@media (min-width: 768px) {
  .page-chrome {
    padding: 0;
  }

  .page-chrome__heading {
    display: none;
  }
}
</style>
