/**
 * Sales history store — list, detail, create sale, and process returns.
 */

import { defineStore } from 'pinia'
import { translateNow } from '@/i18n'
import type { Sale } from '../types/models'
import type { SaleCreatePayload, ReturnCreatePayload, SaleReturn } from '../api/sales'
import { useSessionStore } from './session'
import {
  fetchSales as apiFetchSales,
  fetchSale as apiFetchSale,
  createSale as apiCreateSale,
  processReturn as apiProcessReturn,
} from '../api/sales'

interface FetchSalesParams {
  session?: number
  page?: number
}

interface SalesState {
  sales: Sale[]
  currentSale: Sale | null
  isLoading: boolean
  isCreating: boolean
  error: string | null
  hasMore: boolean
  page: number
}

export const useSalesStore = defineStore('sales', {
  state: (): SalesState => ({
    sales: [],
    currentSale: null,
    isLoading: false,
    isCreating: false,
    error: null,
    hasMore: false,
    page: 1,
  }),

  getters: {
    hasSales: (state): boolean => state.sales.length > 0,
  },

  actions: {
    async fetchSales(params?: FetchSalesParams): Promise<void> {
      this.isLoading = true
      this.error = null

      const targetPage = params?.page ?? 1
      const isFirstPage = targetPage === 1

      if (isFirstPage) {
        this.sales = []
        this.page = 1
      }

      try {
        const response = await apiFetchSales({
          session: params?.session,
          page: targetPage,
        })

        if (isFirstPage) {
          this.sales = [...response.results]
        } else {
          this.sales = [...this.sales, ...response.results]
        }

        this.hasMore = response.next !== null
        this.page = targetPage
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('sales.loadingError')
      } finally {
        this.isLoading = false
      }
    },

    async fetchSale(id: number): Promise<void> {
      this.isLoading = true
      this.error = null

      try {
        const sale = await apiFetchSale(id)
        this.currentSale = { ...sale }
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('sales.saleDetailsFailed')
        throw error
      } finally {
        this.isLoading = false
      }
    },

    async createSale(payload: SaleCreatePayload): Promise<Sale> {
      this.isCreating = true
      this.error = null

      try {
        const sessionStore = useSessionStore()
        const sale = await apiCreateSale(payload)
        this.currentSale = { ...sale }
        this.sales = [{ ...sale }, ...this.sales]

        if (sessionStore.isOpen) {
          const activeLocationId = typeof sessionStore.currentSession?.location === 'object'
            ? sessionStore.currentSession.location?.id
            : undefined
          await sessionStore.loadCurrentSession(activeLocationId)
        }

        return sale
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('sales.createSaleFailed')
        throw error
      } finally {
        this.isCreating = false
      }
    },

    async processReturn(saleId: number, returnData: ReturnCreatePayload): Promise<SaleReturn> {
      this.isLoading = true
      this.error = null

      try {
        const result = await apiProcessReturn(saleId, returnData)
        await this.fetchSale(saleId)
        if (this.currentSale) {
          this.sales = this.sales.map((sale) => (
            sale.id === saleId ? { ...sale, ...this.currentSale } : sale
          ))
        }
        return result
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : translateNow('sales.returnFailed')
        throw error
      } finally {
        this.isLoading = false
      }
    },

    clearCurrentSale(): void {
      this.currentSale = null
      this.error = null
    },
  },
})
