<script setup lang="ts">
import { ref } from 'vue'
import { Copy, Check } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { createCredential, type CreateCredentialResponse } from '@/api/integrations'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; created: [] }>()

const vendor = ref('yespos')
const isSaving = ref(false)
const error = ref<string | null>(null)
const result = ref<CreateCredentialResponse | null>(null)
const copied = ref(false)

async function onGenerate(): Promise<void> {
  isSaving.value = true
  error.value = null
  try {
    result.value = await createCredential(vendor.value)
    emit('created')
  } catch (err: any) {
    error.value = err?.response?.data?.detail ?? 'Ошибка создания ключа'
  } finally {
    isSaving.value = false
  }
}

async function onCopy(): Promise<void> {
  if (!result.value) return
  await navigator.clipboard.writeText(result.value.full_key)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function onClose(): void {
  if (!result.value || window.confirm('Ключ больше не будет показан. Закрыть?')) {
    result.value = null
    error.value = null
    emit('update:open', false)
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Новый ключ интеграции" @close="onClose">
    <div class="sheet-body">
      <template v-if="!result">
        <div class="section-label">Провайдер</div>
        <div class="vendor-chip-row">
          <button class="chip active" type="button">YesPos</button>
        </div>

        <p class="hint">
          Ключ будет показан один раз сразу после создания. Сохраните его в безопасном месте.
        </p>

        <div v-if="error" class="error-text">{{ error }}</div>

        <button
          class="primary-btn"
          type="button"
          :disabled="isSaving"
          @click="onGenerate"
        >
          {{ isSaving ? 'Создание…' : 'Создать ключ' }}
        </button>
      </template>

      <template v-else>
        <div class="warn-banner">
          Сохраните ключ сейчас — больше он показан не будет.
        </div>

        <div class="section-label">Ключ ({{ result.prefix }}…)</div>
        <div class="key-display-row">
          <code class="key-display">{{ result.full_key }}</code>
          <button class="copy-btn" type="button" @click="onCopy">
            <Check v-if="copied" :size="16" :stroke-width="2.5" />
            <Copy v-else :size="16" :stroke-width="2" />
          </button>
        </div>

        <button class="primary-btn" type="button" @click="onClose">Готово</button>
      </template>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.vendor-chip-row { display: flex; gap: var(--space-2); }
.chip { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-full); background: transparent; color: var(--color-text-secondary); font-size: var(--text-sm); cursor: pointer; }
.chip.active { border-color: var(--color-brand-600); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.hint { margin: 0; font-size: var(--text-sm); color: var(--color-text-secondary); }
.error-text { font-size: var(--text-sm); color: var(--color-error); }
.warn-banner { padding: var(--space-3); background: color-mix(in srgb, var(--color-warning) 12%, transparent); border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--color-text-primary); font-weight: var(--font-semibold); }
.key-display-row { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-3); background: var(--color-bg-secondary); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); }
.key-display { flex: 1; font-size: var(--text-xs); font-family: var(--font-mono, monospace); word-break: break-all; color: var(--color-text-primary); }
.copy-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-secondary); cursor: pointer; flex-shrink: 0; }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
