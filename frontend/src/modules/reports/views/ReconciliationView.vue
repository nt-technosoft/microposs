<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ArrowLeft, RefreshCcw, AlertTriangle, CheckCircle2, AlertCircle, Siren, ChevronDown } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import { fetchLatestReconciliation, type ReconciliationSummary } from '@/api/analytics'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'

const router = useRouter()
const { t, locale } = useI18n()
const loading = ref(false)
const error = ref<string | null>(null)
const summary = ref<ReconciliationSummary | null>(null)
const expandedCheckCode = ref<string | null>(null)

const statusLabel = computed(() => {
  if (summary.value?.overall_status === 'ok') return t('reports.reconcile.okTitle')
  if (summary.value?.overall_status === 'warning') return t('reports.reconcile.warningTitle')
  return t('reports.reconcile.mismatchTitle')
})

const statusTone = computed(() => summary.value?.overall_status ?? 'ok')

const statusHint = computed(() => {
  if (summary.value?.overall_status === 'ok') return t('reports.reconcile.okHint')
  if (summary.value?.overall_status === 'warning') return t('reports.reconcile.warningHint')
  return t('reports.reconcile.mismatchHint')
})

const orderedChecks = computed(() =>
  [...(summary.value?.checks ?? [])].sort((left, right) => {
    const order = { mismatch: 0, warning: 1, ok: 2 }
    return order[left.status] - order[right.status]
  }),
)

const issueChecks = computed(() => orderedChecks.value.filter((check) => check.status !== 'ok'))

const checkCopy = computed<Record<string, { title: string; summary: string; actual: string; expected: string }>>(() => ({
  sales_settlement: {
    title: t('reports.reconcile.salesSettlementTitle'),
    summary: t('reports.reconcile.salesSettlementSummary'),
    actual: t('reports.reconcile.salesSettlementActual'),
    expected: t('reports.reconcile.salesSettlementExpected'),
  },
  receivable_ledger: {
    title: t('reports.reconcile.receivableLedgerTitle'),
    summary: t('reports.reconcile.receivableLedgerSummary'),
    actual: t('reports.reconcile.receivableLedgerActual'),
    expected: t('reports.reconcile.receivableLedgerExpected'),
  },
  cash_accounts_vs_entries: {
    title: t('reports.reconcile.cashAccountsTitle'),
    summary: t('reports.reconcile.cashAccountsSummary'),
    actual: t('reports.reconcile.cashAccountsActual'),
    expected: t('reports.reconcile.cashAccountsExpected'),
  },
  closed_sessions_expected_cash: {
    title: t('reports.reconcile.sessionExpectedTitle'),
    summary: t('reports.reconcile.sessionExpectedSummary'),
    actual: t('reports.reconcile.saved'),
    expected: t('reports.reconcile.calculation'),
  },
  closed_sessions_cash_difference: {
    title: t('reports.reconcile.sessionDifferenceTitle'),
    summary: t('reports.reconcile.sessionDifferenceSummary'),
    actual: t('reports.reconcile.saved'),
    expected: t('reports.reconcile.calculation'),
  },
  closed_sessions_nonzero_difference: {
    title: t('reports.reconcile.nonzeroDifferenceTitle'),
    summary: t('reports.reconcile.nonzeroDifferenceSummary'),
    actual: t('reports.reconcile.mismatchAmount'),
    expected: t('reports.reconcile.target'),
  },
  journal_balance: {
    title: t('reports.reconcile.journalBalanceTitle'),
    summary: t('reports.reconcile.journalBalanceSummary'),
    actual: t('reports.reconcile.badJournals'),
    expected: t('reports.reconcile.target'),
  },
  sales_journal_revenue: {
    title: t('reports.reconcile.journalRevenueTitle'),
    summary: t('reports.reconcile.journalRevenueSummary'),
    actual: t('reports.reconcile.salesSettlementActual'),
    expected: t('reports.reconcile.journal'),
  },
  sales_journal_cogs: {
    title: t('reports.reconcile.journalCogsTitle'),
    summary: t('reports.reconcile.journalCogsSummary'),
    actual: t('reports.reconcile.salesSettlementActual'),
    expected: t('reports.reconcile.journal'),
  },
}))

function checkTitle(code: string, fallback: string): string {
  return checkCopy.value[code]?.title ?? fallback
}

function checkSummary(code: string, fallback: string): string {
  return checkCopy.value[code]?.summary ?? fallback
}

function checkActualLabel(code: string, fallback: string): string {
  return checkCopy.value[code]?.actual ?? fallback
}

function checkExpectedLabel(code: string, fallback: string): string {
  return checkCopy.value[code]?.expected ?? fallback
}

function toggleCheck(code: string): void {
  expandedCheckCode.value = expandedCheckCode.value === code ? null : code
}

