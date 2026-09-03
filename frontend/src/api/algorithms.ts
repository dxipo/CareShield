import { requestJson } from './devices'
import type { AlgorithmCapabilities, AlgorithmResult, WorkerStatus } from '../realtime/types'

export interface AlgorithmsStatus {
  redis_reachable: boolean
  workers: WorkerStatus[]
  capabilities: AlgorithmCapabilities
  latest_pipeline_test: AlgorithmResult | null
  latest_fall_detection: AlgorithmResult | null
  latest_fraud_detection: AlgorithmResult | null
}

export interface SystemStatus {
  backend: 'online'
  redis: 'healthy' | 'unavailable'
  ai_worker: 'online' | 'offline'
}

export function fetchAlgorithmsStatus(signal?: AbortSignal): Promise<AlgorithmsStatus> {
  return requestJson('/api/algorithms', signal)
}

export function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return requestJson('/api/system/status', signal)
}

export function fetchFallDetectionHistory(
  limit = 20,
  signal?: AbortSignal,
): Promise<AlgorithmResult[]> {
  return requestJson(`/api/fall-detection/history?limit=${limit}`, signal)
}

export function fetchFraudDetectionHistory(
  limit = 20,
  signal?: AbortSignal,
): Promise<AlgorithmResult[]> {
  return requestJson(`/api/fraud-detection/history?limit=${limit}`, signal)
}

export function acknowledgeFallAlert(signal?: AbortSignal): Promise<{
  alert_active: boolean
  alert_acknowledged: boolean
}> {
  return requestJson('/api/fall-detection/alert/acknowledge', signal, {
    method: 'POST',
  })
}

export function acknowledgeFraudAlert(signal?: AbortSignal): Promise<{
  alert_active: boolean
  alert_acknowledged: boolean
}> {
  return requestJson('/api/fraud-detection/alert/acknowledge', signal, {
    method: 'POST',
  })
}
