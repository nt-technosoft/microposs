import api from './client'

export type AttachmentKind = 'INVOICE' | 'RECEIPT_PHOTO' | 'DOCUMENT' | 'OTHER'
export type AttachableType = 'procurement' | 'procurementreceivebatch'

export interface Attachment {
  id: number
  kind: AttachmentKind
  caption: string
  file: string | null
  uploaded_at: string
  uploaded_by: number | null
  content_type: string
  object_id: number
}

export async function fetchAttachments(
  attachableType: AttachableType,
  attachableId: number,
): Promise<Attachment[]> {
  const { data } = await api.get<Attachment[]>('/api/v1/attachments/', {
    params: { attachable_type: attachableType, attachable_id: attachableId },
  })
  return data
}

export async function uploadAttachment(params: {
  attachableType: AttachableType
  attachableId: number
  file: File
  kind?: AttachmentKind
  caption?: string
}): Promise<Attachment> {
  const form = new FormData()
  form.append('file', params.file)
  form.append('attachable_type', params.attachableType)
  form.append('attachable_id', String(params.attachableId))
  if (params.kind) form.append('kind', params.kind)
  if (params.caption) form.append('caption', params.caption)
  const { data } = await api.post<Attachment>('/api/v1/attachments/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteAttachment(id: number): Promise<void> {
  await api.delete(`/api/v1/attachments/${id}/`)
}
