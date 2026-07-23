<script setup lang="ts">
import { Plus, Search } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { Button } from '@/components/ui/button'
import { formatPrice } from '@/utils/currency'
import type { ProductVariant } from '@/types/models'
import type { SelectOption } from './types'

defineProps<{
  open: boolean
  search: string
  category: number | null
  categoryOptions: SelectOption<number | null>[]
  variants: ProductVariant[]
  variantDisplay: (variant: ProductVariant) => string
}>()

const emit = defineEmits<{
  close: []
  updateSearch: [value: string]
  updateCategory: [value: number | null]
  newProduct: []
  select: [variant: ProductVariant]
}>()

function priceOf(v: ProductVariant): number {
  return Number.parseFloat(String(v.price ?? v.effective_price ?? '0')) || 0
}
</script>

<template>
  <AppBottomSheet :open="open" title="Выбор товара" @close="emit('close')">
    <div class="flex flex-col gap-3">
      <div class="flex items-center gap-2">
        <div class="relative flex-1">
          <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            placeholder="Поиск товара"
            :value="search"
            class="h-11 w-full rounded-[10px] border border-neutral-200 bg-transparent pl-9 pr-3 text-sm text-foreground outline-none transition-colors placeholder:text-neutral-400 focus:border-green-400"
            @input="emit('updateSearch', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <Button variant="outline" class="h-11 shrink-0 gap-1.5" @click="emit('newProduct')">
          <Plus class="size-4" />
          Новый
        </Button>
      </div>

      <BaseSelect
        :model-value="category"
        :options="categoryOptions"
        title="Категория"
        placeholder="Все категории"
        @update:model-value="(value) => emit('updateCategory', value === null ? null : Number(value))"
      />

      <div class="flex max-h-[52vh] flex-col gap-2 overflow-auto">
        <button
          v-for="variant in variants"
          :key="variant.id"
          type="button"
          class="flex w-full items-center justify-between gap-3 rounded-[10px] border border-neutral-200 px-3.5 py-3 text-left transition-colors hover:border-green-300 hover:bg-green-50/40"
          @click="emit('select', variant)"
        >
          <span class="min-w-0 truncate text-sm font-medium text-foreground">{{ variantDisplay(variant) }}</span>
          <span class="shrink-0 text-sm font-semibold tabular-nums text-neutral-500">{{ formatPrice(priceOf(variant), 'UZS') }}</span>
        </button>
        <p v-if="!variants.length" class="py-6 text-center text-sm text-neutral-500">Ничего не найдено.</p>
      </div>
    </div>
  </AppBottomSheet>
</template>
