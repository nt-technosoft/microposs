<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, CheckCircle2 } from 'lucide-vue-next'
import { createConsignmentReturn, fetchProcurement, type ProcurementDetail } from '@/api/partnerships'
import { fetchLocations } from '@/api/inventory'
import { useToast } from '@/composables/useToast'
import BaseSelect from '@/components/base/BaseSelect.vue'
import BaseButton from '@/components/base/BaseButton.vue'

type Disposition = 'RETURN_TO_SUPPLIER' | 'DISPOSE_SUPPLIER_LOSS' | 'DISPOSE_BUSINESS_LOSS' | 'CONVERT_TO_OWN'

interface ReturnLineDraft {
  id: string
  lot_id: number
  name: string
  max_quantity: string
  quantity: string
  disposition: Disposition
  agreed_price_per_unit: string
  notes: string
  selected: boolean
}

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const procurement = ref<ProcurementDetail | null>(null)
const locations = ref<Array<{ value: number; label: string }>>([])
const warehouseId = ref<number | null>(null)
const lines = ref<ReturnLineDraft[]>([])
const notes = ref('')
const isLoading = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')

const selectedLines = computed(() =>
  lines.value.filter((line) => line.selected && Number(line.quantity) > 0),
)

const canSubmit = computed(() => warehouseId.value !== null && selectedLines.value.length > 0 && !isSubmitting.value)

function parseProcurementId(): number {
  const id = Number(route.params.id)
  return Number.isFinite(id) ? id : 0
}

function buildLines(detail: ProcurementDetail): ReturnLineDraft[] {
  return detail.receive_batches.flatMap((batch) =>
    batch.lines.map((line) => ({
      id: crypto.randomUUID(),
      lot_id: line.lot,
      name: line.product_variant_name,
      max_quantity: line.quantity,
      quantity: line.quantity,
      disposition: 'RETURN_TO_SUPPLIER' as Disposition,
      agreed_price_per_unit: line.landed_cost_per_unit_uzs,
      notes: '',
      selected: false,
    })),
  )
}

async function load(): Promise<void> {
  const id = parseProcurementId()
  if (!id) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [detail, locationItems] = await Promise.all([
      fetchProcurement(id),
      fetchLocations(),
    ])
    procurement.value = detail
    lines.value = buildLines(detail)
    locations.value = locationItems
      .filter((location) => location.is_active !== false)
      .map((location) => ({ value: location.id, label: location.name }))
    warehouseId.value = locations.value[0]?.value ?? null
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('procurements.create.consignmentReturnLoadFailed')
  } finally {
    isLoading.value = false
  }
}

async function submit(): Promise<void> {
  const id = parseProcurementId()
  if (!id || !canSubmit.value || warehouseId.value === null) return
  isSubmitting.value = true
  try {
    await createConsignmentReturn(id, {
      warehouse_id: warehouseId.value,
      notes: notes.value.trim(),
      lines: selectedLines.value.map((line) => ({
        lot_id: line.lot_id,
        quantity: line.quantity,
        disposition: line.disposition,
        agreed_price_per_unit: line.agreed_price_per_unit,
        notes: line.notes.trim(),
      })),
    })
    toast.success(t('procurements.create.consignmentReturnCreated'))
    await router.push({ name: 'procurement-detail', params: { id } })
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('procurements.create.consignmentReturnFailed'))
  } finally {
    isSubmitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="header">
      <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1>{{ t('procurements.create.consignmentReturnTitle') }}</h1>
      <span />
    </header>

    <main class="content">
      <p v-if="errorMessage" class="error-row">{{ errorMessage }}</p>
      <p v-else-if="isLoading" class="muted">{{ t('common.loading') }}</p>

      <template v-else>
        <section class="summary">
          <span>{{ procurement ? t('procurements.procurementNumber', { id: procurement.id }) : '' }}</span>
          <strong>{{ selectedLines.length }} / {{ lines.length }}</strong>
        </section>

        <BaseSelect
          v-model="warehouseId"
          :options="locations"
          :title="t('procurements.detail.receiveWarehouseTitle')"
          :placeholder="t('procurements.detail.selectWarehouse')"
        />

        <section class="line-list">
          <article v-for="line in lines" :key="line.id" class="return-row" :class="{ selected: line.selected }">
            <label class="row-check">
              <input v-model="line.selected" type="checkbox" />
              <span>
                <strong>{{ line.name }}</strong>
                <small>{{ t('procurements.create.maxQuantity', { qty: line.max_quantity }) }}</small>
              </span>
            </label>
            <div class="row-grid">
              <input v-model="line.quantity" class="input-field" type="number" min="0" :max="line.max_quantity" step="0.001" />
              <select v-model="line.disposition" class="input-field">
                <option value="RETURN_TO_SUPPLIER">{{ t('procurements.create.dispositionReturn') }}</option>
                <option value="DISPOSE_SUPPLIER_LOSS">{{ t('procurements.create.dispositionSupplierLoss') }}</option>
                <option value="DISPOSE_BUSINESS_LOSS">{{ t('procurements.create.dispositionBusinessLoss') }}</option>
                <option value="CONVERT_TO_OWN">{{ t('procurements.create.dispositionConvert') }}</option>
              </select>
              <input v-model="line.agreed_price_per_unit" class="input-field" type="number" min="0" step="0.000001" />
            </div>
          </article>
        </section>

        <textarea
          v-model="notes"
          class="textarea-field"
          rows="3"
          :placeholder="t('procurements.create.consignmentReturnNotes')"
        />
      </template>
    </main>

    <footer class="footer">
      <BaseButton
        type="button"
        variant="primary"
        size="lg"
        :full-width="true"
        :loading="isSubmitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        <CheckCircle2 :size="18" :stroke-width="2" />
        {{ t('procurements.create.confirmConsignmentReturn') }}
      </BaseButton>
    </footer>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.header {
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

.header h1 {
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 96px);
}

.summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.line-list {
  display: grid;
  gap: var(--space-2);
}

.return-row {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.return-row.selected {
  border-color: var(--color-brand-500);
  background: color-mix(in srgb, var(--color-brand-50) 55%, var(--color-bg-elevated));
}

.row-check {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.row-check span {
  display: grid;
  gap: 4px;
}

.row-check strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.row-check small,
.muted {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.row-grid {
  display: grid;
  grid-template-columns: minmax(72px, 0.5fr) minmax(0, 1.2fr) minmax(80px, 0.7fr);
  gap: var(--space-2);
}

.input-field,
.textarea-field {
  width: 100%;
  min-height: 42px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  padding: 0 var(--space-3);
}

.textarea-field {
  padding-top: var(--space-2);
  resize: vertical;
}

.error-row {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
}

.footer {
  position: sticky;
  bottom: 0;
  padding: var(--space-4);
  background: linear-gradient(to top, var(--color-bg-primary), transparent);
}

@media (max-width: 430px) {
  .row-grid {
    grid-template-columns: 1fr;
  }
}
</style>
