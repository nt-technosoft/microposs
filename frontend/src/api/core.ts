import api from './client'
import { toList, type PaginatedResponse } from './catalog'

export interface Partner {
  id: number
  role: 'INVESTOR' | 'OPERATOR'
  display_name: string
  is_active: boolean
  user: number | null
}

export interface InvestorRelation {
  id: number
  partner: number
  partner_name: string
  partner_user: number | null
  status: 'PENDING' | 'ACTIVE' | 'REVOKED' | 'BLOCKED'
  source: 'MANUAL' | 'INVITE'
  notes: string
  created_at: string
}

export interface InvestorInvite {
  id: number
  token: string
  email: string
  display_name: string
  status: 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED'
  business_name: string
  expires_at: string
  accepted_at: string | null
  accepted_by: number | null
  invite_path: string
  created_at: string
}

export interface InvestorInvitePreview {
  token: string
  email: string
  display_name: string
  status: 'PENDING' | 'ACCEPTED' | 'REVOKED' | 'EXPIRED'
  business_name: string
  expires_at: string
  is_expired: boolean
}

export type BusinessRegistrationRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface BusinessRegistrationRequest {
  id: number
  username: string
  first_name: string
  last_name: string
  full_name: string
  phone: string
  business_name: string
  status: BusinessRegistrationRequestStatus
  rejection_reason: string
  reviewed_by: number | null
  reviewed_at: string | null
  approved_user: number | null
  approved_business: number | null
  approved_business_name: string
  created_at: string
}

export async function fetchPartners(params?: {
  role?: 'INVESTOR' | 'OPERATOR'
  is_active?: boolean
  search?: string
}): Promise<Partner[]> {
  const { data } = await api.get<PaginatedResponse<Partner> | Partner[]>('/api/v1/core/partners/', { params })
  return toList<Partner>(data)
}

export async function fetchInvestorRelations(): Promise<InvestorRelation[]> {
  const { data } = await api.get<PaginatedResponse<InvestorRelation> | InvestorRelation[]>('/api/v1/core/investor-relations/')
  return toList<InvestorRelation>(data)
}

export async function fetchInvestorInvites(): Promise<InvestorInvite[]> {
  const { data } = await api.get<PaginatedResponse<InvestorInvite> | InvestorInvite[]>('/api/v1/core/investor-invites/')
  return toList<InvestorInvite>(data)
}

export async function createInvestorInvite(payload: {
  email?: string
  display_name?: string
  expires_days?: number
}): Promise<InvestorInvite> {
  const { data } = await api.post<InvestorInvite>('/api/v1/core/investor-invites/', payload)
  return data
}

export async function fetchInvestorInvitePreview(token: string): Promise<InvestorInvitePreview> {
  const { data } = await api.get<InvestorInvitePreview>(`/api/v1/core/investor-invites/${token}/preview/`)
  return data
}

export async function acceptInvestorInvite(token: string, displayName = ''): Promise<{
  invite: InvestorInvite
  relation: InvestorRelation
}> {
  const { data } = await api.post(`/api/v1/core/investor-invites/${token}/accept/`, {
    display_name: displayName,
  })
  return data
}

export async function registerInvestorFromInvite(token: string, payload: {
  username: string
  password: string
  display_name?: string
  email?: string
}): Promise<{
  access: string
  refresh: string
  invite: InvestorInvite
  relation: InvestorRelation
}> {
  const { data } = await api.post(`/api/v1/core/investor-invites/${token}/register/`, payload)
  return data
}

export async function createBusinessRegistrationRequest(payload: {
  username: string
  password: string
  first_name: string
  last_name: string
  phone: string
  business_name: string
}): Promise<BusinessRegistrationRequest> {
  const { data } = await api.post<BusinessRegistrationRequest>('/api/v1/core/business-registration-requests/', payload)
  return data
}

export async function fetchBusinessRegistrationRequests(status?: BusinessRegistrationRequestStatus): Promise<BusinessRegistrationRequest[]> {
  const { data } = await api.get<PaginatedResponse<BusinessRegistrationRequest> | BusinessRegistrationRequest[]>(
    '/api/v1/core/business-registration-requests/',
    { params: status ? { status } : undefined },
  )
  return toList<BusinessRegistrationRequest>(data)
}

export async function approveBusinessRegistrationRequest(id: number): Promise<BusinessRegistrationRequest> {
  const { data } = await api.post<BusinessRegistrationRequest>(`/api/v1/core/business-registration-requests/${id}/approve/`)
  return data
}

export async function rejectBusinessRegistrationRequest(id: number, rejectionReason = ''): Promise<BusinessRegistrationRequest> {
  const { data } = await api.post<BusinessRegistrationRequest>(`/api/v1/core/business-registration-requests/${id}/reject/`, {
    rejection_reason: rejectionReason,
  })
  return data
}
