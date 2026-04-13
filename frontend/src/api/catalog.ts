/**
 * API client for catalog domain.
 */

import api from './client'
import type { Category, Product, ProductVariant, DiscountReason } from '../types/models'

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface FetchCategoriesParams {
  root_only?: boolean
}

interface FetchProductsParams {
  category?: number
  search?: string
  is_active?: boolean
  page?: number
  page_size?: number
}

interface FetchVariantsParams {
  product?: number
  location?: number
  active?: boolean
}

export async function fetchCategories(params?: FetchCategoriesParams): Promise<Category[]> {
  const { data } = await api.get<Category[]>('/api/v1/catalog/categories/', { params })
  return data
}

export async function fetchProducts(params?: FetchProductsParams): Promise<PaginatedResponse<Product>> {
  const { data } = await api.get<PaginatedResponse<Product>>('/api/v1/catalog/products/', { params })
  return data
}

export async function fetchProduct(id: number): Promise<Product> {
  const { data } = await api.get<Product>(`/api/v1/catalog/products/${id}/`)
  return data
}

export async function fetchProductVariants(productId: number): Promise<ProductVariant[]> {
  const { data } = await api.get<ProductVariant[]>(`/api/v1/catalog/products/${productId}/variants/`)
  return data
}

export async function fetchVariants(params?: FetchVariantsParams): Promise<ProductVariant[]> {
  const { data } = await api.get<ProductVariant[]>('/api/v1/catalog/variants/', { params })
  return data
}

export async function fetchDiscountReasons(): Promise<DiscountReason[]> {
  const { data } = await api.get<DiscountReason[]>('/api/v1/catalog/discount-reasons/')
  return data
}
