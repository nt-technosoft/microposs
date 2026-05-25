<script setup lang="ts">
const props = defineProps<{ open: boolean; prefix: string }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; confirm: [] }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-overlay" @click.self="emit('update:open', false)">
      <div class="dialog" role="dialog" aria-modal="true">
        <div class="dialog-title">Отозвать ключ?</div>
        <p class="dialog-body">
          Ключ <strong>{{ prefix }}…</strong> будет немедленно деактивирован.
          Все запросы с этим ключом начнут возвращать 401.
        </p>
        <div class="dialog-actions">
          <button class="btn-cancel" type="button" @click="emit('update:open', false)">Отмена</button>
          <button class="btn-revoke" type="button" @click="emit('confirm')">Отозвать</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: color-mix(in srgb, var(--color-bg-primary) 60%, transparent); backdrop-filter: blur(2px); display: grid; place-items: center; z-index: 200; padding: var(--space-4); }
.dialog { background: var(--color-bg-primary); border: 1px solid var(--color-border-default); border-radius: var(--radius-lg); padding: var(--space-5); max-width: 400px; width: 100%; display: grid; gap: var(--space-3); }
.dialog-title { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.dialog-body { margin: 0; font-size: var(--text-sm); color: var(--color-text-secondary); }
.dialog-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
.btn-cancel { padding: var(--space-2) var(--space-4); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); cursor: pointer; }
.btn-revoke { padding: var(--space-2) var(--space-4); border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, var(--color-error) 8%, transparent); color: var(--color-error); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
