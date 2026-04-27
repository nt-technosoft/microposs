<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ArrowLeft, RefreshCcw, AlertTriangle, CheckCircle2, AlertCircle, Siren } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

import { fetchLatestReconciliation, type ReconciliationSummary } from '@/api/analytics'
import { formatPrice } from '@/utils/currency'

const router = useRouter()
const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<ReconciliationSummary | null>(null)

const statusLabel = computed(() => {
  if (summary.value?.overall_status === 'ok') return 'Все контрольные проверки сошлись'
  if (summary.value?.overall_status === 'warning') return 'Есть предупреждения по сверке'
  return 'Есть расхождения между контрольными слоями'
})

const statusTone = computed(() => summary.value?.overall_status ?? 'ok')

const orderedChecks = computed(() =>
  [...(summary.value?.checks ?? [])].sort((left, right) => {
    const order = { mismatch: 0, warning: 1, ok: 2 }
    return order[left.status] - order[right.status]
  }),
)

function formatAmount(value: string): string {
  return formatPrice(value)
}

function statusTitle(status: 'ok' | 'warning' | 'mismatch'): string {
  if (status === 'ok') return 'OK'
  if (status === 'warning') return 'Внимание'
  return 'Расхождение'
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
      <h1 class="title">Сверка</h1>
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
        <section class="hero-panel" :class="`hero-panel--${statusTone}`">
          <div class="hero-icon">
            <CheckCircle2 v-if="statusTone === 'ok'" :size="20" :stroke-width="2" />
            <AlertCircle v-else-if="statusTone === 'warning'" :size="20" :stroke-width="2" />
            <Siren v-else :size="20" :stroke-width="2" />
          </div>
          <div class="hero-copy">
            <p class="hero-kicker">Сверка ядра</p>
            <p class="hero-title">{{ statusLabel }}</p>
            <p class="muted">
              Обновлено: {{ new Date(summary.generated_at).toLocaleString('ru-RU') }}
            </p>
          </div>
        </section>

        <section class="summary-grid">
          <article class="summary-tile">
            <span class="label">Проверок</span>
            <strong class="value">{{ summary.totals.total_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Расхождений</span>
            <strong class="value danger">{{ summary.totals.mismatch_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Предупреждений</span>
            <strong class="value warning">{{ summary.totals.warning_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Затронуто записей</span>
            <strong class="value">{{ summary.totals.affected_records }}</strong>
          </article>
        </section>

        <section class="panel">
          <h2 class="section-title">Контрольные метрики</h2>
          <div class="rows">
            <div v-for="item in summary.highlights" :key="item.key" class="row">
              <span>{{ item.label }}</span>
              <span class="mono">
                {{ item.key === 'journal_entries' || item.key === 'sessions' ? item.value : formatAmount(item.value) }}
              </span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">Проверки</h2>
          <div v-if="orderedChecks.length === 0" class="muted">Нет данных для сверки</div>
          <div v-else class="check-list">
            <article
              v-for="check in orderedChecks"
              :key="check.code"
              class="check-card"
              :class="`check-card--${check.status}`"
            >
              <div class="check-head">
                <div>
                  <h3 class="check-title">{{ check.title }}</h3>
                  <p class="check-summary">{{ check.summary }}</p>
                </div>
                <span class="status-pill" :class="`status-pill--${check.status}`">
                  {{ statusTitle(check.status) }}
                </span>
              </div>

              <div class="check-metrics">
                <div class="metric-box">
                  <span class="label">{{ check.actual_label }}</span>
                  <strong class="mono">{{ formatAmount(check.actual_amount) }}</strong>
                </div>
                <div class="metric-box">
                  <span class="label">{{ check.expected_label }}</span>
                  <strong class="mono">{{ formatAmount(check.expected_amount) }}</strong>
                </div>
                <div class="metric-box">
                  <span class="label">Delta</span>
                  <strong class="mono" :class="{ danger: check.delta_amount !== '0.00' }">
                    {{ formatAmount(check.delta_amount) }}
                  </strong>
                </div>
              </div>

              <div class="check-foot">
                <span class="check-count">Затронуто записей: {{ check.mismatch_count }}</span>
                <span v-if="check.sample_refs.length" class="check-samples">
                  {{ check.sample_refs.join(', ') }}
                </span>
              </div>
            </article>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.reconcile-page {
  min-height: 100%;
  background:
    radial-gradient(circle at top, color-mix(in srgb, var(--color-brand-primary) 10%, transparent), transparent 36%),
    var(--color-bg-primary);
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
  background: color-mix(in srgb, var(--color-bg-primary) 92%, white 8%);
  backdrop-filter: blur(10px);
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

.panel,
.hero-panel,
.summary-tile {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-bg-elevated) 92%, white 8%);
  padding: var(--space-4);
}

.panel {
  display: grid;
  gap: var(--space-3);
}

.panel.error {
  color: var(--color-danger-700);
}

.hero-panel {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: var(--space-3);
  align-items: start;
}

.hero-panel--ok {
  border-color: color-mix(in srgb, var(--color-success-500) 40%, var(--color-border-subtle));
}

.hero-panel--warning {
  border-color: color-mix(in srgb, var(--color-warning-500) 40%, var(--color-border-subtle));
}

.hero-panel--mismatch {
  border-color: color-mix(in srgb, var(--color-danger-500) 40%, var(--color-border-subtle));
}

.hero-icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--color-bg-secondary) 82%, white 18%);
  color: var(--color-text-primary);
}

.hero-copy {
  display: grid;
  gap: 4px;
}

.hero-kicker,
.label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.hero-title,
.value {
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.value.danger {
  color: var(--color-danger-700);
}

.value.warning {
  color: var(--color-warning-700);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.summary-tile {
  display: grid;
  gap: 6px;
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

.check-list {
  display: grid;
  gap: var(--space-3);
}

.check-card {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  padding: var(--space-4);
  display: grid;
  gap: var(--space-3);
}

.check-card--ok {
  border-color: color-mix(in srgb, var(--color-success-500) 38%, var(--color-border-subtle));
}

.check-card--warning {
  border-color: color-mix(in srgb, var(--color-warning-500) 38%, var(--color-border-subtle));
}

.check-card--mismatch {
  border-color: color-mix(in srgb, var(--color-danger-500) 42%, var(--color-border-subtle));
}

.check-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.check-title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.check-summary {
  margin: 6px 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 76px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.status-pill--ok {
  background: color-mix(in srgb, var(--color-success-500) 14%, transparent);
  color: var(--color-success-700);
}

.status-pill--warning {
  background: color-mix(in srgb, var(--color-warning-500) 16%, transparent);
  color: var(--color-warning-700);
}

.status-pill--mismatch {
  background: color-mix(in srgb, var(--color-danger-500) 14%, transparent);
  color: var(--color-danger-700);
}

.check-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.metric-box {
  display: grid;
  gap: 6px;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-bg-secondary) 82%, white 18%);
}

.check-foot {
  display: grid;
  gap: 6px;
}

.check-count {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
}

.check-samples,
.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.mono {
  font-family: var(--font-family-mono);
  color: var(--color-text-primary);
  text-align: right;
}

@media (max-width: 640px) {
  .summary-grid,
  .check-metrics {
    grid-template-columns: 1fr;
  }

  .check-head {
    flex-direction: column;
  }

  .mono {
    text-align: left;
  }
}
</style>
