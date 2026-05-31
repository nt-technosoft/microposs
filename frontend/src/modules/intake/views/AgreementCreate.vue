<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft } from 'lucide-vue-next'
import InvestmentAgreementQuickForm from '@/modules/intake/components/workspace/InvestmentAgreementQuickForm.vue'
import type { InvestmentAgreementDetail } from '@/api/partnerships'
import { Button } from '@/components/ui/button'

const router = useRouter()

function handleCreated(agreement: InvestmentAgreementDetail): void {
  router.push({ name: 'agreement-detail', params: { id: agreement.id } })
}
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
      <div class="mx-auto flex min-h-14 w-full max-w-3xl items-center gap-3 px-4">
        <Button variant="ghost" size="icon" type="button" aria-label="Назад" @click="router.back()">
          <ArrowLeft />
        </Button>
        <div class="min-w-0">
          <p class="text-lg font-semibold text-foreground">Новый инвестдоговор</p>
          <p class="text-xs text-muted-foreground">Фиксация капитала, прибыли и будущего пересчёта</p>
        </div>
      </div>
    </header>

    <section class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-4">
      <InvestmentAgreementQuickForm @created="handleCreated" />
    </section>
  </main>
</template>
