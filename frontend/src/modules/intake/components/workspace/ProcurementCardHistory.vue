<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'
import AttachmentList from './AttachmentList.vue'
import AttachmentUploader from './AttachmentUploader.vue'
import { Card } from '@/components/ui/card'
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
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <button
      type="button"
      class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left"
      @click="isExpanded = !isExpanded"
    >
      <span class="text-base font-semibold text-foreground">История и документы</span>
      <div class="flex items-center gap-2">
        <span v-if="attachments.length" class="rounded-full bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">{{ attachments.length }}</span>
        <span v-if="history.length" class="text-xs text-neutral-500">{{ history.length }} событий</span>
        <ChevronUp v-if="isExpanded" class="size-[18px] text-neutral-400" />
        <ChevronDown v-else class="size-[18px] text-neutral-400" />
      </div>
    </button>

    <Transition name="expand">
      <div v-if="isExpanded" class="flex flex-col gap-3 px-4 pb-4">
        <!-- Attachments -->
        <div class="flex flex-col gap-2 border-t border-neutral-200 pt-3">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Документы</span>
          <p v-if="isLoadingAttachments" class="text-sm text-neutral-500">Загрузка…</p>
          <AttachmentList
            v-else
            :attachments="attachments"
            :can-delete="canEdit"
            @view="() => {}"
            @delete="onDeleteAttachment"
          />
        </div>

        <div v-if="canEdit" class="flex flex-col gap-2 border-t border-neutral-200 pt-3">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Прикрепить файл</span>
          <AttachmentUploader
            attachable-type="procurement"
            :attachable-id="procurementId"
            default-kind="INVOICE"
            @uploaded="onUploaded"
          />
        </div>

        <!-- Events timeline -->
        <div v-if="history.length" class="flex flex-col gap-2 border-t border-neutral-200 pt-3">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">События</span>
          <div class="flex flex-col gap-2">
            <div v-for="(event, idx) in visibleHistory" :key="idx" class="flex items-start gap-3">
              <span class="mt-1.5 size-2 shrink-0 rounded-full bg-green-400" />
              <div class="flex flex-col gap-0.5">
                <span class="text-sm text-foreground">{{ event.title }}</span>
                <span class="text-xs text-neutral-500">{{ fmtDate(event.date) }}</span>
              </div>
            </div>
          </div>
          <button
            v-if="history.length > 10 && !showAllHistory"
            type="button"
            class="self-start text-sm font-medium text-green-700"
            @click="showAllHistory = true"
          >
            Показать все ({{ history.length }})
          </button>
        </div>
      </div>
    </Transition>
  </Card>
</template>

<style scoped>
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
