<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft, Plus, Trash2, Check, Search,
  Wallet, Handshake, Users, Truck, Package,
  AlertCircle,
} from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useIdempotency } from '@/composables/useIdempotency'
import { formatPrice } from '@/utils/currency'
import { ReceiptType } from '@/types/enums'
import type { Location, Supplier, ProductVariant } from '@/types/models'
import type { Investor } from '@/api/investors'
import { fetchLocations } from '@/api/inventory'
import { fetchSuppliers } from '@/api/suppliers'
import { fetchInvestors } from '@/api/investors'
import { fetchVariants } from '@/api/catalog'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import api from '@/api/client'

// ── Router & composables ────────────────────────────────────────────────────

const router = useRouter()
const toast = useToast()
const { generateRequestId } = useIdempotency()

// ── Receipt type config ──────────────────────────────────────────────────────

interface TypeCard {
  type: ReceiptType
  label: string
  description: string
  icon: typeof Wallet
}

const TYPE_CARDS: TypeCard[] = [
  {
    type: ReceiptType.BUSINESS_OWNED,
    label: 'Свои деньги',
    description: 'Закуплено из собственных средств бизнеса',
    icon: Wallet,
  },
  {
    type: ReceiptType.MUDARABA,
    label: 'Мудараба',
    description: 'Инвестор вносит капитал, бизнес управляет',
    icon: Handshake,
  },
  {
    type: ReceiptType.MUSHARAKA,
    label: 'Мушарака',
    description: 'Совместное участие в капитале и управлении',
    icon: Users,
  },
  {
    type: ReceiptType.SUPPLIER_PURCHASE,
    label: 'Поставщик',
    description: 'Закупка у поставщика с отсрочкой или сразу',
    icon: Truck,
  },
  {
    type: ReceiptType.CONSIGNMENT,
    label: 'Консигнация',
    description: 'Товар принят на реализацию от поставщика',
    icon: Package,
  },
]

// ── Form state ───────────────────────────────────────────────────────────────

const selectedType = ref<ReceiptType>(ReceiptType.BUSINESS_OWNED)
const selectedLocationId = ref<number | null>(null)
const selectedSupplierId = ref<number | null>(null)
const notes = ref('')

// ── Reference data ───────────────────────────────────────────────────────────

const locations = ref<Location[]>([])
const suppliers = ref<Supplier[]>([])
const investors = ref<Investor[]>([])
const isLoadingRefs = ref(false)

// ── Participants ─────────────────────────────────────────────────────────────

interface ParticipantRow {
  id: string
  entity_id: number | null
  capital_amount: string
  profit_ratio: string
}

const participants = ref<ParticipantRow[]>([])

function addParticipant(): void {
  participants.value = [
    ...participants.value,
    {
      id: crypto.randomUUID(),
      entity_id: null,
      capital_amount: '',
      profit_ratio: '',
    },
  ]
}

function removeParticipant(rowId: string): void {
  participants.value = participants.value.filter((p) => p.id !== rowId)
}

function updateParticipant(rowId: string, field: keyof Omit<ParticipantRow, 'id'>, value: string | number | null): void {
  participants.value = participants.value.map((p) =>
    p.id === rowId ? { ...p, [field]: value } : p,
  )
}

const totalCapital = computed<number>(() => {
  return participants.value.reduce((sum, p) => {
    const amount = parseFloat(p.capital_amount) || 0
    return sum + amount
  }, 0)
})

const profitRatioSum = computed<number>(() => {
  return participants.value.reduce((sum, p) => {
    const ratio = parseFloat(p.profit_ratio) || 0
    return sum + ratio
  }, 0)
})

const profitRatioValid = computed<boolean>(() => {
  if (participants.value.length === 0) return false
  return Math.abs(profitRatioSum.value - 1.0) < 0.001
})

// ── Lines ─────────────────────────────────────────────────────────────────────

interface LineRow {
  id: string
  variant: ProductVariant | null
  quantity: string
  cost_per_unit: string
}

const lines = ref<LineRow[]>([])

