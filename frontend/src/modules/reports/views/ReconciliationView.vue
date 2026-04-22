<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ArrowLeft, RefreshCcw, AlertTriangle } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

import { fetchLatestReconciliation, type ReconciliationSummary } from '@/api/analytics'
import { toRussianGapCategory, toRussianReconciliationKey } from '@/utils/russianLabels'

const router = useRouter()
const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<ReconciliationSummary | null>(null)

const deltaEntries = computed(() =>
  Object.entries(summary.value?.deltas ?? {}),
)

const hasAnyDelta = computed(() =>
  deltaEntries.value.some(([, value]) => {
    if (typeof value === 'string') {
      return value !== '0' && value !== '0.00'
    }
    return true
  }),
)

function formatDeltaKey(key: string): string {
  return toRussianReconciliationKey(key)
}

function formatGapKey(key: string): string {
  return toRussianGapCategory(key)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    summary.value = await fetchLatestReconciliation()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить сверку'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="reconcile-page">
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="title">Сверка Excel</h1>
      <button class="icon-btn" type="button" aria-label="Обновить" @click="load">
        <RefreshCcw :size="18" :stroke-width="2" />
      </button>
    </header>

    <main class="content">
      <section v-if="loading" class="panel">
        <p class="muted">Загрузка сверки...</p>
      </section>

      <section v-else-if="error" class="panel error">
        <AlertTriangle :size="18" :stroke-width="2" />
        <p>{{ error }}</p>
      </section>

      <template v-else-if="summary">
        <section class="panel">
          <p class="label">Пакет импорта</p>
          <p class="value">#{{ summary.batch_id }}</p>
          <p class="muted">Завершён: {{ new Date(summary.finished_at).toLocaleString('ru-RU') }}</p>
        </section>

        <section class="panel">
          <p class="label">Статус дельт</p>
          <p class="value" :class="{ danger: hasAnyDelta }">
            {{ hasAnyDelta ? 'Есть расхождения' : 'Схождение в пределах ожиданий' }}
          </p>
        </section>

        <section class="panel">
          <h2 class="section-title">Расхождения</h2>
          <div v-if="deltaEntries.length === 0" class="muted">Нет рассчитанных дельт</div>
          <div v-else class="rows">
            <div v-for="[key, value] in deltaEntries" :key="key" class="row">
              <span>{{ formatDeltaKey(key) }}</span>
              <span class="mono">{{ typeof value === 'string' ? value : JSON.stringify(value) }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">Журнал проблем</h2>
          <div v-if="Object.keys(summary.gap_summary || {}).length === 0" class="muted">
            Ошибок в последнем пакете сверки не найдено
          </div>
          <div v-else class="rows">
            <div v-for="(count, key) in summary.gap_summary" :key="key" class="row">
              <span>{{ formatGapKey(key) }}</span>
              <span class="mono">{{ count }}</span>
            </div>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.reconcile-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.title {
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  border-radius: var(--radius-md);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 24px);
}

.panel {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
  display: grid;
  gap: var(--space-2);
}

.panel.error {
  color: var(--color-danger-700);
}

.label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.value {
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.value.danger {
  color: var(--color-danger-700);
}

.section-title {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.rows {
  display: grid;
  gap: var(--space-2);
}

.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.row:last-child {
  border-bottom: none;
}

.mono {
  font-family: var(--font-family-mono);
  color: var(--color-text-primary);
  text-align: right;
}

.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}
</style>
