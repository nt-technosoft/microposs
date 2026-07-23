import api from './client'

export interface IntegrationCredential {
  id: string
  vendor: string
  prefix: string
  status: 'active' | 'revoked' | 'expired'
  scopes: string[]
  created_at: string
  last_used_at: string | null
}

export interface CreateCredentialResponse {
  id: string
  prefix: string
  full_key: string
  created_at: string
}

export async function fetchCredentials(signal?: AbortSignal): Promise<IntegrationCredential[]> {
  const res = await api.get<IntegrationCredential[]>('/api/v1/integrations/credentials', { signal })
  return res.data
}

export async function createCredential(vendor: string): Promise<CreateCredentialResponse> {
  const res = await api.post<CreateCredentialResponse>('/api/v1/integrations/credentials', { vendor })
  return res.data
}

export async function revokeCredential(id: string): Promise<void> {
  await api.post(`/api/v1/integrations/credentials/${id}/revoke`)
}