function formatAmount(value: string): string {
  return formatPrice(value)
}

function formatCheckValue(code: string, value: string): string {
  if (code === 'journal_balance') {
    return t('reports.reconcile.pcs', {
      count: Number(value || 0).toLocaleString(intlLocale(locale.value)),
    })
  }
  return formatAmount(value)
}

function highlightValue(item: { key: string; value: string; currency?: string }): string {
  if (item.key === 'journal_entries' || item.key === 'sessions') return item.value
  return formatPrice(item.value, item.currency ?? 'UZS')
}

function statusTitle(status: 'ok' | 'warning' | 'mismatch'): string {
  if (status === 'ok') return t('reports.reconcile.statusOk')
  if (status === 'warning') return t('reports.reconcile.statusWarning')
  return t('reports.reconcile.statusMismatch')
}

function refLabel(rawRef: string): string {
  const [type, id] = rawRef.split(':')
  const labels: Record<string, string> = {
    sale: t('reports.reconcile.refSale'),
    customer: t('reports.reconcile.refCustomer'),
    cash_account: t('reports.reconcile.refCashAccount'),
    session: t('reports.reconcile.refSession'),
    journal: t('reports.reconcile.refJournal'),
  }
  return `${labels[type] ?? type} #${id ?? ''}`.trim()
}

function formatGeneratedAt(value: string): string {
  return new Date(value).toLocaleString(intlLocale(locale.value))
}

function canOpenRef(rawRef: string): boolean {
  return rawRef.startsWith('sale:')
}

function currencyLines(value?: Record<string, string>): Array<{ currency: string; amount: string }> {
  return Object.entries(value ?? {}).map(([currency, amount]) => ({
    currency,
    amount,
  }))
}

