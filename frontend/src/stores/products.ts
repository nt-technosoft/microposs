/**
 * Product catalog store — categories, paginated products, search, discount reasons.
 * Used by the Sales module for browsing and adding items to the cart.
 */

import { defineStore } from 'pinia'
import type { Product, Category, DiscountReason } from '../types/models'
import {
  fetchProducts as apiFetchProducts,
  fetchCategories as apiFetchCategories,
  fetchDiscountReasons as apiFetchDiscountReasons,
} from '../api/catalog'
import { useSessionStore } from './session'

const PAGE_SIZE = 20

// Timer lives outside store state — no reactivity overhead, no serialization
let _searchTimer: ReturnType<typeof setTimeout> | null = null

interface ProductsState {
  products: Product[]
  categories: Category[]
  selectedCategory: number | null
  searchQuery: string
  isLoading: boolean
  hasMore: boolean
  page: number
  discountReasons: DiscountReason[]
}

export const useProductsStore = defineStore('products', {
  state: (): ProductsState => ({
    products: [],
    categories: [],
    selectedCategory: null,
    searchQuery: '',
    isLoading: false,
    hasMore: false,
    page: 1,
    discountReasons: [],
  }),

  getters: {
    filteredProducts: (state): Product[] => state.products,
  },

  actions: {
    async fetchCategories(): Promise<void> {
      try {
        const result = await apiFetchCategories()
        this.categories = [...result]
      } catch (error: unknown) {
        console.error('Failed to fetch categories:', error)
      }
    },

    async fetchProducts(reset = false): Promise<void> {
      if (reset) {
        this.page = 1
        this.products = []
        this.hasMore = false
      }

      this.isLoading = true

      try {
        const sessionStore = useSessionStore()
        const locationId = sessionStore.currentSession?.location?.id
        const response = await apiFetchProducts({
          category: this.selectedCategory ?? undefined,
          search: this.searchQuery || undefined,
          is_active: true,
          location_id: locationId,
          page: this.page,
          page_size: PAGE_SIZE,
        })

        if (reset || this.page === 1) {
          this.products = [...response.results]
        } else {
          this.products = [...this.products, ...response.results]
        }

        this.hasMore = response.next !== null
      } catch (error: unknown) {
        console.error('Failed to fetch products:', error)
      } finally {
        this.isLoading = false
      }
    },

    async loadMore(): Promise<void> {
      if (!this.hasMore || this.isLoading) return

      this.page = this.page + 1
      await this.fetchProducts(false)
    },

    async setCategory(categoryId: number | null): Promise<void> {
      this.selectedCategory = categoryId
      await this.fetchProducts(true)
    },

    setSearch(query: string): void {
      this.searchQuery = query

      if (_searchTimer !== null) clearTimeout(_searchTimer)
      _searchTimer = setTimeout(() => {
        _searchTimer = null
        this.fetchProducts(true)
      }, 300)
    },

    async fetchDiscountReasons(): Promise<void> {
      try {
        const result = await apiFetchDiscountReasons()
        this.discountReasons = [...result]
      } catch (error: unknown) {
        console.error('Failed to fetch discount reasons:', error)
      }
    },
  },
})
