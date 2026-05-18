<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import InvestmentAgreementQuickForm from '@/modules/intake/components/workspace/InvestmentAgreementQuickForm.vue'
import type { InvestmentAgreementDetail } from '@/api/partnerships'

const router = useRouter()

function handleCreated(agreement: InvestmentAgreementDetail): void {
  router.push({ name: 'agreement-detail', params: { id: agreement.id } })
}
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1>Новый инвестдоговор</h1>
      <span />
    </header>

    <main class="content">
      <InvestmentAgreementQuickForm @created="handleCreated" />
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg-secondary);
}

.topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  min-height: var(--header-height);
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) 40px;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
  backdrop-filter: blur(14px);
}

.topbar h1 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  text-align: center;
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
}

.content {
  max-width: 680px;
  margin: 0 auto;
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-4));
}
</style>