function openRef(rawRef: string): void {
  const [type, id] = rawRef.split(':')
  if (type === 'sale' && id) {
    router.push({ name: 'reports-sale-explanation', params: { id } })
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    summary.value = await fetchLatestReconciliation()
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('reports.reconcile.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="reconcile-page">
    <header class="page-header">
      <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="title">{{ t('reports.reconciliation') }}</h1>
      <button class="icon-btn" type="button" :aria-label="t('common.refresh')" @click="load">
        <RefreshCcw :size="18" :stroke-width="2" />
      </button>
    </header>

    <main class="content">
      <section v-if="loading" class="panel">
        <p class="muted">{{ t('reports.reconcile.loading') }}</p>
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
            <p class="hero-kicker">{{ t('reports.reconcile.core') }}</p>
            <p class="hero-title">{{ statusLabel }}</p>
            <p class="muted">
              {{ t('reports.reconcile.updatedAt', { date: formatGeneratedAt(summary.generated_at) }) }}
            </p>
            <p class="muted">{{ statusHint }}</p>
          </div>
        </section>

        <section class="summary-grid">
          <article class="summary-tile">
            <span class="label">{{ t('reports.reconcile.totalChecks') }}</span>
            <strong class="value">{{ summary.totals.total_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">{{ t('reports.reconcile.needsFix') }}</span>
            <strong class="value danger">{{ summary.totals.mismatch_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">{{ t('reports.reconcile.warnings') }}</span>
            <strong class="value warning">{{ summary.totals.warning_checks }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">{{ t('reports.reconcile.affectedRecords') }}</span>
            <strong class="value">{{ summary.totals.affected_records }}</strong>
          </article>
        </section>

        <section v-if="issueChecks.length" class="panel issue-panel">
          <h2 class="section-title">{{ t('reports.reconcile.mismatches') }}</h2>
          <div class="issue-list">
            <article
              v-for="check in issueChecks"
              :key="`issue-${check.code}`"
              class="issue-row"
              :class="`issue-row--${check.status}`"
            >
              <div>
                <strong>{{ checkTitle(check.code, check.title) }}</strong>
                <span>
                  {{ t('reports.reconcile.issueLine', {
                    count: check.mismatch_count,
                    delta: formatCheckValue(check.code, check.delta_amount),
                  }) }}
                </span>
              </div>
              <button type="button" class="issue-action" @click="toggleCheck(check.code)">
                {{ t('reports.reconcile.details') }}
              </button>
            </article>
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">{{ t('reports.reconcile.controlMetrics') }}</h2>
          <div class="rows">
            <div v-for="item in summary.highlights" :key="item.key" class="row">
              <span>{{ item.label }}</span>
              <span class="mono">
                {{ highlightValue(item) }}
              </span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2 class="section-title">{{ t('reports.reconcile.checks') }}</h2>
          <div v-if="orderedChecks.length === 0" class="muted">{{ t('reports.reconcile.noData') }}</div>
          <div v-else class="check-list">
            <article
              v-for="check in orderedChecks"
              :key="check.code"
              class="check-card"
              :class="`check-card--${check.status}`"
            >
              <button
                type="button"
                class="check-head"
                :aria-expanded="expandedCheckCode === check.code"
                @click="toggleCheck(check.code)"
              >
                <div>
                  <h3 class="check-title">{{ checkTitle(check.code, check.title) }}</h3>
                  <p class="check-summary">{{ checkSummary(check.code, check.summary) }}</p>
                </div>
                <span class="check-state">
                  <span class="status-pill" :class="`status-pill--${check.status}`">
                    {{ statusTitle(check.status) }}
                  </span>
                  <ChevronDown class="check-chevron" :size="16" :stroke-width="2" />
                </span>
              </button>

              <div v-if="check.status !== 'ok' || expandedCheckCode === check.code" class="check-metrics">
                <div class="metric-box">
                  <span class="label">{{ checkActualLabel(check.code, check.actual_label) }}</span>
                  <strong v-if="!currencyLines(check.actual_by_currency).length" class="mono">
                    {{ formatCheckValue(check.code, check.actual_amount) }}
                  </strong>
                  <span
                    v-for="line in currencyLines(check.actual_by_currency)"
                    :key="`actual-${check.code}-${line.currency}`"
                    class="currency-line"
                  >
                    {{ formatPrice(line.amount, line.currency) }}
                  </span>
                </div>
                <div class="metric-box">
                  <span class="label">{{ checkExpectedLabel(check.code, check.expected_label) }}</span>
                  <strong v-if="!currencyLines(check.expected_by_currency).length" class="mono">
                    {{ formatCheckValue(check.code, check.expected_amount) }}
                  </strong>
                  <span
                    v-for="line in currencyLines(check.expected_by_currency)"
                    :key="`expected-${check.code}-${line.currency}`"
                    class="currency-line"
                  >
                    {{ formatPrice(line.amount, line.currency) }}
                  </span>
                </div>
                <div class="metric-box">
                  <span class="label">{{ t('reports.reconcile.delta') }}</span>
                  <strong class="mono" :class="{ danger: check.delta_amount !== '0.00' }">
                    {{ formatCheckValue(check.code, check.delta_amount) }}
                  </strong>
                </div>
              </div>

              <div v-if="check.status !== 'ok' || expandedCheckCode === check.code" class="check-foot">
                <span class="check-count">
                  {{ t('reports.reconcile.affectedCount', { count: check.mismatch_count }) }}
                </span>
                <div v-if="check.sample_refs.length" class="sample-list">
                  <button
                    v-for="sample in check.sample_refs"
                    :key="sample"
                    class="sample-chip"
                    type="button"
                    :disabled="!canOpenRef(sample)"
                    @click="openRef(sample)"
                  >
                    {{ refLabel(sample) }}
                  </button>
                </div>
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
  border-radius: var(--radius-lg);
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

.issue-panel {
  border-color: color-mix(in srgb, var(--color-danger-500) 26%, var(--color-border-subtle));
}

.issue-list {
  display: grid;
  gap: var(--space-2);
}

.issue-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
}

.issue-row > div {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.issue-row strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.issue-row span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.issue-row--mismatch {
  border-left: 3px solid var(--color-danger-500);
}

.issue-row--warning {
  border-left: 3px solid var(--color-warning-500);
}

.issue-action {
  min-height: 32px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
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
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  overflow: hidden;
  padding: 0;
  display: grid;
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
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 0;
  background: transparent;
  text-align: left;
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

.check-state {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.check-chevron {
  color: var(--color-text-tertiary);
  transition: transform 160ms ease;
}

.check-head[aria-expanded='true'] .check-chevron {
  transform: rotate(180deg);
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
  padding: 0 var(--space-3) var(--space-3);
}

.metric-box {
  display: grid;
  gap: 6px;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-bg-secondary) 82%, white 18%);
}

.currency-line {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: 1.25;
}

.check-foot {
  display: grid;
  gap: 6px;
  padding: 0 var(--space-3) var(--space-3);
}

.check-count {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
}

.sample-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.sample-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 var(--space-2);
  border: 0;
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.sample-chip:not(:disabled) {
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
}

.sample-chip:disabled {
  cursor: default;
}

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
  .content {
    padding: var(--space-3);
    padding-bottom: calc(var(--bottom-nav-height) + 24px);
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .summary-tile {
    padding: var(--space-3);
  }

  .summary-tile .label {
    font-size: var(--text-xs);
  }

  .check-metrics {
    grid-template-columns: 1fr;
  }

  .check-head {
    align-items: flex-start;
  }

  .mono {
    text-align: left;
  }

  .issue-row {
    align-items: flex-start;
  }
}
</style>
