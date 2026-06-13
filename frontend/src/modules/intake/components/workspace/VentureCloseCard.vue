<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckBig, LockKeyhole, Flag } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { ClosePreview } from '@/api/partnerships'

// E17 5b: contextual "next action" for closing a venture / agreement. The card
// only appears once the backend says wind-down is reached (show_close) or the
// entity is already CLOSED. Gates live on the backend — this only displays them.
const props = defineProps<{
  entityLabel: string // 'приход' | 'договор'
  preview: ClosePreview | null
  busy?: boolean
}>()

const emit = defineEmits<{ close: [] }>()

const isClosed = computed(() => props.preview?.status === 'CLOSED')
const visible = computed(() => isClosed.value || Boolean(props.preview?.show_close))
const closeable = computed(() => Boolean(props.preview?.closeable))
const reasons = computed(() => props.preview?.blocking_reasons ?? [])
const closedTitle = computed(
  () => props.entityLabel.charAt(0).toUpperCase() + props.entityLabel.slice(1) + ' закрыт',
)
</script>

<template>
  <Card v-if="visible" class="rounded-2xl bg-background">
    <template v-if="isClosed">
      <CardContent class="flex items-center gap-3 py-4">
        <CircleCheckBig class="size-5 shrink-0 text-green-700" aria-hidden="true" />
        <div>
          <p class="font-medium text-foreground">{{ closedTitle }}</p>
          <p class="mt-0.5 text-xs text-muted-foreground">Итоги зафиксированы, операции закрыты.</p>
        </div>
      </CardContent>
    </template>

    <template v-else>
      <CardHeader>
        <div class="flex items-start justify-between gap-3">
          <div>
            <CardTitle class="text-base">Закрыть {{ entityLabel }}</CardTitle>
            <CardDescription class="mt-1">
              {{ closeable
                ? 'Всё сведено — можно закрывать.'
                : 'Чтобы закрыть, осталось завершить шаги ниже.' }}
            </CardDescription>
          </div>
          <Flag class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        </div>
      </CardHeader>
      <CardContent class="flex flex-col gap-3">
        <ul v-if="!closeable && reasons.length" class="flex flex-col gap-2">
          <li
            v-for="reason in reasons"
            :key="reason"
            class="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning"
          >
            <LockKeyhole class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{{ reason }}</span>
          </li>
        </ul>

        <Button
          type="button"
          class="w-full sm:w-auto"
          :disabled="!closeable || busy"
          @click="emit('close')"
        >
          <CircleCheckBig data-icon="inline-start" />
          Закрыть {{ entityLabel }}
        </Button>
      </CardContent>
    </template>
  </Card>
</template>
