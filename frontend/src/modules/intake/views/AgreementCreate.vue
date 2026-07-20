<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import InvestmentAgreementQuickForm from '@/modules/intake/components/workspace/InvestmentAgreementQuickForm.vue'
import type { InvestmentAgreementDetail } from '@/api/partnerships'
import PageChrome from '@/components/layout/PageChrome.vue'
import PageContainer from '@/components/layout/PageContainer.vue'
import { Button } from '@/components/ui/button'

const router = useRouter()

function handleCreated(agreement: InvestmentAgreementDetail): void {
  router.push({ name: 'agreement-detail', params: { id: agreement.id } })
}
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <PageContainer size="wide" :padded="false" class="py-4 sm:py-6">
      <PageChrome
        title="Новый инвестдоговор"
        description="Фиксация капитала, прибыли и будущего пересчёта."
      >
        <template #primary>
          <Button variant="outline" size="icon" type="button" aria-label="Назад" @click="router.back()">
            <ArrowLeft />
          </Button>
        </template>
      </PageChrome>

      <section class="px-4 sm:px-6 lg:px-8">
        <InvestmentAgreementQuickForm @created="handleCreated" />
      </section>
    </PageContainer>
  </main>
</template>
