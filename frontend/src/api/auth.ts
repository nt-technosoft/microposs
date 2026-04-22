/**
 * API client for auth domain.
 * Uses a plain axios instance — not the authenticated client —
 * because these endpoints are called before tokens are available.
 */

import axios from 'axios'

import api from './client'

const BASE_URL = import.meta.env.VITE_API_URL || ''

export interface CurrentUserResponse {
  id: number
  username: string
  role: string | null
  active_tenant_id: number | null
  tenant_name: string
}

export interface TokenPair {
  access: string
  refresh: string
}

export interface RefreshedToken {
  access: string
}

export async function login(username: string, password: string): Promise<TokenPair> {
  const { data } = await axios.post<TokenPair>(`${BASE_URL}/api/v1/auth/token/`, {
    username,
    password,
  })
  return data
}

export async function refreshToken(refresh: string): Promise<RefreshedToken> {
  const { data } = await axios.post<RefreshedToken>(`${BASE_URL}/api/v1/auth/token/refresh/`, {
    refresh,
  })
  return data
}

export async function fetchCurrentUser(): Promise<CurrentUserResponse> {
  const { data } = await api.get<CurrentUserResponse>('/api/v1/auth/me/')
  return data
}
