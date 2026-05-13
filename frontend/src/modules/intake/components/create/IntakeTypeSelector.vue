<script setup lang="ts">
import type { Component } from 'vue'
import type { ProcurementType } from '@/types/enums'
import { useI18n } from 'vue-i18n'

interface TypeCard {
  type: ProcurementType
  labelKey: string
  descriptionKey: string
  icon: Component
  disabled?: boolean
}

defineProps<{
  cards: TypeCard[]
  selectedType: ProcurementType
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [type: ProcurementType]
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <h2 class="section-title">{{ t('procurements.create.procurementType') }}</h2>
    <div class="type-grid">
      <button
        v-for="card in cards"
        :key="card.type"
        class="type-card"
        :class="{ selected: selectedType === card.type }"
        :disabled="disabled"
        @click="emit('select', card.type)"
      >
        <div class="type-card-icon">
          <component :is="card.icon" :size="22" :stroke-width="1.75" />
        </div>
        <span class="type-card-label">{{ t(card.labelKey) }}</span>
        <span class="type-card-desc">{{ t(card.descriptionKey) }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.type-grid { display:grid; gap: var(--space-3); }
.type-card { display:grid; gap: var(--space-2); text-align:left; padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.type-card.selected { border-color: var(--color-brand-500); box-shadow: 0 0 0 2px rgba(27,138,111,0.12); }
.type-card.disabled, .type-card:disabled { opacity: 0.55; }
.type-card-label { font-weight: var(--font-semibold); }
.type-card-desc { color: var(--color-text-secondary); font-size: var(--text-sm); }
</style>
