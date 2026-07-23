<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  presentation?: 'dialog' | 'side'
}>(), {
  title: '',
  description: '',
  presentation: 'dialog',
})

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()

function updateOpen(open: boolean): void {
  if (!open && props.open) emit('close')
}
</script>

<template>
  <Dialog :open="open" @update:open="updateOpen">
    <DialogContent
      :show-close-button="false"
      class="responsive-overlay__content"
      :data-presentation="presentation"
    >
      <div class="responsive-overlay__handle" aria-hidden="true" />

      <DialogHeader class="responsive-overlay__header">
        <div class="min-w-0">
          <DialogTitle :class="{ 'sr-only': !title }">
            {{ title || t('common.dialog') }}
          </DialogTitle>
          <DialogDescription v-if="description" class="mt-1">
            {{ description }}
          </DialogDescription>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          class="shrink-0"
          :aria-label="t('common.close')"
          @click="emit('close')"
        >
          <X />
        </Button>
      </DialogHeader>

      <div class="responsive-overlay__body">
        <slot />
      </div>

      <footer v-if="$slots.footer" class="responsive-overlay__footer">
        <slot name="footer" />
      </footer>
    </DialogContent>
  </Dialog>
</template>

<style>
.responsive-overlay__content {
  top: auto !important;
  right: 0 !important;
  bottom: 0 !important;
  left: 0 !important;
  display: flex !important;
  width: 100% !important;
  max-width: none !important;
  max-height: 92dvh;
  transform: none !important;
  translate: none !important;
  flex-direction: column;
  gap: 0 !important;
  overflow: hidden;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0 !important;
  padding: 0 !important;
}

.responsive-overlay__handle {
  width: 36px;
  height: 4px;
  flex: none;
  margin: var(--space-3) auto var(--space-2);
  border-radius: var(--radius-full);
  background: var(--neutral-300);
}

.responsive-overlay__header {
  display: flex !important;
  flex: none;
  flex-direction: row !important;
  align-items: flex-start !important;
  justify-content: space-between;
  gap: var(--space-3);
  border-bottom: 1px solid var(--border);
  padding: 0 var(--space-4) var(--space-3);
  text-align: left !important;
}

.responsive-overlay__body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--space-4);
  padding-bottom: calc(var(--space-5) + env(safe-area-inset-bottom, 0px));
}

.responsive-overlay__footer {
  flex: none;
  border-top: 1px solid var(--border);
  padding: var(--space-3) var(--space-4);
  padding-bottom: calc(var(--space-3) + env(safe-area-inset-bottom, 0px));
}

@media (min-width: 768px) {
  .responsive-overlay__content {
    top: 50% !important;
    right: auto !important;
    bottom: auto !important;
    left: 50% !important;
    width: min(680px, calc(100vw - 3rem)) !important;
    max-height: min(820px, calc(100dvh - 3rem));
    transform: translate(-50%, -50%) !important;
    translate: none !important;
    border-radius: var(--radius-xl) !important;
  }

  .responsive-overlay__content[data-presentation="side"] {
    top: var(--space-4) !important;
    right: var(--space-4) !important;
    bottom: var(--space-4) !important;
    left: auto !important;
    width: min(560px, calc(100vw - 3rem)) !important;
    max-height: none;
    transform: none !important;
    translate: none !important;
  }

  .responsive-overlay__handle {
    display: none;
  }

  .responsive-overlay__header {
    padding: var(--space-5);
  }

  .responsive-overlay__body {
    padding: var(--space-5);
  }

  .responsive-overlay__footer {
    padding: var(--space-4) var(--space-5);
  }
}
</style>