function addEmptyLine(): void {
  lines.value = [
    ...lines.value,
    {
      id: crypto.randomUUID(),
      variant: null,
      quantity: '1',
      cost_per_unit: '',
    },
  ]
}

function removeLine(rowId: string): void {
  lines.value = lines.value.filter((l) => l.id !== rowId)
}

function updateLine(rowId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null): void {
  lines.value = lines.value.map((l) =>
    l.id === rowId ? { ...l, [field]: value } : l,
  )
}

function lineTotal(line: LineRow): number {
  const qty = parseFloat(line.quantity) || 0
  const cost = parseFloat(line.cost_per_unit) || 0
  return qty * cost
}

const grandTotal = computed<number>(() => {
  return lines.value.reduce((sum, l) => sum + lineTotal(l), 0)
})

// ── Variant picker bottom sheet ──────────────────────────────────────────────

const variantSheetOpen = ref(false)
const variantSearch = ref('')
const variantSearchResults = ref<ProductVariant[]>([])
const variantSearchLoading = ref(false)
const activeLineId = ref<string | null>(null)

let variantSearchTimeout: ReturnType<typeof setTimeout> | null = null

function openVariantPicker(lineId: string): void {
  activeLineId.value = lineId
  variantSearch.value = ''
  variantSearchResults.value = []
  variantSheetOpen.value = true
}

function closeVariantPicker(): void {
  variantSheetOpen.value = false
  activeLineId.value = null
}

async function searchVariants(query: string): Promise<void> {
  if (variantSearchTimeout) clearTimeout(variantSearchTimeout)

  variantSearchTimeout = setTimeout(async () => {
    if (!query.trim()) {
      variantSearchResults.value = []
      return
    }
    variantSearchLoading.value = true
    try {
      const results = await fetchVariants({ active: true })
      variantSearchResults.value = results.filter((v) => {
        const nameMatch = v.attribute_values.some((a) =>
          a.value.toLowerCase().includes(query.toLowerCase()),
        )
        const skuMatch = v.sku.toLowerCase().includes(query.toLowerCase())
        return nameMatch || skuMatch
      })
    } catch {
      toast.error('Ошибка поиска товаров')
    } finally {
      variantSearchLoading.value = false
    }
  }, 300)
}

function selectVariant(variant: ProductVariant): void {
  if (!activeLineId.value) return
  updateLine(activeLineId.value, 'variant', variant)

  if (!lines.value.find((l) => l.id === activeLineId.value)?.cost_per_unit) {
    if (variant.price) {
      updateLine(activeLineId.value, 'cost_per_unit', variant.price)
    }
  }

  closeVariantPicker()
}

function variantLabel(variant: ProductVariant): string {
  const attrs = variant.attribute_values.map((a) => a.value).join(', ')
  return attrs || `SKU: ${variant.sku}`
}

// ── Computed helpers ─────────────────────────────────────────────────────────

const needsSupplier = computed<boolean>(() =>
  selectedType.value === ReceiptType.SUPPLIER_PURCHASE ||
  selectedType.value === ReceiptType.CONSIGNMENT,
)

const needsParticipants = computed<boolean>(() =>
  selectedType.value === ReceiptType.MUDARABA ||
  selectedType.value === ReceiptType.MUSHARAKA,
)

// ── Validation ───────────────────────────────────────────────────────────────

interface ValidationResult {
  valid: boolean
  message: string
}

