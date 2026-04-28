<script setup lang="ts">
import { useRouter } from 'vue-router'

type SectionMode = 'procurements' | 'agreements'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  eyebrow?: string
  activeMode: SectionMode
  primaryLabel?: string
  primaryAriaLabel?: string
}>(), {
  subtitle: '',
  eyebrow: '',
  primaryLabel: '',
  primaryAriaLabel: '',
})

const emit = defineEmits<{
  primary: []
}>()

const router = useRouter()

function openMode(mode: SectionMode): void {
  if (mode === props.activeMode) return
  router.push({ name: mode === 'procurements' ? 'procurement-list' : 'agreement-list' })
}
</script>

<template>
  <section class="section-shell">
    <header class="section-header">
      <div class="title-block" :class="{ 'title-block--compact': !eyebrow && !subtitle }">
        <span v-if="eyebrow" class="eyebrow">{{ eyebrow }}</span>
        <h1 class="title">{{ title }}</h1>
        <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
      </div>

      <div class="header-actions">
        <slot name="header-actions" />
        <button
          v-if="primaryLabel"
          class="primary-btn"
          type="button"
          :aria-label="primaryAriaLabel || primaryLabel"
          @click="emit('primary')"
        >
          {{ primaryLabel }}
        </button>
      </div>
    </header>

    <nav class="mode-switch" aria-label="Переключение между приходами и договорами">
      <button
        class="mode-switch-btn"
        :class="{ active: activeMode === 'procurements' }"
        type="button"
        @click="openMode('procurements')"
      >
        Приходы
      </button>
      <button
        class="mode-switch-btn"
        :class="{ active: activeMode === 'agreements' }"
        type="button"
        @click="openMode('agreements')"
      >
        Договоры
      </button>
    </nav>

    <div v-if="$slots.summary" class="summary-slot">
      <slot name="summary" />
    </div>

    <main class="body-slot">
      <slot />
    </main>
  </section>
</template>

<style scoped>
.section-shell {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--color-bg-primary);
}

.section-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-primary) 88%, transparent);
  backdrop-filter: blur(14px);
}

.title-block {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.title-block--compact {
  gap: 0;
}

.eyebrow {
  font-size: var(--text-2xs);
  font-weight: var(--font-semibold);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}

.title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  line-height: var(--leading-tight);
  color: var(--color-text-primary);
}

.subtitle {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  color: var(--color-text-secondary);
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
  flex-shrink: 0;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.primary-btn:hover {
  background: var(--color-brand-600);
}

.primary-btn:active {
  transform: scale(0.97);
}

.mode-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  margin: var(--space-2) var(--space-4) 0;
  padding: 4px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.mode-switch-btn {
  min-height: 38px;
  border-radius: calc(var(--radius-lg) - 4px);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.mode-switch-btn.active {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  box-shadow: var(--shadow-xs);
}

.summary-slot {
  padding: var(--space-2) var(--space-4) 0;
}

.body-slot {
  flex: 1;
  padding: var(--space-2) var(--space-4) calc(var(--bottom-nav-height) + var(--space-4));
}
</style>
