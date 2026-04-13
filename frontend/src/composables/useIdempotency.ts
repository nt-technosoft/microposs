/**
 * Generate unique client_request_id for idempotent POST requests.
 */

export function useIdempotency() {
  function generateRequestId(): string {
    return crypto.randomUUID()
  }

  return { generateRequestId }
}
