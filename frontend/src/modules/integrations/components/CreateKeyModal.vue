<script setup lang="ts">
import { ref } from 'vue'
import { Copy, Check, ShieldAlert } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useToast } from '@/composables/useToast'
import { copyToClipboard } from '@/utils/clipboard'
import { createCredential, type CreateCredentialResponse } from '@/api/integrations'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; created: [] }>()

const toast = useToast()

const vendor = ref('yespos')
const isSaving = ref(false)
const error = ref<string | null>(null)
const result = ref<CreateCredentialResponse | null>(null)
const copied = ref(false)

async function copyKey(): Promise<void> {
  if (!result.value) return
  const ok = await copyToClipboard(result.value.full_key)
  if (ok) {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
    toast.success('Ключ скопирован в буфер обмена')
  } else {
    toast.error('Не удалось скопировать. Скопируйте ключ вручную.')
  }
}

async function onGenerate(): Promise<void> {
  isSaving.value = true
  error.value = null
  try {
    result.value = await createCredential(vendor.value)
    emit('created')
    // The key is shown only once — copy it immediately so it isn't lost.
    await copyKey()
  } catch (err: any) {
    error.value = err?.response?.data?.detail ?? 'Ошибка создания ключа'
  } finally {
    isSaving.value = false
  }
}

function onClose(): void {
  if (!result.value || window.confirm('Ключ больше не будет показан. Закрыть?')) {
    result.value = null
    error.value = null
    copied.value = false
    emit('update:open', false)
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Новый ключ интеграции" @close="onClose">
    <div class="flex flex-col gap-4">
      <template v-if="!result">
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Провайдер</span>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-full border border-primary bg-primary/5 px-3.5 py-1.5 text-sm font-medium text-foreground"
            >YesPos</button>
          </div>
        </div>

        <p class="text-sm leading-relaxed text-neutral-500">
          Ключ будет показан один раз сразу после создания и автоматически скопирован в буфер обмена. Сохраните его в безопасном месте.
        </p>

        <p v-if="error" class="text-sm text-negative">{{ error }}</p>

        <Button class="h-12 w-full text-base" :disabled="isSaving" @click="onGenerate">
          {{ isSaving ? 'Создание…' : 'Создать ключ' }}
        </Button>
      </template>

      <template v-else>
        <div class="flex items-start gap-2.5 rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-3">
          <ShieldAlert class="mt-0.5 size-4 shrink-0 text-warning" />
          <span class="text-sm font-medium text-foreground">Скопировано в буфер. Сохраните ключ сейчас — больше он показан не будет.</span>
        </div>

        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Ключ ({{ result.prefix }}…)</span>
          <div class="flex items-center gap-2 rounded-[10px] border border-neutral-200 bg-neutral-50 p-3">
            <code class="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{{ result.full_key }}</code>
            <button
              type="button"
              :class="cn(
                'flex size-9 shrink-0 items-center justify-center rounded-[8px] border transition-colors',
                copied ? 'border-positive/40 bg-positive/10 text-positive' : 'border-neutral-200 bg-surface text-neutral-500 hover:bg-neutral-100',
              )"
              :aria-label="copied ? 'Скопировано' : 'Скопировать'"
              @click="copyKey"
            >
              <Check v-if="copied" :size="16" :stroke-width="2.5" />
              <Copy v-else :size="16" :stroke-width="2" />
            </button>
          </div>
        </div>

        <Button variant="outline" class="h-11 w-full gap-2" @click="copyKey">
          <Check v-if="copied" :size="16" :stroke-width="2.5" />
          <Copy v-else :size="16" :stroke-width="2" />
          {{ copied ? 'Скопировано' : 'Скопировать ещё раз' }}
        </Button>

        <Button class="h-12 w-full text-base" @click="onClose">Готово</Button>
      </template>
    </div>
  </AppBottomSheet>
</template>