function validate(): ValidationResult {
  if (!selectedLocationId.value) {
    return { valid: false, message: 'Выберите склад' }
  }

  if (needsSupplier.value && !selectedSupplierId.value) {
    return { valid: false, message: 'Выберите поставщика' }
  }

  if (needsParticipants.value) {
    if (participants.value.length === 0) {
      return { valid: false, message: 'Добавьте хотя бы одного участника' }
    }
    for (const p of participants.value) {
      if (!p.entity_id) return { valid: false, message: 'Выберите инвестора для каждого участника' }
      if (!p.capital_amount || parseFloat(p.capital_amount) <= 0) {
        return { valid: false, message: 'Укажите сумму капитала для каждого участника' }
      }
      if (!p.profit_ratio || parseFloat(p.profit_ratio) <= 0) {
        return { valid: false, message: 'Укажите долю прибыли для каждого участника' }
      }
    }
    if (!profitRatioValid.value) {
      return { valid: false, message: `Сумма долей прибыли должна быть 1.00 (сейчас: ${profitRatioSum.value.toFixed(2)})` }
    }
  }

  if (lines.value.length === 0) {
    return { valid: false, message: 'Добавьте хотя бы один товар' }
  }

  for (const line of lines.value) {
    if (!line.variant) return { valid: false, message: 'Выберите товар для каждой строки' }
    if (!line.quantity || parseFloat(line.quantity) <= 0) {
      return { valid: false, message: 'Укажите количество для каждого товара' }
    }
    if (!line.cost_per_unit || parseFloat(line.cost_per_unit) <= 0) {
      return { valid: false, message: 'Укажите стоимость для каждого товара' }
    }
  }

  return { valid: true, message: '' }
}

// ── Submit ───────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const isConfirming = ref(false)
const formError = ref<string | null>(null)

function buildPayload() {
  const payload: Record<string, unknown> = {
    receipt_type: selectedType.value,
    location_id: selectedLocationId.value,
    client_request_id: generateRequestId(),
    lines: lines.value.map((l) => ({
      product_variant_id: l.variant!.id,
      quantity: parseFloat(l.quantity),
      cost_per_unit: parseFloat(l.cost_per_unit),
    })),
  }

  if (needsSupplier.value && selectedSupplierId.value) {
    payload.supplier_id = selectedSupplierId.value
  }

  if (needsParticipants.value && participants.value.length > 0) {
    payload.participants = participants.value.map((p) => ({
      entity_type: 'investor',
      entity_id: p.entity_id,
      capital_amount: parseFloat(p.capital_amount),
      profit_ratio: parseFloat(p.profit_ratio),
    }))
  }

  if (notes.value.trim()) {
    payload.notes = notes.value.trim()
  }

  return payload
}

async function saveDraft(): Promise<void> {
  formError.value = null
  const { valid, message } = validate()
  if (!valid) {
    formError.value = message
    return
  }

  isSaving.value = true
  try {
    const { data } = await api.post<{ id: number }>('/api/v1/inventory/receipts/', buildPayload())
    toast.success('Черновик сохранён')
    router.push({ name: 'intake-detail', params: { id: data.id } })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Не удалось сохранить черновик'
    formError.value = msg
    toast.error(msg)
  } finally {
    isSaving.value = false
  }
}

async function confirmReceipt(): Promise<void> {
  formError.value = null
  const { valid, message } = validate()
  if (!valid) {
    formError.value = message
    return
  }

  isConfirming.value = true
  try {
    const { data: receipt } = await api.post<{ id: number }>('/api/v1/inventory/receipts/', buildPayload())
    await api.post(`/api/v1/inventory/receipts/${receipt.id}/confirm/`)
    toast.success('Приход подтверждён!')
    router.push({ name: 'intake-detail', params: { id: receipt.id } })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Не удалось подтвердить приход'
    formError.value = msg
    toast.error(msg)
  } finally {
    isConfirming.value = false
  }
}

// ── Load reference data ───────────────────────────────────────────────────────

onMounted(async () => {
  isLoadingRefs.value = true
  try {
    const [locs, sups, invs] = await Promise.all([
      fetchLocations(),
      fetchSuppliers().then((r) => r.results),
      fetchInvestors().then((r) => r.results),
    ])
    locations.value = locs
    suppliers.value = sups
    investors.value = invs

    if (locs.length === 1) {
      selectedLocationId.value = locs[0].id
    }
  } catch {
    toast.error('Ошибка загрузки справочных данных')
  } finally {
    isLoadingRefs.value = false
  }
})
</script>

