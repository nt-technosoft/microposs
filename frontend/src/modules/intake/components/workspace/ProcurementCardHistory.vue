<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import AttachmentList from './AttachmentList.vue'
import AttachmentUploader from './AttachmentUploader.vue'
import { fetchAttachments, deleteAttachment, type Attachment } from '@/api/attachments'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()

const isExpanded = ref(false)
const attachments = ref<Attachment[]>([])
const isLoadingAttachments = ref(false)
const showAllHistory = ref(false)

const history = computed(() => props.procurement.history ?? [])
const visibleHistory = computed(() => showAllHistory.value ? history.value : history.value.slice(0, 10))
const canEdit = computed(() => props.procurement.status === 'OPEN')
const procurementId = computed(() => props.procurement.documents.procurement.id)

async function loadAttachments(): Promise<void> {
  isLoadingAttachments.value = true
  try {
    attachments.value = await fetchAttachments('procurement', procurementId.value)
  } catch {
    attachments.value = []
  } finally {
    isLoadingAttachments.value = false
  }
}

watch(isExpanded, (expanded) => {
  if (expanded && !attachments.value.length && !isLoadingAttachments.value) {
    loadAttachments()
  }
})

function onUploaded(att: Attachment): void {
  attachments.value = [...attachments.value, att]
}

async function onDeleteAttachment(id: number): Promise<void> {
  try {
    await deleteAttachment(id)
    attachments.value = attachments.value.filter((a) => a.id !== id)
  } catch { /* toast shown by global handler */ }
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

<template>
  <div class="history-card">
    <button class="card-header" type="button" @click="isExpanded = !isExpanded">
      <span class="card-title">История и документы</span>
      <div class="header-right">
        <span v-if="attachments.length" class="att-count">{{ attachments.length }}</span>
        <span v-if="history.length" class="hist-count">{{ history.length }} событий</span>
        <ChevronUp v-if="isExpanded" :size="18" :stroke-width="2" class="chevron" />
        <ChevronDown v-else :size="18" :stroke-width="2" class="chevron" />
      </div>
    </button>

    <Transition name="expand">
      <div v-if="isExpanded" class="expanded-body">
        <!-- Attachments section -->
        <div class="section">
          <div class="section-label">Документы</div>
          <div v-if="isLoadingAttachments" class="loading-text">Загрузка…</div>
          <AttachmentList
            v-else
            :attachments="attachments"
            :can-delete="canEdit"
            @view="() => {}"
            @delete="onDeleteAttachment"
          />
        </div>

        <div v-if="canEdit" class="section">
          <div class="section-label">Прикрепить файл</div>
          <AttachmentUploader
            attachable-type="procurement"
            :attachable-id="procurementId"
            default-kind="INVOICE"
            @uploaded="onUploaded"
          />
        </div>

        <!-- Events timeline -->
        <div v-if="history.length" class="section">
          <div class="section-label">События</div>
          <div class="timeline">
            <div v-for="(event, idx) in visibleHistory" :key="idx" class="timeline-row">
              <div class="tl-dot" />
              <div class="tl-content">
                <span class="tl-title">{{ event.title }}</span>
                <span class="tl-date">{{ fmtDate(event.date) }}</span>
              </div>
            </div>
          </div>
          <button
            v-if="history.length > 10 && !showAllHistory"
            class="show-all-btn"
            type="button"
            @click="showAllHistory = true"
          >
            Показать все ({{ history.length }})
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.history-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); }
.card-header { display: flex; align-items: center; justify-content: space-between; background: transparent; border: 0; padding: 0; cursor: pointer; text-align: left; width: 100%; min-height: 44px; }
.card-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.header-right { display: flex; align-items: center; gap: var(--space-2); }
.att-count { font-size: var(--text-xs); font-weight: var(--font-semibold); padding: 2px 6px; background: var(--color-brand-100); color: var(--color-brand-700); border-radius: var(--radius-full); }
.hist-count { font-size: var(--text-xs); color: var(--color-text-secondary); }
.chevron { color: var(--color-text-tertiary); }
.expanded-body { display: grid; gap: var(--space-3); }
.section { display: grid; gap: var(--space-2); padding-top: var(--space-2); border-top: 1px solid var(--color-border-subtle); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.loading-text { font-size: var(--text-sm); color: var(--color-text-secondary); }
.timeline { display: grid; gap: var(--space-2); }
.timeline-row { display: flex; align-items: flex-start; gap: var(--space-3); }
.tl-dot { flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%; background: var(--color-brand-400); margin-top: 4px; }
.tl-content { display: flex; flex-direction: column; gap: 2px; }
.tl-title { font-size: var(--text-sm); color: var(--color-text-primary); }
.tl-date { font-size: var(--text-xs); color: var(--color-text-secondary); }
.show-all-btn { background: transparent; border: 0; color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; padding: 0; text-align: left; }

.expand-enter-active { animation: expand-in 150ms var(--ease-out); }
.expand-leave-active { animation: expand-in 100ms var(--ease-in) reverse; }

@keyframes expand-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .expand-enter-active, .expand-leave-active { animation: none; }
}
</style>
