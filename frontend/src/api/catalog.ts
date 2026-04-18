/**
 * API client for catalog domain.
 */

import api from './client'
import type {
  Category,
  CategoryAttributeTemplate,
  CategoryCharacteristicTemplate,
  DiscountReason,
  Product,
  ProductVariant,
} from '../types/models'
import type { PricingMode } from '../types/enums'

export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

interface PaginatedLike<T> {
  count?: unknown
  next?: unknown
  previous?: unknown
  results?: unknown
}

export function toList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[]
  }
  if (
    payload
    && typeof payload === 'object'
    && Array.isArray((payload as PaginatedLike<T>).results)
  ) {
    return (payload as { results: T[] }).results
  }
  return []
}

export function toPaginated<T>(payload: unknown): PaginatedResponse<T> {
  if (
    payload
    && typeof payload === 'object'
    && Array.isArray((payload as PaginatedLike<T>).results)
  ) {
    const paginated = payload as PaginatedLike<T>
    const countValue = typeof paginated.count === 'number'
      ? paginated.count
      : Number(toList<T>(payload).length)
    return {
      count: Number.isFinite(countValue) ? countValue : 0,
      next: typeof paginated.next === 'string' ? paginated.next : null,
      previous: typeof paginated.previous === 'string' ? paginated.previous : null,
      results: toList<T>(payload),
    }
  }
  const results = toList<T>(payload)
  return {
    count: results.length,
    next: null,
    previous: null,
    results,
  }
}

interface FetchCategoriesParams {
  root_only?: boolean
}

interface FetchProductsParams {
  category?: number
  search?: string
  is_active?: boolean
  location?: number
  location_id?: number
  page?: number
  page_size?: number
}

interface FetchVariantsParams {
  product?: number
  location?: number
  location_id?: number
  active?: boolean
  search?: string
  category?: number
  page?: number
  page_size?: number
}

export interface CategoryUpsertPayload {
  name: string
  parent?: number | null
  default_pricing_mode: PricingMode
  sort_order?: number
}

export interface CategoryApplySettingsPayload {
  apply_to_existing: boolean
  apply_pricing_mode?: boolean
  apply_characteristics?: boolean
}

export interface CategoryAttributeTemplatePayload {
  attribute: number
  is_variant_generating: boolean
}

export interface CategoryCharacteristicTemplatePayload {
  name: string
  default_value: string
  sort_order: number
}

export interface ProductVariantPayload {
  attribute_value_ids?: number[]
  sku?: string
  price?: string | null
}

export interface ProductCharacteristicPayload {
  name: string
  value: string
}

export interface ProductCreatePayload {
  name: string
  category_id?: number | null
  base_price?: string | null
  pricing_mode?: PricingMode
  description?: string
  variants?: ProductVariantPayload[]
  characteristics?: ProductCharacteristicPayload[]
}

export interface ProductUpdatePayload {
  name?: string
  category?: number | null
  description?: string
  base_price?: string | null
  pricing_mode?: PricingMode
  is_active?: boolean
}

export async function fetchCategories(params?: FetchCategoriesParams): Promise<Category[]> {
  const { data } = await api.get<PaginatedResponse<Category> | Category[]>('/api/v1/catalog/categories/', { params })
  return toList<Category>(data)
}

export async function fetchCategory(id: number): Promise<Category> {
  const { data } = await api.get<Category>(`/api/v1/catalog/categories/${id}/`)
  return data
}

export async function createCategory(payload: CategoryUpsertPayload): Promise<Category> {
  const { data } = await api.post<Category>('/api/v1/catalog/categories/', payload)
  return data
}

export async function updateCategory(id: number, payload: Partial<CategoryUpsertPayload>): Promise<Category> {
  const { data } = await api.patch<Category>(`/api/v1/catalog/categories/${id}/`, payload)
  return data
}

export async function applyCategorySettings(
  id: number,
  payload: CategoryApplySettingsPayload,
): Promise<{ updated_count: number }> {
  const { data } = await api.post<{ updated_count: number }>(
    `/api/v1/catalog/categories/${id}/apply-settings/`,
    payload,
  )
  return data
}