<template>
  <div class="create-page">
    <!-- ── Header ──────────────────────────────────────────────── -->
    <header class="page-header">
      <button class="btn-back" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="20" :stroke-width="1.75" />
      </button>
      <h1 class="page-title">Новый приход</h1>
      <div class="header-spacer" />
    </header>

    <div class="form-body">

      <!-- ── Section 1: Тип прихода ────────────────────────────── -->
      <section class="form-section">
        <h2 class="section-title">Тип финансирования</h2>
        <div class="type-grid">
          <button
            v-for="card in TYPE_CARDS"
            :key="card.type"
            class="type-card"
            :class="{ selected: selectedType === card.type }"
            @click="selectedType = card.type"
          >
            <div class="type-card-icon">
              <component :is="card.icon" :size="22" :stroke-width="1.75" />
              <span v-if="selectedType === card.type" class="type-check">
                <Check :size="12" :stroke-width="2.5" />
              </span>
            </div>
            <span class="type-card-label">{{ card.label }}</span>
            <span class="type-card-desc">{{ card.description }}</span>
          </button>
        </div>
      </section>

      <!-- ── Section 2: Склад & поставщик ─────────────────────── -->
      <section class="form-section">
        <h2 class="section-title">Склад назначения</h2>

        <div class="field-group">
          <label class="field-label">Склад <span class="required">*</span></label>
          <select
            v-model="selectedLocationId"
            class="select-field"
            :disabled="isLoadingRefs"
          >
            <option :value="null" disabled>Выберите склад</option>
            <option v-for="loc in locations" :key="loc.id" :value="loc.id">
              {{ loc.name }}
            </option>
          </select>
        </div>

        <div v-if="needsSupplier" class="field-group">
          <label class="field-label">Поставщик <span class="required">*</span></label>
          <select
            v-model="selectedSupplierId"
            class="select-field"
            :disabled="isLoadingRefs"
          >
            <option :value="null" disabled>Выберите поставщика</option>
            <option v-for="sup in suppliers" :key="sup.id" :value="sup.id">
              {{ sup.name }}
            </option>
          </select>
        </div>
      </section>

      <!-- ── Section 3: Участники ──────────────────────────────── -->
      <section v-if="needsParticipants" class="form-section">
        <div class="section-header">
          <h2 class="section-title">Участники</h2>
          <button class="btn-add-small" @click="addParticipant">
            <Plus :size="14" :stroke-width="2.5" />
            Добавить
          </button>
        </div>

        <div v-if="participants.length === 0" class="empty-hint">
          Нажмите «Добавить», чтобы указать инвесторов
        </div>

        <div
          v-for="participant in participants"
          :key="participant.id"
          class="participant-card"
        >
          <div class="participant-header">
            <span class="participant-num">Участник</span>
            <button
              class="btn-delete"
              aria-label="Удалить участника"
              @click="removeParticipant(participant.id)"
            >
              <Trash2 :size="14" :stroke-width="1.75" />
            </button>
          </div>

          <div class="field-group">
            <label class="field-label">Инвестор</label>
            <select
              :value="participant.entity_id"
              class="select-field"
              @change="(e) => updateParticipant(participant.id, 'entity_id', Number((e.target as HTMLSelectElement).value) || null)"
            >
              <option :value="null" disabled>Выберите инвестора</option>
              <option v-for="inv in investors" :key="inv.id" :value="inv.id">
                {{ inv.name }}
              </option>
            </select>
          </div>

          <div class="field-row">
            <div class="field-group flex-1">
              <label class="field-label">Капитал (сум)</label>
              <input
                type="number"
                class="input-field"
                placeholder="0"
                :value="participant.capital_amount"
                min="0"
                @input="(e) => updateParticipant(participant.id, 'capital_amount', (e.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field-group flex-1">
              <label class="field-label">Доля прибыли</label>
              <input
                type="number"
                class="input-field"
                placeholder="0.00–1.00"
                :value="participant.profit_ratio"
                step="0.01"
                min="0"
                max="1"
                @input="(e) => updateParticipant(participant.id, 'profit_ratio', (e.target as HTMLInputElement).value)"
              />
            </div>
          </div>
        </div>

        <!-- Ratio summary -->
        <div v-if="participants.length > 0" class="ratio-summary">
          <span class="ratio-label">Сумма долей прибыли:</span>
          <span
            class="ratio-value"
            :class="profitRatioValid ? 'ratio-ok' : 'ratio-err'"
          >
            {{ profitRatioSum.toFixed(2) }}
            <Check v-if="profitRatioValid" :size="14" :stroke-width="2.5" />
            <AlertCircle v-else :size="14" :stroke-width="1.75" />
          </span>
        </div>

        <div v-if="participants.length > 0 && totalCapital > 0" class="ratio-summary">
          <span class="ratio-label">Итого капитал:</span>
          <span class="ratio-value ratio-ok">{{ formatPrice(totalCapital) }}</span>
        </div>
      </section>

      <!-- ── Section 4: Товары ──────────────────────────────────── -->
      <section class="form-section">
        <div class="section-header">
          <h2 class="section-title">Товары</h2>
          <button class="btn-add-small" @click="addEmptyLine">
            <Plus :size="14" :stroke-width="2.5" />
            Добавить товар
          </button>
        </div>

        <div v-if="lines.length === 0" class="empty-hint">
          Нажмите «Добавить товар», чтобы указать позиции прихода
        </div>

        <div
          v-for="line in lines"
          :key="line.id"
          class="line-card"
        >
          <div class="line-header">
            <button
              class="btn-variant-select"
              @click="openVariantPicker(line.id)"
            >
              <span v-if="line.variant" class="variant-selected-label">
                {{ variantLabel(line.variant) }}
              </span>
              <span v-else class="variant-placeholder">
                <Search :size="14" :stroke-width="1.75" />
                Выбрать товар
              </span>
            </button>
            <button
              class="btn-delete"
              aria-label="Удалить строку"
              @click="removeLine(line.id)"
            >
              <Trash2 :size="14" :stroke-width="1.75" />
            </button>
          </div>

          <div v-if="line.variant" class="line-sku">SKU: {{ line.variant.sku }}</div>

          <div class="field-row">
            <div class="field-group flex-1">
              <label class="field-label">Количество</label>
              <input
                type="number"
                class="input-field"
                placeholder="1"
                :value="line.quantity"
                min="1"
                step="1"
                @input="(e) => updateLine(line.id, 'quantity', (e.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field-group flex-1">
              <label class="field-label">Стоимость за ед.</label>
              <input
                type="number"
                class="input-field"
                placeholder="0"
                :value="line.cost_per_unit"
                min="0"
                @input="(e) => updateLine(line.id, 'cost_per_unit', (e.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div v-if="lineTotal(line) > 0" class="line-total">
            Итого: {{ formatPrice(lineTotal(line)) }}
          </div>
        </div>

        <!-- Grand total -->
        <div v-if="lines.length > 0 && grandTotal > 0" class="grand-total">
          <span class="grand-label">Общая сумма прихода</span>
          <span class="grand-amount tabular-nums">{{ formatPrice(grandTotal) }}</span>
        </div>
      </section>

      <!-- ── Notes ──────────────────────────────────────────────── -->
      <section class="form-section">
        <h2 class="section-title">Заметки</h2>
        <textarea
          v-model="notes"
          class="textarea-field"
          placeholder="Необязательные комментарии к приходу..."
          rows="3"
        />
      </section>

      <!-- ── Form error ─────────────────────────────────────────── -->
      <div v-if="formError" class="form-error" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" />
        <span>{{ formError }}</span>
      </div>

      <!-- ── Action buttons ─────────────────────────────────────── -->
      <div class="actions">
        <button
          class="btn-draft"
          :disabled="isSaving || isConfirming"
          @click="saveDraft"
        >
          <span v-if="isSaving" class="btn-spinner" />
          <span :class="{ invisible: isSaving }">Сохранить черновик</span>
        </button>

        <button
          class="btn-confirm"
          :disabled="isSaving || isConfirming"
          @click="confirmReceipt"
        >
          <span v-if="isConfirming" class="btn-spinner btn-spinner--light" />
          <span :class="{ invisible: isConfirming }">Подтвердить приход →</span>
        </button>
      </div>

    </div>

    <!-- ── Variant picker bottom sheet ──────────────────────────── -->
    <AppBottomSheet
      :open="variantSheetOpen"
      title="Выбор товара"
      @close="closeVariantPicker"
    >
      <div class="variant-search-wrap">
        <div class="variant-search-field">
          <Search :size="16" :stroke-width="1.75" class="search-icon" />
          <input
            v-model="variantSearch"
            type="text"
            class="search-input"
            placeholder="Поиск по названию или SKU…"
            autofocus
            @input="searchVariants(variantSearch)"
          />
        </div>
      </div>

      <div v-if="variantSearchLoading" class="sheet-loading">
        <div class="sheet-spinner" />
        <span>Поиск…</span>
      </div>

      <div v-else-if="variantSearch && variantSearchResults.length === 0" class="sheet-empty">
        Товары не найдены
      </div>

      <div v-else-if="!variantSearch" class="sheet-hint">
        Начните вводить название товара или SKU
      </div>

      <div v-else class="variant-results">
        <button
          v-for="variant in variantSearchResults"
          :key="variant.id"
          class="variant-result-item"
          @click="selectVariant(variant)"
        >
          <div class="variant-result-info">
            <span class="variant-result-name">{{ variantLabel(variant) }}</span>
            <span class="variant-result-sku">SKU: {{ variant.sku }}</span>
          </div>
          <span v-if="variant.price" class="variant-result-price tabular-nums">
            {{ formatPrice(variant.price) }}
          </span>
        </button>
      </div>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────────────── */

