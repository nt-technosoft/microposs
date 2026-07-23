<script setup lang="ts">
import { Trash2, FileText, Image, File } from 'lucide-vue-next'
import type { Attachment } from '@/api/attachments'

const props = defineProps<{ attachments: Attachment[]; canDelete: boolean }>()
const emit = defineEmits<{ view: [id: number]; delete: [id: number] }>()

const KIND_LABELS: Record<string, string> = {
  INVOICE: 'Накладная',
  RECEIPT_PHOTO: 'Фото приёма',
  DOCUMENT: 'Документ',
  OTHER: 'Файл',
}

function isImage(url: string | null): boolean {
  if (!url) return false
  return /\.(jpg|jpeg|png|webp|gif)$/i.test(url)
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

function onView(att: Attachment): void {
  if (att.file) window.open(att.file, '_blank', 'noopener')
  emit('view', att.id)
}

function onDelete(att: Attachment): void {
  if (window.confirm(`Удалить «${att.caption || KIND_LABELS[att.kind] || att.kind}»?`)) {
    emit('delete', att.id)
  }
}
</script>

<template>
  <div v-if="!attachments.length" class="empty-text">Нет прикреплённых файлов.</div>
  <div v-else class="attachment-grid">
    <div v-for="att in attachments" :key="att.id" class="attachment-card" @click="onView(att)">
      <div class="att-icon">
        <Image v-if="isImage(att.file)" :size="20" :stroke-width="1.5" />
        <FileText v-else-if="att.kind === 'INVOICE' || att.kind === 'DOCUMENT'" :size="20" :stroke-width="1.5" />
        <File v-else :size="20" :stroke-width="1.5" />
      </div>
      <div class="att-info">
        <span class="att-label">{{ att.caption || KIND_LABELS[att.kind] || att.kind }}</span>
        <span class="att-date">{{ fmtDate(att.uploaded_at) }}</span>
      </div>
      <button v-if="canDelete" class="att-delete" type="button" @click.stop="onDelete(att)">
        <Trash2 :size="14" :stroke-width="2" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.empty-text { font-size: var(--text-sm); color: var(--color-text-secondary); padding: var(--space-2) 0; }
.attachment-grid { display: grid; gap: var(--space-2); }
.attachment-card { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; }
.att-icon { flex-shrink: 0; color: var(--color-text-tertiary); }
.att-info { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.att-label { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-date { font-size: var(--text-xs); color: var(--color-text-secondary); }
.att-delete { flex-shrink: 0; padding: var(--space-2); border: 0; background: transparent; color: var(--color-text-tertiary); cursor: pointer; border-radius: var(--radius-sm); }
.att-delete:hover { color: var(--color-error); background: color-mix(in srgb, var(--color-error) 8%, transparent); }
</style>
