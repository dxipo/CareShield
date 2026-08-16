export interface HealthResponse {
  status: 'ok'
  service: 'backend'
}

export async function fetchBackendHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', { signal })

  if (!response.ok) {
    throw new Error(`Backend health request failed with HTTP ${response.status}`)
  }

  return (await response.json()) as HealthResponse
}
