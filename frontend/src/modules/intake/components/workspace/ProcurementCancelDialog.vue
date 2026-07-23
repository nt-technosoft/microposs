<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { AlertTriangle } from 'lucide-vue-next'
import BaseModal from '@/components/base/BaseModal.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [reason: string]
}>()

const reason = ref('')
const reasonError = ref(false)

const canCancel = computed(() =>
  props.procurement.policy.allowed_actions.includes('CANCEL_WORKSPACE'),
)

const blockReason = computed(() => {
  if (canCancel.value) return null
  const hasBatches = props.procurement.documents.receive_batches.length > 0
  if (hasBatches) return 'Нельзя отменить — уже есть приёмки товара.'
  return 'Отмена недоступна для этого прихода.'
})

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  reason.value = ''
  reasonError.value = false
})

function onConfirm(): void {
  if (!reason.value.trim()) { reasonError.value = true; return }
  emit('confirm', reason.value.trim())
  emit('update:open', false)
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="`Отменить приход #${procurement.id}?`"
    size="sm"
    @close="emit('update:open', false)"
  >
    <div class="body">
      <div v-if="blockReason" class="block-state">
        <AlertTriangle :size="20" :stroke-width="2" class="block-icon" />
        <p class="block-text">{{ blockReason }}</p>
      </div>

      <template v-else>
        <div class="warning-box">
          <AlertTriangle :size="16" :stroke-width="2" />
          <span>Это действие необратимо. Приход и все связанные записи будут отменены.</span>
        </div>

        <div class="field-label">Причина <span class="required">*</span></div>
        <textarea
          v-model="reason"
          class="reason-input"
          :class="{ error: reasonError }"
          rows="3"
          placeholder="Укажите причину отмены…"
          @input="reasonError = false"
        />
        <div v-if="reasonError" class="error-text">Причина обязательна</div>
      </template>
    </div>

    <template #footer>
      <button class="btn-cancel" type="button" @click="emit('update:open', false)">Назад</button>
      <button
        v-if="canCancel"
        class="btn-confirm"
        type="button"
        @click="onConfirm"
      >Отменить приход</button>
    </template>
  </BaseModal>
</template>

<style scoped>
.body { display: grid; gap: var(--space-3); }
.block-state { display: flex; align-items: flex-start; gap: var(--space-3); padding: var(--space-4); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.block-icon { flex-shrink: 0; color: #F59E0B; margin-top: 2px; }
.block-text { margin: 0; font-size: var(--text-sm); color: var(--color-text-secondary); }
.warning-box { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-3); background: color-mix(in srgb, var(--color-error) 8%, transparent); border: 1px solid color-mix(in srgb, var(--color-error) 20%, transparent); border-radius: var(--radius-md); font-size: var(--text-sm); color: var(--color-error); }
.field-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.required { color: var(--color-error); }
.reason-input { width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); resize: vertical; font-family: inherit; }
.reason-input.error { border-color: var(--color-error); }
.error-text { font-size: var(--text-xs); color: var(--color-error); }
.btn-cancel { flex: 1; min-height: 44px; border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: transparent; color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.btn-confirm { flex: 1; min-height: 44px; border: 0; border-radius: var(--radius-lg); background: var(--color-error); color: white; font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
