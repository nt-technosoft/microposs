<script setup lang="ts">
import { ref, computed } from 'vue'
import { UserPlus, Check } from 'lucide-vue-next'
import { useCustomersStore } from '@/stores/customers'
import { useToast } from '@/composables/useToast'
import type { Customer } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSearch from '@/components/base/BaseSearch.vue'
import BaseButton from '@/components/base/BaseButton.vue'

interface Props {
  open: boolean
  selectedCustomerId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  selectedCustomerId: null,
})

const emit = defineEmits<{
  close: []
  select: [customer: Customer]
}>()

const customersStore = useCustomersStore()
const toast = useToast()

const customerSearch = ref('')
const showNewCustomerForm = ref(false)
const newCustomerName = ref('')
const newCustomerPhone = ref('')
const isCreatingCustomer = ref(false)

const filteredCustomers = computed(() => {
  const q = customerSearch.value.trim().toLowerCase()
  if (!q) return customersStore.customers
  return customersStore.customers.filter(
    (c) =>
      c.name.toLowerCase().includes(q) ||
      c.phone.toLowerCase().includes(q),
  )
})

async function handleSearch(query: string): Promise<void> {
  await customersStore.fetchCustomers({ search: query })
}

function selectCustomer(customer: Customer): void {
  emit('select', { ...customer })
}

function showNewCustomer(): void {
  showNewCustomerForm.value = true
  newCustomerName.value = ''
  newCustomerPhone.value = ''
}

async function createAndSelectCustomer(): Promise<void> {
  const name = newCustomerName.value.trim()
  if (!name) {
    toast.error('Введите имя покупателя')
    return
  }

  isCreatingCustomer.value = true
  try {
    const customer = await customersStore.createCustomer({
      name,
      phone: newCustomerPhone.value.trim() || undefined,
    })
    selectCustomer(customer)
    toast.success(`Покупатель "${customer.name}" создан`)
  } catch {
    toast.error('Не удалось создать покупателя')
  } finally {
    isCreatingCustomer.value = false
  }
}

function handleClose(): void {
  showNewCustomerForm.value = false
  newCustomerName.value = ''
  newCustomerPhone.value = ''
  emit('close')
}
</script>

