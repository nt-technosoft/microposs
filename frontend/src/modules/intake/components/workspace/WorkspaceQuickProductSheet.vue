<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { SelectOption } from './types'

defineProps<{
  open: boolean
  name: string
  categoryId: number | null
  basePrice: string
  categoryOptions: SelectOption<number | null>[]
  error: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  updateName: [value: string]
  updateCategoryId: [value: number | null]
  updateBasePrice: [value: string]
  submit: []
}>()
</script>

<template>
  <AppBottomSheet :open="open" title="Новый товар" @close="emit('close')">
    <form class="flex flex-col gap-4" @submit.prevent="emit('submit')">
      <div v-if="error" class="flex items-start gap-2 rounded-[10px] border border-negative/20 bg-negative/5 px-3.5 py-3 text-sm text-negative">
        <AlertCircle class="mt-0.5 size-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <label class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Название</span>
        <Input
          type="text"
          placeholder="Например, Кока-Кола 1.5л"
          :model-value="name"
          @update:model-value="emit('updateName', String($event))"
        />
      </label>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Категория</span>
        <BaseSelect
          :model-value="categoryId"
          :options="categoryOptions"
          title="Категория товара"
          placeholder="Без категории"
          @update:model-value="(value) => emit('updateCategoryId', value === null ? null : Number(value))"
        />
      </div>

      <label class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Базовая цена продажи</span>
        <Input
          type="number"
          min="0"
          inputmode="decimal"
          placeholder="0"
          class="tabular-nums"
          :model-value="basePrice"
          @update:model-value="emit('updateBasePrice', String($event))"
        />
      </label>

      <Button type="submit" class="h-12 w-full text-base" :disabled="saving">
        {{ saving ? 'Создание…' : 'Создать и добавить' }}
      </Button>
    </form>
  </AppBottomSheet>
</template>
