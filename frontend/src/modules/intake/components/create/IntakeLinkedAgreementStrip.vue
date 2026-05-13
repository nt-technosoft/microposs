<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  agreementId: number
}>()

const router = useRouter()
const { t } = useI18n()
</script>

<template>
  <section class="linked-agreement-strip">
    <div>
      <span>{{ t('procurements.create.capitalSource') }}</span>
      <strong>{{ t('procurements.agreementTitle', { id: props.agreementId }) }}</strong>
    </div>
    <button type="button" @click="router.push({ name: 'agreement-detail', params: { id: props.agreementId } })">
      {{ t('common.details') }}
    </button>
  </section>
</template>

<style scoped>
.linked-agreement-strip { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-brand-50); }
.linked-agreement-strip div { min-width:0; display:grid; gap: 2px; }
.linked-agreement-strip span { color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-medium); }
.linked-agreement-strip strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.linked-agreement-strip button { flex:0 0 auto; min-height:34px; padding:0 var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); }
</style>
