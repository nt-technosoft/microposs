<script setup lang="ts">
interface Props {
  title: string
  description?: string
  actionLabel?: string
}

withDefaults(defineProps<Props>(), {
  description: '',
  actionLabel: '',
})

defineEmits<{
  action: []
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-illustration">
      <slot name="illustration">
        <div class="empty-placeholder" />
      </slot>
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p v-if="description" class="empty-description">{{ description }}</p>
    <button
      v-if="actionLabel"
      class="empty-action"
      @click="$emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.empty-illustration {
  margin-bottom: var(--space-6);
}

.empty-placeholder {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  border: 2px dashed var(--color-border-default);
}

.empty-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.empty-description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  max-width: 280px;
  margin-bottom: var(--space-6);
}

.empty-action {
  height: 44px;
  padding: 0 var(--space-5);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
}

.empty-action:hover {
  background: var(--color-brand-600);
}

.empty-action:active {
  transform: scale(0.97);
}
</style>
