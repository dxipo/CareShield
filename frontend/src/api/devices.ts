export type DeviceStatus = 'online' | 'offline' | 'unknown'

export interface DeviceChannel {
  number: number | null
  name: string | null
}

export interface DeviceSummary {
  id: string
  provider: 'ezviz'
  device_serial: string
  name: string | null
  model: string | null
  online: boolean | null
  status: DeviceStatus
  device_type: string | null
  camera_count: number | null
  channels: DeviceChannel[]
  updated_at: string | null
}

export interface DeviceDetail extends DeviceSummary {
  local_name: string | null
  firmware_version: string | null
  network_type: string | null
  signal: string | null
}

export interface EzvizIntegrationStatus {
  configured: boolean
  reachable: boolean
  message: string | null
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

export async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string' && payload.detail) {
        detail = payload.detail
      }
    } catch {
      // Keep the safe HTTP-only fallback when the response is not JSON.
    }
    throw new ApiRequestError(detail, response.status)
  }
  return (await response.json()) as T
}

export function fetchEzvizStatus(signal?: AbortSignal): Promise<EzvizIntegrationStatus> {
  return requestJson('/api/integrations/ezviz/status', signal)
}

export function fetchDevices(signal?: AbortSignal): Promise<DeviceSummary[]> {
  return requestJson('/api/devices', signal)
}

export function fetchDeviceDetail(
  deviceSerial: string,
  signal?: AbortSignal,
): Promise<DeviceDetail> {
  return requestJson(`/api/devices/${encodeURIComponent(deviceSerial)}`, signal)
}