.create-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--color-bg-primary);
}

/* ── Header ─────────────────────────────────────────────────────────────── */

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
}

.btn-back {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.btn-back:hover {
  background: var(--color-bg-secondary);
}

.page-title {
  flex: 1;
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.header-spacer {
  width: 36px;
  flex-shrink: 0;
}

/* ── Form body ──────────────────────────────────────────────────────────── */

.form-body {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-bottom: var(--space-8);
}

/* ── Sections ───────────────────────────────────────────────────────────── */

.form-section {
  padding: var(--space-5);
  border-bottom: 1px solid var(--color-border-subtle);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Type cards grid ────────────────────────────────────────────────────── */

.type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
}

.type-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 2px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-out),
              background var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
  min-height: 90px;
}

.type-card:active {
  transform: scale(0.97);
}

.type-card.selected {
  border-color: var(--color-brand-400);
  background: var(--color-brand-50);
}

.type-card-icon {
  position: relative;
  color: var(--color-text-secondary);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out);
}

.type-card.selected .type-card-icon {
  background: var(--color-brand-100);
  color: var(--color-brand-600);
}

.type-check {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-brand-500);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}

.type-card-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.type-card-desc {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  line-height: var(--leading-normal);
}

/* ── Fields ─────────────────────────────────────────────────────────────── */

