/**
 * Customers store — list, debt summary, create customer, record payments.
 */

import { defineStore } from 'pinia'
import { translateNow } from '@/i18n'
import type { Customer } from '../types/models'
import type {
  DebtSummaryItem,
  CustomerCreatePayload,
  CustomerPaymentPayload,
  CustomerPayment,
} from '../api/customers'
import {
  fetchCustomers as apiFetchCustomers,
  fetchDebtSummary as apiFetchDebtSummary,
  createCustomer as apiCreateCustomer,
  recordPayment as apiRecordPayment,
} from '../api/customers'

interface FetchCustomersParams {
  search?: string
  has_debt?: boolean
}

interface CustomersState {
  customers: Customer[]
  debtSummary: DebtSummaryItem[]
  isLoading: boolean
  searchQuery: string
  error: string | null
}

export const useCustomersStore = defineStore('customers', {
  state: (): CustomersState => ({
    customers: [],
    debtSummary: [],
    isLoading: false,
    searchQuery: '',
    error: null,
  }),

  getters: {
    customersWithDebt: (state): Customer[] =>
      state.customers.filter((c) => parseFloat(c.outstanding_balance) > 0),

    totalOutstandingDebt: (state): string =>
      state.debtSummary
        .reduce((sum, item) => sum + parseFloat(item.outstanding_balance), 0)
        .toFixed(2),
  },

  actions: {
    async fetchCustomers(params?: FetchCustomersParams): Promise<void> {
      this.isLoading = true
      this.error = null

      if (params?.search !== undefined) {
        this.searchQuery = params.search
      }

      try {
        const response = await apiFetchCustomers({
          search: params?.search || undefined,
          has_debt: params?.has_debt,
        })
        this.customers = [...response.results]
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('customers.loadFailed')
      } finally {
        this.isLoading = false
      }
    },

    async fetchDebtSummary(): Promise<void> {
      this.isLoading = true
      this.error = null

      try {
        const result = await apiFetchDebtSummary()
        this.debtSummary = [...result]
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('customers.debtSummaryFailed')
      } finally {
        this.isLoading = false
      }
    },

    async createCustomer(data: CustomerCreatePayload): Promise<Customer> {
      this.isLoading = true
      this.error = null

      try {
        const customer = await apiCreateCustomer(data)
        this.customers = [{ ...customer }, ...this.customers]
        return customer
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('customers.createFailed')
        throw error
      } finally {
        this.isLoading = false
      }
    },

    async recordPayment(customerId: number, data: CustomerPaymentPayload): Promise<CustomerPayment> {
      this.isLoading = true
      this.error = null

      try {
        const payment = await apiRecordPayment(customerId, data)

        // Update outstanding_balance for the customer in local state (immutable update)
        this.customers = this.customers.map((c) =>
          c.id === customerId
            ? {
                ...c,
                outstanding_balance: (
                  parseFloat(c.outstanding_balance) - parseFloat(payment.amount)
                ).toFixed(2),
              }
            : c,
        )

        // Sync debt summary entry if present
        this.debtSummary = this.debtSummary.map((item) =>
          item.id === customerId
            ? {
                ...item,
                outstanding_balance: (
                  parseFloat(item.outstanding_balance) - parseFloat(payment.amount)
                ).toFixed(2),
              }
            : item,
        )

        return payment
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('customers.paymentFailed')
        throw error
      } finally {
        this.isLoading = false
      }
    },
  },
})
