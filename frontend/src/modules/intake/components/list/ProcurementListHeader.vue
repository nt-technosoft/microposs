<script setup lang="ts">
import { Handshake, Plus, RefreshCcw } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'

defineProps<{
  isLoading: boolean
}>()

defineEmits<{
  refresh: []
  create: []
  createPartnership: []
}>()
</script>

<template>
  <header class="sticky top-0 z-[var(--z-sticky)] border-b border-border/70 bg-background/92 backdrop-blur supports-[backdrop-filter]:bg-background/80">
    <div class="mx-auto flex w-full max-w-[var(--max-content-width)] items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
      <div class="min-w-0 flex-1">
        <h1 class="truncate text-xl font-semibold leading-tight text-foreground">
          Приходы
        </h1>
      </div>

      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          :disabled="isLoading"
          aria-label="Обновить приходы"
          class="rounded-full bg-card"
          @click="$emit('refresh')"
        >
          <RefreshCcw data-icon="inline-start" :class="{ 'animate-spin': isLoading }" />
        </Button>
        <Button
          variant="outline"
          class="hidden rounded-full bg-card sm:inline-flex"
          @click="$emit('createPartnership')"
        >
          <Handshake data-icon="inline-start" />
          Партнёрский
        </Button>
        <Button class="rounded-full shadow-sm" @click="$emit('create')">
          <Plus data-icon="inline-start" />
          Новый
        </Button>
      </div>
    </div>
  </header>
</template>
