interface ErrorPayload {
  detail?: string | string[]
  [key: string]: unknown
}

interface AxiosLikeError {
  response?: {
    data?: ErrorPayload | string
  }
  message?: string
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosLikeError
  const payload = axiosError?.response?.data

  if (typeof payload === 'string' && payload.trim()) {
    return payload
  }

  if (payload && typeof payload === 'object') {
    const detail = payload.detail
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0] === 'string') {
      return detail[0]
    }
  }

  if (axiosError?.message) {
    return axiosError.message
  }

  return fallback
}
