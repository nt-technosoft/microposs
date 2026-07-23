<script setup lang="ts">
import { AlertCircle, PackageOpen, Plus, RotateCcw } from 'lucide-vue-next'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

defineProps<{
  state: 'loading' | 'error' | 'empty'
  error?: string | null
  canCreate?: boolean
}>()

defineEmits<{
  retry: []
  create: []
}>()
</script>

<template>
  <div
    v-if="state === 'loading'"
    class="divide-y divide-neutral-200 overflow-hidden rounded-[14px] border border-neutral-200 bg-surface"
  >
    <div v-for="n in 6" :key="n" class="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3.5 sm:px-5">
      <Skeleton class="size-2.5 rounded-full" />
      <div class="grid gap-1.5">
        <Skeleton class="h-4 w-40" />
        <Skeleton class="h-3 w-56" />
      </div>
      <Skeleton class="h-4 w-20 justify-self-end" />
    </div>
  </div>

  <Alert v-else-if="state === 'error'" variant="destructive" class="rounded-[14px]">
    <AlertCircle class="size-4" />
    <AlertTitle>Не удалось загрузить приходы</AlertTitle>
    <AlertDescription class="flex flex-col gap-3">
      <span>{{ error }}</span>
      <Button variant="outline" class="w-fit" @click="$emit('retry')">
        <RotateCcw data-icon="inline-start" />
        Повторить
      </Button>
    </AlertDescription>
  </Alert>

  <div
    v-else
    class="flex flex-col items-center gap-3 rounded-[14px] border border-dashed border-neutral-200 bg-surface px-6 py-12 text-center"
  >
    <div class="grid size-12 place-items-center rounded-full bg-neutral-100 text-neutral-500">
      <PackageOpen class="size-6" />
    </div>
    <div class="grid gap-1">
      <strong class="text-base font-semibold text-foreground">
        {{ canCreate ? 'Приходов пока нет' : 'Ничего не найдено' }}
      </strong>
      <span class="text-sm text-neutral-500">
        {{ canCreate ? 'Создайте первый приход, чтобы начать товарный цикл.' : 'По выбранному фильтру приходов нет.' }}
      </span>
    </div>
    <Button v-if="canCreate" class="rounded-full" @click="$emit('create')">
      <Plus data-icon="inline-start" />
      Создать приход
    </Button>
  </div>
</template>
