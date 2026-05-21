<script setup lang="ts">
import { ref } from 'vue'
import { Paperclip } from 'lucide-vue-next'
import { uploadAttachment, type Attachment, type AttachableType, type AttachmentKind } from '@/api/attachments'

const KIND_OPTIONS: { key: AttachmentKind; label: string }[] = [
  { key: 'INVOICE', label: 'Накладная' },
  { key: 'RECEIPT_PHOTO', label: 'Фото приёма' },
  { key: 'DOCUMENT', label: 'Документ' },
  { key: 'OTHER', label: 'Другое' },
]

const props = defineProps<{
  attachableType: AttachableType
  attachableId: number
  defaultKind: AttachmentKind
}>()

const emit = defineEmits<{ uploaded: [attachment: Attachment] }>()

const selectedFile = ref<File | null>(null)
const kind = ref<AttachmentKind>(props.defaultKind)
const caption = ref('')
const isUploading = ref(false)
const error = ref<string | null>(null)

function onFileChange(e: Event): void {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  selectedFile.value = f
  error.value = null
}

async function onSubmit(): Promise<void> {
  if (!selectedFile.value) return
  isUploading.value = true
  error.value = null
  try {
    const att = await uploadAttachment({
      attachableType: props.attachableType,
      attachableId: props.attachableId,
      file: selectedFile.value,
      kind: kind.value,
      caption: caption.value || undefined,
    })
    emit('uploaded', att)
    selectedFile.value = null
    caption.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Ошибка загрузки'
  } finally {
    isUploading.value = false
  }
}
</script>

<template>
  <div class="uploader">
    <div class="kind-chips">
      <button
        v-for="opt in KIND_OPTIONS"
        :key="opt.key"
        class="chip"
        :class="{ active: kind === opt.key }"
        type="button"
        @click="kind = opt.key"
      >{{ opt.label }}</button>
    </div>

    <input class="caption-input" type="text" v-model="caption" placeholder="Подпись (необязательно)" />

    <label class="file-label">
      <Paperclip :size="14" :stroke-width="2.5" />
      <span>{{ selectedFile ? selectedFile.name : 'Выбрать файл' }}</span>
      <input class="file-input" type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx" @change="onFileChange" />
    </label>

    <div v-if="error" class="error-text">{{ error }}</div>

    <button
      class="upload-btn"
      type="button"
      :disabled="!selectedFile || isUploading"
      @click="onSubmit"
    >
      {{ isUploading ? 'Загружается…' : 'Прикрепить файл' }}
    </button>
  </div>
</template>

<style scoped>
.uploader { display: grid; gap: var(--space-2); }
.kind-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chip { padding: var(--space-1) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-full); background: transparent; color: var(--color-text-secondary); font-size: var(--text-xs); cursor: pointer; }
.chip.active { border-color: var(--color-brand-600); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.caption-input { width: 100%; min-height: 40px; padding: 0 var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.file-label { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); cursor: pointer; color: var(--color-text-secondary); font-size: var(--text-sm); }
.file-input { display: none; }
.error-text { font-size: var(--text-xs); color: var(--color-error); }
.upload-btn { min-height: 40px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.upload-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