<template>
  <AppBottomSheet :open="open" title="Выбрать покупателя" @close="handleClose">
    <div class="customer-sheet">
      <!-- Search -->
      <BaseSearch
        v-model="customerSearch"
        placeholder="Поиск по имени или телефону"
        :debounce="300"
        @search="handleSearch"
      />

      <!-- New customer form -->
      <Transition name="slide-down">
        <div v-if="showNewCustomerForm" class="new-customer-form">
          <h4 class="new-customer-form__title">Новый покупатель</h4>
          <div class="field">
            <label class="field__label" for="customer-name">Имя *</label>
            <input
              id="customer-name"
              v-model="newCustomerName"
              class="field__input"
              type="text"
              placeholder="Введите имя"
              autocomplete="off"
            />
          </div>
          <div class="field">
            <label class="field__label" for="customer-phone">Телефон</label>
            <input
              id="customer-phone"
              v-model="newCustomerPhone"
              class="field__input"
              type="tel"
              placeholder="+998 90 000 00 00"
              autocomplete="tel"
            />
          </div>
          <div class="new-customer-form__actions">
            <BaseButton
              variant="ghost"
              size="sm"
              @click="showNewCustomerForm = false"
            >
              Отмена
            </BaseButton>
            <BaseButton
              variant="primary"
              size="sm"
              :loading="isCreatingCustomer"
              @click="createAndSelectCustomer"
            >
              Создать и выбрать
            </BaseButton>
          </div>
        </div>
      </Transition>

      <!-- Add new button -->
      <button
        v-if="!showNewCustomerForm"
        class="new-customer-btn"
        @click="showNewCustomer"
      >
        <UserPlus :size="18" :stroke-width="1.75" />
        <span>Новый покупатель</span>
      </button>

      <!-- Loading -->
      <div v-if="customersStore.isLoading" class="sheet-loading" aria-label="Загрузка">
        <div class="sheet-loading__spinner" />
        <span>Загрузка...</span>
      </div>

      <!-- Customer list -->
      <ul
        v-else-if="filteredCustomers.length > 0"
        class="customer-list"
        aria-label="Список покупателей"
      >
        <li
          v-for="customer in filteredCustomers"
          :key="customer.id"
          class="customer-row"
          :class="{ 'customer-row--selected': selectedCustomerId === customer.id }"
          role="button"
          :aria-selected="selectedCustomerId === customer.id"
          tabindex="0"
          @click="selectCustomer(customer)"
          @keydown.enter="selectCustomer(customer)"
          @keydown.space.prevent="selectCustomer(customer)"
        >
          <div class="customer-row__avatar" aria-hidden="true">
            {{ customer.name.charAt(0).toUpperCase() }}
          </div>
          <div class="customer-row__info">
            <span class="customer-row__name">{{ customer.name }}</span>
            <span v-if="customer.phone" class="customer-row__phone">{{ customer.phone }}</span>
          </div>
          <div class="customer-row__meta">
            <span
              v-if="parseFloat(customer.outstanding_balance) > 0"
              class="customer-row__debt"
            >
              {{ formatPrice(customer.outstanding_balance) }}
            </span>
            <Check
              v-if="selectedCustomerId === customer.id"
              :size="18"
              :stroke-width="2.5"
              class="customer-row__check"
            />
          </div>
        </li>
      </ul>

      <!-- Empty search -->
      <div
        v-else-if="!customersStore.isLoading && customerSearch.trim()"
        class="sheet-empty"
      >
        <p class="sheet-empty__text">Покупатель не найден</p>
        <BaseButton variant="ghost" size="sm" @click="showNewCustomer">
          Создать нового
        </BaseButton>
      </div>

      <!-- No customers -->
      <div v-else-if="!customersStore.isLoading" class="sheet-empty">
        <p class="sheet-empty__text">Нет покупателей</p>
      </div>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.customer-sheet {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* New customer button */
.new-customer-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-accent-50);
  border: 1.5px dashed var(--color-accent-400);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--color-accent-600);
  cursor: pointer;
  text-align: left;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.new-customer-btn:hover {
  background: var(--color-accent-100);
  border-color: var(--color-accent-500);
}

/* New customer form */
.new-customer-form {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  border: 1px solid var(--color-border-default);
}

.new-customer-form__title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field__label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.field__input {
  height: 44px;
  padding: 0 var(--space-4);
  background: var(--color-bg-elevated);
  border: 1.5px solid var(--color-border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  outline: none;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.field__input:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 3px var(--color-brand-100);
}

.field__input::placeholder {
  color: var(--color-text-tertiary);
}

.new-customer-form__actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

/* Customer list */
.customer-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.customer-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  outline: none;
  transition: background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.customer-row:hover,
.customer-row:focus-visible {
  background: var(--color-bg-secondary);
}

.customer-row--selected {
  background: var(--color-brand-50);
}

.customer-row__avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--color-brand-100);
  color: var(--color-brand-600);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  flex-shrink: 0;
}

.customer-row__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.customer-row__name {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.customer-row__phone {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.customer-row__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.customer-row__debt {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-error);
  background: var(--color-error-bg);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-family: var(--font-mono);
}

.customer-row__check {
  color: var(--color-brand-500);
  flex-shrink: 0;
}

/* Loading */
.sheet-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.sheet-loading__spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border-default);
  border-top-color: var(--color-brand-500);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* Empty state */
.sheet-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.sheet-empty__text {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: 0;
}

/* Transitions */
.slide-down-enter-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-spring);
}

.slide-down-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-in),
    transform var(--duration-fast) var(--ease-in);
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .slide-down-enter-active,
  .slide-down-leave-active,
  .sheet-loading__spinner {
    animation: none;
    transition: none;
  }
}
</style>