.field-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.required {
  color: var(--color-error);
}

.select-field {
  height: 48px;
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236B635A' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right var(--space-4) center;
  padding-right: var(--space-10);
  transition: border-color var(--duration-fast) var(--ease-out),
              box-shadow var(--duration-fast) var(--ease-out);
  outline: none;
}

.select-field:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

.select-field:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-field {
  height: 48px;
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  transition: border-color var(--duration-fast) var(--ease-out),
              box-shadow var(--duration-fast) var(--ease-out);
  outline: none;
  width: 100%;
}

.input-field:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

.input-field::placeholder {
  color: var(--color-text-tertiary);
}

.textarea-field {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  font-family: var(--font-primary);
  resize: vertical;
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out),
              box-shadow var(--duration-fast) var(--ease-out);
}

.textarea-field:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

.textarea-field::placeholder {
  color: var(--color-text-tertiary);
}

.field-row {
  display: flex;
  gap: var(--space-3);
}

.flex-1 {
  flex: 1;
  min-width: 0;
}

/* ── Add small button ────────────────────────────────────────────────────── */

.btn-add-small {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  height: 30px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  border: 1px solid var(--color-brand-200);
  transition: background var(--duration-fast) var(--ease-out);
}

.btn-add-small:hover {
  background: var(--color-brand-100);
}