export async function fetchCategoryAttributes(id: number): Promise<CategoryAttributeTemplate[]> {
  const { data } = await api.get<CategoryAttributeTemplate[]>(
    `/api/v1/catalog/categories/${id}/attributes/`,
  )
  return toList<CategoryAttributeTemplate>(data)
}

export async function replaceCategoryAttributes(
  id: number,
  payload: CategoryAttributeTemplatePayload[],
): Promise<CategoryAttributeTemplate[]> {
  const { data } = await api.put<CategoryAttributeTemplate[]>(
    `/api/v1/catalog/categories/${id}/attributes/`,
    payload,
  )
  return toList<CategoryAttributeTemplate>(data)
}

export async function fetchCategoryCharacteristics(id: number): Promise<CategoryCharacteristicTemplate[]> {
  const { data } = await api.get<CategoryCharacteristicTemplate[]>(
    `/api/v1/catalog/categories/${id}/characteristics/`,
  )
  return toList<CategoryCharacteristicTemplate>(data)
}

export async function replaceCategoryCharacteristics(
  id: number,
  payload: CategoryCharacteristicTemplatePayload[],
): Promise<CategoryCharacteristicTemplate[]> {
  const { data } = await api.put<CategoryCharacteristicTemplate[]>(
    `/api/v1/catalog/categories/${id}/characteristics/`,
    payload,
  )
  return toList<CategoryCharacteristicTemplate>(data)
}

export async function fetchProducts(params?: FetchProductsParams): Promise<PaginatedResponse<Product>> {
  const { data } = await api.get<PaginatedResponse<Product> | Product[]>('/api/v1/catalog/products/', { params })
  return toPaginated<Product>(data)
}

export async function fetchProduct(id: number): Promise<Product> {
  const { data } = await api.get<Product>(`/api/v1/catalog/products/${id}/`)
  return data
}

export async function fetchProductVariants(
  productId: number,
  params?: { location_id?: number; location?: number },
): Promise<ProductVariant[]> {
  const { data } = await api.get<PaginatedResponse<ProductVariant> | ProductVariant[]>(
    `/api/v1/catalog/products/${productId}/variants/`,
    { params },
  )
  return toList<ProductVariant>(data)
}

export async function createProduct(payload: ProductCreatePayload): Promise<Product> {
  const { data } = await api.post<Product>('/api/v1/catalog/products/', payload)
  return data
}

export async function updateProduct(id: number, payload: ProductUpdatePayload): Promise<Product> {
  const { data } = await api.patch<Product>(`/api/v1/catalog/products/${id}/`, payload)
  return data
}

export async function uploadProductPhoto(id: number, file: File): Promise<{ photo_url: string | null }> {
  const form = new FormData()
  form.append('photo', file)
  const { data } = await api.post<{ photo_url: string | null }>(
    `/api/v1/catalog/products/${id}/photo/`,
    form,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  )
  return data
}

export async function deleteProductPhoto(id: number): Promise<{ photo_url: string | null }> {
  const { data } = await api.delete<{ photo_url: string | null }>(
    `/api/v1/catalog/products/${id}/photo/`,
  )
  return data
}

export async function fetchVariants(params?: FetchVariantsParams): Promise<ProductVariant[]> {
  const { data } = await api.get<PaginatedResponse<ProductVariant> | ProductVariant[]>(
    '/api/v1/catalog/variants/',
    { params },
  )
  return toList<ProductVariant>(data)
}

export async function fetchVariantsPaginated(
  params?: FetchVariantsParams,
): Promise<PaginatedResponse<ProductVariant>> {
  const { data } = await api.get<PaginatedResponse<ProductVariant> | ProductVariant[]>(
    '/api/v1/catalog/variants/',
    { params },
  )
  return toPaginated<ProductVariant>(data)
}

export async function fetchDiscountReasons(): Promise<DiscountReason[]> {
  const { data } = await api.get<PaginatedResponse<DiscountReason> | DiscountReason[]>(
    '/api/v1/catalog/discount-reasons/',
  )
  return toList<DiscountReason>(data)
}