/* ── Participant card ────────────────────────────────────────────────────── */

.participant-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
}

.participant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.participant-num {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

/* ── Ratio summary ──────────────────────────────────────────────────────── */

.ratio-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

.ratio-label {
  color: var(--color-text-secondary);
}

.ratio-value {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-weight: var(--font-semibold);
  font-family: var(--font-mono);
}

.ratio-ok {
  color: var(--color-success);
}

.ratio-err {
  color: var(--color-error);
}

/* ── Line card ──────────────────────────────────────────────────────────── */

.line-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
}

.line-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.btn-variant-select {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  height: 44px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-border-default);
  background: var(--color-bg-elevated);
  text-align: left;
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-out),
              background var(--duration-fast) var(--ease-out);
  overflow: hidden;
}

.btn-variant-select:hover {
  border-color: var(--color-brand-300);
  background: var(--color-brand-50);
}

.variant-selected-label {
  color: var(--color-text-primary);
  font-weight: var(--font-medium);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.variant-placeholder {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.line-sku {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  padding: 0 var(--space-1);
}

.line-total {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-brand-600);
  text-align: right;
  font-family: var(--font-mono);
}

/* ── Delete button ──────────────────────────────────────────────────────── */

.btn-delete {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out);
}

.btn-delete:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* ── Grand total ────────────────────────────────────────────────────────── */

.grand-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-default);
}

.grand-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

.grand-amount {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

/* ── Empty hint ─────────────────────────────────────────────────────────── */

.empty-hint {
  padding: var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-md);
}

/* ── Form error ─────────────────────────────────────────────────────────── */

.form-error {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-5);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  border-top: 1px solid var(--color-border-subtle);
}

/* ── Actions ────────────────────────────────────────────────────────────── */

.actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-5);
}

.btn-draft {
  position: relative;
  width: 100%;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.btn-draft:hover:not(:disabled) {
  background: var(--color-bg-sunken);
}

.btn-draft:active:not(:disabled) {
  transform: scale(0.98);
}

.btn-draft:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-confirm {
  position: relative;
  width: 100%;
  height: 52px;
  border-radius: var(--radius-lg);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.btn-confirm:hover:not(:disabled) {
  background: var(--color-brand-600);
}

.btn-confirm:active:not(:disabled) {
  transform: scale(0.98);
}

.btn-confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Button spinner ─────────────────────────────────────────────────────── */

.btn-spinner {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 20px;
  height: 20px;
  border: 2px solid rgba(0, 0, 0, 0.15);
  border-top-color: var(--color-text-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.btn-spinner--light {
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
}

.invisible {
  visibility: hidden;
}

@keyframes spin {
  to { transform: translate(-50%, -50%) rotate(360deg); }
}

/* ── Variant picker sheet ───────────────────────────────────────────────── */

.variant-search-wrap {
  margin-bottom: var(--space-4);
}

.variant-search-field {
  position: relative;
}

.search-icon {
  position: absolute;
  left: var(--space-4);
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-tertiary);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 48px;
  padding: 0 var(--space-4) 0 calc(var(--space-4) + 24px + var(--space-2));
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.search-input:focus {
  border-color: var(--color-border-focus);
  background: var(--color-bg-elevated);
}

.search-input::placeholder {
  color: var(--color-text-tertiary);
}

.sheet-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.sheet-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border-default);
  border-top-color: var(--color-brand-500);
  border-radius: 50%;
  animation: spin2 0.6s linear infinite;
}

@keyframes spin2 {
  to { transform: rotate(360deg); }
}

.sheet-empty,
.sheet-hint {
  padding: var(--space-8) var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.variant-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.variant-result-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  text-align: left;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
}

.variant-result-item:hover {
  background: var(--color-bg-secondary);
}

.variant-result-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.variant-result-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.variant-result-sku {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.variant-result-price {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

/* ── Reduced motion ─────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .btn-spinner, .sheet-spinner { animation: none; }
  .type-card, .btn-add-small, .btn-draft, .btn-confirm,
  .btn-variant-select, .btn-delete, .variant-result-item { transition: none; }
}
</style>
